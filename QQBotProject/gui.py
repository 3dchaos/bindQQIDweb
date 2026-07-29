import os
import sys
import threading
import asyncio
import subprocess
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import dataset
import shutil
import re
from data_manager import read_file_data, write_file_data
from bot_core import BotWorker
from config import DB_URL, DEFAULT_WS_URL, DEFAULT_BIND_FILE
import script_implant
from drop_rate_panel import DropRatePanel
from mon_gen_panel import MonGenPanel
from map_editor_panel import MapEditorPanel
from server_monitor_panel import ServerMonitorPanel

# 典狱长官网地址
OFFICIAL_SITE_URL = "https://dyznb.com/"

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("典狱长群服管理中心 v1.2")
        self.root.geometry("1180x800")
        self.root.minsize(1080, 680)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        # 启用 tkdnd 拖拽支持（给 MonGen 编辑器用）
        try:
            self.root.tk.call("package", "require", "tkdnd")
        except Exception:
            pass

        self.worker = None
        self.script_vars_entries = {} # 存储变量名和对应的 Entry
        self.setup_ui()
        self.load_config_from_db()
        self.load_data()
        self.check_implant_files() # 初始检测一次
        self.root.after(800, self.open_official_site)

    def setup_ui(self):
        # 配置分页样式 - 加粗标签、明显描边
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#1a1a1a", borderwidth=4, relief="solid")
        style.configure("TNotebook.Tab",
                        background="#3a3a3a",
                        foreground="#dddddd",
                        padding=[30, 10],
                        borderwidth=3,
                        relief="raised",
                        font=("Microsoft YaHei UI", 12, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", "#0078d4"), ("active", "#555555")],
                  foreground=[("selected", "#ffffff"), ("active", "#ffffff")],
                  relief=[("selected", "sunken")])
        # 创建主分页控件
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=4)

        # ===== Tab 1: QQ Robot - 机器人控制面板 =====
        self.tab_bot = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_bot, text="QQ机器人")

        # --- Top toolbar: Connection + Sync Dirs ---
        top_container = ttk.Frame(self.tab_bot)
        top_container.pack(fill="x", padx=8, pady=6)

        # Left: LLOneBot connection
        top_left = ttk.LabelFrame(top_container, text="LLOneBot 连接设置")
        top_left.pack(side="left", fill="both", expand=True, padx=(0, 4))
        fl = ttk.Frame(top_left)
        fl.pack(fill="x", padx=6, pady=4)
        ttk.Label(fl, text="WS:", font=("", 9, "bold")).pack(side="left", padx=2)
        self.ent_url = ttk.Entry(fl, width=32)
        self.ent_url.pack(side="left", fill="x", expand=True, padx=2)
        ttk.Label(fl, text="Token:", font=("", 9, "bold")).pack(side="left", padx=2)
        self.ent_token = ttk.Entry(fl, width=12)
        self.ent_token.pack(side="left", padx=2)
        self.btn_start = ttk.Button(fl, text="▶ 启动", width=7, command=self.start_bot)
        self.btn_start.pack(side="left", padx=2)
        self.btn_stop = ttk.Button(fl, text="■ 停止", width=7, state="disabled", command=self.stop_bot)
        self.btn_stop.pack(side="left", padx=2)

        # Right: Sync directories
        top_right = ttk.LabelFrame(top_container, text="同步目录设置")
        top_right.pack(side="left", fill="both", expand=True, padx=(4, 0))
        fr = ttk.Frame(top_right)
        fr.pack(fill="x", padx=6, pady=2)
        ttk.Label(fr, text="注册:", width=6, font=("", 9, "bold")).pack(side="left")
        self.ent_file_path = ttk.Entry(fr)
        self.ent_file_path.pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(fr, text="浏览", width=5, command=self.browse_file).pack(side="left")

        fr2 = ttk.Frame(top_right)
        fr2.pack(fill="x", padx=6, pady=2)
        ttk.Label(fr2, text="未使用:", width=6, font=("", 9, "bold")).pack(side="left")
        self.ent_unused_path = ttk.Entry(fr2)
        self.ent_unused_path.pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(fr2, text="浏览", width=5, command=self.browse_unused_file).pack(side="left")
        ttk.Label(fr2, text="已使用:", width=6, font=("", 9, "bold")).pack(side="left", padx=(8, 0))
        self.ent_used_log_path = ttk.Entry(fr2)
        self.ent_used_log_path.pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(fr2, text="浏览", width=5, command=self.browse_used_log_file).pack(side="left")

        sync_btn_f = ttk.Frame(top_right)
        sync_btn_f.pack(fill="x", padx=6, pady=2)
        ttk.Button(sync_btn_f, text="☁ 日志->DB", command=self.force_sync_text_to_db).pack(side="left", padx=2, expand=True, fill="x")
        ttk.Button(sync_btn_f, text="☁ DB->未使用", command=self.force_sync_db_to_text).pack(side="left", padx=2, expand=True, fill="x")
        # --- Ad banner ---
        ad_frame = tk.Frame(self.tab_bot, bg="#101820", cursor="hand2", height=56)
        ad_frame.pack(fill="x", padx=8, pady=(0, 6))
        ad_frame.pack_propagate(False)
        ad_frame.bind("<Button-1>", lambda event: self.open_official_site())

        ad_title = tk.Label(ad_frame, text="⚔ 典狱长软件监控网关", bg="#101820", fg="#f2c94c", font=("Microsoft YaHei UI", 13, "bold"), cursor="hand2")
        ad_title.pack(side="left", padx=(16, 8))
        ad_title.bind("<Button-1>", lambda event: self.open_official_site())

        ad_text = tk.Label(ad_frame, text="让流氓软件无处逍形 · 守护程序安全", bg="#101820", fg="#f0f0f0", font=("Microsoft YaHei UI", 10), cursor="hand2")
        ad_text.pack(side="left")
        ad_text.bind("<Button-1>", lambda event: self.open_official_site())

        ad_link = tk.Label(ad_frame, text="访问官网 dyznb.com →", bg="#101820", fg="#8fd3ff", font=("Microsoft YaHei UI", 10, "underline"), cursor="hand2")
        ad_link.pack(side="right", padx=16)
        ad_link.bind("<Button-1>", lambda event: self.open_official_site())

        # --- Main body: split into left (controls) and right (zone mgmt) ---
        body_frame = ttk.Frame(self.tab_bot)
        body_frame.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        body_frame.columnconfigure(0, weight=3)
        body_frame.columnconfigure(1, weight=2)
        body_frame.rowconfigure(0, weight=1)

        # ===== Left panel =====
        left_panel = ttk.Frame(body_frame)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        left_panel.rowconfigure(1, weight=1)

        # Row 0: Limits + Switches + Recall (horizontal)
        row1 = ttk.Frame(left_panel)
        row1.pack(fill="x", pady=(0, 6))

        # --- Limits ---
        limit_f = ttk.LabelFrame(row1, text="上限控制")
        limit_f.pack(side="left", fill="y", padx=(0, 3))
        for text, spin_attr, val_range in [
            ("QQ注册上限:", "spin_limit", (1, 100)),
            ("CDK购买上限:", "spin_cdk_limit", (1, 100)),
            ("群CDK容量:", "spin_group_cdk_limit", (1, 1000))
        ]:
            f = ttk.Frame(limit_f)
            f.pack(fill="x", padx=6, pady=2)
            ttk.Label(f, text=text, font=("", 9)).pack(side="left")
            setattr(self, spin_attr, tk.Spinbox(f, from_=val_range[0], to=val_range[1], width=6, font=("Consolas", 9)))
            getattr(self, spin_attr).pack(side="right", padx=2)
        ttk.Button(limit_f, text="💾 保存上限", command=self.save_all_settings).pack(fill="x", padx=6, pady=4)

        # --- Group switches ---
        grp_f = ttk.LabelFrame(row1, text="群功能开关")
        grp_f.pack(side="left", fill="y", padx=3)
        switches = [
            ("群管理", "var_manage"),
            ("群签到", "var_checkin"),
            ("巡逻(自动踢黑)", "var_patrol"),
            ("自动进群", "var_auto_join"),
            ("自动同意好友", "var_auto_friend")
        ]
        for text, var_attr in switches:
            setattr(self, var_attr, tk.BooleanVar(value=False))
            ttk.Checkbutton(grp_f, text=text, variable=getattr(self, var_attr), command=self.update_bot_flags).pack(anchor="w", padx=6, pady=1)

        # Decoder/Bind row
        for text, var_attr, ent_attr in [("解码", "var_decoder", "ent_decoder_group"), ("绑定", "var_group_bind", "ent_bind_group")]:
            setattr(self, var_attr, tk.BooleanVar(value=False))
            f = ttk.Frame(grp_f)
            f.pack(fill="x", padx=6, pady=1)
            ttk.Checkbutton(f, text=text, variable=getattr(self, var_attr), command=self.update_bot_flags).pack(side="left")
            setattr(self, ent_attr, ttk.Entry(f, width=12))
            getattr(self, ent_attr).pack(side="right", padx=2)

        # --- Recall settings ---
        recall_f = ttk.LabelFrame(row1, text="撤回设置")
        recall_f.pack(side="left", fill="y", padx=(3, 0))
        self.var_auto_recall = tk.BooleanVar(value=False)
        self.var_recall_delay = tk.IntVar(value=3)
        self.recall_cmds_vars = {}
        rc_top = ttk.Frame(recall_f)
        rc_top.pack(fill="x", padx=6, pady=2)
        ttk.Checkbutton(rc_top, text="自动撤回", variable=self.var_auto_recall, command=self.update_bot_flags).pack(side="left")
        ttk.Label(rc_top, text="延迟").pack(side="left", padx=(8, 2))
        tk.Spinbox(rc_top, from_=1, to=60, width=4, textvariable=self.var_recall_delay, command=self.update_bot_flags).pack(side="left")
        ttk.Label(rc_top, text="秒").pack(side="left")
        self.recall_cmds_frame = ttk.Frame(recall_f)
        self.recall_cmds_frame.pack(fill="x", padx=6, pady=2)
        commands = [
            ("menu", "菜单"), ("checkin", "签到"), ("points", "积分"),
            ("buy_cdk", "购CDK"), ("list_my_cdk", "我的CDK"), ("list_zones", "区表"),
            ("list_my_accounts", "我的号")
        ]
        for i, (cid, cname) in enumerate(commands):
            var = tk.BooleanVar(value=True)
            self.recall_cmds_vars[cid] = var
            ttk.Checkbutton(self.recall_cmds_frame, text=cname, variable=var, command=self.update_bot_flags).grid(row=i//4, column=i%4, sticky="w", padx=2)

        # ===== Right panel: Zone management =====
        right_panel = ttk.LabelFrame(body_frame, text="区服管理")
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.rowconfigure(0, weight=1)
        right_panel.columnconfigure(0, weight=1)

        self.list_zones = tk.Listbox(right_panel, font=("Consolas", 10), selectbackground="#1a6b3c")
        self.list_zones.grid(row=0, column=0, columnspan=4, sticky="nsew", padx=6, pady=4)

        self.ent_new_zone = ttk.Entry(right_panel, font=("", 10))
        self.ent_new_zone.grid(row=1, column=0, columnspan=4, sticky="ew", padx=6, pady=2)

        btn_f = ttk.Frame(right_panel)
        btn_f.grid(row=2, column=0, columnspan=4, sticky="ew", padx=6, pady=4)
        ttk.Button(btn_f, text="➕ 添加", width=7, command=self.add_zone).pack(side="left", padx=1)
        ttk.Button(btn_f, text="➖ 删除", width=7, command=self.del_zone).pack(side="left", padx=1)
        ttk.Button(btn_f, text="🗑 扫无效", width=8, command=self.cleanup_records).pack(side="right", padx=1)
        ttk.Button(btn_f, text="🔄 刷新", width=7, command=self.load_data).pack(side="right", padx=1)

        # --- Bottom: Running log ---
        log_frame = ttk.LabelFrame(body_frame, text="运行日志")
        log_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.txt_log = scrolledtext.ScrolledText(log_frame, state="disabled", height=8, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4", insertbackground="white")
        self.txt_log.grid(row=0, column=0, sticky="nsew", padx=6, pady=4)
# ===== Tab 2: Version Management - 版本植入与安全清理 =====
        self.tab_version = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_version, text="版本管理")
        self.tab_version.columnconfigure(0, weight=1)
        self.tab_version.rowconfigure(0, weight=3)
        self.tab_version.rowconfigure(1, weight=2)

        # ===== Upper section: Version implant =====
        implant_main = ttk.LabelFrame(self.tab_version, text="版本植入")
        implant_main.grid(row=0, column=0, sticky="nsew", pady=(4, 2), padx=4)
        implant_main.columnconfigure(0, weight=0, minsize=280)
        implant_main.columnconfigure(1, weight=1)
        implant_main.rowconfigure(0, weight=1)

        # Left panel: Implant controls
        implant_left = ttk.Frame(implant_main)
        implant_left.grid(row=0, column=0, sticky="nsew", padx=(4, 2), pady=4)
        implant_left.columnconfigure(0, weight=1)

        # Template checkbox row
        tmpl_f = ttk.LabelFrame(implant_left, text="选择模板")
        tmpl_f.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.implant_vars = {}
        self.implant_checks = {}
        tmpl_row = ttk.Frame(tmpl_f)
        tmpl_row.pack(fill="x", padx=6, pady=4)
        for name, fname in [("QF闯关", "QF.txt"), ("QM命令", "QM.txt"), ("NPC对话", "典狱长.txt"), ("功能脚本", "典狱长功能")]:
            var = tk.BooleanVar(value=True)
            self.implant_vars[name] = var
            chk = tk.Checkbutton(tmpl_row, text=name, variable=var,
                                  fg="white", bg="#555555",
                                  selectcolor="#444444",
                                  font=("Microsoft YaHei UI", 9, "bold"),
                                  indicatoron=0, width=10, padx=2, pady=1)
            chk.pack(side="left", padx=2)
            self.implant_checks[name] = (chk, fname)

        # Variable refresh and list
        ttk.Button(implant_left, text="🔄 刷新变量", command=self.refresh_script_variables).grid(row=1, column=0, sticky="ew", pady=2)

        var_list_f = ttk.LabelFrame(implant_left, text="注入变量")
        var_list_f.grid(row=2, column=0, sticky="nsew", pady=2)
        var_list_f.rowconfigure(0, weight=1)
        var_list_f.columnconfigure(0, weight=1)
        self.canvas_vars = tk.Canvas(var_list_f, highlightthickness=0, bg="#2b2b2b")
        self.scrollbar_vars = ttk.Scrollbar(var_list_f, orient="vertical", command=self.canvas_vars.yview)
        self.scrollable_vars_frame = ttk.Frame(self.canvas_vars)
        self.scrollable_vars_frame.bind("<Configure>", lambda e: self.canvas_vars.configure(scrollregion=self.canvas_vars.bbox("all")))
        self.canvas_vars.create_window((0, 0), window=self.scrollable_vars_frame, anchor="nw")
        self.canvas_vars.configure(yscrollcommand=self.scrollbar_vars.set)
        self.canvas_vars.grid(row=0, column=0, sticky="nsew")
        self.scrollbar_vars.grid(row=0, column=1, sticky="ns")

        # Version directory selection
        dir_f = ttk.LabelFrame(implant_left, text="版本目录")
        dir_f.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        dir_f.columnconfigure(0, weight=1)
        self.ent_version_dir = ttk.Entry(dir_f, font=("Consolas", 9))
        self.ent_version_dir.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 2))
        ttk.Button(dir_f, text="📁 选择版本目录", command=self.browse_version_dir).grid(row=1, column=0, sticky="ew", padx=6, pady=2)
        self.lbl_game_name = ttk.Label(dir_f, text="游戏: 未知", font=("Microsoft YaHei UI", 10, "bold"), foreground="#2a7a3a")
        self.lbl_game_name.grid(row=2, column=0, sticky="w", padx=6, pady=(0, 4))
        self.btn_write_implant = ttk.Button(dir_f, text="⚡ 写入功能", state="disabled", command=self.write_implant_function)
        self.btn_write_implant.grid(row=3, column=0, sticky="ew", padx=6, pady=(0, 4))

        # Right panel: Implant running log
        log_implant_f = ttk.LabelFrame(implant_main, text="版本植入运行日志")
        log_implant_f.grid(row=0, column=1, sticky="nsew", padx=(2, 4), pady=4)
        log_implant_f.rowconfigure(0, weight=1)
        log_implant_f.columnconfigure(0, weight=1)
        self.txt_implant_log = scrolledtext.ScrolledText(log_implant_f, state="disabled",
                                                          font=("Consolas", 10),
                                                          bg="#1e1e1e", fg="#d4d4d4",
                                                          insertbackground="white")
        self.txt_implant_log.grid(row=0, column=0, sticky="nsew", padx=6, pady=4)

        # ===== Lower section: Security cleanup =====
        clean_f = ttk.LabelFrame(self.tab_version, text="安全清理")
        clean_f.grid(row=1, column=0, sticky="nsew", pady=(2, 4), padx=4)
        clean_f.columnconfigure(0, weight=1)

        clean_top = ttk.Frame(clean_f)
        clean_top.pack(fill="x", padx=8, pady=6)

        self.clean_vars = {
            "obfuscate": tk.BooleanVar(value=False),
            "suspicious": tk.BooleanVar(value=False),
            "gm_list": tk.BooleanVar(value=False),
            "custom_cmds": tk.BooleanVar(value=False),
            "trade_intercept": tk.BooleanVar(value=False)
        }
        for cid, cname in [
            ("obfuscate", "混淆GM命令"),
            ("suspicious", "嫌疑脚本清理"),
            ("gm_list", "清理GM列表"),
            ("custom_cmds", "清除自定义命令"),
            ("trade_intercept", "角色交易拦截")
        ]:
            chk = ttk.Checkbutton(clean_top, text=cname, variable=self.clean_vars[cid])
            chk.pack(side="left", padx=6)

        clean_bottom = ttk.Frame(clean_f)
        clean_bottom.pack(fill="x", padx=8, pady=(0, 6))
        self.btn_cleanup = ttk.Button(clean_bottom, text="🧹 清除后门", state="disabled",
                                      command=self.cleanup_backdoors, width=20)
        self.btn_cleanup.pack(side="left", padx=2)
        ttk.Button(clean_bottom, text="🔄 刷新变量", command=self.refresh_script_variables, width=18).pack(side="left", padx=2)

        # ===== Tab 3: 爆率查询 =====
        self.tab_drop = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_drop, text="爆率查询")
        self.drop_panel = DropRatePanel(self.tab_drop)
        self.drop_panel.pack(fill="both", expand=True)

        # ===== Tab 4: MonGen 编辑器 =====
        self.tab_mongen = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_mongen, text="MonGen刷怪编辑器")
        self.mon_gen_panel = MonGenPanel(self.tab_mongen)
        self.mon_gen_panel.pack(fill="both", expand=True)

        # ===== Tab 5: 地图属性管理 =====
        self.tab_map = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_map, text="地图属性")
        self.map_editor_panel = MapEditorPanel(self.tab_map)
        self.map_editor_panel.pack(fill="both", expand=True)

        # ===== Tab 6: 人数监控 =====
        self.tab_monitor = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_monitor, text="人数监控")
        self.monitor_panel = ServerMonitorPanel(self.tab_monitor)
        self.monitor_panel.pack(fill="both", expand=True)

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
            self.log_implant(f"保存配置异常: {e}")

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
            self.log_implant(f"系统: 配置已同步 (QQ上限: {max_b}, CDK上限: {max_cdk_b}, 群容量: {max_g_cdk})")

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

    def log_implant(self, text):
        """Write log to the version management page's running log window"""
        def _write():
            if hasattr(self, 'txt_implant_log'):
                self.txt_implant_log.config(state="normal")
                self.txt_implant_log.insert("end", text + "\n")
                self.txt_implant_log.see("end")
                self.txt_implant_log.config(state="disabled")
        self.root.after(0, _write)

    def load_data(self):
        path = self.get_current_file()
        if not os.path.exists(path):
            self.log_implant(f"提示: 文件不存在，将会在首次记录时创建: {path}")
            return
        self.list_zones.delete(0, "end")
        zones, recs = read_file_data(path)
        for z in zones: self.list_zones.insert("end", z)
        self.log_implant(f"系统: 已加载 {len(zones)} 个区服，{len(recs)} 条记录")

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
                self.log_implant(f"清理完成: 已删除 {removed_count} 条失效注册记录 (所属区服不在列表中)")
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
            name = script_implant.get_game_name(directory, self.log_implant)
            self.lbl_game_name.config(text=f"游戏名称: {name}")
            self.btn_write_implant.config(state="normal")
            self.btn_cleanup.config(state="normal")
            self.save_all_settings()

    def load_game_name_from_ini(self, directory):
        # 兼容旧逻辑，但现在主要由 browse_version_dir 调用 script_implant
        name = script_implant.get_game_name(directory, self.log_implant)
        self.lbl_game_name.config(text=f"游戏名称: {name}")

    def check_implant_files(self):
        """检查 Mir2Text 目录下的文件是否存在并更新 UI 颜色"""
        mir_path = script_implant.get_mir_path()
        items = [(name, fname) for name, (chk, fname) in self.implant_checks.items()]
        results = script_implant.check_templates(mir_path, items)

        all_ok = True
        for name, exists in results.items():
            chk, _ = self.implant_checks[name]
            if exists:
                chk.config(bg="green")
            else:
                chk.config(bg="red")
                all_ok = False
        return all_ok

    def refresh_script_variables(self):
        """扫描所有模板文件并提取变量显示在 UI 上 (去重处理)"""
        self.check_implant_files()
        mir_path = script_implant.get_mir_path()
        unified_vars = script_implant.get_unified_variables(mir_path, self.log_implant)

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

        self.log_implant(f"系统: 已提取并去重 {len(unified_vars)} 个模板变量")

    def write_implant_function(self):
        """执行脚本注入逻辑"""
        version_dir = self.ent_version_dir.get().strip()
        if not version_dir or not os.path.isdir(version_dir):
            messagebox.showerror("错误", "请先选择有效的版本目录")
            return

        selected_items = [name for name, var in self.implant_vars.items() if var.get()]
        if not selected_items:
            messagebox.showwarning("提示", "请选择至少一个要写入的功能")
            return

        if not messagebox.askyesno("确认", f"此操作将修改版本脚本文件 (已选: {', '.join(selected_items)})，确定要继续吗？"):
            return

        user_inputs = {name: ent.get().strip() for name, ent in self.script_vars_entries.items()}
        mir_path = script_implant.get_mir_path()

        if script_implant.implant_scripts(version_dir, mir_path, user_inputs, self.log_implant, selected_items):
            messagebox.showinfo("完成", "版本功能植入已完成！")
        else:
            messagebox.showerror("错误", "注入过程中发生异常，请查看日志")

    def cleanup_backdoors(self):
        """执行安全清理逻辑"""
        version_dir = self.ent_version_dir.get().strip()
        if not version_dir or not os.path.isdir(version_dir):
            messagebox.showerror("错误", "请先选择有效的版本目录")
            return

        selected_cleans = [name for name, var in self.clean_vars.items() if var.get()]
        if not selected_cleans:
            messagebox.showwarning("提示", "请选择至少一个清理项")
            return

        if not messagebox.askyesno("确认", f"确定要执行安全清理吗？(已选 {len(selected_cleans)} 项)\n\n❗ 注意：请在【关闭引擎】情况下执行，或执行完毕后【重启引擎】以生效。"):
            return

        self.log_implant(f"系统: 开始执行安全清理...")

        success_count = 0
        if self.clean_vars["obfuscate"].get():
            if script_implant.obfuscate_gm_commands(version_dir, self.log_implant):
                success_count += 1

        if self.clean_vars["suspicious"].get():
            # 特殊处理：弹出交互窗口
            suspicious_results = script_implant.scan_for_suspicious_segments(version_dir, self.log_implant)
            if suspicious_results:
                self.show_suspicious_cleanup_dialog(suspicious_results)
                success_count += 1
            else:
                self.log("✅ 嫌疑脚本扫描完成，未发现需要清理的代码段")
                success_count += 1 # 没扫到也算某种意义上的成功

        if self.clean_vars["gm_list"].get():
            if script_implant.clear_gm_list(version_dir, self.log_implant):
                success_count += 1

        if self.clean_vars["custom_cmds"].get():
            if script_implant.clear_custom_commands(version_dir, self.log_implant):
                success_count += 1

        if self.clean_vars["trade_intercept"].get():
            if script_implant.intercept_role_trade(version_dir, self.log_implant):
                success_count += 1

        self.log_implant(f"系统: 安全清理任务执行完毕，成功完成 {success_count}/{len(selected_cleans)} 项。")
        messagebox.showinfo("完成", f"安全清理任务执行完毕！\n成功完成 {success_count} 项操作。")

    def show_suspicious_cleanup_dialog(self, results):
        """显示嫌疑代码清理对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("🛡️ 嫌疑代码段落清理确认")
        dialog.geometry("900x640")
        dialog.transient(self.root)
        dialog.grab_set()

        lbl = ttk.Label(dialog, text=f"共发现 {len(results)} 处嫌疑代码段，请确认是否删除 (默认全选):", font=("", 10, "bold"))
        lbl.pack(fill="x", padx=10, pady=10)

        # 滚动区域
        container = ttk.Frame(dialog)
        container.pack(fill="both", expand=True, padx=10, pady=5)

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 列表条目
        item_vars = []
        for res in results:
            var = tk.BooleanVar(value=True)
            item_vars.append((var, res))

            frame = ttk.LabelFrame(scrollable_frame, text=f"文件: {res['rel_path']} | 行: {res.get('start_line', '?')}-{res.get('end_line', '?')} | 段落: {res['segment']}")
            frame.pack(fill="x", padx=5, pady=5)

            top_line = ttk.Frame(frame)
            top_line.pack(fill="x")
            keywords = ", ".join(res.get('keywords') or [res['keyword']])
            ttk.Checkbutton(top_line, text=f"包含关键字: {keywords}", variable=var).pack(side="left")
            ttk.Button(
                top_line,
                text="打开文本",
                command=lambda item=res: self.open_text_at_line(item.get('path'), item.get('start_line', 1)),
                width=10
            ).pack(side="right", padx=5)

            # 显示内容预览 (只看前几行)
            txt = tk.Text(frame, height=5, font=("Consolas", 9), wrap="none")
            txt.insert("1.0", res['content'])
            txt.config(state="disabled")
            txt.pack(fill="x", padx=5, pady=2)

        def do_delete():
            to_delete = [res for var, res in item_vars if var.get()]
            if not to_delete:
                dialog.destroy()
                return

            if messagebox.askyesno("确认删除", f"确定要从脚本中永久删除选中的 {len(to_delete)} 处代码吗？"):
                count = script_implant.delete_script_segments(to_delete, self.log_implant)
                messagebox.showinfo("完成", f"已成功删除 {count} 处嫌疑代码段！")
                dialog.destroy()

        btn_f = ttk.Frame(dialog)
        btn_f.pack(fill="x", pady=10)
        ttk.Button(btn_f, text="立即清理选中项", command=do_delete, width=20).pack(side="right", padx=10)
        ttk.Button(btn_f, text="取消", command=dialog.destroy, width=10).pack(side="right", padx=5)
        dialog.wait_window()

    def open_text_at_line(self, file_path, line_no=1):
        """打开文本文件，并尽量跳转到指定行。"""
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("错误", "文件不存在，无法打开")
            return

        try:
            line_no = max(1, int(line_no or 1))
        except (TypeError, ValueError):
            line_no = 1

        editors = []
        code_cmd = shutil.which("code") or shutil.which("code.cmd")
        if code_cmd:
            editors.append([code_cmd, "-g", f"{file_path}:{line_no}"])

        notepadpp_cmd = shutil.which("notepad++") or shutil.which("notepad++.exe")
        common_notepadpp_paths = [
            r"C:\Program Files\Notepad++\notepad++.exe",
            r"C:\Program Files (x86)\Notepad++\notepad++.exe"
        ]
        if not notepadpp_cmd:
            notepadpp_cmd = next((path for path in common_notepadpp_paths if os.path.exists(path)), None)
        if notepadpp_cmd:
            editors.append([notepadpp_cmd, f"-n{line_no}", file_path])

        subl_cmd = shutil.which("subl") or shutil.which("sublime_text")
        if subl_cmd:
            editors.append([subl_cmd, f"{file_path}:{line_no}"])

        for command in editors:
            try:
                subprocess.Popen(command)
                self.log_implant(f"已打开文本: {file_path} (行 {line_no})")
                return
            except Exception as e:
                self.log_implant(f"打开编辑器失败，尝试下一个: {e}")

        try:
            os.startfile(file_path)
            self.log_implant(f"已用默认程序打开文本: {file_path}。当前默认编辑器不支持自动跳转到第 {line_no} 行。")
        except Exception as e:
            messagebox.showerror("错误", f"打开文本失败: {e}")

    def open_official_site(self):
        """打开典狱长官网。"""
        try:
            webbrowser.open(OFFICIAL_SITE_URL, new=2)
        except Exception as e:
            self.log_implant(f"打开官网失败: {e}")

    def on_close(self):
        """关闭程序前打开官网。"""
        self.open_official_site()
        if self.worker:
            self.worker.running = False
            if self.worker.loop:
                self.worker.loop.call_soon_threadsafe(self.worker.loop.stop)
        self.root.destroy()
