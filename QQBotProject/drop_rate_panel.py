import os
import sys
import threading
import time
import socket
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import re

from drop_rate_manager import GameDataManager
from drop_rate_web import app, set_global_db_manager


class DropRatePanel(ttk.Frame):
    """爆率查询嵌入式面板，可放入 Notebook 标签页"""

    def __init__(self, parent):
        super().__init__(parent)
        self.server_root_dir = ""
        self.port = 8080
        self.db_manager = None
        self.server_thread = None
        self.server_running = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self.setup_ui()

    def setup_ui(self):
        # ===== 上方配置区 =====
        config_frame = ttk.LabelFrame(self, text="服务端配置")
        config_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))
        config_frame.columnconfigure(1, weight=1)

        # 根目录选择
        ttk.Label(config_frame, text="服务端根目录:", font=("", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=6, pady=(6, 2))
        self.dir_var = tk.StringVar()
        dir_entry = ttk.Entry(config_frame, textvariable=self.dir_var, font=("Consolas", 9))
        dir_entry.grid(row=0, column=1, sticky="ew", padx=(4, 2), pady=(6, 2))
        ttk.Button(config_frame, text="浏览", width=6, command=self.browse_dir).grid(
            row=0, column=2, padx=(0, 6), pady=(6, 2))

        # 服务端名称
        ttk.Label(config_frame, text="服务端名称:", font=("", 9, "bold")).grid(
            row=1, column=0, sticky="w", padx=6, pady=2)
        self.lbl_server_name = ttk.Label(config_frame, text="请先选择目录",
                                          foreground="#0078d4", font=("", 9, "bold"))
        self.lbl_server_name.grid(row=1, column=1, sticky="w", padx=4, pady=2)

        # 端口号
        ttk.Label(config_frame, text="端口号:", font=("", 9, "bold")).grid(
            row=2, column=0, sticky="w", padx=6, pady=2)
        self.port_var = tk.StringVar(value="8080")
        port_entry = ttk.Entry(config_frame, textvariable=self.port_var, width=10,
                                font=("Consolas", 9))
        port_entry.grid(row=2, column=1, sticky="w", padx=4, pady=2)

        # 按钮行
        btn_frame = ttk.Frame(config_frame)
        btn_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=6, pady=(4, 6))

        self.btn_init = ttk.Button(btn_frame, text="初始化数据",
                                    command=self.initialize_data)
        self.btn_init.pack(side="left", padx=2)

        self.btn_start = ttk.Button(btn_frame, text="启动服务器",
                                     command=self.start_server, state="disabled")
        self.btn_start.pack(side="left", padx=2)

        self.btn_stop = ttk.Button(btn_frame, text="停止服务器",
                                    command=self.stop_server, state="disabled")
        self.btn_stop.pack(side="left", padx=2)

        self.btn_browser = ttk.Button(btn_frame, text="打开浏览器",
                                       command=self.open_browser, state="disabled")
        self.btn_browser.pack(side="left", padx=2)

        # ===== 典狱长封挂插件广告横幅 =====
        ad_frame = tk.Frame(self, bg="#101820", cursor="hand2", height=42)
        ad_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        ad_frame.grid_propagate(False)
        ad_frame.bind("<Button-1>", lambda e: self.open_dyz_website())

        ad_icon = tk.Label(ad_frame, text="\u2694", bg="#101820", fg="#f2c94c",
                           font=("", 16), cursor="hand2")
        ad_icon.pack(side="left", padx=(12, 4))
        ad_icon.bind("<Button-1>", lambda e: self.open_dyz_website())

        ad_text = tk.Label(ad_frame,
                           text="典狱长封挂插件 \u2014 让外挂无处遁形，还游戏一片净土",
                           bg="#101820", fg="#e8e8e8",
                           font=("Microsoft YaHei UI", 10, "bold"),
                           cursor="hand2")
        ad_text.pack(side="left", padx=4)
        ad_text.bind("<Button-1>", lambda e: self.open_dyz_website())

        ad_link = tk.Label(ad_frame, text="访问官网 dyzplugin.win \u2192",
                           bg="#101820", fg="#8fd3ff",
                           font=("Microsoft YaHei UI", 9, "underline"),
                           cursor="hand2")
        ad_link.pack(side="right", padx=12)
        ad_link.bind("<Button-1>", lambda e: self.open_dyz_website())

        # ===== 下方日志区 =====
        log_frame = ttk.LabelFrame(self, text="运行日志")
        log_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, state="disabled",
            font=("Consolas", 10),
            bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white", wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=6, pady=4)

    def log(self, message):
        """线程安全地写入日志"""
        def _write():
            self.log_text.config(state="normal")
            self.log_text.insert("end",
                f"[{time.strftime('%H:%M:%S')}] {message}\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        try:
            self.winfo_toplevel().after(0, _write)
        except:
            pass

    def browse_dir(self):
        """选择服务端根目录"""
        directory = filedialog.askdirectory(title="选择传奇服务端根目录")
        if directory:
            self.dir_var.set(directory)
            self.server_root_dir = directory
            self.log(f"选择目录: {directory}")

            # 立即读取服务端名称
            config_file = os.path.join(directory, "Config.ini")
            if os.path.exists(config_file):
                try:
                    name = self._read_server_name(config_file)
                    self.lbl_server_name.config(text=name)
                    self.log(f"读取到服务端名称: {name}")
                except Exception as e:
                    self.lbl_server_name.config(text="读取失败")
                    self.log(f"读取服务端名称失败: {e}")
            else:
                self.lbl_server_name.config(text="未找到 Config.ini")
                self.log("未找到 Config.ini 文件")

    def _read_server_name(self, config_file):
        """从 Config.ini 读取游戏名称"""
        encodings = ['gbk', 'utf-8']
        content = None
        for enc in encodings:
            try:
                with open(config_file, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        if content is None:
            return "DefaultServer"
        match = re.search(r'GameName=([^\r\n]+)', content)
        return match.group(1).strip() if match else "DefaultServer"

    def initialize_data(self):
        """初始化爆率数据"""
        if not self.dir_var.get().strip():
            self.log("请先选择服务端根目录")
            return

        self.server_root_dir = self.dir_var.get().strip()
        try:
            self.port = int(self.port_var.get().strip())
            if self.port < 1 or self.port > 65535:
                raise ValueError("端口超出范围")
        except ValueError as e:
            self.log(f"端口号无效: {e}")
            return

        self.btn_init.config(state="disabled")
        self.log("开始初始化数据...")

        def _init_thread():
            try:
                self.db_manager = GameDataManager(self.server_root_dir, self.port)

                # 检查端口是否可用
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.bind(('localhost', self.port))
                        s.close()
                    self.log(f"端口 {self.port} 可用")
                except OSError:
                    self.log(f"端口 {self.port} 仍被占用，请先停止已运行的服务器")
                    self._enable_init_btn()
                    return

                # 初始化数据
                success, message = self.db_manager.initialize_data()
                if success:
                    self.log("数据初始化成功")
                    for line in message.split('\n'):
                        if line.strip():
                            self.log(f"  {line.strip()}")
                    self.btn_start.config(state="normal")
                else:
                    self.log(f"数据初始化失败: {message}")

            except Exception as e:
                self.log(f"初始化异常: {e}")
            finally:
                self._enable_init_btn()

        threading.Thread(target=_init_thread, daemon=True).start()

    def _enable_init_btn(self):
        """重新启用初始化按钮（线程安全）"""
        try:
            self.winfo_toplevel().after(0, lambda: self.btn_init.config(state="normal"))
        except:
            pass

    def start_server(self):
        """启动 Flask Web 服务器"""
        if not self.db_manager:
            self.log("请先初始化数据")
            return
        if self.server_running:
            self.log("服务器已在运行中")
            return

        try:
            new_port = int(self.port_var.get().strip())
            if new_port < 1 or new_port > 65535:
                raise ValueError("端口超出范围")
            self.port = new_port
        except ValueError as e:
            self.log(f"端口号无效: {e}")
            return

        # 检查端口是否可用
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', self.port))
                s.close()
        except OSError:
            self.log(f"端口 {self.port} 仍被占用，无法启动")
            return

        self.server_running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.btn_browser.config(state="normal")

        set_global_db_manager(self.db_manager)

        local_ip = self.db_manager.get_local_ip()
        self.log(f"Web 服务器启动于端口 {self.port}")
        self.log(f"浏览器访问: http://{local_ip}:{self.port}")

        def _run_flask():
            try:
                app.run(host='0.0.0.0', port=self.port, debug=False, threaded=True)
            except Exception as e:
                self.log(f"服务器停止: {e}")
                self.server_running = False
                try:
                    self.winfo_toplevel().after(0, lambda: (
                        self.btn_start.config(state="normal"),
                        self.btn_stop.config(state="disabled"),
                        self.btn_browser.config(state="disabled")
                    ))
                except:
                    pass

        self.server_thread = threading.Thread(target=_run_flask, daemon=True)
        self.server_thread.start()

    def stop_server(self):
        """停止 Web 服务器"""
        if not self.server_running:
            return
        self.server_running = False
        self.btn_stop.config(state="disabled")
        self.btn_start.config(state="normal")
        self.btn_browser.config(state="disabled")

        self.log("正在停止服务器...")
        # 通过 HTTP 请求优雅关闭 Flask 服务器
        import urllib.request
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/shutdown")
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass  # 服务器关闭时连接断开，异常正常

        # 等待端口完全释放（最多 3 秒）
        for _ in range(15):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', self.port))
                    s.close()
                self.log("端口已释放")
                break
            except OSError:
                time.sleep(0.2)
        else:
            self.log("等待端口释放超时，请稍后重试")

        self.log("服务器已停止")

    def open_browser(self):
        """在浏览器中打开查询页面"""
        if not self.server_running:
            self.log("服务器未运行")
            return
        try:
            local_ip = self.db_manager.get_local_ip() if self.db_manager else "127.0.0.1"
            url = f"http://{local_ip}:{self.port}"
            webbrowser.open(url, new=2)
            self.log(f"已打开浏览器: {url}")
        except Exception as e:
            self.log(f"打开浏览器失败: {e}")

    def open_dyz_website(self):
        """打开典狱长封挂插件官网"""
        try:
            webbrowser.open("https://dyzplugin.win/", new=2)
        except Exception as e:
            self.log(f"打开官网失败: {e}")
