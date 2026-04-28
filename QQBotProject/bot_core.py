import json
import asyncio
import websockets
import re
import dataset
import datetime
from data_manager import read_file_data, write_file_data
from config import DB_URL

class BotWorker:
    def __init__(self, ws_url, max_binds, log_func, get_filepath_func):
        self.ws_url = ws_url
        self.max_binds = max_binds
        self.log_func = log_func
        self.get_filepath = get_filepath_func
        
        # 界面控制开关
        self.enable_group_manage = False
        self.enable_checkin = False
        self.enable_patrol = False 
        
        self.running = False
        self.loop = None
        
        # API 异步请求字典
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
            if result.get("status") == "failed": return None
            return result.get("data")
        except asyncio.TimeoutError:
            self.pending_requests.pop(echo_id, None)
            return None

    async def send_private_msg(self, websocket, user_id, text):
        await websocket.send(json.dumps({"action": "send_private_msg", "params": {"user_id": user_id, "message": text}}))

    async def send_group_msg(self, websocket, group_id, text):
        await websocket.send(json.dumps({"action": "send_group_msg", "params": {"group_id": group_id, "message": text}}))

    
    # --- [辅助方法] 生成通用的开区列表回复文本 ---
    def get_zones_msg(self, zones, records):
        counts = {z: 0 for z in zones}
        for r in records:
            try:
                # 记录格式: account:zone|qq|nickname
                acc_zone = r.split('|')[0]
                zone = acc_zone.split(':')[1]
                if zone in counts: counts[zone] += 1
            except: pass
        
        reply = "【🏰 当前开区列表及注册人数】\n"
        if not zones:
            reply += "暂无开区信息。"
        else:
            for z in zones:
                reply += f"🔹 {z} ：{counts.get(z, 0)} 人已注册\n"
        return reply.strip()

    # --- 处理私聊消息 (自动附带列表版) ---
    async def handle_private_message(self, websocket, data):
        sender = data.get("sender", {})
        qq_num = sender.get("user_id")
        nickname = sender.get("nickname", "未知昵称")
        msg_text = data.get("raw_message", "").strip()

        filepath = self.get_filepath()
        zones, records = read_file_data(filepath)

        # 1. 指令：开区列表
        if msg_text == "开区列表":
            reply = self.get_zones_msg(zones, records)
            await self.send_private_msg(websocket, qq_num, reply)
            return

        # 2. 指令：查下名下账号
        if msg_text == "查下名下账号":
            found = []
            for r in records:
                try:
                    parts = r.split('|')
                    if len(parts) >= 2 and parts[1] == str(qq_num):
                        acc_zone = parts[0]
                        acc, zone = acc_zone.split(':')
                        found.append(f"账号：{acc} ({zone})")
                except: pass
            reply = "【👤 您名下已绑定账号】\n" + ("\n".join(found) if found else "未查询到记录")
            await self.send_private_msg(websocket, qq_num, reply)
            return

        # 3. 绑定指令匹配
        bind_match = re.search(r"绑定\s*(\S+)\s*(?:账号[:：]?)?\s*(\S+)", msg_text)
        
        if bind_match:
            zone_name = re.sub(r"[,，:：\-\s]", "", bind_match.group(1).strip())
            account = re.sub(r"[,，:：\-\s]", "", bind_match.group(2).strip())
            
            # 获取公共列表，准备在失败时使用
            zones_list_txt = self.get_zones_msg(zones, records)

            # 校验区服是否存在
            if zone_name not in zones:
                fail_msg = f"❌ 注册失败：【{zone_name}】不在开区名单内！\n\n{zones_list_txt}"
                await self.send_private_msg(websocket, qq_num, fail_msg)
                return

            # 校验是否已被注册
            my_binds = 0
            account_registered = False
            for r in records:
                try:
                    p = r.split('|')
                    if p[0] == f"{account}:{zone_name}": account_registered = True
                    if p[1] == str(qq_num): my_binds += 1
                except: continue

            if account_registered:
                fail_msg = f"❌ 注册失败：账号【{account}】在【{zone_name}】已被占用！\n\n{zones_list_txt}"
                await self.send_private_msg(websocket, qq_num, fail_msg)
                return

            # 校验次数上限
            if my_binds >= self.max_binds:
                fail_msg = f"❌ 注册失败：您在此区的名额已满({self.max_binds}个)！\n\n{zones_list_txt}"
                await self.send_private_msg(websocket, qq_num, fail_msg)
                return

            # 最终写入
            new_record = f"{account}:{zone_name}|{qq_num}|{nickname}"
            records.append(new_record)
            if write_file_data(filepath, zones, records):
                success_msg = f"🎉 绑定成功！\n区服：{zone_name}\n账号：{account}\n祝您游戏愉快！"
                await self.send_private_msg(websocket, qq_num, success_msg)
                self.log_func(f"✅ 私聊绑定成功: {new_record}")
            return

        # 4. 兜底回复
        default_reply = (
            "🤖 无法识别指令。请尝试：\n"
            "1. 绑定 1区 123 (推荐)\n"
            "2. 开区列表\n"
            "3. 查下名下账号"
        )
        await self.send_private_msg(websocket, qq_num, default_reply)

    async def handle_group_increase(self, websocket, data):
        if not self.enable_patrol: return
        group_id = data.get("group_id")
        user_id = str(data.get("user_id"))
        self_id = data.get("self_id")

        if str(user_id) == str(self_id): return 

        if self.table_blacklist.find_one(group_id=group_id, user_id=user_id):
            self.log_func(f"🚨 巡逻触发: 发现黑名单成员 {user_id} 加入群 {group_id}，正在拦截...")
            
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
                await self.call_api(websocket, "set_group_kick", {"group_id": group_id, "user_id": int(user_id), "reject_add_request": False})
                await self.send_group_msg(websocket, group_id, f"{user_id}为本群黑名单，已将他踢出群。")
                self.log_func(f"✅ 巡逻踢黑成功: 已自动清退成员 {user_id}")
            else:
                self.log_func(f"❌ 巡逻踢黑失败: 机器人在群 {group_id} 没有管理员权限。")

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

        if re.match(r"^/(?:加入黑名单QQ|加黑)\s*(\d+)$", clean_msg):
            cmd_type = "add_black"
            target_qq = re.match(r"^/(?:加入黑名单QQ|加黑)\s*(\d+)$", clean_msg).group(1)
        elif re.match(r"^/(?:删除黑名单QQ|删黑)\s*(\d+)$", clean_msg):
            cmd_type = "del_black"
            target_qq = re.match(r"^/(?:删除黑名单QQ|删黑)\s*(\d+)$", clean_msg).group(1)
        elif re.match(r"^/(?:黑名单QQ|黑名单|黑)$", clean_msg):
            cmd_type = "list_black"
        elif "/功能" in clean_msg:
            cmd_type = "menu"
        elif clean_msg == "/签到":
            cmd_type = "checkin"
        elif clean_msg == "/积分":
            cmd_type = "points"

        if not cmd_type: return

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

        # 2. 验证【发送消息的人】是否为管理员
        is_sender_admin = role in ["owner", "admin"]
        if cmd_type in ["add_black", "del_black", "list_black"]:
            if not is_sender_admin:
                self.log_func(f"🚫 拦截: 成员 {user_id} 并非管理，无权操作黑名单。")
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 权限不足！需要您是本群的群主或管理员！")
                return

        # ================ 路由 ================
        if cmd_type == "menu":
            reply = "1，/签到(获得1积分)\n2，/黑名单QQ(查看黑名单列表)\n3，/加入黑名单QQ XXXX\n4，/删除黑名单QQ XXXX\n5，/积分(查看成员积分)"
            await self.send_group_msg(websocket, group_id, reply)
            
        elif cmd_type == "checkin":
            if not self.enable_checkin: return
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            record = self.table_group.find_one(group_id=group_id, user_id=user_id)
            if not record:
                self.table_group.insert(dict(group_id=group_id, user_nickname=nickname, user_id=user_id, points=1, last_checkin_date=today))
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 签到成功，积分+1")
            elif record['last_checkin_date'] == today:
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 签到失败，今天已经签到过了~")
            else:
                self.table_group.update(dict(id=record['id'], points=record['points'] + 1, last_checkin_date=today, user_nickname=nickname), ['id'])
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 签到成功，积分+1")
                
        elif cmd_type == "points":
            if not self.enable_checkin: return
            record = self.table_group.find_one(group_id=group_id, user_id=user_id)
            if not record:
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 没有你的记录")
            else:
                pts = record['points']
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 你拥有积分是:{pts}，签到时间为：{record['last_checkin_date']}")

        elif cmd_type == "list_black":
            bl_records = list(self.table_blacklist.find(group_id=group_id))
            if not bl_records:
                await self.send_group_msg(websocket, group_id, "当前群的黑名单为空。")
            else:
                bl_qqs = [str(x['user_id']) for x in bl_records]
                await self.send_group_msg(websocket, group_id, f"当前群黑名单包含QQ: {', '.join(bl_qqs)}")

        elif cmd_type == "add_black" and target_qq:
            if not self.table_blacklist.find_one(group_id=group_id, user_id=target_qq):
                self.table_blacklist.insert(dict(group_id=group_id, user_id=target_qq))
                await self.send_group_msg(websocket, group_id, f"已将QQ {target_qq} 成功加入黑名单。")
                self.log_func(f"✅ 加入黑名单: {target_qq}")
                
                if self.enable_patrol:
                    await self.call_api(websocket, "set_group_kick", {"group_id": group_id, "user_id": int(target_qq), "reject_add_request": False})
            else:
                await self.send_group_msg(websocket, group_id, f"QQ {target_qq} 已经在黑名单列表中了。")

        elif cmd_type == "del_black" and target_qq:
            self.table_blacklist.delete(group_id=group_id, user_id=target_qq)
            await self.send_group_msg(websocket, group_id, f"已将QQ {target_qq} 移出黑名单。")
            self.log_func(f"✅ 移出黑名单: {target_qq}")

    async def start(self):
        self.running = True
        try:
            self.db = dataset.connect(DB_URL)
            self.table_group = self.db['QQgroup']
            self.table_blacklist = self.db['Blacklist']
            self.table_bot_admin = self.db['BotGroupAdmin']
            self.log_func("✅ 数据库加载成功")
        except Exception as e:
            self.log_func(f"❌ 数据库异常: {e}")
            return

        self.log_func(f"正在连接: {self.ws_url}")
        try:
            async with websockets.connect(self.ws_url) as websocket:
                self.log_func("✅ LLOneBot 连接成功！")
                while self.running:
                    try:
                        msg = await websocket.recv()
                        data = json.loads(msg)
                        
                        if "echo" in data:
                            echo_id = str(data["echo"])
                            if echo_id in self.pending_requests:
                                if not self.pending_requests[echo_id].done():
                                    self.pending_requests[echo_id].set_result(data)
                                del self.pending_requests[echo_id]
                            continue

                        if data.get("post_type") == "notice" and data.get("notice_type") == "group_increase":
                            asyncio.create_task(self.handle_group_increase(websocket, data))

                        elif data.get("post_type") == "notice" and data.get("notice_type") == "group_admin":
                            sub_type = data.get("sub_type")
                            group_id = data.get("group_id")
                            user_id = data.get("user_id")
                            if str(user_id) == str(data.get("self_id")):
                                is_admin = (sub_type == "set")
                                self.table_bot_admin.upsert(dict(group_id=group_id, is_admin=is_admin), ["group_id"])
                                status_txt = "提拔为" if is_admin else "取消了"
                                self.log_func(f"🔔 权限变动: 机器人在群 {group_id} 被{status_txt}管理权限")

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