import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.scrolledtext as scrolledtext
import threading
import time
import re
import os
import pymem
import psutil
import webbrowser
import http.server
import socketserver
import urllib.request
import json

class ServerMonitorPanel(ttk.Frame):
    def __init__(self, parent):
        ttk.Frame.__init__(self, parent)
        
        # === 新增：绑定窗口关闭事件（点击右上角X时触发）===
        self.is_monitoring = False
        self.monitor_thread = None
        
        # 缓存数据
        self.file_list = []      
        self.process_dict = {}   
        
        # === HTTP文件托管服务 ===
        self.external_ip = "获取中..."
        self.http_port = "5454"
        self.http_server = None
        self.http_server_thread = None
        self.http_file_map = {}
        self.http_handler_class = None
        # 启动后自动获取外网IP
        self.after(200, self.fetch_external_ip)
        
        self.bind('<<IPFetched>>', lambda e: self._update_ip_display())
        self.bind('<<TreeUpdate>>', self._flush_tree_updates)
        self.bind('<<Log>>', self._flush_log)
        self._pending_tree_updates = []
        self._pending_log_msgs = []
        # === 线程安全：用 event_generate 把后台任务派回主线程 ===
        
        self.last_file_contents = {}
        # === 新增：用于记录上一次写入的内容，避免重复写入引起文件冲突 ===
        self.setup_ui()
        self.refresh_processes()


    def on_closing(self):
        """程序关闭时打开网站并退出"""
        pass  # embedded panel    

    def setup_ui(self):
        # ================= 顶部：全局列表控制区 =================
        frame_setup = tk.LabelFrame(self, text="列表全局设置 (同步修改 [Setup])", padx=10, pady=5)
        frame_setup.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(frame_setup, text="自动刷新:").pack(side=tk.LEFT, padx=5)
        self.cb_auto_refresh = ttk.Combobox(frame_setup, values=["0 (关闭)", "1 (开启)"], width=10, state="readonly")
        self.cb_auto_refresh.current(1)  
        self.cb_auto_refresh.pack(side=tk.LEFT, padx=5)
        
        tk.Label(frame_setup, text="刷新速度(秒):").pack(side=tk.LEFT, padx=5)
        self.entry_refresh_speed = tk.Entry(frame_setup, width=10)
        self.entry_refresh_speed.insert(0, "3") 
        self.entry_refresh_speed.pack(side=tk.LEFT, padx=5)
        
        tk.Label(frame_setup, text="* 启动监控后，软件会自动将此设置写入所有监控中的列表文件", fg="gray").pack(side=tk.LEFT, padx=20)

        # ================= HTTP外部访问区 =================
        frame_http = tk.LabelFrame(self, text="HTTP外部访问 (托管列表文件)", padx=10, pady=5)
        frame_http.pack(fill=tk.X, padx=10, pady=5)
        
        row_http = tk.Frame(frame_http)
        row_http.pack(fill=tk.X, pady=2)
        self.entry_ip = tk.Entry(row_http, width=22)
        self.entry_ip.pack(side=tk.LEFT, padx=5)
        tk.Button(row_http, text="🔄 刷新IP", command=self.fetch_external_ip).pack(side=tk.LEFT, padx=2)
        tk.Label(row_http, text="端口:").pack(side=tk.LEFT, padx=5)
        self.entry_http_port = tk.Entry(row_http, width=8)
        self.entry_http_port.insert(0, self.http_port)
        self.entry_http_port.pack(side=tk.LEFT, padx=5)

        tk.Label(row_http, text="* 启动监控后自动开启HTTP托管服务", fg="gray").pack(side=tk.LEFT, padx=5)
        
        # URL列表显示
        self.frame_urls = tk.Frame(frame_http)
        self.frame_urls.pack(fill=tk.X, pady=(0, 2))
        self.frame_urls_inner = tk.Frame(self.frame_urls)
        self.frame_urls_inner.pack(fill=tk.X, padx=20)
        self.lbl_url_placeholder = tk.Label(self.frame_urls_inner, text="(暂无文件，请先添加监控规则)", fg="gray", anchor='w')
        self.lbl_url_placeholder.pack(fill=tk.X)

        # ================= 添加监控规则区 =================
        frame_config = tk.LabelFrame(self, text="添加监控规则", padx=10, pady=10)
        frame_config.pack(fill=tk.X, padx=10, pady=5)
        
        # 第一行：列表文件选择
        row1 = tk.Frame(frame_config)
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="列表文件:", width=10, anchor='e').pack(side=tk.LEFT)
        self.cb_files = ttk.Combobox(row1, width=60, state="readonly")
        self.cb_files.pack(side=tk.LEFT, padx=5)
        self.cb_files.bind('<<ComboboxSelected>>', self.on_file_selected)
        tk.Button(row1, text="✚ 添加列表文件", command=self.add_list_file).pack(side=tk.LEFT)
        
        # 第二行：服务器与进程选择
        row2 = tk.Frame(frame_config)
        row2.pack(fill=tk.X, pady=2)
        tk.Label(row2, text="服务器标题:", width=10, anchor='e').pack(side=tk.LEFT)
        self.cb_servers = ttk.Combobox(row2, width=20, state="readonly")
        self.cb_servers.pack(side=tk.LEFT, padx=5)
        
        tk.Label(row2, text="目标进程:", width=10, anchor='e').pack(side=tk.LEFT)
        self.cb_processes = ttk.Combobox(row2, width=45, state="readonly")
        self.cb_processes.pack(side=tk.LEFT, padx=5)
        tk.Button(row2, text="刷新进程", command=self.refresh_processes).pack(side=tk.LEFT)
        
        # 第三行：最高人数与添加按钮
        row3 = tk.Frame(frame_config)
        row3.pack(fill=tk.X, pady=2)
        tk.Label(row3, text="最高人数:", width=10, anchor='e').pack(side=tk.LEFT)
        self.entry_max = tk.Entry(row3, width=10)
        self.entry_max.insert(0, "100")
        self.entry_max.pack(side=tk.LEFT, padx=5)
        
        tk.Button(row3, text="添加到监控列表", command=self.add_rule, bg="#d9edf7").pack(side=tk.LEFT, padx=20)
        
        # ================= 中间：监控规则列表 =================
        frame_rules = tk.LabelFrame(self, text="当前监控列表 (一对一指定)", padx=10, pady=10)
        frame_rules.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 新增 current_p 列存放实时在线人数
        columns = ("file", "server", "process_desc", "max_p", "current_p", "pid", "pname")
        self.tree = ttk.Treeview(frame_rules, columns=columns, show="headings", height=6)
        
        self.tree.heading("file", text="列表文件")
        self.tree.heading("server", text="列表标题")
        self.tree.heading("process_desc", text="绑定的进程")
        self.tree.heading("max_p", text="最高人数")
        self.tree.heading("current_p", text="当前在线人数") # 新增列
        
        self.tree.column("file", width=180)
        self.tree.column("server", width=120)
        self.tree.column("process_desc", width=250)
        self.tree.column("max_p", width=80, anchor="center")
        self.tree.column("current_p", width=100, anchor="center") # 新增列
        
        self.tree.displaycolumns=("file", "server", "process_desc", "max_p", "current_p")
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.TOP, pady=(0, 5))
        
        # 按钮控制区 (放进单独的 frame 里对齐)
        frame_tree_btns = tk.Frame(frame_rules)
        frame_tree_btns.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Button(frame_tree_btns, text="✘ 删除选中规则", command=self.delete_rule).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_tree_btns, text="♺ 清空监控列表", command=self.clear_rules).pack(side=tk.LEFT, padx=5)
        
        # ================= 底部：状态日志区 =================
        frame_log = tk.LabelFrame(self, text="运行状态日志", padx=10, pady=5)
        frame_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.txt_log = scrolledtext.ScrolledText(frame_log, height=6, state=tk.DISABLED, bg="#f4f4f4")
        self.txt_log.pack(fill=tk.BOTH, expand=True)
        
        frame_ctrl = tk.Frame(self, pady=10)
        frame_ctrl.pack(fill=tk.X)
        self.btn_start = tk.Button(frame_ctrl, text="▶ 开始监控", command=self.toggle_monitor, bg="green", fg="white", font=("Arial", 12, "bold"), width=20)
        self.btn_start.pack()

        # === 新增：典狱长官网小广告标签 ===
        lbl_ad = tk.Label(frame_ctrl, text="典狱长官网: dyznb.com", fg="blue", cursor="hand2", font=("Arial", 9, "underline"))
        lbl_ad.pack(pady=3)
        lbl_ad.bind("<Button-1>", lambda e: webbrowser.open("http://dyznb.com"))

    # ================= 核心逻辑 =================
    
    def log(self, message):
        now = time.strftime("%H:%M:%S")
        msg = f"[{now}] {message}\n"
        self._pending_log_msgs.append(msg)
        try:
            self.event_generate('<<Log>>', when='tail')
        except RuntimeError:
            pass

    def _flush_log(self, event=None):
        """主线程中刷新日志队列"""
        if not self._pending_log_msgs:
            return
        self.txt_log.config(state=tk.NORMAL)
        for m in self._pending_log_msgs:
            self.txt_log.insert(tk.END, m)
            self.txt_log.see(tk.END)
        self._pending_log_msgs.clear()
        self.txt_log.config(state=tk.DISABLED)

    def _flush_tree_updates(self, event=None):
        """主线程中刷新树形控件更新队列"""
        if not self._pending_tree_updates:
            return
        for item_id, val in self._pending_tree_updates:
            if self.tree.exists(item_id):
                vals = list(self.tree.item(item_id, "values"))
                vals[4] = val
                self.tree.item(item_id, values=vals)
        self._pending_tree_updates.clear()

    def refresh_processes(self):
        self.cb_processes.set('正在扫描...')
        self.update()
        
        self.process_dict.clear()
        display_list = []
        
        for p in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                pid = p.info['pid']
                name = p.info['name']
                exe_path = p.info['exe']
                
                if name and "m2server" in name.lower():
                    display_path = exe_path if exe_path else "权限不足，无法读取路径"
                    desc = f"[{pid}] {name} - {display_path}"
                    
                    self.process_dict[desc] = (pid, name, exe_path)
                    display_list.append(desc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
                
        self.cb_processes['values'] = display_list
        if display_list:
            self.cb_processes.current(0)
            self.log(f"进程刷新完成，共找到 {len(display_list)} 个 M2Server 进程。")
        else:
            self.cb_processes.set('')
            self.log("进程刷新完成，未找到相关联进程。")

    def add_list_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not filepath:
            return
            
        if filepath not in self.file_list:
            self.file_list.append(filepath)
            self.cb_files['values'] = self.file_list
            
        self.cb_files.set(filepath)
        self.parse_file(filepath)

    def on_file_selected(self, event):
        filepath = self.cb_files.get()
        if filepath:
            self.parse_file(filepath)

    def parse_file(self, filepath):
        servers = []
        try:
            with open(filepath, 'r', encoding='gbk', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(';'):
                        continue
                    if '=' in line and '|' in line:
                        parts = line.split('=', 1)[1].split('|')
                        if len(parts) > 1:
                            raw_title = parts[1]
                            clean_title = re.sub(r'\s*\[\d+/\d+\]$', '', raw_title).strip()
                            if clean_title and clean_title not in servers:
                                servers.append(clean_title)
                                
            self.cb_servers['values'] = servers
            if servers:
                self.cb_servers.current(0)
            else:
                self.cb_servers.set('')
                
        except Exception as e:
            messagebox.showerror("错误", f"读取文件失败: {e}")

    def add_rule(self):
        filepath = self.cb_files.get()
        server = self.cb_servers.get()
        process_desc = self.cb_processes.get()
        max_p = self.entry_max.get().strip()
        
        if not all([filepath, server, process_desc, max_p]):
            messagebox.showwarning("警告", "请将列表文件、服务器、进程和最高人数填写完整！")
            return
        if not max_p.isdigit():
            messagebox.showwarning("警告", "最高人数必须是纯数字！")
            return
            
        # ================= 1. 重复检查逻辑 =================
        for item in self.tree.get_children():
            existing_file = self.tree.item(item, "values")[0]
            existing_server = self.tree.item(item, "values")[1]
            if existing_file == filepath and existing_server == server:
                messagebox.showwarning("重复警告", f"【{server}】在所选列表文件中已存在监控规则，无需重复添加！")
                return

        pid, pname, _ = self.process_dict[process_desc]
        short_file = os.path.basename(filepath)
        
        # 初始化在线人数展示为 "-"
        self.tree.insert("", tk.END, values=(filepath, server, process_desc, max_p, "-", pid, pname))
        self.log(f"添加规则: [{short_file}] -> {server} (PID: {pid})")
        self.update_url_list()

    def delete_rule(self):
        selected = self.tree.selection()
        if not selected:
            return
        for item in selected:
            val = self.tree.item(item, "values")
            self.tree.delete(item)
            self.log(f"删除规则: {val[1]}")
        self.update_url_list()

    # ================= 2. 新增清空列表功能 =================
    def clear_rules(self):
        if messagebox.askyesno("确认", "确定要清空所有监控规则吗？"):
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.log("监控规则已全部清空。")
        self.update_url_list()

    def toggle_monitor(self):
        if not self.is_monitoring:
            if len(self.tree.get_children()) == 0:
                messagebox.showerror("错误", "监控列表为空，请先添加监控规则！")
                return
            
            auto_ref_val = "1" if "1" in self.cb_auto_refresh.get() else "0"
            ref_speed = self.entry_refresh_speed.get().strip()
            if not ref_speed.isdigit():
                messagebox.showerror("错误", "刷新速度必须为纯数字！")
                return
            
            # 启动HTTP托管服务（如果尚未启动）
            if not self.http_server:
                self._start_http_server()
            
            self.is_monitoring = True
            self.btn_start.config(text="■ 停止监控", bg="red")
            self.entry_http_port.config(state=tk.DISABLED)
            self.log(">>> 监控已启动 <<<")
            
            self.monitor_thread = threading.Thread(target=self.monitor_loop, args=(auto_ref_val, ref_speed))
            self.monitor_thread.daemon = True
            self.monitor_thread.start()
        else:
            self.is_monitoring = False
            self.btn_start.config(text="▶ 开始监控", bg="green")
            self.entry_http_port.config(state=tk.NORMAL)
            
            # 停止HTTP托管服务
            self._stop_http_server()
            
            # 停止监控后，把人数显示重置为 "-"
            for item in self.tree.get_children():
                self.update_tree_item_ui(item, "-")
            self.log(">>> 监控已停止 <<<")

    def get_player_count(self, pid, pname):
        try:
            pm = pymem.Pymem(int(pid))
            module = pymem.process.module_from_name(pm.process_handle, pname)
            if not module: return -1
            address = module.lpBaseOfDll + 0x130C3B0
            return pm.read_int(address)
        except Exception:
            return -1

    def update_tree_item_ui(self, item_id, current_val):
        """ 线程安全的 UI 列表更新方法 """
        if self.tree.exists(item_id):
            vals = list(self.tree.item(item_id, "values"))
            vals[4] = current_val  # 第 5 列是在线人数
            self.tree.item(item_id, values=vals)

    def monitor_loop(self, auto_ref_val, ref_speed):
        while self.is_monitoring:
            file_groups = {}
            # 整理任务队列，并且附加上 GUI 的 item_id 方便后续更新界面
            items = self.tree.get_children()
            for item in items:
                fp, srv, desc, maxp, curp, pid, pname = self.tree.item(item, "values")
                if fp not in file_groups:
                    file_groups[fp] = []
                file_groups[fp].append({
                    'item_id': item,
                    'server': srv,
                    'pid': int(pid),
                    'pname': pname,
                    'max': int(maxp)
                })
            
            for filepath, rules in file_groups.items():
                configs_to_update = []
                for rule in rules:
                    current_p = self.get_player_count(rule['pid'], rule['pname'])
                    
                    # ================= 3. 实时将人数投射到软件界面 (保证线程安全) =================
                    display_p = str(current_p) if current_p >= 0 else "离线/异常"
                    self._pending_tree_updates.append((rule['item_id'], display_p))
                    try:
                        self.event_generate('<<TreeUpdate>>', when='tail')
                    except RuntimeError:
                        pass
                    
                    if current_p >= 0:
                        configs_to_update.append({
                            "title": rule['server'],
                            "current": current_p,
                            "max": rule['max']
                        })
                    else:
                        self.log(f"警告: {rule['server']} 进程(PID:{rule['pid']})读取失败，可能引擎已关闭。")
                
                # 如果有数据就更新列表 txt
                if configs_to_update:
                    self.update_list_file(filepath, configs_to_update, auto_ref_val, ref_speed)
            
            # 持续监控延时 (默认 5 秒扫描一次，降低 CPU 占用)
            for _ in range(1):
                if not self.is_monitoring:
                    break
                time.sleep(1)

    def update_list_file(self, filepath, configs, auto_ref_val, ref_speed):
        try:
            if not os.path.exists(filepath):
                return
                
            with open(filepath, 'r', encoding='gbk', errors='ignore') as f:
                lines = f.readlines()
            
            new_lines = []
            update_count = 0
            in_setup_section = False
            
            for line in lines:
                raw_line = line.strip()
                if raw_line == '[Setup]':
                    in_setup_section = True 
                elif raw_line.startswith('[') and raw_line != '[Setup]':
                    in_setup_section = False 
                
                if in_setup_section:
                    if raw_line.startswith('刷新速度='):
                        new_lines.append(f"刷新速度={ref_speed}\n") 
                        continue
                    elif raw_line.startswith('自动刷新='):
                        new_lines.append(f"自动刷新={auto_ref_val}\n") 
                        continue
                
                updated = False
                for cfg in configs:
                    target_title = cfg['title']
                    if f"|{target_title}" in line or f"|{target_title} [" in line:
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            color, data = parts
                            data = data.rstrip('\n')  # strip trailing newline to prevent double-newline buildup
                            fields = data.split('|')
                            if len(fields) > 1:
                                clean_title = re.sub(r'\s*\[\d+/\d+\]$', '', fields[1]).strip()
                                
                                if clean_title == target_title:
                                    ratio = cfg['current'] / cfg['max']
                                    if ratio >= 1.0: new_color = "249"
                                    elif ratio >= 0.6: new_color = "151"
                                    else: new_color = "250"
                                        
                                    fields[1] = f"{clean_title} [{cfg['current']}/{cfg['max']}]"
                                    new_line = f"{new_color}={'|'.join(fields)}\n"
                                    
                                    new_lines.append(new_line)
                                    updated = True
                                    update_count += 1
                                    break
                
                if not updated:
                    new_lines.append(line)
            
            # === 新增优化 1：如果组装后的文件内容跟上一次完全一样，则直接跳过不写硬盘 ===
            new_file_text = "".join(new_lines)
            if self.last_file_contents.get(filepath) == new_file_text:
                return  # 内容没变，不操作文件，完美解决 99% 的冲突
            
            # === 新增优化 2：带重试机制的原子替换（防止登录器刚好在读时冲突）===
            temp_filepath = filepath + ".tmp"
            with open(temp_filepath, 'w', encoding='gbk') as f:
                f.write(new_file_text)
            
            success = False
            for attempt in range(3):  # 最多重试 3 次
                try:
                    os.replace(temp_filepath, filepath)
                    success = True
                    break
                except PermissionError:
                    time.sleep(0.05)  # 如果文件正被登录器占用，稍微等待 50 毫秒再试
            
            if success:
                self.last_file_contents[filepath] = new_file_text  # 记录最新的内容缓存
                
        except Exception as e:
            self.log(f"更新列表文件异常: {e}")
    # ================= HTTP外部访问方法 =================
    
    def fetch_external_ip(self):
        """后台线程获取外网IP（获取失败时保留手动输入能力）"""
        def _fetch():
            ip = ""
            services = [
                "https://myip.ipip.net",
                "https://jsonip.com",
                "https://api64.ipify.org?format=json",
                "https://httpbin.org/ip",
            ]
            for url in services:
                try:
                    req = urllib.request.urlopen(url, timeout=5)
                    text = req.read().decode('utf-8', errors='ignore')
                    try:
                        data = json.loads(text)
                        if 'ip' in data:
                            ip = data['ip']
                            break
                        elif 'origin' in data:
                            ip = data['origin'].split(',')[0].strip()
                            break
                    except json.JSONDecodeError:
                        pass
                    m = re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', text)
                    if m:
                        ip = m.group()
                        break
                except Exception:
                    continue
            self.external_ip = ip if ip else "获取失败（可手动填写）"
            try:
                self.event_generate('<<IPFetched>>', when='tail')
            except RuntimeError:
                pass
        self.entry_ip.delete(0, tk.END)
        self.entry_ip.insert(0, "外网IP: 获取中...")
        threading.Thread(target=_fetch, daemon=True).start()
    
    def _update_ip_display(self):
        """更新IP显示（IP获取失败时用户可手动填写）"""
        ip_text = self.external_ip if self.external_ip and self.external_ip != "获取失败" else "获取失败（可手动填写）"
        self.entry_ip.config(state=tk.NORMAL)
        self.entry_ip.delete(0, tk.END)
        self.entry_ip.insert(0, ip_text)
        if self.http_server:
            self.update_url_list()
    
    def _start_http_server(self):
        """启动HTTP文件托管服务"""
        port_str = self.entry_http_port.get().strip()
        if not port_str.isdigit():
            messagebox.showwarning("警告", "端口必须是纯数字！")
            return
        port = int(port_str)
        if port < 1 or port > 65535:
            messagebox.showwarning("警告", "端口范围必须在 1-65535 之间！")
            return
        
        # 构建文件名到路径的映射（按文件去重）
        self._sync_http_file_map()
        
        if not self.http_file_map:
            messagebox.showwarning("警告", "监控列表为空，请先添加监控规则！")
            return
        
        # 通过类变量共享文件映射
        class MonitorFileHandler(http.server.BaseHTTPRequestHandler):
            file_map = {}
            
            def do_GET(self):
                path = self.path.lstrip('/')
                if path in self.file_map:
                    actual_path = self.file_map[path]
                    try:
                        with open(actual_path, 'rb') as f:
                            content = f.read()
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/plain; charset=gbk')
                        self.send_header('Content-Length', str(len(content)))
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(content)
                    except Exception as e:
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(str(e).encode('utf-8'))
                else:
                    if path == '' or path == 'index.html':
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/html; charset=utf-8')
                        self.end_headers()
                        files = list(self.file_map.keys())
                        html = '<html><body><h2>托管的列表文件</h2><ul>'
                        for f in files:
                            html += f'<li><a href="/{f}">{f}</a></li>'
                        html += '</ul></body></html>'
                        self.wfile.write(html.encode('utf-8'))
                    else:
                        self.send_response(404)
                        self.end_headers()
                        self.wfile.write(b"File not found")
            
            def log_message(self, format, *args):
                pass  # 静默日志
        
        MonitorFileHandler.file_map = self.http_file_map.copy()
        self.http_handler_class = MonitorFileHandler  # save ref for live updates
        
        try:
            self.http_server = socketserver.TCPServer(("0.0.0.0", port), MonitorFileHandler)
            self.http_server_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
            self.http_server_thread.start()
            self.entry_http_port.config(state=tk.DISABLED)
            ip_tip = self.entry_ip.get().strip() or "<外网IP>"
            self.log(f"HTTP托管服务已启动: http://{ip_tip}:{port}")
            self.update_url_list()
        except Exception as e:
            messagebox.showerror("错误", f"启动HTTP服务失败: {e}")
    
    def _stop_http_server(self):
        """停止HTTP文件托管服务"""
        if self.http_server:
            try:
                self.http_server.shutdown()
                self.http_server.server_close()
            except Exception:
                pass
            self.http_server = None
            self.http_server_thread = None
            self.entry_http_port.config(state=tk.NORMAL)
            self.log("HTTP服务已停止")
            self.update_url_list()
    
    def _sync_http_file_map(self):
        """同步HTTP文件映射到处理器类（支持热更新，按文件去重）"""
        self.http_file_map = {}
        seen = set()
        for item in self.tree.get_children():
            vals = self.tree.item(item, "values")
            filepath = vals[0]
            basename = os.path.basename(filepath)
            if basename not in seen:
                seen.add(basename)
                self.http_file_map[basename] = filepath
        if self.http_handler_class:
            self.http_handler_class.file_map = self.http_file_map.copy()
    
    def update_url_list(self):
        """刷新URL显示列表（按文件去重）"""
        self._sync_http_file_map()
        for widget in self.frame_urls_inner.winfo_children():
            widget.destroy()
        
        if self.http_server and self.tree.get_children():
            port = self.entry_http_port.get().strip()
            seen = set()
            for item in self.tree.get_children():
                vals = self.tree.item(item, "values")
                basename = os.path.basename(vals[0])
                if basename not in seen:
                    seen.add(basename)
                    ip_display = self.entry_ip.get().strip()
                    if not ip_display or "获取" in ip_display or "请填写" in ip_display:
                        ip_display = "<请填写外网IP>"
                    url = f"http://{ip_display}:{port}/{basename}"
                    lbl = tk.Label(self.frame_urls_inner, text=url, fg="blue", cursor="hand2", anchor='w')
                    lbl.pack(fill=tk.X, pady=1)
                    lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
        else:
            lbl = tk.Label(self.frame_urls_inner, text="(暂无文件，请先添加监控规则)", fg="gray", anchor='w')
            lbl.pack(fill=tk.X)