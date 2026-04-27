import sys
import json
import asyncio
import websockets
import re
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog

# ----------------- 数据读写核心逻辑 (增加 filepath 参数) -----------------
def read_file_data(filepath):
    zones = []
    records = []
    if not filepath or not os.path.exists(filepath):
        return zones, records
    try:
        with open(filepath, 'r', encoding='gbk') as f:
            lines = f.readlines()
            if not lines:
                return zones, records
            first_line = lines[0].strip()
            if first_line.startswith(';区列表:'):
                z_str = first_line.replace(';区列表:', '')
                if z_str:
                    zones = z_str.split('|')
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
        with open(filepath, 'w', encoding='gbk') as f:
            f.write(f";区列表:{'|'.join(zones)}\n")
            for r in records:
                f.write(f"{r}\n")
        return True
    except Exception as e:
        print(f"写入文件错误: {e}")
        return False

# ----------------- Bot 核心逻辑 -----------------
class BotWorker:
    def __init__(self, ws_url, max_binds, log_func, get_filepath_func):
        self.ws_url = ws_url
        self.max_binds = max_binds
        self.log_func = log_func
        self.get_filepath = get_filepath_func # 通过函数实时获取界面上的文件路径
        self.running = False
        self.loop = None

    async def send_private_msg(self, websocket, user_id, text):
        payload = {"action": "send_private_msg", "params": {"user_id": user_id, "message": text}}
        await websocket.send(json.dumps(payload))

    async def handle_private_message(self, websocket, data):
        sender = data.get("sender", {})
        qq_num = sender.get("user_id")
        nickname = sender.get("nickname", "未知昵称")
        msg_text = data.get("raw_message", "").strip()

        # 实时读取当前指定的文件
        filepath = self.get_filepath()
        zones, records = read_file_data(filepath)

        # 指令处理 (逻辑同前)
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
                self.log_func(f"✅ 绑定成功: {new_record}")
            return

        await self.send_private_msg(websocket, qq_num, "无法识别指令。请尝试：\n1. 绑定XXX区，账号：123\n2. 开区列表\n3. 查下名下账号")

    async def start(self):
        self.running = True
        self.log_func(f"正在连接: {self.ws_url}")
        try:
            async with websockets.connect(self.ws_url) as websocket:
                self.log_func("✅ 连接成功！")
                while self.running:
                    try:
                        msg = await websocket.recv()
                        data = json.loads(msg)
                        if data.get("post_type") == "message" and data.get("message_type") == "private":
                            await self.handle_private_message(websocket, data)
                    except: pass
        except Exception as e:
            self.log_func(f"❌ 连接异常: {e}")
        self.running = False

# ----------------- GUI 界面 -----------------
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("老登群服管理中心 (Tkinter兼容版)")
        self.root.geometry("850x550")
        self.worker = None

        # 1. 顶部：连接设置
        top_frame = ttk.LabelFrame(root, text="连接设置")
        top_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(top_frame, text="WS地址:").pack(side="left", padx=5)
        self.ent_url = ttk.Entry(top_frame)
        self.ent_url.insert(0, "ws://127.0.0.1:3001")
        self.ent_url.pack(side="left", fill="x", expand=True, padx=5)

        ttk.Label(top_frame, text="Token:").pack(side="left", padx=5)
        self.ent_token = ttk.Entry(top_frame, width=15)
        self.ent_token.pack(side="left", padx=5)

        self.btn_start = ttk.Button(top_frame, text="启动 Bot", command=self.start_bot)
        self.btn_start.pack(side="left", padx=5)
        self.btn_stop = ttk.Button(top_frame, text="停止", state="disabled", command=self.stop_bot)
        self.btn_stop.pack(side="left", padx=5)

        # 2. 第二行：文件路径选择
        file_frame = ttk.LabelFrame(root, text="注册目录设置")
        file_frame.pack(fill="x", padx=10, pady=5)
        
        self.ent_file_path = ttk.Entry(file_frame)
        self.ent_file_path.insert(0, os.path.join(os.getcwd(), "bind_records.txt")) # 默认当前目录下
        self.ent_file_path.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        
        ttk.Button(file_frame, text="选择文件", command=self.browse_file).pack(side="left", padx=5)

        # 3. 中间主体
        mid_frame = ttk.Frame(root)
        mid_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 左侧配置
        left_frame = ttk.Frame(mid_frame)
        left_frame.pack(side="left", fill="y", padx=(0, 10))

        limit_f = ttk.Frame(left_frame)
        limit_f.pack(fill="x", pady=5)
        ttk.Label(limit_f, text="注册上限:").pack(side="left")
        self.spin_limit = tk.Spinbox(limit_f, from_=1, to=100, width=5)
        self.spin_limit.delete(0, "end")
        self.spin_limit.insert(0, "2")
        self.spin_limit.pack(side="left", padx=5)

        zone_f = ttk.LabelFrame(left_frame, text="区服管理")
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

        # 右侧日志
        log_f = ttk.LabelFrame(mid_frame, text="运行日志")
        log_f.pack(side="right", fill="both", expand=True)
        self.txt_log = scrolledtext.ScrolledText(log_f, state="disabled", font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True, padx=5, pady=5)

        self.load_data()

    def browse_file(self):
        """弹出文件选择对话框"""
        filename = filedialog.askopenfilename(
            title="选择注册目录文本文件",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            self.ent_file_path.delete(0, "end")
            self.ent_file_path.insert(0, filename)
            self.load_data()

    def get_current_file(self):
        """实时获取输入框里的文件路径"""
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
        self.log(f"系统: 已从指定路径加载 {len(zones)} 个区服，{len(recs)} 条记录")

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
        final_url = f"{url}?access_token={token}" if token else url
        max_b = int(self.spin_limit.get())

        # 将获取文件路径的函数传给 worker
        self.worker = BotWorker(final_url, max_b, self.log, self.get_current_file)
        
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
            if self.worker.loop: self.worker.loop.call_soon_threadsafe(self.worker.loop.stop)
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.log("系统: Bot 已停止")

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()