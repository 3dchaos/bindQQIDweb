import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser
import shutil
from datetime import datetime
import re
import os
import re
import chardet

# 全局版本号
VERSION = "1.0"

class MapEditorPanel(ttk.Frame):
    def __init__(self, parent):
        ttk.Frame.__init__(self, parent)
        # 数据存储
        self.maps_data = {}  # 存储地图数据
        self.maps_order = []  # 存储地图顺序
        self.current_map = None  # 当前选中的地图
        self.map_info_file = ""  # MapInfo.txt文件路径
        
        # 真正的开关参数 - 只有这些是无值的开关参数
        self.boolean_parameters = {
            "BATTLINGDISEXIT": "战斗状态禁止退出",
            "RUNMON": "允许穿怪",
            "RUNHUMAN": "允许穿人",
            "NORUNMON": "禁止穿怪",
            "NORUNHUMAN": "禁止穿人",
            "NEEDHOLE": "进入需要洞",
            "NORECALL": "禁止记忆召唤",
            "NOGUILDRECALL": "禁止行会召唤",
            "NODEARRECALL": "禁止夫妻召唤",
            "NOMASTERRECALL": "禁止师徒传送",
            "NORANDOMMOVE": "禁止随机传送",
            "NODRUG": "禁止使用任何药品",
            "MINE": "可以挖矿",
            "NOAUTODROPITEMTOBAG": "禁止物品自动入包",
            "NOAUTORANGEPICKITEM": "禁止范围拾取",
            "NOPOSITIONMOVE": "禁止定座标移动",
            "QUIZ": "禁止喊话",
            "ALLOWUSEMYSHOP": "允许摆摊",
            "FIGHT2": "杀人不犯法但会爆装备",
            "NODROPITEM": "禁止死亡爆装备",
            "NOHEROPROTECT": "禁止英雄守护",
            "FIGHT4": "挑战地图",
            "SAFE": "安全地图",
            "FIGHT": "PK地图不犯法不爆装备",
            "NOHORSE": "禁止骑马",
            "NOAUTOONLINE": "禁止挂机",
            "NOCALLPET": "禁止召唤宠物",
            "MISSION": "任务地图",
            "NOMANNOMON": "智能刷怪",
            "NOCALLHERO": "禁止召唤英雄",
            "DISABLECALLHERO": "禁止召唤英雄",
            "NIGHT": "夜晚效果",
            "DARK": "黑暗效果",
            "DAY": "白天效果",
            "DELDROPITEM": "死亡物品立即消失",
            "NODROPUSEITEMS": "死亡不掉落物品",
            "NOSAFEPOSITIONMOVE": "禁止安全区传送",
            "ONKILLMON": "杀死怪物触发",
            "NOTSTONE": "魔血石无效",
            "NOCHALLENGE": "禁止挑战",
            "NOTHROWITEM": "禁止丢物品",
            "SLAVENOTATTACKHUMAN": "宝宝不攻击人物",
            "SLAVENOTATTACKHERO": "宝宝不攻击英雄",
            "NODEAL": "禁止交易",
            "NOSHOP": "禁止使用商铺",
            "SHOWNATIONCOLOR": "强制显示国家颜色"
        }
        
        # 带值参数 - 需要输入具体值的参数
        self.value_parameters = {
            "CHECKQUEST": "进入本地图执行任务脚本",
            "NEEDSET_ON": "进入本地图需要人物指定标志为打开状态",
            "NEEDSET_OFF": "进入本地图需要人物指定标志为关闭状态",
            "MUSIC": "进入本地图播放音乐",
            "EXPRATE": "进入本地图后杀怪经验倍数",
            "PKWINLEVEL": "进入本地图后可以PK升级",
            "PKWINEXP": "进入本地图后可以PK得经验",
            "PKLOSTLEVEL": "进入本地图后可以PK死亡掉等级",
            "PKLOSTEXP": "进入本地图后可以PK死亡掉经验",
            "DECHP": "进入本地图后自动减HP",
            "INCHP": "进入本地图后自动加HP",
            "DECGAMEGOLD": "进入本地图后自动减游戏币",
            "INCGAMEGOLD": "进入本地图后自动加游戏币",
            "INCGAMEPOINT": "进入本地图后自动加游戏点",
            "DECGAMEPOINT": "进入本地图后自动减游戏点",
            "NORECONNECT": "进游戏时退出本地图",
            "FIGHT3": "行会战地图",
            "NOALLOWUSEITEMS": "不允许使用指定物品",
            "NOTALLOWUSEITEMS": "禁止使用指定物品",
            "NOTALLOWUSEMAGIC": "禁止使用技能",
            "THUNDER": "闪电效果",
            "LAVA": "岩浆效果",
            "CUSTOMEFFECT": "自定义特效",
            "FLAME": "火焰伤害",
            "NEEDLEVELTIME": "等级时间限制",
            "DECEXPRATETIME": "减双倍经验时间",
            "NGEXPRATE": "内功经验倍数",
            "PULSEXPRATE": "经络经验倍数",
            "SAYLEVEL": "说话等级限制",
            "REVIVAL": "复活次数限制",
            "DIETIME": "死亡自动掉线时间",
            "FB": "副本设置",
            "DROPITEMADDUSERBAG": "物品直接进入背包",
            "NOSWITCHATTACKMODE": "锁定攻击模式"
        }
        
        self.setup_ui()
        
    def setup_ui(self):
        # 主框架
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 顶部按钮框架
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(top_frame, text="选择根目录", command=self.select_root_dir).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(top_frame, text="重新加载", command=self.reload_data).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(top_frame, text="保存更改", command=self.save_changes).pack(side=tk.LEFT, padx=(0, 10))
        
        # 状态标签
        self.status_label = ttk.Label(top_frame, text="请选择根目录")
        self.status_label.pack(side=tk.RIGHT)
        
        # 分割框架
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        
        # 左侧地图列表框架
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=1)
        
        # 地图列表
        ttk.Label(left_frame, text="地图列表:", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        self.map_listbox = tk.Listbox(left_frame, width=30, font=("Arial", 10))
        self.map_listbox.pack(fill=tk.BOTH, expand=True)
        self.map_listbox.bind('<<ListboxSelect>>', self.on_map_select)
        
        # 右侧编辑框架
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=2)
        
        # 地图信息显示
        info_frame = ttk.LabelFrame(right_frame, text="地图信息")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 地图基本信息编辑
        map_info_grid = ttk.Frame(info_frame)
        map_info_grid.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(map_info_grid, text="地图ID:", font=("Arial", 11)).grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.map_id_var = tk.StringVar()
        self.map_id_entry = ttk.Entry(map_info_grid, textvariable=self.map_id_var, width=15)
        self.map_id_entry.grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
        
        ttk.Label(map_info_grid, text="地图名:", font=("Arial", 11)).grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        self.map_name_var = tk.StringVar()
        self.map_name_entry = ttk.Entry(map_info_grid, textvariable=self.map_name_var, width=20)
        self.map_name_entry.grid(row=0, column=3, sticky=tk.W, padx=(0, 10))
        
        ttk.Label(map_info_grid, text="父级地图:", font=("Arial", 11)).grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
        self.parent_id_var = tk.StringVar()
        self.parent_id_entry = ttk.Entry(map_info_grid, textvariable=self.parent_id_var, width=10)
        self.parent_id_entry.grid(row=0, column=5, sticky=tk.W)
        
        # 复制地图编号编辑框
        ttk.Label(map_info_grid, text="复制编号:", font=("Arial", 11)).grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        self.copy_id_var = tk.StringVar()
        self.copy_id_entry = ttk.Entry(map_info_grid, textvariable=self.copy_id_var, width=15)
        self.copy_id_entry.grid(row=1, column=1, sticky=tk.W, padx=(0, 10), pady=(5, 0))
        
        # 参数编辑区域
        param_frame = ttk.LabelFrame(right_frame, text="地图参数")
        param_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建参数编辑区域
        self.create_parameter_editors(param_frame)
        
        # 广告链接
        ad_frame = ttk.Frame(main_frame)
        ad_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=1)
        
        ad_label = ttk.Label(ad_frame, text="典狱长软件", font=("Arial", 8), foreground="gray")
        ad_label.pack(side=tk.RIGHT)
        
        # 绑定点击事件
        def open_ad_link(event):
                webbrowser.open("http://dyzplugin.win/")
        
        ad_label.bind("<Button-1>", open_ad_link)
        ad_label.bind("<Enter>", lambda e: ad_label.configure(foreground="blue", cursor="hand2"))
        ad_label.bind("<Leave>", lambda e: ad_label.configure(foreground="gray", cursor=""))
        
    def create_parameter_editors(self, parent):
        # 创建滚动框架
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 参数编辑控件
        self.boolean_vars = {}  # 开关参数变量
        self.value_vars = {}  # 带值参数变量
        self.value_entries = {} # 带值参数输入框
        
        row = 0
        
        # 添加布尔参数（勾选框）
        ttk.Label(scrollable_frame, text="开关参数:", font=("Arial", 12, "bold")).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, padx=(10, 5), pady=(10, 5)
        )
        row += 1
        
        for param, description in self.boolean_parameters.items():
            # 创建勾选框
            var = tk.BooleanVar()
            checkbox = ttk.Checkbutton(scrollable_frame, text=f"{param}: {description}", 
                                     variable=var, command=lambda p=param, v=var: self.on_checkbox_change(p, v))
            checkbox.grid(row=row, column=0, columnspan=3, sticky=tk.W, padx=(20, 10), pady=3)
            
            self.boolean_vars[param] = var
            row += 1
        
        # 添加带值参数（输入框）
        ttk.Label(scrollable_frame, text="带值参数:", font=("Arial", 12, "bold")).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, padx=(10, 5), pady=(10, 5)
        )
        row += 1
        
        for param, description in self.value_parameters.items():
            # 参数名称标签
            ttk.Label(scrollable_frame, text=f"{param}:", font=("Arial", 11, "bold")).grid(
                row=row, column=0, sticky=tk.W, padx=(20, 5), pady=3
            )
            
            # 参数描述
            ttk.Label(scrollable_frame, text=description, font=("Arial", 10)).grid(
                row=row, column=1, sticky=tk.W, padx=(0, 10), pady=3
            )
            
            # 参数值输入框
            var = tk.StringVar()
            entry = ttk.Entry(scrollable_frame, textvariable=var, width=35)
            entry.grid(row=row, column=2, sticky=tk.W, padx=(0, 10), pady=3)
            
            self.value_vars[param] = var
            self.value_entries[param] = entry
            
            row += 1
        
        # 添加自定义参数输入
        ttk.Label(scrollable_frame, text="自定义参数:", font=("Arial", 12, "bold")).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, padx=(10, 5), pady=(10, 5)
        )
        row += 1
        
        self.custom_param_var = tk.StringVar()
        self.custom_param_entry = ttk.Entry(scrollable_frame, textvariable=self.custom_param_var, width=60)
        self.custom_param_entry.grid(row=row, column=0, columnspan=3, sticky=tk.W, padx=(20, 10), pady=(5, 2))
        
        # 布局滚动组件
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
    def on_checkbox_change(self, param, var):
        """勾选框变化事件"""
        pass  # 可以在这里添加实时保存或其他逻辑
        
    def select_root_dir(self):
        root_dir = filedialog.askdirectory(title="选择根目录")
        if root_dir:
            map_info_path = os.path.join(root_dir, "Mir200", "Envir", "MapInfo.txt")
            if os.path.exists(map_info_path):
                self.map_info_file = map_info_path
                self.status_label.config(text=f"已加载: {os.path.basename(root_dir)}")
                self.load_map_info()
            else:
                messagebox.showerror("错误", f"未找到文件: {map_info_path}")
                self.status_label.config(text="文件未找到")
                
    def detect_encoding(self, file_path):
        """检测文件编码"""
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read()
                result = chardet.detect(raw_data)
                encoding = result['encoding']
                
                # 对于ANSI编码文件，强制使用GBK
                if encoding and encoding.lower() in ['gbk', 'gb2312', 'gb18030', 'windows-1252', 'iso-8859-1']:
                    return 'gbk'
                elif encoding:
                    return encoding
                else:
                    # 如果检测失败，尝试GBK编码
                    return 'gbk'
        except Exception:
            # 如果检测失败，默认使用GBK
            return 'gbk'
    
    def load_map_info(self):
        """加载MapInfo.txt文件"""
        if not self.map_info_file:
            return
            
        try:
            self.status_label.config(text="正在加载文件...")
            self.update()
            
            # 强制使用GBK编码读取ANSI文件
            encoding = 'gbk'
            
            print(f"正在加载文件: {self.map_info_file}")
            print(f"使用编码: {encoding}")
            
            with open(self.map_info_file, 'r', encoding=encoding) as f:
                content = f.read()
            
            print(f"文件加载成功，内容长度: {len(content)} 字符")
            print(f"文件行数: {len(content.split(chr(10)))}")
            
            self.parse_map_info(content)
            self.update_map_list()
            
            self.status_label.config(text=f"已加载 {len(self.maps_data)} 个地图")
            
        except Exception as e:
            print(f"加载文件时出错: {e}")
            messagebox.showerror("错误", f"加载MapInfo.txt文件时出错:\n{str(e)}")
            self.status_label.config(text="加载失败")
    
    def parse_map_info(self, content):
        """解析MapInfo.txt内容"""
        self.maps_data = {}
        self.maps_order = [] # 清空顺序
        lines = content.split('\n')
        
        print(f"开始解析，总行数: {len(lines)}")
        map_count = 0
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith(';'):
                continue
                
            # 解析地图定义
            if line.startswith('[') and ']' in line:
                # 找到地图定义的结束位置
                end_bracket = line.find(']')
                map_def = line[1:end_bracket]  # 去掉方括号
                remaining_line = line[end_bracket+1:].strip()  # 剩余部分（参数）
                
                # 使用正则表达式分割，支持制表符和多个空格
                parts = re.split('\s+', map_def.strip())
                
                if len(parts) >= 2:
                    map_id = parts[0].strip()
                    map_name = parts[1].strip()
                    
                    # 处理复制地图格式 [hlmg|hl001 火龙迷宫]
                    copy_id = ""
                    if '|' in map_id:
                        # 正确理解：hlmg是地图编号，hl001是复制编号
                        map_id, copy_id = map_id.split('|')
                        map_id = map_id.strip()
                        copy_id = copy_id.strip()
                    
                    # 处理子级地图格式 [0122 宫殿 0]
                    parent_id = ""
                    if len(parts) >= 3:
                        parent_id = parts[2].strip()
                    
                    # 使用地图ID作为唯一标识符，避免重复名称问题
                    unique_key = f"{map_id}_{map_name}"
                    
                    self.maps_data[unique_key] = {
                        'id': map_id,
                        'name': map_name,
                        'parent_id': parent_id,
                        'copy_id': copy_id,  # 复制地图编号
                        'parameters': {},
                        'transfers': []
                    }
                    self.maps_order.append(unique_key) # 添加到顺序列表
                    map_count += 1
                    
                    print(f"第{line_num}行: 解析地图 '{map_name}' (ID: {map_id}, 复制ID: {copy_id}, 父级: {parent_id})")
                    
                    # 解析同一行中的参数（如果有的话）
                    if remaining_line:
                        params = self.parse_parameters(remaining_line)
                        self.maps_data[unique_key]['parameters'].update(params)
                    
            elif '\t' in line and '->' in line:
                # 传送点定义 "FOX01 115,19 -> FOX03 34,51"
                parts = line.split('\t')
                if len(parts) >= 4:
                    source_map = parts[0].strip()
                    source_coords = parts[1].strip()
                    target_info = parts[3].strip()
                    
                    # 解析目标地图和坐标
                    target_parts = target_info.split('\t')
                    if len(target_parts) >= 2:
                        target_map = target_parts[0].strip()
                        target_coords = target_parts[1].strip()
                        
                        # 找到对应的地图名称
                        for unique_key, map_data in self.maps_data.items():
                            if map_data['id'] == source_map:
                                map_data['transfers'].append({
                                    'source_coords': source_coords,
                                    'target_map': target_map,
                                    'target_coords': target_coords
                                })
                                break
                                
            else:
                # 参数行（单独的参数行）
                parts = line.split('\t')
                if len(parts) >= 2:
                    map_id = parts[0].strip()
                    params_str = parts[1].strip()
                    
                    # 找到对应的地图
                    for unique_key, map_data in self.maps_data.items():
                        if map_data['id'] == map_id:
                            # 解析参数
                            params = self.parse_parameters(params_str)
                            map_data['parameters'].update(params)
                            break
        
        print(f"解析完成，共找到 {map_count} 张地图")
        print(f"地图列表: {list(self.maps_data.keys())}")
    
    def parse_parameters(self, params_str):
        """解析参数字符串"""
        params = {}
        
        # 分割参数（支持多个空格和制表符）
        param_parts = re.split(r'[\s\t]+', params_str)
        
        for part in param_parts:
            part = part.strip()
            if not part:
                continue
                
            # 检查是否是带括号的参数（如CHECKQUEST(任务ID)）
            if '(' in part and part.endswith(')'):
                param_name = part[:part.find('(')]
                param_value = part[part.find('(')+1:part.rfind(')')]
                
                # 统一参数名为大写
                param_name_upper = param_name.upper()
                
                # 检查是否是已知的开关参数
                if param_name_upper in self.boolean_parameters:
                    params[param_name_upper] = ""
                    continue
                
                # 检查是否是已知的带值参数
                if param_name_upper in self.value_parameters:
                    params[param_name_upper] = param_value
                    continue
                else:
                    # 未知的带值参数，保持原样
                    params[param_name] = param_value
                continue
                
            # 检查无括号的参数
            # 统一参数名为大写
            part_upper = part.upper()
            
            # 检查是否是开关参数
            if part_upper in self.boolean_parameters:
                params[part_upper] = ""
                continue
                
            # 检查是否是带值参数
            if part_upper in self.value_parameters:
                params[part_upper] = ""
                continue
            else:
                # 未知参数，作为自定义参数，保持原样
                if part not in params:
                    params[part] = ""
        
        return params
    
    def update_map_list(self):
        """更新地图列表"""
        self.map_listbox.delete(0, tk.END)
        for unique_key in self.maps_order: # 按顺序显示
            map_data = self.maps_data[unique_key]
            self.map_listbox.insert(tk.END, map_data['name'])
    
    def on_map_select(self, event):
        """地图选择事件"""
        selection = self.map_listbox.curselection()
        if selection:
            map_name = self.map_listbox.get(selection[0])
            self.current_map = map_name
            self.load_map_parameters(map_name)
    
    def load_map_parameters(self, map_name):
        """加载地图参数到编辑界面"""
        # 找到对应的地图数据
        for unique_key, map_data in self.maps_data.items():
            if map_data['name'] == map_name:
                self.current_map = unique_key # 使用唯一键作为当前地图
                break
        
        if self.current_map not in self.maps_data:
            return
            
        map_data = self.maps_data[self.current_map]
        
        # 更新地图基本信息
        self.map_id_var.set(map_data['id'])
        self.map_name_var.set(map_data['name'])
        self.parent_id_var.set(map_data['parent_id'])
        self.copy_id_var.set(map_data.get('copy_id', ''))
        
        # 清空所有参数值
        for var in self.boolean_vars.values():
            var.set(False)
            
        for var in self.value_vars.values():
            var.set("")
        
        # 设置参数值
        for param, value in map_data['parameters'].items():
            if param in self.boolean_vars:
                # 开关参数
                self.boolean_vars[param].set(True)
            elif param in self.value_vars:
                # 带值参数
                self.value_vars[param].set(value)
            else:
                # 自定义参数
                self.custom_param_var.set(f"{param}({value})" if value else param)
    
    def reload_data(self):
        """重新加载数据"""
        if self.map_info_file:
            self.load_map_info()
    
    def save_changes(self):
        """保存更改"""
        if not self.current_map or not self.map_info_file:
            messagebox.showwarning("警告", "请先选择地图")
            return
            
        try:
            self.status_label.config(text="正在保存...")
            self.update()
            
            # 更新当前地图的基本信息
            map_data = self.maps_data[self.current_map]
            map_data['id'] = self.map_id_var.get().strip()
            map_data['name'] = self.map_name_var.get().strip()
            map_data['parent_id'] = self.parent_id_var.get().strip()
            map_data['copy_id'] = self.copy_id_var.get().strip()
            
            # 更新地图名称（如果地图名改变了）
            new_map_name = map_data['name']
            old_map_name = map_data['name']  # 获取旧的地图名
            
            # 如果地图名改变了，需要更新显示
            if new_map_name != old_map_name:
                # 更新地图列表显示
                self.update_map_list()
            
            # 更新参数
            new_params = {}
            
            # 收集开关参数
            for param, var in self.boolean_vars.items():
                if var.get():
                    new_params[param] = ""
            
            # 收集带值参数
            for param, var in self.value_vars.items():
                value = var.get().strip()
                if value:
                    new_params[param] = value
            
            # 处理自定义参数
            custom_param = self.custom_param_var.get().strip()
            if custom_param:
                # 解析自定义参数
                if '(' in custom_param and custom_param.endswith(')'):
                    param_name = custom_param[:custom_param.find('(')]
                    param_value = custom_param[custom_param.find('(')+1:custom_param.rfind(')')]
                    new_params[param_name] = param_value
                else:
                    new_params[custom_param] = ""
            
            # 更新地图数据
            map_data['parameters'] = new_params
            
            # 备份并保存文件
            self.backup_and_save()
            
            self.status_label.config(text="保存成功")
            messagebox.showinfo("成功", "地图参数已保存")
            
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")
            self.status_label.config(text="保存失败")
    
    def save_map_info_file(self):
        """保存MapInfo.txt文件（完整重写）"""
        content_lines = []
        
        # 生成地图定义
        for unique_key in self.maps_order: # 按顺序保存
            map_data = self.maps_data[unique_key]
            # 构建地图定义行
            if map_data.get('copy_id'):
                # 复制地图格式 [hlmg|hl001 火龙迷宫]
                map_def = f"[{map_data['id']}|{map_data['copy_id']}\t{map_data['name']}]"
            else:
                # 普通地图格式或子级地图格式
                map_def = f"[{map_data['id']}\t{map_data['name']}"
                if map_data['parent_id'] and map_data['parent_id'] != "0":
                    map_def += f"\t{map_data['parent_id']}"
                map_def += "]"
            
            content_lines.append(map_def)
            
            # 生成传送点 "FOX01 115,19 -> FOX03 34,51"
            for transfer in map_data['transfers']:
                transfer_line = f"{map_data['id']}\t{transfer['source_coords']}\t->\t{transfer['target_map']}\t{transfer['target_coords']}"
                content_lines.append(transfer_line)
            
            # 生成参数行
            if map_data['parameters']:
                param_str = self.build_parameter_string(map_data['parameters'])
                content_lines.append(f"{map_data['id']}\t{param_str}")
            
            content_lines.append("")  # 空行分隔
        
        # 写入文件
        try:
            # 强制使用GBK编码保存ANSI文件
            encoding = 'gbk'
                
            with open(self.map_info_file, 'w', encoding=encoding) as f:
                f.write('\n'.join(content_lines))
                
        except Exception as e:
            raise Exception(f"写入文件失败: {str(e)}")
    
    def backup_and_save(self):
        """备份并保存文件（只修改当前编辑的地图）"""
        try:
                    
            # 创建备份文件名
            backup_dir = os.path.dirname(self.map_info_file)
            backup_name = f"MapInfo_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            backup_path = os.path.join(backup_dir, backup_name)
            
            # 备份原文件
            shutil.copy2(self.map_info_file, backup_path)
            
            # 读取原文件内容
            encoding = 'gbk'
            with open(self.map_info_file, 'r', encoding=encoding) as f:
                lines = f.readlines()
            
            # 找到当前编辑的地图在文件中的位置
            current_map_data = self.maps_data[self.current_map]
            current_map_id = current_map_data['id']
            
            # 查找地图定义行和参数行
            map_def_line_index = -1
            param_line_index = -1
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line or line.startswith(';'):
                    continue
                
                # 查找地图定义行 - 更精确的匹配
                if line.startswith('[') and ']' in line:
                    # 提取地图ID进行精确匹配
                    map_def_part = line[1:line.find(']')]
                    parts = map_def_part.split('\t')
                    if len(parts) >= 1:
                        map_id_in_line = parts[0].strip()
                        # 处理复制地图格式 [hlmg|hl001 火龙迷宫]
                        if '|' in map_id_in_line:
                            map_id_in_line = map_id_in_line.split('|')[0].strip()
                        
                        if map_id_in_line == current_map_id:
                            map_def_line_index = i
                            # 查找后续的参数行
                            for j in range(i + 1, len(lines)):
                                next_line = lines[j].strip()
                                if not next_line or next_line.startswith(';'):
                                    continue
                                if next_line.startswith('['):
                                    break  # 遇到下一个地图定义
                                if '\t' in next_line and not '->' in next_line:
                                    # 这可能是参数行
                                    parts = next_line.split('\t')
                                    if len(parts) >= 2 and parts[0].strip() == current_map_id:
                                        param_line_index = j
                                        break
                            break
            
            # 构建新的地图定义行（包含参数）
            if current_map_data.get('copy_id'):
                new_map_def = f"[{current_map_data['id']}|{current_map_data['copy_id']}\t{current_map_data['name']}]"
            else:
                new_map_def = f"[{current_map_data['id']}\t{current_map_data['name']}"
                if current_map_data['parent_id'] and current_map_data['parent_id'] != "0":
                    new_map_def += f"\t{current_map_data['parent_id']}"
                new_map_def += "]"
            
            # 添加参数到地图定义行
            if current_map_data['parameters']:
                param_str = self.build_parameter_string(current_map_data['parameters'])
                new_map_def += f"\t{param_str}"
            
            # 更新文件内容
            if map_def_line_index != -1:
                # 更新地图定义行（包含参数）
                lines[map_def_line_index] = new_map_def + '\n'
                
                # 删除原来的参数行（如果有的话）
                if param_line_index != -1:
                    lines.pop(param_line_index)
                
                # 写入文件
                with open(self.map_info_file, 'w', encoding=encoding) as f:
                    f.writelines(lines)
                
                # 显示备份信息
                self.status_label.config(text=f"已备份: {backup_name}")
            else:
                raise Exception(f"未找到地图 {current_map_id} 的定义行")
                
        except Exception as e:
            raise Exception(f"备份并保存文件失败: {str(e)}")
    
    def build_parameter_string(self, parameters):
        """构建参数字符串"""
        param_parts = []
        
        for param, value in parameters.items():
            # 统一参数名为大写
            param_upper = param.upper()
            if value:
                param_parts.append(f"{param_upper}({value})")
            else:
                param_parts.append(param_upper)
        
        return '\t'.join(param_parts)