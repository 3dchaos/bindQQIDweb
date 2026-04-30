import sys
import json
import asyncio
import websockets
import re
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import dataset
import datetime

# ----------------- 数据读写核心逻辑 (私聊绑定用) -----------------
def read_file_data(filepath):
    zones, records = [], []
    if not filepath or not os.path.exists(filepath):
        return zones, records
    try:
        with open(filepath, 'r', encoding='gbk', errors='replace') as f:
            lines = f.readlines()
            if not lines: return zones, records

            first_line = lines[0].strip()
            if first_line.startswith(';区列表:'):
                z_str = first_line.replace(';区列表:', '')
                if z_str: zones = z_str.split('|')

            for line in lines[1:]:
                line = line.strip()
                if line and not line.startswith(';'): 
                    records.append(line)
    except Exception as e:
        print(f"读取文件错误: {e}")
    return zones, records

def write_file_data(filepath, zones, records):
    if not filepath: return False
    try:
        with open(filepath, 'w', encoding='gbk', errors='replace') as f:
            f.write(f";区列表:{'|'.join(zones)}\n")
            for r in records: f.write(f"{r}\n")
        return True
    except Exception as e:
        return False

# ----------------- Bot 核心逻辑 -----------------
class BotWorker:
    def __init__(self, ws_url, max_binds, log_func, get_filepath_func):
        self.ws_url = ws_url
        self.max_binds = max_binds
        self.log_func = log_func
        self.get_filepath = get_filepath_func
        
        # 界面控制开关
        self.enable_group_manage = False
        self.enable_checkin = False
        self.enable_patrol = False  # 新增：巡逻自动踢黑开关
        
        self.running = False
        self.loop = None
        self.db = None
        
        # 数据表
        self.table_group = None
        self.table_blacklist = None
        self.table_bot_admin = None
        
        self.pending_requests = {}
        self.request_id_counter = 0

    async def call_api(self, websocket, action, params):
        self.request_id_counter += 1
        echo_id = str(self.request_id_counter)
        future = self.loop.create_future()
        self.pending_requests[echo_id] = future
        
        payload = {"action": action, "params": params, "echo": echo_id}
        await websocket.send(json.dumps(payload))
        
        try:
            result = await asyncio.wait_for(future, timeout=3.0)
            if result.get("status") == "failed":
                return None
            return result.get("data")
        except asyncio.TimeoutError:
            self.pending_requests.pop(echo_id, None)
            return None

    async def send_private_msg(self, websocket, user_id, text):
        await websocket.send(json.dumps({"action": "send_private_msg", "params": {"user_id": user_id, "message": text}}))

    async def send_group_msg(self, websocket, group_id, text):
        await websocket.send(json.dumps({"action": "send_group_msg", "params": {"group_id": group_id, "message": text}}))

    # --- 处理私聊消息 ---
    async def handle_private_message(self, websocket, data):
        sender = data.get("sender", {})
        qq_num = sender.get("user_id")
        nickname = sender.get("nickname", "未知昵称")
        msg_text = data.get("raw_message", "").strip()

        filepath = self.get_filepath()
        zones, records = read_file_data(filepath)

        if msg_text == "开区列表":
            counts = {z: 0 for z in zones}
            for r in records:
                try:
                    acc_zone = r.split('|')[0]
                    zone = acc_zone.split(':')[1]
                    if zone in counts: counts[zone] += 1
                except: pass
            reply = "【目前开区列表及注册人数】\n" + ("\n".join([f"- {z} : {counts[z]}人" for z in zones]) if zones else "暂无开区")
            await self.send_private_msg(websocket, qq_num, reply.strip())
            return

        if msg_text == "查下名下账号":
            found = []
            for r in records:
                try:
                    parts = r.split('|')
                    if len(parts) >= 2 and parts[1] == str(qq_num):
                        acc, zone = parts[0].split(':')
                        found.append(f"账号：{acc} ({zone})")
                except: pass
            reply = "【名下已绑定账号】\n" + ("\n".join(found) if found else "未查询到记录")
            await self.send_private_msg(websocket, qq_num, reply)
            return

        match = re.match(r"^绑定(.+?)[，,]\s*账号[：:](.+)$", msg_text)
        if match:
            zone_name, account = match.group(1).strip(), match.group(2).strip()
            if zone_name not in zones:
                await self.send_private_msg(websocket, qq_num, f"错误：【{zone_name}】不存在")
                return

            my_binds = 0
            account_registered = False
            for r in records:
                try:
                    p = r.split('|')
                    if p[0] == f"{account}:{zone_name}": account_registered = True
                    if p[1] == str(qq_num): my_binds += 1
                except: continue

            if account_registered:
                await self.send_private_msg(websocket, qq_num, f"失败：账号【{account}】已在【{zone_name}】注册")
                return
            if my_binds >= self.max_binds:
                await self.send_private_msg(websocket, qq_num, f"失败：注册已达上限({self.max_binds}次)")
                return

            new_record = f"{account}:{zone_name}|{qq_num}|{nickname}"
            records.append(new_record)
            if write_file_data(filepath, zones, records):
                await self.send_private_msg(websocket, qq_num, f"成功绑定！\n账号：{account}\n区服：{zone_name}\nQQ：{qq_num}")
                self.log_func(f"✅ 私聊绑定成功: {new_record}")
            else:
                await self.send_private_msg(websocket, qq_num, "❌ 绑定失败：系统无法写入记录，请联系管理员。")
                self.log_func(f"❌ 私聊绑定失败: {new_record}")
            return

    # --- 处理群成员加入事件 (自动踢黑逻辑) ---
    async def handle_group_increase(self, websocket, data):
        if not self.enable_patrol: return
        
        group_id = data.get("group_id")
        user_id = str(data.get("user_id"))
        self_id = data.get("self_id")

        if str(user_id) == str(self_id):
            return  # 机器人自己进群，直接忽略

        # 读取该群的黑名单，比对是否有符合
        if self.table_blacklist.find_one(group_id=group_id, user_id=user_id):
            self.log_func(f"🚨 巡逻触发: 发现黑名单成员 {user_id} 加入群 {group_id}，正在拦截...")
            
            # 判断机器人是否为管理员
            is_bot_admin = False
            bot_admin_record = self.table_bot_admin.find_one(group_id=group_id)
            if bot_admin_record is not None:
                is_bot_admin = bot_admin_record['is_admin']
            else:
                bot_info = await self.call_api(websocket, "get_group_member_info", {"group_id": group_id, "user_id": self_id, "no_cache": True})
                if bot_info:
                    bot_role = bot_info.get("role", "member")
                    is_bot_admin = bot_role in ["owner", "admin"]
                    self.table_bot_admin.upsert(dict(group_id=group_id, is_admin=is_bot_admin), ["group_id"])

            if is_bot_admin:
                # 调用踢人 API
                await self.call_api(websocket, "set_group_kick", {"group_id": group_id, "user_id": int(user_id), "reject_add_request": False})
                # 发送通知消息
                await self.send_group_msg(websocket, group_id, f"{user_id}为本群黑名单，已将他踢出群。")
                self.log_func(f"✅ 巡逻踢黑成功: 已自动清退成员 {user_id}")
            else:
                self.log_func(f"❌ 巡逻踢黑失败: 机器人在群 {group_id} 没有管理员权限。")

    # --- 处理群聊消息 (指令识别与双向权限控制) ---
    async def handle_group_message(self, websocket, data):
        if not self.enable_group_manage: return

        group_id = data.get("group_id")
        sender = data.get("sender", {})
        user_id = sender.get("user_id")
        nickname = sender.get("nickname", "未知昵称")
        role = sender.get("role", "member")
        raw_msg = data.get("raw_message", "").strip()
        self_id = data.get("self_id")

        clean_msg = re.sub(rf"\[CQ:at,qq={self_id}(,name=[^\]]+)?\]\s*", "", raw_msg).strip()

        cmd_type = ""
        target_qq = ""

        # 多重别名正则匹配 (\s* 表示兼容有无空格)
        add_match = re.match(r"^/(?:加入黑名单QQ|加黑)\s*(\d+)$", clean_msg)
        del_match = re.match(r"^/(?:删除黑名单QQ|删黑)\s*(\d+)$", clean_msg)
        list_match = re.match(r"^/(?:黑名单QQ|黑名单|黑)$", clean_msg)

        if add_match:
            cmd_type = "add_black"
            target_qq = add_match.group(1)
        elif del_match:
            cmd_type = "del_black"
            target_qq = del_match.group(1)
        elif list_match:
            cmd_type = "list_black"
        elif "/功能" in clean_msg:
            cmd_type = "menu"
        elif clean_msg == "/签到":
            cmd_type = "checkin"
        elif clean_msg == "/积分":
            cmd_type = "points"

        if not cmd_type:
            return

        # 1. 验证【机器人本身】是否为管理员
        is_bot_admin = False
        bot_admin_record = self.table_bot_admin.find_one(group_id=group_id)
        
        if bot_admin_record is not None:
            is_bot_admin = bot_admin_record['is_admin']
        else:
            bot_info = await self.call_api(websocket, "get_group_member_info", {"group_id": group_id, "user_id": self_id, "no_cache": True})
            if bot_info:
                bot_role = bot_info.get("role", "member")
                is_bot_admin = bot_role in ["owner", "admin"]
                self.table_bot_admin.upsert(dict(group_id=group_id, is_admin=is_bot_admin), ["group_id"])
            
        if not is_bot_admin:
            await self.send_group_msg(websocket, group_id, "⚠️ 抱歉，本机器人必须拥有【群主/管理员】权限，才能在此群开启功能哦~")
            return

        # 2. 验证【发送消息的人】是否为管理员（专属黑名单拦截）
        is_sender_admin = role in ["owner", "admin"]
        if cmd_type in ["add_black", "del_black", "list_black"]:
            if not is_sender_admin:
                self.log_func(f"🚫 拦截: 成员 {user_id} 并非管理，无权操作黑名单。")
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 权限不足！操作黑名单功能需要您是本群的群主或管理员！")
                return

        # ================ 路由处理 ================
        if cmd_type == "menu":
            reply = (
                "1，/签到(获得1积分)\n"
                "2，/黑名单QQ(查看黑名单列表)\n"
                "3，/加入黑名单QQ XXXX\n"
                "4，/删除黑名单QQ XXXX\n"
                "5，/积分(查看成员积分)"
            )
            await self.send_group_msg(websocket, group_id, reply)
            return

        if cmd_type == "checkin":
            if not self.enable_checkin: return
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            record = self.table_group.find_one(group_id=group_id, user_id=user_id)
            if not record:
                self.table_group.insert(dict(group_id=group_id, user_nickname=nickname, user_id=user_id, points=1, last_checkin_date=today))
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 签到成功，积分+1")
            else:
                if record['last_checkin_date'] == today:
                    await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 签到失败，今天已经签到过了~")
                else:
                    self.table_group.update(dict(id=record['id'], points=record['points'] + 1, last_checkin_date=today, user_nickname=nickname), ['id'])
                    await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 签到成功，积分+1")
            return

        if cmd_type == "points":
            if not self.enable_checkin: return
            record = self.table_group.find_one(group_id=group_id, user_id=user_id)
            if not record:
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 没有你的记录")
            else:
                pts = record['points']
                last_time = record['last_checkin_date']
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 你拥有积分是:{pts}，签到时间为：{last_time}")
            return

        if cmd_type == "list_black":
            bl_records = list(self.table_blacklist.find(group_id=group_id))
            if not bl_records:
                await self.send_group_msg(websocket, group_id, "当前群的黑名单为空。")
            else:
                bl_qqs = [str(x['user_id']) for x in bl_records]
                await self.send_group_msg(websocket, group_id, f"当前群黑名单包含QQ: {', '.join(bl_qqs)}")
            return

        if cmd_type == "add_black" and target_qq:
            if not self.table_blacklist.find_one(group_id=group_id, user_id=target_qq):
                self.table_blacklist.insert(dict(group_id=group_id, user_id=target_qq))
                await self.send_group_msg(websocket, group_id, f"已将QQ {target_qq} 成功加入黑名单。")
                self.log_func(f"✅ 加入黑名单: {target_qq}")
                
                # 若开启了自动踢黑，管理员加黑的同时顺便执行一次静默踢出（万一该人已经在群内）
                if self.enable_patrol:
                    await self.call_api(websocket, "set_group_kick", {"group_id": group_id, "user_id": int(target_qq), "reject_add_request": False})
            else:
                await self.send_group_msg(websocket, group_id, f"QQ {target_qq} 已经在黑名单列表中了。")
            return

        if cmd_type == "del_black" and target_qq:
            self.table_blacklist.delete(group_id=group_id, user_id=target_qq)
            await self.send_group_msg(websocket, group_id, f"已将QQ {target_qq} 移出黑名单。")
            self.log_func(f"✅ 移出黑名单: {target_qq}")
            return

    async def start(self):
        self.running = True
        try:
            self.db = dataset.connect("sqlite:///qqbot.db")
            self.table_group = self.db['QQgroup']
            self.table_blacklist = self.db['Blacklist']
            self.table_bot_admin = self.db['BotGroupAdmin']
            self.log_func("✅ SQLite 数据库连接成功 (qqbot.db)")
        except Exception as e:
            self.log_func(f"❌ 数据库异常: {e}")
            return

        self.log_func(f"正在连接 WebSocket: {self.ws_url}")
        try:
            async with websockets.connect(self.ws_url) as websocket:
                self.log_func("✅ WebSocket 连接成功！等待接收消息...")
                while self.running:
                    try:
                        msg = await websocket.recv()
                        data = json.loads(msg)
                        
                        # 拦截 API 响应
                        if "echo" in data:
                            echo_id = str(data["echo"])
                            if echo_id in self.pending_requests:
                                if not self.pending_requests[echo_id].done():
                                    self.pending_requests[echo_id].set_result(data)
                                del self.pending_requests[echo_id]
                            continue

                        # 监听：成员变动增加 (入群踢黑触发器)
                        if data.get("post_type") == "notice" and data.get("notice_type") == "group_increase":
                            asyncio.create_task(self.handle_group_increase(websocket, data))

                        # 监听：管理员变动通知事件 (动态更新数据库管理员表)
                        elif data.get("post_type") == "notice" and data.get("notice_type") == "group_admin":
                            sub_type = data.get("sub_type")
                            group_id = data.get("group_id")
                            user_id = data.get("user_id")
                            self_id = data.get("self_id")
                            
                            # 仅处理机器人自己的权限变动
                            if str(user_id) == str(self_id):
                                is_admin = (sub_type == "set")
                                self.table_bot_admin.upsert(dict(group_id=group_id, is_admin=is_admin), ["group_id"])
                                status_txt = "提拔为" if is_admin else "取消了"
                                self.log_func(f"🔔 监控到权限变动: 机器人在群 {group_id} 被{status_txt}管理权限，已更新配置表！")

                        # 常规事件处理
                        elif data.get("post_type") == "message":
                            msg_type = data.get("message_type")
                            if msg_type == "private":
                                asyncio.create_task(self.handle_private_message(websocket, data))
                            elif msg_type == "group":
                                asyncio.create_task(self.handle_group_message(websocket, data))
                    except json.JSONDecodeError: pass
        except Exception as e:
            self.log_func(f"❌ 连接异常或断开: {e}")
        self.running = False


