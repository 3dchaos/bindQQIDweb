import os
import sys
import threading
import asyncio
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import dataset
import shutil
import re
from data_manager import read_file_data, write_file_data
from bot_core import BotWorker
from config import DB_URL, DEFAULT_WS_URL, DEFAULT_BIND_FILE
import script_implant

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("老登群服管理中心 v1.2")
        self.root.geometry("1100x650")

        self.worker = None
        self.script_vars_entries = {} # 存储变量名和对应的 Entry
        self.setup_ui()
        self.load_config_from_db()
        self.load_data()
        self.check_implant_files() # 初始检测一次

    def setup_ui(self):
        # --- 顶部：分左右两半 ---
        top_container = ttk.Frame(self.root)
        top_container.pack(fill="x", padx=10, pady=5)

        # 1. 左侧：连接设置
        top_left = ttk.LabelFrame(top_container, text="LLOneBot 连接设置")
        top_left.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        ttk.Label(top_left, text="WS:").pack(side="left", padx=2)
        self.ent_url = ttk.Entry(top_left, width=30)
        self.ent_url.pack(side="left", fill="x", expand=True, padx=2)

        ttk.Label(top_left, text="Token:").pack(side="left", padx=2)
        self.ent_token = ttk.Entry(top_left, width=10)
        self.ent_token.pack(side="left", padx=2)

        self.btn_start = ttk.Button(top_left, text="启动", width=6, command=self.start_bot)
        self.btn_start.pack(side="left", padx=2)
        self.btn_stop = ttk.Button(top_left, text="停止", width=6, state="disabled", command=self.stop_bot)
        self.btn_stop.pack(side="left", padx=2)

        # 2. 右侧：同步目录设置
        top_right = ttk.LabelFrame(top_container, text="同步目录设置")
        top_right.pack(side="left", fill="both", expand=True, padx=(5, 0))
        
        # 使用 Grid 缩减高度
        # 私聊注册
        f1 = ttk.Frame(top_right)
        f1.pack(fill="x", pady=1)
        ttk.Label(f1, text="注册:", width=6).pack(side="left")
        self.ent_file_path = ttk.Entry(f1)
        self.ent_file_path.pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(f1, text="..", width=3, command=self.browse_file).pack(side="left")

        # 游戏文件 (并排显示)
        f23 = ttk.Frame(top_right)
        f23.pack(fill="x", pady=1)
        
        ttk.Label(f23, text="未使用:", width=6).pack(side="left")
        self.ent_unused_path = ttk.Entry(f23)
        self.ent_unused_path.pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(f23, text="..", width=3, command=self.browse_unused_file).pack(side="left")

        ttk.Label(f23, text="已使用:", width=6).pack(side="left", padx=(5,0))
        self.ent_used_log_path = ttk.Entry(f23)
        self.ent_used_log_path.pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(f23, text="..", width=3, command=self.browse_used_log_file).pack(side="left")

        # 强制同步按钮
        sync_btn_f = ttk.Frame(top_right)
        sync_btn_f.pack(fill="x", pady=2)
        ttk.Button(sync_btn_f, text="📥 日志->DB", command=self.force_sync_text_to_db).pack(side="left", padx=2, expand=True, fill="x")
        ttk.Button(sync_btn_f, text="📤 DB->未使用", command=self.force_sync_db_to_text).pack(side="left", padx=2, expand=True, fill="x")

        # --- 中间主体 (核心功能区 + 日志) ---
        mid_frame = ttk.Frame(self.root)
        mid_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 栅格布局：设置区占前 4 列，日志占最后 1 列且可伸缩
        mid_frame.columnconfigure(2, weight=1)
        mid_frame.columnconfigure(3, weight=1)
        mid_frame.columnconfigure(4, weight=1)
        mid_frame.rowconfigure(0, weight=1)

        # --- 第一列：上限控制 ---
        col1 = ttk.Frame(mid_frame)
        col1.grid(row=0, column=0, sticky="nw", padx=2)
        
        limit_box = ttk.LabelFrame(col1, text="上限控制")
        limit_box.pack(fill="x", pady=5)
        
        for text, spin_attr, val_range in [
            ("QQ注册上限:", "spin_limit", (1, 100)),
            ("CDK购上限:", "spin_cdk_limit", (1, 100)),
            ("群CDK容量:", "spin_group_cdk_limit", (1, 1000))
        ]:
            f = ttk.Frame(limit_box)
            f.pack(fill="x", padx=5, pady=2)
            ttk.Label(f, text=text).pack(side="left")
            setattr(self, spin_attr, tk.Spinbox(f, from_=val_range[0], to=val_range[1], width=5))
            getattr(self, spin_attr).pack(side="right", padx=5)
        
        ttk.Button(limit_box, text="💾 保存所有上限", command=self.save_all_settings).pack(fill="x", padx=5, pady=5)
        ttk.Button(col1, text="🔃 刷新文本数据", command=self.load_data).pack(fill="x", pady=5)

        # --- 第二列：功能开关 ---
        col2 = ttk.Frame(mid_frame)
        col2.grid(row=0, column=1, sticky="nw", padx=2)
        
        grp_f = ttk.LabelFrame(col2, text="群功能开关")
        grp_f.pack(fill="x", pady=5)
        
        switches = [
            ("开启群管理", "var_manage"),
            ("开启群签到", "var_checkin"),
            ("巡逻(自动踢黑)", "var_patrol"),
            ("自动进群", "var_auto_join"),
            ("自动同意好友", "var_auto_friend")
        ]
        for text, var_attr in switches:
            setattr(self, var_attr, tk.BooleanVar(value=False))
            ttk.Checkbutton(grp_f, text=text, variable=getattr(self, var_attr), command=self.update_bot_flags).pack(anchor="w", padx=5)
        
        # 解码/绑定
        for text, var_attr, ent_attr in [("解码", "var_decoder", "ent_decoder_group"), ("绑定", "var_group_bind", "ent_bind_group")]:
            setattr(self, var_attr, tk.BooleanVar(value=False))
            f = ttk.Frame(grp_f)
            f.pack(fill="x", padx=5, pady=1)
            ttk.Checkbutton(f, text=text, variable=getattr(self, var_attr), command=self.update_bot_flags).pack(side="left")
            setattr(self, ent_attr, ttk.Entry(f, width=10))
            getattr(self, ent_attr).pack(side="right", padx=2)

        # --- 第三列：撤回 & 区服 ---
        col3 = ttk.Frame(mid_frame)
        col3.grid(row=0, column=2, sticky="nw", padx=2)
        
        recall_f = ttk.LabelFrame(col3, text="撤回设置")
        recall_f.pack(fill="x", pady=5)
        
        self.var_auto_recall = tk.BooleanVar(value=False)
        self.var_recall_delay = tk.IntVar(value=3)
        self.recall_cmds_vars = {}
        
        rc_top = ttk.Frame(recall_f)
        rc_top.pack(fill="x", padx=5, pady=2)
        ttk.Checkbutton(rc_top, text="自动", variable=self.var_auto_recall, command=self.update_bot_flags).pack(side="left")
        tk.Spinbox(rc_top, from_=1, to=60, width=3, textvariable=self.var_recall_delay, command=self.update_bot_flags).pack(side="left", padx=2)
        ttk.Label(rc_top, text="秒").pack(side="left")

        # 指令选择 (精简版)
        self.recall_cmds_frame = ttk.Frame(recall_f)
        self.recall_cmds_frame.pack(fill="x", padx=2)
        commands = [
            ("menu", "菜单"), ("checkin", "签到"), ("points", "积分"),
            ("buy_cdk", "购CDK"), ("list_my_cdk", "我的CDK"), ("list_zones", "区表"),
            ("list_my_accounts", "我的号")
        ]
        for i, (cid, cname) in enumerate(commands):
            var = tk.BooleanVar(value=True)
            self.recall_cmds_vars[cid] = var
            ttk.Checkbutton(self.recall_cmds_frame, text=cname, variable=var, command=self.update_bot_flags).grid(row=i//2, column=i%2, sticky="w")

        # 区服管理 (移到下面或作为第四列)
        zone_f = ttk.LabelFrame(col3, text="区服管理")
        zone_f.pack(fill="both", expand=True, pady=5)
        self.list_zones = tk.Listbox(zone_f, width=15, height=8)
        self.list_zones.pack(fill="both", expand=True, padx=5, pady=2)
        self.ent_new_zone = ttk.Entry(zone_f, width=12)
        self.ent_new_zone.pack(fill="x", padx=5)
        btn_f = ttk.Frame(zone_f)
        btn_f.pack(fill="x")
        ttk.Button(btn_f, text="+", width=3, command=self.add_zone).pack(side="left", padx=5)
        ttk.Button(btn_f, text="-", width=3, command=self.del_zone).pack(side="left")
        ttk.Button(btn_f, text="扫", width=3, command=self.cleanup_records).pack(side="right", padx=5)

        # --- 第四列：版本植入 ---
        col4 = ttk.Frame(mid_frame)
        col4.grid(row=0, column=3, sticky="nw", padx=2)
        
        implant_f = ttk.LabelFrame(col4, text="版本植入")
        implant_f.pack(fill="both", expand=True, pady=5)
        
        self.lbl_implant_items = {}
        f_status = ttk.Frame(implant_f)
        f_status.pack(fill="x")
        for name, fname in [("QF", "QF.txt"), ("QM", "QM.txt"), ("NPC", "老登.txt"), ("功能", "老登功能")]:
            lbl = tk.Label(f_status, text=name, width=4, fg="white", bg="grey", font=("", 8))
            lbl.pack(side="left", padx=2, pady=1)
            self.lbl_implant_items[name] = (lbl, fname)
            
        ttk.Button(implant_f, text="刷新变量", command=self.refresh_script_variables).pack(fill="x", padx=5, pady=2)
        
        # 变量列表容器
        var_list_f = ttk.LabelFrame(implant_f, text="注入变量")
        var_list_f.pack(fill="both", expand=True, padx=5, pady=2)
        
        self.canvas_vars = tk.Canvas(var_list_f, width=180)
        self.scrollbar_vars = ttk.Scrollbar(var_list_f, orient="vertical", command=self.canvas_vars.yview)
        self.scrollable_vars_frame = ttk.Frame(self.canvas_vars)
        
        self.scrollable_vars_frame.bind(
            "<Configure>",
            lambda e: self.canvas_vars.configure(scrollregion=self.canvas_vars.bbox("all"))
        )
        
        self.canvas_vars.create_window((0, 0), window=self.scrollable_vars_frame, anchor="nw")
        self.canvas_vars.configure(yscrollcommand=self.scrollbar_vars.set)
        
        self.canvas_vars.pack(side="left", fill="both", expand=True)
        self.scrollbar_vars.pack(side="right", fill="y")
        
        self.ent_version_dir = ttk.Entry(implant_f, width=12)
        self.ent_version_dir.pack(fill="x", padx=5, pady=2)
        ttk.Button(implant_f, text="选择版本目录", command=self.browse_version_dir).pack(fill="x", padx=5)
        self.lbl_game_name = ttk.Label(implant_f, text="游戏: 未知", font=("", 9), foreground="blue")
        self.lbl_game_name.pack(padx=5)
        self.btn_write_implant = ttk.Button(implant_f, text="写入功能", state="disabled", command=self.write_implant_function)
        self.btn_write_implant.pack(fill="x", padx=5, pady=5)

        # --- 第五列：运行日志 (占用剩余所有空间) ---
        log_frame = ttk.LabelFrame(mid_frame, text="运行日志")
        log_frame.grid(row=0, column=4, sticky="nsew", padx=5, pady=5)
        self.txt_log = scrolledtext.ScrolledText(log_frame, state="disabled", width=40, font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True, padx=5, pady=5)

    def load_config_from_db(self):
        try:
            temp_db = dataset.connect(DB_URL)
            conf = temp_db['Config'].find_one(id=1)
            if conf:
                self.ent_url.delete(0, "end")
                self.ent_url.insert(0, conf.get('ws_url', DEFAULT_WS_URL))
                self.ent_token.delete(0, "end")
                self.ent_token.insert(0, conf.get('token', ""))
                self.ent_file_path.delete(0, "end")
                self.ent_file_path.insert(0, conf.get('filepath', DEFAULT_BIND_FILE))
                self.ent_unused_path.delete(0, "end")
                self.ent_unused_path.insert(0, conf.get('game_unused_path', ""))
                self.ent_used_log_path.delete(0, "end")
                self.ent_used_log_path.insert(0, conf.get('game_used_log_path', ""))
                
                # 加载开关状态
                self.var_manage.set(conf.get('enable_manage', False))
                self.var_checkin.set(conf.get('enable_checkin', False))
                self.var_patrol.set(conf.get('enable_patrol', False))
                self.var_auto_join.set(conf.get('enable_auto_join', False))
                self.var_auto_friend.set(conf.get('enable_auto_friend', False))
                self.var_auto_recall.set(conf.get('enable_auto_recall', False))
                self.var_recall_delay.set(conf.get('recall_delay', 3))
                
                # 加载撤回指令列表
                import json
                saved_cmds = conf.get('recall_cmds', "")
                if saved_cmds:
                    try:
                        cmds_list = json.loads(saved_cmds)
                        for cid, var in self.recall_cmds_vars.items():
                            var.set(cid in cmds_list)
                    except: pass

                self.var_decoder.set(conf.get('enable_decoder', False))
                self.ent_decoder_group.delete(0, "end")
                self.ent_decoder_group.insert(0, str(conf.get('decoder_group', "")))
                
                self.var_group_bind.set(conf.get('enable_group_bind', False))
                self.ent_bind_group.delete(0, "end")
                self.ent_bind_group.insert(0, str(conf.get('bind_group', "")))

                # 加载注册上限
                self.spin_limit.delete(0, "end")
                self.spin_limit.insert(0, str(conf.get('max_binds', 2)))
                # 加载 CDK 上限
                self.spin_cdk_limit.delete(0, "end")
                self.spin_cdk_limit.insert(0, str(conf.get('max_cdk_binds', 5)))
                # 加载群 CDK 总容量
                self.spin_group_cdk_limit.delete(0, "end")
                self.spin_group_cdk_limit.insert(0, str(conf.get('max_group_cdk', 100)))
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
        auto_friend = self.var_auto_friend.get()
        auto_recall = self.var_auto_recall.get()
        recall_delay = self.var_recall_delay.get()
        
        # 获取开启撤回的指令列表
        import json
        recall_cmds = [cid for cid, var in self.recall_cmds_vars.items() if var.get()]
        recall_cmds_json = json.dumps(recall_cmds)
        
        try:
            max_b = int(self.spin_limit.get())
        except: max_b = 2
        try:
            max_cdk_b = int(self.spin_cdk_limit.get())
        except: max_cdk_b = 5
        try:
            max_g_cdk = int(self.spin_group_cdk_limit.get())
        except: max_g_cdk = 100

        game_unused = self.ent_unused_path.get().strip()
        game_used = self.ent_used_log_path.get().strip()

        try:
            temp_db = dataset.connect(DB_URL)
            temp_db['Config'].upsert(dict(
                id=1, 
                ws_url=url, 
                token=token, 
                filepath=filepath,
                game_unused_path=game_unused,
                game_used_log_path=game_used,
                enable_manage=manage,
                enable_checkin=checkin,
                enable_patrol=patrol,
                enable_auto_join=self.var_auto_join.get(),
                enable_auto_friend=auto_friend,
                enable_auto_recall=auto_recall,
                recall_delay=recall_delay,
                recall_cmds=recall_cmds_json,
                enable_decoder=self.var_decoder.get(),
                decoder_group=self.ent_decoder_group.get().strip(),
                enable_group_bind=self.var_group_bind.get(),
                bind_group=self.ent_bind_group.get().strip(),
                max_binds=max_b,
                max_cdk_binds=max_cdk_b,
                max_group_cdk=max_g_cdk
            ), ['id'])
        except Exception as e:
            self.log(f"保存配置异常: {e}")

        # 如果 Worker 正在运行，同步更新其参数
        if self.worker:
            self.worker.enable_group_manage = manage
            self.worker.enable_checkin = checkin
            self.worker.enable_patrol = patrol
            self.worker.max_binds = max_b
            self.worker.max_cdk_binds = max_cdk_b
            self.worker.max_group_cdk = max_g_cdk
            self.worker.game_unused_file = game_unused
            self.worker.game_used_log_file = game_used
            self.worker.enable_auto_join = self.var_auto_join.get()
            self.worker.enable_auto_friend = auto_friend
            self.worker.enable_auto_recall = auto_recall
            self.worker.recall_delay = recall_delay
            self.worker.recall_cmds = recall_cmds
            self.worker.enable_decoder = self.var_decoder.get()
            self.worker.enable_decoder_group = self.ent_decoder_group.get().strip()
            self.worker.enable_group_bind = self.var_group_bind.get()
            self.worker.enable_bind_group = self.ent_bind_group.get().strip()
            self.log(f"系统: 配置已同步 (QQ上限: {max_b}, CDK上限: {max_cdk_b}, 群容量: {max_g_cdk})")

    def update_bot_flags(self):
        self.save_all_settings()

    def browse_file(self):
        filename = filedialog.askopenfilename(title="选择注册目录文本文件", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if filename:
            self.ent_file_path.delete(0, "end")
            self.ent_file_path.insert(0, filename)
            self.save_all_settings()
            self.load_data()

    def browse_unused_file(self):
        filename = filedialog.askopenfilename(title="选择游戏【未使用CDK】文本文件", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if filename:
            self.ent_unused_path.delete(0, "end")
            self.ent_unused_path.insert(0, filename)
            self.save_all_settings()

    def browse_used_log_file(self):
        filename = filedialog.askopenfilename(title="选择游戏【已使用日志】文本文件", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if filename:
            self.ent_used_log_path.delete(0, "end")
            self.ent_used_log_path.insert(0, filename)
            self.save_all_settings()

    def force_sync_text_to_db(self):
        if not self.worker:
            self.log("❌ 请先启动 Bot 后再执行强制同步")
            return
        # 在异步事件循环中运行
        self.worker.loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self.worker.manual_sync_text_to_db())
        )

    def force_sync_db_to_text(self):
        if not self.worker:
            self.log("❌ 请先启动 Bot 后再执行强制同步")
            return
        self.worker.loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self.worker.manual_sync_db_to_text())
        )

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

    def cleanup_records(self):
        path = self.get_current_file()
        if not os.path.exists(path): return
        
        zones, recs = read_file_data(path)
        valid_records = []
        removed_count = 0
        
        for r in recs:
            try:
                acc_zone = r.split('|')[0]
                zone = acc_zone.rsplit(':', 1)[-1]
                if zone in zones:
                    valid_records.append(r)
                else:
                    removed_count += 1
            except:
                removed_count += 1
        
        if removed_count > 0:
            if write_file_data(path, zones, valid_records):
                self.log(f"清理完成: 已删除 {removed_count} 条失效注册记录 (所属区服不在列表中)")
                self.load_data()
            else:
                self.log("❌ 清理失败: 无法写入文件")
        else:
            self.log("提示: 未发现失效注册记录，无需清理")

    def start_bot(self):
        url = self.ent_url.get().strip()
        token = self.ent_token.get().strip()
        
        # 启动前保存所有当前设置
        self.save_all_settings()

        final_url = f"{url}?access_token={token}" if token else url
        max_b = int(self.spin_limit.get())

        self.worker = BotWorker(final_url, max_b, self.log, self.get_current_file)
        # 初始同步开关状态
        try:
            self.worker.max_cdk_binds = int(self.spin_cdk_limit.get())
        except: self.worker.max_cdk_binds = 5
        try:
            self.worker.max_group_cdk = int(self.spin_group_cdk_limit.get())
        except: self.worker.max_group_cdk = 100
        
        self.worker.game_unused_file = self.ent_unused_path.get().strip()
        self.worker.game_used_log_file = self.ent_used_log_path.get().strip()
        
        self.worker.enable_group_manage = self.var_manage.get()
        self.worker.enable_checkin = self.var_checkin.get()
        self.worker.enable_patrol = self.var_patrol.get()
        self.worker.enable_auto_join = self.var_auto_join.get()
        self.worker.enable_auto_friend = self.var_auto_friend.get()
        self.worker.enable_auto_recall = self.var_auto_recall.get()
        self.worker.recall_delay = self.var_recall_delay.get()
        self.worker.recall_cmds = [cid for cid, var in self.recall_cmds_vars.items() if var.get()]
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

    def browse_version_dir(self):
        directory = filedialog.askdirectory(title="选择版本根目录")
        if directory:
            self.ent_version_dir.delete(0, "end")
            self.ent_version_dir.insert(0, directory)
            name = script_implant.get_game_name(directory, self.log)
            self.lbl_game_name.config(text=f"游戏名称: {name}")
            self.btn_write_implant.config(state="normal")
            self.save_all_settings()

    def load_game_name_from_ini(self, directory):
        # 兼容旧逻辑，但现在主要由 browse_version_dir 调用 script_implant
        name = script_implant.get_game_name(directory, self.log)
        self.lbl_game_name.config(text=f"游戏名称: {name}")

    def check_implant_files(self):
        """检查 Mir2Text 目录下的文件是否存在并更新 UI 颜色"""
        mir_path = script_implant.get_mir_path()
        items = [(name, fname) for name, (lbl, fname) in self.lbl_implant_items.items()]
        results = script_implant.check_templates(mir_path, items)

        all_ok = True
        for name, exists in results.items():
            lbl, _ = self.lbl_implant_items[name]
            if exists:
                lbl.config(bg="green")
            else:
                lbl.config(bg="red")
                all_ok = False
        return all_ok

    def refresh_script_variables(self):
        """扫描所有模板文件并提取变量显示在 UI 上 (去重处理)"""
        self.check_implant_files()
        mir_path = script_implant.get_mir_path()
        unified_vars = script_implant.get_unified_variables(mir_path, self.log)

        self.script_vars_entries.clear()
        for widget in self.scrollable_vars_frame.winfo_children():
            widget.destroy()

        if not unified_vars:
            ttk.Label(self.scrollable_vars_frame, text="未发现变量").pack()
        else:
            # 按名称排序，方便查找
            for var_name in sorted(unified_vars.keys()):
                def_val = unified_vars[var_name]
                row = ttk.Frame(self.scrollable_vars_frame)
                row.pack(fill="x", pady=1)
                ttk.Label(row, text=f"{var_name}:", width=12).pack(side="left")
                ent = ttk.Entry(row, width=10)
                ent.insert(0, def_val)
                ent.pack(side="right", padx=2, fill="x", expand=True)
                self.script_vars_entries[var_name] = ent

        self.log(f"系统: 已提取并去重 {len(unified_vars)} 个模板变量")

    def write_implant_function(self):
        """执行脚本注入逻辑"""
        version_dir = self.ent_version_dir.get().strip()
        if not version_dir or not os.path.isdir(version_dir):
            messagebox.showerror("错误", "请先选择有效的版本目录")
            return

        if not messagebox.askyesno("确认", "此操作将修改版本脚本文件，确定要继续吗？"):
            return

        user_inputs = {name: ent.get().strip() for name, ent in self.script_vars_entries.items()}
        mir_path = script_implant.get_mir_path()

        if script_implant.implant_scripts(version_dir, mir_path, user_inputs, self.log):
            messagebox.showinfo("完成", "版本功能植入已完成！")
        else:
            messagebox.showerror("错误", "注入过程中发生异常，请查看日志")