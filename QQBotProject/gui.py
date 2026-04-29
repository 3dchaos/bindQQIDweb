import os
import threading
import asyncio
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import dataset
from data_manager import read_file_data, write_file_data
from bot_core import BotWorker
from config import DB_URL, DEFAULT_WS_URL, DEFAULT_BIND_FILE

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("老登群服管理中心")
        self.root.geometry("900x600")
        self.worker = None

        self.setup_ui()
        self.load_config_from_db()
        self.load_data()

    def setup_ui(self):
        # 1. 顶部：连接设置
        top_frame = ttk.LabelFrame(self.root, text="LLOneBot 连接设置")
        top_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(top_frame, text="WS地址:").pack(side="left", padx=5)
        self.ent_url = ttk.Entry(top_frame)
        self.ent_url.pack(side="left", fill="x", expand=True, padx=5)

        ttk.Label(top_frame, text="Token:").pack(side="left", padx=5)
        self.ent_token = ttk.Entry(top_frame, width=15)
        self.ent_token.pack(side="left", padx=5)

        self.btn_start = ttk.Button(top_frame, text="启动 Bot", command=self.start_bot)
        self.btn_start.pack(side="left", padx=5)
        self.btn_stop = ttk.Button(top_frame, text="停止", state="disabled", command=self.stop_bot)
        self.btn_stop.pack(side="left", padx=5)

        # 2. 第二行：文件路径选择
        file_frame = ttk.LabelFrame(self.root, text="私聊注册目录设置")
        file_frame.pack(fill="x", padx=10, pady=5)
        
        self.ent_file_path = ttk.Entry(file_frame)
        self.ent_file_path.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        
        ttk.Button(file_frame, text="选择文件", command=self.browse_file).pack(side="left", padx=5)

        # 3. 中间主体
        mid_frame = ttk.Frame(self.root)
        mid_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 左侧面板
        left_frame = ttk.Frame(mid_frame)
        left_frame.pack(side="left", fill="y", padx=(0, 10))

        grp_f = ttk.LabelFrame(left_frame, text="群管理功能开关")
        grp_f.pack(fill="x", pady=5)
        
        self.var_manage = tk.BooleanVar(value=False)
        self.var_checkin = tk.BooleanVar(value=False)
        self.var_patrol = tk.BooleanVar(value=False)
        self.var_auto_join = tk.BooleanVar(value=False) # 新增：自动进群开关变量
        self.var_decoder = tk.BooleanVar(value=False) # 新增：解码器开关变量
        self.var_group_bind = tk.BooleanVar(value=False) # 新增：群绑定开关变量

        ttk.Checkbutton(grp_f, text="开启群管理 (总开关)", variable=self.var_manage, command=self.update_bot_flags).pack(anchor="w", padx=10, pady=2)
        ttk.Checkbutton(grp_f, text="开启群签到 (子开关)", variable=self.var_checkin, command=self.update_bot_flags).pack(anchor="w", padx=10, pady=2)
        ttk.Checkbutton(grp_f, text="巡逻群成员 (自动踢黑)", variable=self.var_patrol, command=self.update_bot_flags).pack(anchor="w", padx=10, pady=2)
        ttk.Checkbutton(grp_f, text="自动识别邀请进群", variable=self.var_auto_join, command=self.update_bot_flags).pack(anchor="w", padx=10, pady=2)
        
        # 解码器设置
        decoder_f = ttk.Frame(grp_f)
        decoder_f.pack(fill="x", padx=10, pady=2)
        ttk.Checkbutton(decoder_f, text="开启解码器功能", variable=self.var_decoder, command=self.update_bot_flags).pack(side="left")
        ttk.Label(decoder_f, text=" 监听群:").pack(side="left")
        self.ent_decoder_group = ttk.Entry(decoder_f, width=12)
        self.ent_decoder_group.pack(side="left", padx=5)
        
        # 群绑定设置
        bind_f = ttk.Frame(grp_f)
        bind_f.pack(fill="x", padx=10, pady=2)
        ttk.Checkbutton(bind_f, text="开启群内绑定", variable=self.var_group_bind, command=self.update_bot_flags).pack(side="left")
        ttk.Label(bind_f, text=" 绑定群:").pack(side="left")
        self.ent_bind_group = ttk.Entry(bind_f, width=12)
        self.ent_bind_group.pack(side="left", padx=5)
        
        ttk.Button(grp_f, text="更新所有开关配置", command=self.save_all_settings).pack(fill="x", padx=10, pady=5)

        limit_f = ttk.Frame(left_frame)
        limit_f.pack(fill="x", pady=5)
        ttk.Label(limit_f, text="每QQ私聊注册上限:").pack(side="left")
        self.spin_limit = tk.Spinbox(limit_f, from_=1, to=100, width=5)
        self.spin_limit.insert(0, "2")
        self.spin_limit.pack(side="left", padx=5)
        ttk.Button(limit_f, text="更新", width=5, command=self.save_all_settings).pack(side="left")

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

        # 右侧日志
        log_f = ttk.LabelFrame(mid_frame, text="运行日志")
        log_f.pack(side="right", fill="both", expand=True)
        self.txt_log = scrolledtext.ScrolledText(log_f, state="disabled", font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True, padx=5, pady=5)

    def load_config_from_db(self):
        try:
            temp_db = dataset.connect(DB_URL)
            conf = temp_db['Config'].find_one(id=1)
            if conf:
                self.ent_url.insert(0, conf.get('ws_url', DEFAULT_WS_URL))
                self.ent_token.insert(0, conf.get('token', ""))
                self.ent_file_path.insert(0, conf.get('filepath', DEFAULT_BIND_FILE))
                
                # 加载开关状态
                self.var_manage.set(conf.get('enable_manage', False))
                self.var_checkin.set(conf.get('enable_checkin', False))
                self.var_patrol.set(conf.get('enable_patrol', False))
                self.var_auto_join.set(conf.get('enable_auto_join', False))
                self.var_decoder.set(conf.get('enable_decoder', False))
                self.ent_decoder_group.delete(0, "end")
                self.ent_decoder_group.insert(0, str(conf.get('decoder_group', "")))
                
                self.var_group_bind.set(conf.get('enable_group_bind', False))
                self.ent_bind_group.delete(0, "end")
                self.ent_bind_group.insert(0, str(conf.get('bind_group', "")))

                # 加载注册上限
                limit = conf.get('max_binds', 2)
                self.spin_limit.delete(0, "end")
                self.spin_limit.insert(0, str(limit))
            else:
                self.ent_url.insert(0, DEFAULT_WS_URL)
                self.ent_file_path.insert(0, DEFAULT_BIND_FILE)
        except:
            self.ent_url.insert(0, DEFAULT_WS_URL)
            self.ent_file_path.insert(0, DEFAULT_BIND_FILE)

    def save_all_settings(self):
        """将当前界面所有设置保存到数据库，并同步到运行中的 Worker"""
        url = self.ent_url.get().strip()
        token = self.ent_token.get().strip()
        filepath = self.get_current_file()
        
        manage = self.var_manage.get()
        checkin = self.var_checkin.get()
        patrol = self.var_patrol.get()
        
        try:
            max_b = int(self.spin_limit.get())
        except:
            max_b = 2

        try:
            temp_db = dataset.connect(DB_URL)
            temp_db['Config'].upsert(dict(
                id=1, 
                ws_url=url, 
                token=token, 
                filepath=filepath,
                enable_manage=manage,
                enable_checkin=checkin,
                enable_patrol=patrol,
                enable_auto_join=self.var_auto_join.get(),
                enable_decoder=self.var_decoder.get(),
                decoder_group=self.ent_decoder_group.get().strip(),
                enable_group_bind=self.var_group_bind.get(),
                bind_group=self.ent_bind_group.get().strip(),
                max_binds=max_b
            ), ['id'])
        except Exception as e:
            self.log(f"保存配置异常: {e}")

        # 如果 Worker 正在运行，同步更新其参数
        if self.worker:
            self.worker.enable_group_manage = manage
            self.worker.enable_checkin = checkin
            self.worker.enable_patrol = patrol
            self.worker.max_binds = max_b
            self.worker.enable_auto_join = self.var_auto_join.get()
            self.worker.enable_decoder = self.var_decoder.get()
            self.worker.enable_decoder_group = self.ent_decoder_group.get().strip()
            self.worker.enable_group_bind = self.var_group_bind.get()
            self.worker.enable_bind_group = self.ent_bind_group.get().strip()
            self.log(f"系统: 配置已同步到运行中的 Bot (上限: {max_b})")

    def update_bot_flags(self):
        self.save_all_settings()

    def browse_file(self):
        filename = filedialog.askopenfilename(title="选择注册目录文本文件", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if filename:
            self.ent_file_path.delete(0, "end")
            self.ent_file_path.insert(0, filename)
            self.save_all_settings()
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
        
        # 启动前保存所有当前设置
        self.save_all_settings()

        final_url = f"{url}?access_token={token}" if token else url
        max_b = int(self.spin_limit.get())

        self.worker = BotWorker(final_url, max_b, self.log, self.get_current_file)
        # 初始同步开关状态
        self.worker.enable_group_manage = self.var_manage.get()
        self.worker.enable_checkin = self.var_checkin.get()
        self.worker.enable_patrol = self.var_patrol.get()
        self.worker.enable_auto_join = self.var_auto_join.get()
        self.worker.enable_decoder = self.var_decoder.get()
        self.worker.enable_decoder_group = self.ent_decoder_group.get().strip()
        self.worker.enable_group_bind = self.var_group_bind.get()
        self.worker.enable_bind_group = self.ent_bind_group.get().strip()
        
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