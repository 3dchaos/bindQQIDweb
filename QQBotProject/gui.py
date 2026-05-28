import os
import sys
import threading
import asyncio
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import dataset
import configparser
from data_manager import read_file_data, write_file_data
from bot_core import BotWorker
from config import DB_URL, DEFAULT_WS_URL, DEFAULT_BIND_FILE

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("老登群服管理中心 v1.2")
        self.root.geometry("1100x650")

        self.worker = None
        self.setup_ui()
        self.load_config_from_db()
        self.load_data()
        self.check_implant_files() # 初始检测一次

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
        file_frame = ttk.LabelFrame(self.root, text="同步目录设置")
        file_frame.pack(fill="x", padx=10, pady=5)
        
        # 私聊注册目录
        f1 = ttk.Frame(file_frame)
        f1.pack(fill="x", pady=2)
        ttk.Label(f1, text="私聊注册:", width=10).pack(side="left", padx=5)
        self.ent_file_path = ttk.Entry(f1)
        self.ent_file_path.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(f1, text="选择", width=5, command=self.browse_file).pack(side="left", padx=5)

        # 游戏未使用CDK文件
        f2 = ttk.Frame(file_frame)
        f2.pack(fill="x", pady=2)
        ttk.Label(f2, text="未使用CDK:", width=10).pack(side="left", padx=5)
        self.ent_unused_path = ttk.Entry(f2)
        self.ent_unused_path.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(f2, text="选择", width=5, command=self.browse_unused_file).pack(side="left", padx=5)

        # 游戏已使用日志文件
        f3 = ttk.Frame(file_frame)
        f3.pack(fill="x", pady=2)
        ttk.Label(f3, text="已使用日志:", width=10).pack(side="left", padx=5)
        self.ent_used_log_path = ttk.Entry(f3)
        self.ent_used_log_path.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(f3, text="选择", width=5, command=self.browse_used_log_file).pack(side="left", padx=5)

        # 强制同步按钮
        sync_btn_f = ttk.Frame(file_frame)
        sync_btn_f.pack(fill="x", pady=5)
        ttk.Button(sync_btn_f, text="📥 强制同步：日志 -> 数据库", command=self.force_sync_text_to_db).pack(side="left", padx=10, expand=True, fill="x")
        ttk.Button(sync_btn_f, text="📤 强制同步：数据库 -> 未使用文件", command=self.force_sync_db_to_text).pack(side="left", padx=10, expand=True, fill="x")

        # 3. 中间主体 (使用 Grid 布局实现四列)
        mid_frame = ttk.Frame(self.root)
        mid_frame.pack(fill="x", padx=10, pady=5)

        # --- 第一列：核心设置 & 上限控制 ---
        col1 = ttk.Frame(mid_frame)
        col1.grid(row=0, column=0, sticky="nw", padx=5)
        
        limit_box = ttk.LabelFrame(col1, text="注册 & CDK 上限")
        limit_box.pack(fill="x", pady=5)
        
        # QQ 注册上限
        l_f1 = ttk.Frame(limit_box)
        l_f1.pack(fill="x", padx=5, pady=2)
        ttk.Label(l_f1, text="QQ注册上限:").pack(side="left")
        self.spin_limit = tk.Spinbox(l_f1, from_=1, to=100, width=5)
        self.spin_limit.pack(side="left", padx=5)
        
        # CDK 购买上限
        l_f2 = ttk.Frame(limit_box)
        l_f2.pack(fill="x", padx=5, pady=2)
        ttk.Label(l_f2, text="CDK购上限:").pack(side="left")
        self.spin_cdk_limit = tk.Spinbox(l_f2, from_=1, to=100, width=5)
        self.spin_cdk_limit.pack(side="left", padx=5)
        
        # 群 CDK 总容量
        l_f3 = ttk.Frame(limit_box)
        l_f3.pack(fill="x", padx=5, pady=2)
        ttk.Label(l_f3, text="群CDK容量:").pack(side="left")
        self.spin_group_cdk_limit = tk.Spinbox(l_f3, from_=1, to=1000, width=5)
        self.spin_group_cdk_limit.pack(side="left", padx=5)
        
        ttk.Button(limit_box, text="更新所有上限", command=self.save_all_settings).pack(fill="x", padx=5, pady=5)
        
        ttk.Button(col1, text="🔃 刷新文本数据", command=self.load_data).pack(fill="x", pady=5)

        # --- 第二列：群管理开关 ---
        col2 = ttk.Frame(mid_frame)
        col2.grid(row=0, column=1, sticky="nw", padx=5)
        
        grp_f = ttk.LabelFrame(col2, text="群管理功能开关")
        grp_f.pack(fill="x", pady=5)
        
        self.var_manage = tk.BooleanVar(value=False)
        self.var_checkin = tk.BooleanVar(value=False)
        self.var_patrol = tk.BooleanVar(value=False)
        self.var_auto_join = tk.BooleanVar(value=False)
        self.var_auto_friend = tk.BooleanVar(value=False)
        self.var_decoder = tk.BooleanVar(value=False)
        self.var_group_bind = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(grp_f, text="开启群管理", variable=self.var_manage, command=self.update_bot_flags).pack(anchor="w", padx=5)
        ttk.Checkbutton(grp_f, text="开启群签到", variable=self.var_checkin, command=self.update_bot_flags).pack(anchor="w", padx=5)
        ttk.Checkbutton(grp_f, text="巡逻(自动踢黑)", variable=self.var_patrol, command=self.update_bot_flags).pack(anchor="w", padx=5)
        ttk.Checkbutton(grp_f, text="自动进群", variable=self.var_auto_join, command=self.update_bot_flags).pack(anchor="w", padx=5)
        ttk.Checkbutton(grp_f, text="自动同意好友", variable=self.var_auto_friend, command=self.update_bot_flags).pack(anchor="w", padx=5)
        
        # 解码/绑定
        dec_f = ttk.Frame(grp_f)
        dec_f.pack(fill="x", padx=5, pady=2)
        ttk.Checkbutton(dec_f, text="解码", variable=self.var_decoder, command=self.update_bot_flags).pack(side="left")
        self.ent_decoder_group = ttk.Entry(dec_f, width=10)
        self.ent_decoder_group.pack(side="left", padx=2)
        
        bnd_f = ttk.Frame(grp_f)
        bnd_f.pack(fill="x", padx=5, pady=2)
        ttk.Checkbutton(bnd_f, text="绑定", variable=self.var_group_bind, command=self.update_bot_flags).pack(side="left")
        self.ent_bind_group = ttk.Entry(bnd_f, width=10)
        self.ent_bind_group.pack(side="left", padx=2)

        # --- 第三列：撤回设置 ---
        col3 = ttk.Frame(mid_frame)
        col3.grid(row=0, column=2, sticky="nw", padx=5)
        
        recall_f = ttk.LabelFrame(col3, text="撤回设置")
        recall_f.pack(fill="x", pady=5)
        
        self.var_auto_recall = tk.BooleanVar(value=False)
        self.var_recall_delay = tk.IntVar(value=3)
        self.recall_cmds_vars = {}
        
        rc_top = ttk.Frame(recall_f)
        rc_top.pack(fill="x", padx=5, pady=2)
        ttk.Checkbutton(rc_top, text="自动撤回", variable=self.var_auto_recall, command=self.update_bot_flags).pack(side="left")
        self.spin_recall_delay = tk.Spinbox(rc_top, from_=1, to=60, width=3, textvariable=self.var_recall_delay, command=self.update_bot_flags)
        self.spin_recall_delay.pack(side="left", padx=2)
        ttk.Label(rc_top, text="秒").pack(side="left")

        # 指令选择
        self.recall_cmds_frame = ttk.Frame(recall_f)
        self.recall_cmds_frame.pack(fill="x", padx=5, pady=2)
        commands = [
            ("menu", "菜单"), ("checkin", "签到"), ("points", "积分"),
            ("buy_cdk", "购CDK"), ("list_my_cdk", "我的CDK"), ("list_zones", "区表"),
            ("list_my_accounts", "我的号"), ("group_bind", "群绑"), ("decoder", "解码"),
            ("admin", "管理"), ("patrol", "巡逻")
        ]
        for i, (cid, cname) in enumerate(commands):
            var = tk.BooleanVar(value=True)
            self.recall_cmds_vars[cid] = var
            ttk.Checkbutton(self.recall_cmds_frame, text=cname, variable=var, command=self.update_bot_flags).grid(row=i//2, column=i%2, sticky="w")

        # --- 第四列：区服列表 ---
        col4 = ttk.Frame(mid_frame)
        col4.grid(row=0, column=3, sticky="nw", padx=5)
        
        zone_f = ttk.LabelFrame(col4, text="区服管理")
        zone_f.pack(fill="both", expand=True, pady=5)
        
        self.list_zones = tk.Listbox(zone_f, width=18, height=12)
        self.list_zones.pack(fill="both", expand=True, padx=5, pady=2)
        
        self.ent_new_zone = ttk.Entry(zone_f, width=15)
        self.ent_new_zone.pack(fill="x", padx=5, pady=2)
        
        btn_f = ttk.Frame(zone_f)
        btn_f.pack(fill="x", pady=2)
        ttk.Button(btn_f, text="添加", width=6, command=self.add_zone).pack(side="left", padx=2)
        ttk.Button(btn_f, text="删除", width=6, command=self.del_zone).pack(side="left", padx=2)
        ttk.Button(zone_f, text="清理失效注册", command=self.cleanup_records).pack(fill="x", padx=5, pady=2)

        # --- 第五列：版本植入功能 ---
        col5 = ttk.Frame(mid_frame)
        col5.grid(row=0, column=4, sticky="nw", padx=5)
        
        implant_f = ttk.LabelFrame(col5, text="版本植入功能")
        implant_f.pack(fill="both", expand=True, pady=5)
        
        # 状态列表
        self.lbl_implant_items = {}
        items = [("QFunction", "QF.txt"), ("QManage", "QM.txt"), ("NPC", "老登.txt"), ("功能", "老登功能")]
        for name, fname in items:
            lbl = tk.Label(implant_f, text=name, width=15, fg="white", bg="grey")
            lbl.pack(fill="x", padx=5, pady=2)
            self.lbl_implant_items[name] = (lbl, fname)
            
        ttk.Button(implant_f, text="重新读取", command=self.check_implant_files).pack(fill="x", padx=5, pady=5)
        
        # 目录选择
        dir_f = ttk.Frame(implant_f)
        dir_f.pack(fill="x", padx=5, pady=5)
        ttk.Label(dir_f, text="版本根目录:").pack(anchor="w")
        self.ent_version_dir = ttk.Entry(dir_f, width=18)
        self.ent_version_dir.pack(fill="x", side="left", expand=True)
        ttk.Button(dir_f, text="..", width=3, command=self.browse_version_dir).pack(side="left", padx=2)
        
        self.lbl_game_name = ttk.Label(implant_f, text="游戏名称: 未知", foreground="blue")
        self.lbl_game_name.pack(anchor="w", padx=5)
        
        self.btn_write_implant = ttk.Button(implant_f, text="写入功能", state="disabled")
        self.btn_write_implant.pack(fill="x", padx=5, pady=5)

        # 4. 底部：日志
        log_frame = ttk.LabelFrame(self.root, text="运行日志")
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.txt_log = scrolledtext.ScrolledText(log_frame, height=10, state="disabled", font=("Consolas", 9))
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
            self.load_game_name_from_ini(directory)
            self.save_all_settings()

    def load_game_name_from_ini(self, directory):
        ini_path = os.path.join(directory, "Config.ini")
        if os.path.exists(ini_path):
            try:
                cp = configparser.ConfigParser()
                # 尝试用 GBK 读取
                try:
                    cp.read(ini_path, encoding="gbk")
                except:
                    cp.read(ini_path, encoding="utf-8")
                
                name = cp.get("GameConf", "GameName", fallback="未知")
                self.lbl_game_name.config(text=f"游戏名称: {name}")
            except Exception as e:
                self.lbl_game_name.config(text="游戏名称: 读取失败")
                self.log(f"⚠️ 读取 Config.ini 异常: {e}")
        else:
            self.lbl_game_name.config(text="游戏名称: 找不到 Config.ini")

    def check_implant_files(self):
        """检查 Mir2Text 目录下的文件是否存在并更新 UI 颜色"""
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        mir_path = os.path.join(base_dir, "Mir2Text")
        
        for name, (lbl, fname) in self.lbl_implant_items.items():
            f_path = os.path.join(mir_path, fname)
            exists = False
            if name == "功能": # 检查子目录
                exists = os.path.isdir(f_path)
            else:
                exists = os.path.exists(f_path)
            
            if exists:
                lbl.config(bg="green")
            else:
                lbl.config(bg="red")