# ----------------- GUI 界面 -----------------
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("老登群服管理中心")
        self.root.geometry("900x600")
        self.worker = None

        top_frame = ttk.LabelFrame(root, text="LLOneBot 连接设置")
        top_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(top_frame, text="WS地址:").pack(side="left", padx=5)
        self.ent_url = ttk.Entry(top_frame)
        self.ent_url.pack(side="left", fill="x", expand=True, padx=5)

        ttk.Label(top_frame, text="Token:").pack(side="left", padx=5)
        self.ent_token = ttk.Entry(top_frame, width=15)
        self.ent_token.pack(side="left", padx=5)

        # 读取数据库内存储的WS和TOKEN配置
        try:
            temp_db = dataset.connect("sqlite:///qqbot.db")
            conf = temp_db['Config'].find_one(id=1)
            if conf:
                self.ent_url.insert(0, conf.get('ws_url', "ws://127.0.0.1:3001"))
                self.ent_token.insert(0, conf.get('token', ""))
            else:
                self.ent_url.insert(0, "ws://127.0.0.1:3001")
        except:
            self.ent_url.insert(0, "ws://127.0.0.1:3001")

        self.btn_start = ttk.Button(top_frame, text="启动 Bot", command=self.start_bot)
        self.btn_start.pack(side="left", padx=5)
        self.btn_stop = ttk.Button(top_frame, text="停止", state="disabled", command=self.stop_bot)
        self.btn_stop.pack(side="left", padx=5)

        file_frame = ttk.LabelFrame(root, text="私聊注册目录设置")
        file_frame.pack(fill="x", padx=10, pady=5)
        
        self.ent_file_path = ttk.Entry(file_frame)
        self.ent_file_path.insert(0, os.path.join(os.getcwd(), "bind_records.txt"))
        self.ent_file_path.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        
        ttk.Button(file_frame, text="选择文件", command=self.browse_file).pack(side="left", padx=5)

        mid_frame = ttk.Frame(root)
        mid_frame.pack(fill="both", expand=True, padx=10, pady=5)

        left_frame = ttk.Frame(mid_frame)
        left_frame.pack(side="left", fill="y", padx=(0, 10))

        # ====== 核心升级：增加巡逻成员复选框 ======
        grp_f = ttk.LabelFrame(left_frame, text="群管理功能开关")
        grp_f.pack(fill="x", pady=5)
        
        self.var_manage = tk.BooleanVar(value=False)
        self.var_checkin = tk.BooleanVar(value=False)
        self.var_patrol = tk.BooleanVar(value=False) # 巡逻开关
        
        cb1 = ttk.Checkbutton(grp_f, text="开启群管理 (总开关)", variable=self.var_manage, command=self.update_bot_flags)
        cb1.pack(anchor="w", padx=10, pady=2)
        cb2 = ttk.Checkbutton(grp_f, text="开启群签到 (子开关)", variable=self.var_checkin, command=self.update_bot_flags)
        cb2.pack(anchor="w", padx=10, pady=2)
        cb3 = ttk.Checkbutton(grp_f, text="巡逻群成员 (自动踢黑)", variable=self.var_patrol, command=self.update_bot_flags)
        cb3.pack(anchor="w", padx=10, pady=2)

        limit_f = ttk.Frame(left_frame)
        limit_f.pack(fill="x", pady=5)
        ttk.Label(limit_f, text="每QQ私聊注册上限:").pack(side="left")
        self.spin_limit = tk.Spinbox(limit_f, from_=1, to=100, width=5)
        self.spin_limit.delete(0, "end")
        self.spin_limit.insert(0, "2")
        self.spin_limit.pack(side="left", padx=5)

        zone_f = ttk.LabelFrame(left_frame, text="区服列表管理")
        zone_f.pack(fill="both", expand=True)
        self.list_zones = tk.Listbox(zone_f, width=30)
        self.list_zones.pack(fill="both", expand=True, padx=5, pady=5)
        self.ent_new_zone = ttk.Entry(zone_f)
        self.ent_new_zone.pack(fill="x", padx=5)
        btn_f = ttk.Frame(zone_f)
        btn_f.pack(fill="x", pady=5)
        ttk.Button(btn_f, text="添加", command=self.add_zone).pack(side="left", padx=5, expand=True, fill="x")
        ttk.Button(btn_f, text="删除", command=self.del_zone).pack(side="left", padx=5, expand=True, fill="x")
        
        ttk.Button(left_frame, text="🔃 刷新文本数据", command=self.load_data).pack(fill="x", pady=5)

        log_f = ttk.LabelFrame(mid_frame, text="运行日志")
        log_f.pack(side="right", fill="both", expand=True)
        self.txt_log = scrolledtext.ScrolledText(log_f, state="disabled", font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True, padx=5, pady=5)

        self.load_data()

    def update_bot_flags(self):
        if self.worker:
            self.worker.enable_group_manage = self.var_manage.get()
            self.worker.enable_checkin = self.var_checkin.get()
            self.worker.enable_patrol = self.var_patrol.get()

    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="选择注册目录文本文件",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            self.ent_file_path.delete(0, "end")
            self.ent_file_path.insert(0, filename)
            self.load_data()

    def get_current_file(self):
        return self.ent_file_path.get().strip()

    def log(self, text):
        def _write():
            self.txt_log.config(state="normal")
            self.txt_log.insert("end", text + "\n")
            self.txt_log.see("end")
            self.txt_log.config(state="disabled")
        self.root.after(0, _write)

    def load_data(self):
        path = self.get_current_file()
        if not os.path.exists(path):
            self.log(f"提示: 文件不存在，将会在首次记录时创建: {path}")
            return
            
        self.list_zones.delete(0, "end")
        zones, recs = read_file_data(path)
        for z in zones: self.list_zones.insert("end", z)
        self.log(f"系统: 已加载 {len(zones)} 个区服，{len(recs)} 条记录")

    def sync_to_file(self):
        path = self.get_current_file()
        zones = list(self.list_zones.get(0, "end"))
        _, recs = read_file_data(path)
        write_file_data(path, zones, recs)

    def add_zone(self):
        name = self.ent_new_zone.get().strip()
        if name and name not in self.list_zones.get(0, "end"):
            self.list_zones.insert("end", name)
            self.ent_new_zone.delete(0, "end")
            self.sync_to_file()

    def del_zone(self):
        sel = self.list_zones.curselection()
        if sel:
            self.list_zones.delete(sel)
            self.sync_to_file()

    def start_bot(self):
        url = self.ent_url.get().strip()
        token = self.ent_token.get().strip()
        
        # 将最新的网络配置保存至数据库
        try:
            temp_db = dataset.connect("sqlite:///qqbot.db")
            temp_db['Config'].upsert(dict(id=1, ws_url=url, token=token), ['id'])
        except Exception as e:
            self.log(f"保存配置异常: {e}")

        final_url = f"{url}?access_token={token}" if token else url
        max_b = int(self.spin_limit.get())

        self.worker = BotWorker(final_url, max_b, self.log, self.get_current_file)
        self.update_bot_flags()
        
        def run_async():
            self.worker.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.worker.loop)
            self.worker.loop.run_until_complete(self.worker.start())
        
        self.thread = threading.Thread(target=run_async, daemon=True)
        self.thread.start()
        
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")

    def stop_bot(self):
        if self.worker:
            self.worker.running = False
            if self.worker.loop: 
                self.worker.loop.call_soon_threadsafe(self.worker.loop.stop)
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.log("系统: Bot 已停止")

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()