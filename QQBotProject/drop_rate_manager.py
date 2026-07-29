import os
import sqlite3
import socket
import re
import subprocess

class GameDataManager:
    def __init__(self, server_root_dir, port):
        self.server_root_dir = server_root_dir
        self.port = port
        self.config_file = os.path.join(self.server_root_dir, "Config.ini")
        self.server_name = self.get_server_name()
        self.db_path = os.path.join(self.server_root_dir, "Mir200", "M2Data", "dyzSearch.DB")
        self.mon_items_dir = os.path.join(self.server_root_dir, "Mir200", "Envir", "MonItems")
        self.mon_gen_file = os.path.join(self.server_root_dir, "Mir200", "Envir", "MonGen.txt")
        self.map_info_file = os.path.join(self.server_root_dir, "Mir200", "Envir", "MapInfo.txt")
        # 检测当前程序目录下的sqlite3.dll
        self.sqlite_dll = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sqlite3.dll")
        self.map_aliases = {}  # 存储地图名到别称的映射
    
    def get_local_ip(self):
        """获取本机IP地址"""
        try:
            # 创建一个UDP套接字
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # 连接到一个外部地址（不需要真实连接）
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def kill_port_process(self, port):
        """强制关闭指定端口的进程"""
        try:
            # 使用netstat查找占用端口的进程
            result = subprocess.run(
                ['netstat', '-ano'], 
                capture_output=True, 
                text=True, 
                shell=True
            )
            
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if f':{port} ' in line and 'LISTENING' in line:
                        # 提取PID
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            pid = parts[-1]
                            try:
                                # 终止进程
                                subprocess.run(['taskkill', '/PID', pid, '/F'], 
                                            capture_output=True, shell=True)
                                return True
                            except:
                                pass
            return False
        except Exception as e:
            print(f"关闭端口进程失败: {e}")
            return False
    
    def get_server_name(self):
        """从Config.ini文件读取服务端名字"""
        if not os.path.exists(self.config_file):
            return "DefaultServer"
        
        try:
            with open(self.config_file, 'r', encoding='gbk') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    content = f.read()
            except:
                return "DefaultServer"
        
        # 查找GameName
        match = re.search(r'GameName=([^\r\n]+)', content)
        if match:
            server_name = match.group(1).strip()
            return server_name
        else:
            return "DefaultServer"
        
    def check_port_availability(self):
        """检查端口是否被占用"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', self.port))
                s.close()
                return True
        except OSError:
            return False
    
    def check_required_files(self):
        """检查必需的文件和目录"""
        # 检查Config.ini文件
        if not os.path.exists(self.config_file):
            return False, f"错误: {self.config_file} 文件不存在"
        
        # 检查Envir/MonItems目录
        if not os.path.exists(self.mon_items_dir):
            return False, f"错误: {self.mon_items_dir} 目录不存在"
        
        # 检查MonGen.txt文件
        if not os.path.exists(self.mon_gen_file):
            return False, f"错误: {self.mon_gen_file} 文件不存在"
        
        # 检查MapInfo.txt文件
        if not os.path.exists(self.map_info_file):
            return False, f"错误: {self.map_info_file} 文件不存在"
        
        # 检查sqlite3.dll
        if not os.path.exists(self.sqlite_dll):
            return False, f"错误: {self.sqlite_dll} 文件不存在"
        
        return True, "所有文件检查通过"
    
    def create_database(self):
        """创建数据库和表"""
        # 确保M2Data目录存在
        m2data_dir = os.path.dirname(self.db_path)
        os.makedirs(m2data_dir, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 使用服务端名字作为表名前缀
        map_table = f"{self.server_name}_Map"
        monitems_table = f"{self.server_name}_MonItems"
        item_table = f"{self.server_name}_Item"
        
        # 检查Map表是否存在
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{map_table}'")
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            # 创建新表
            cursor.execute(f'''
                CREATE TABLE {map_table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    map_name TEXT NOT NULL,
                    map_alias TEXT,
                    x INTEGER NOT NULL,
                    y INTEGER NOT NULL,
                    monster_name TEXT NOT NULL,
                    range_val INTEGER NOT NULL,
                    count INTEGER NOT NULL,
                    refresh_time INTEGER NOT NULL,
                    country TEXT,
                    color TEXT
                )
            ''')
        else:
            # 检查map_alias列是否存在
            cursor.execute(f"PRAGMA table_info({map_table})")
            columns = [column[1] for column in cursor.fetchall()]
            if 'map_alias' not in columns:
                # 添加map_alias列
                cursor.execute(f"ALTER TABLE {map_table} ADD COLUMN map_alias TEXT")
        
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {monitems_table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monster_name TEXT NOT NULL,
                item_name TEXT NOT NULL,
                probability TEXT NOT NULL,
                rate_numerator INTEGER NOT NULL,
                rate_denominator INTEGER NOT NULL
            )
        ''')
        
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {item_table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL UNIQUE
            )
        ''')
        
        # 保存表名到实例变量
        self.map_table = map_table
        self.monitems_table = monitems_table
        self.item_table = item_table
        
        conn.commit()
        conn.close()
        return "数据库创建成功"
    
    def parse_map_info(self):
        """解析MapInfo.txt文件，获取地图名和别称的对应关系"""
        self.map_aliases = {}
        
        try:
            with open(self.map_info_file, 'r', encoding='gbk') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(';') or not line.startswith('['):
                        continue
                    
                    # 找到第一个]的位置
                    end_bracket = line.find(']')
                    if end_bracket == -1:
                        continue
                    
                    # 提取[ ]中的内容
                    bracket_content = line[1:end_bracket]
                    
                    # 按制表符或空格分割
                    parts = re.split(r'\s+', bracket_content)
                    if len(parts) >= 2:
                        map_name = parts[0]
                        map_alias = parts[1]
                        
                        # 如果地图名包含|，取|前面的部分
                        if '|' in map_name:
                            map_name = map_name.split('|')[0]
                        
                        self.map_aliases[map_name] = map_alias
        
        except UnicodeDecodeError:
            try:
                with open(self.map_info_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith(';') or not line.startswith('['):
                            continue
                        
                        # 找到第一个]的位置
                        end_bracket = line.find(']')
                        if end_bracket == -1:
                            continue
                        
                        # 提取[ ]中的内容
                        bracket_content = line[1:end_bracket]
                        
                        # 按制表符或空格分割
                        parts = re.split(r'\s+', bracket_content)
                        if len(parts) >= 2:
                            map_name = parts[0]
                            map_alias = parts[1]
                            
                            # 如果地图名包含|，取|前面的部分
                            if '|' in map_name:
                                map_name = map_name.split('|')[0]
                            
                            self.map_aliases[map_name] = map_alias
            except:
                return f"错误: 无法读取文件 {self.map_info_file}"
        
        return f"共解析到 {len(self.map_aliases)} 个地图映射"
    
    def parse_monster_items(self):
        """解析怪物爆出物品数据"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 清空现有数据
        cursor.execute(f"DELETE FROM {self.monitems_table}")
        cursor.execute(f"DELETE FROM {self.item_table}")
        
        processed_files = 0
        for filename in os.listdir(self.mon_items_dir):
            if filename.endswith('.txt'):
                monster_name = filename[:-4]  # 去掉.txt后缀
                file_path = os.path.join(self.mon_items_dir, filename)
                
                content = None
                # 尝试多种编码
                encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
                for encoding in encodings:
                    try:
                        with open(file_path, 'r', encoding=encoding) as f:
                            content = f.read()
                        break
                    except UnicodeDecodeError:
                        continue
                    except FileNotFoundError:
                        print(f"无法找到怪物文件: {file_path}")
                        break
                
                if content is not None:
                    self._parse_monster_file_content(conn, cursor, monster_name, content)
                    processed_files += 1
        
        conn.commit()
        conn.close()
        return f"怪物物品数据解析完成，处理了 {processed_files} 个文件"
    
    def _parse_monster_file_content(self, conn, cursor, monster_name, content):
        """解析怪物文件内容，支持新的#CHILD格式和#CALL格式"""
        lines = content.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # 跳过空行和注释
            if not line or line.startswith(';'):
                i += 1
                continue
            
            # 检查是否是#CALL格式（大小写不敏感）
            if line.upper().startswith('#CALL'):
                i = self._parse_call_block(conn, cursor, monster_name, lines, i)
            # 检查是否是#CHILD格式（大小写不敏感）
            elif line.upper().startswith('#CHILD'):
                i = self._parse_child_block(conn, cursor, monster_name, lines, i)
            else:
                # 解析传统格式: "1/10 祈祷之刃"
                parts = line.split()
                if len(parts) >= 2:
                    rate_part = parts[0]
                    item_name = ' '.join(parts[1:])
                    
                    # 解析概率
                    if '/' in rate_part:
                        try:
                            numerator, denominator = map(int, rate_part.split('/'))
                            probability = f"{numerator}/{denominator}"
                            
                            # 插入MonItems表
                            cursor.execute(f'''
                                INSERT INTO {self.monitems_table} (monster_name, item_name, probability, rate_numerator, rate_denominator)
                                VALUES (?, ?, ?, ?, ?)
                            ''', (monster_name, item_name, probability, numerator, denominator))
                            
                            # 插入Item表（如果不存在）
                            cursor.execute(f'''
                                INSERT OR IGNORE INTO {self.item_table} (item_name)
                                VALUES (?)
                            ''', (item_name,))
                            
                        except ValueError:
                            pass
            
            i += 1
    
    def _parse_call_block(self, conn, cursor, monster_name, lines, start_index):
        """解析#CALL块"""
        # 解析#CALL行
        call_line = lines[start_index].strip()
        
        # 解析格式: #CALL [\\爆率系统\基础爆率.txt] @药水
        # 或者: #CALL [爆率系统\基础爆率.txt] @药水
        if '[' in call_line and ']' in call_line:
            # 提取文件路径
            start_bracket = call_line.find('[')
            end_bracket = call_line.find(']')
            file_path_part = call_line[start_bracket + 1:end_bracket]
            
            # 提取标签名
            tag_part = call_line[end_bracket + 1:].strip()
            if tag_part.startswith('@'):
                tag_name = tag_part[1:]  # 去掉@符号
            else:
                tag_name = tag_part
            
            # 构建完整文件路径
            if file_path_part.startswith('\\\\'):
                # 绝对路径格式，去掉开头的\\
                relative_path = file_path_part[2:]
            else:
                # 相对路径格式
                relative_path = file_path_part
            
            # 构建完整路径
            full_path = os.path.join(self.server_root_dir, "Mir200", "Envir", "QuestDiary", relative_path)
            
            print(f"尝试解析外部文件: {full_path}")
            print(f"查找标签: {tag_name}")
            
            # 读取外部爆率文件
            self._parse_external_drop_file(conn, cursor, monster_name, full_path, tag_name)
        
        return start_index + 1
    
    def _parse_external_drop_file(self, conn, cursor, monster_name, file_path, tag_name):
        """解析外部爆率文件"""
        content = None
        
        # 尝试多种编码
        encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                print(f"成功使用 {encoding} 编码读取文件: {file_path}")
                break
            except UnicodeDecodeError:
                continue
            except FileNotFoundError:
                print(f"无法找到外部爆率文件: {file_path}")
                return
        
        if content is None:
            print(f"无法读取外部爆率文件: {file_path}")
            return
        
        # 查找指定标签
        lines = content.split('\n')
        i = 0
        
        # 先列出文件中所有的标签
        all_tags = []
        for line in lines:
            line = line.strip()
            if line.startswith('[@') and line.endswith(']'):
                all_tags.append(line)
        
        print(f"文件中找到的标签: {all_tags}")
        
        while i < len(lines):
            line = lines[i].strip()
            
            # 查找标签 [@药水] 或 [药水]
            if line == f"[@{tag_name}]" or line == f"[{tag_name}]":
                print(f"找到匹配的标签: {line}")
                # 查找开始大括号
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('{'):
                    i += 1
                
                if i >= len(lines):
                    break
                
                # 解析大括号内的内容
                i += 1  # 跳过开始大括号
                while i < len(lines):
                    line = lines[i].strip()
                    
                    if line == '}':  # 结束大括号
                        break
                    elif line.startswith(';') or not line:  # 注释或空行
                        i += 1
                        continue
                    elif line.upper().startswith('#CHILD'):  # CHILD块（大小写不敏感）
                        i = self._parse_child_block(conn, cursor, monster_name, lines, i)
                        continue
                    else:
                        # 解析普通物品行
                        parts = line.split()
                        if len(parts) >= 2:
                            rate_part = parts[0]
                            item_name = ' '.join(parts[1:])
                            
                            if '/' in rate_part:
                                try:
                                    numerator, denominator = map(int, rate_part.split('/'))
                                    probability = f"{numerator}/{denominator}"
                                    
                                    # 插入MonItems表
                                    cursor.execute(f'''
                                        INSERT INTO {self.monitems_table} (monster_name, item_name, probability, rate_numerator, rate_denominator)
                                        VALUES (?, ?, ?, ?, ?)
                                    ''', (monster_name, item_name, probability, numerator, denominator))
                                    
                                    # 插入Item表（如果不存在）
                                    cursor.execute(f'''
                                        INSERT OR IGNORE INTO {self.item_table} (item_name)
                                        VALUES (?)
                                    ''', (item_name,))
                                    
                                except ValueError:
                                    pass
                    
                    i += 1
                break
            
            i += 1
    
    def _parse_child_block(self, conn, cursor, monster_name, lines, start_index):
        """解析#CHILD块"""
        # 解析#CHILD行
        child_line = lines[start_index].strip()
        child_parts = child_line.split()
        
        if len(child_parts) < 2:
            return start_index + 1
        
        # 解析子爆率
        child_rate = child_parts[1]
        # 检查是否有RANDOM参数，忽略后面的参数（大小写不敏感）
        is_random = False
        for i in range(2, len(child_parts)):
            if child_parts[i].upper() == 'RANDOM':
                is_random = True
                break
        
        try:
            child_numerator, child_denominator = map(int, child_rate.split('/'))
        except ValueError:
            return start_index + 1
        
        # 查找开始括号
        i = start_index + 1
        while i < len(lines) and not lines[i].strip().startswith('('):
            i += 1
        
        if i >= len(lines):
            return i
        
        # 解析括号内的物品
        items_in_block = []
        i += 1  # 跳过开始括号
        
        while i < len(lines):
            line = lines[i].strip()
            
            if line == ')':  # 结束括号
                break
            elif line.startswith(';') or not line:  # 注释或空行
                i += 1
                continue
            elif line.upper().startswith('#CHILD'):  # 嵌套的CHILD块（大小写不敏感）
                i = self._parse_child_block(conn, cursor, monster_name, lines, i)
                continue
            else:
                # 解析物品行
                parts = line.split()
                if len(parts) >= 2:
                    rate_part = parts[0]
                    item_name = ' '.join(parts[1:])
                    
                    if '/' in rate_part:
                        try:
                            numerator, denominator = map(int, rate_part.split('/'))
                            
                            # 计算组合概率
                            if is_random:
                                # RANDOM模式：子爆率 * 物品爆率
                                combined_numerator = child_numerator * numerator
                                combined_denominator = child_denominator * denominator
                            else:
                                # 普通模式：子爆率 * 物品爆率
                                combined_numerator = child_numerator * numerator
                                combined_denominator = child_denominator * denominator
                            
                            probability = f"{combined_numerator}/{combined_denominator}"
                            
                            # 插入MonItems表
                            cursor.execute(f'''
                                INSERT INTO {self.monitems_table} (monster_name, item_name, probability, rate_numerator, rate_denominator)
                                VALUES (?, ?, ?, ?, ?)
                            ''', (monster_name, item_name, probability, combined_numerator, combined_denominator))
                            
                            # 插入Item表（如果不存在）
                            cursor.execute(f'''
                                INSERT OR IGNORE INTO {self.item_table} (item_name)
                                VALUES (?)
                            ''', (item_name,))
                            
                        except ValueError:
                            pass
            
            i += 1
        
        return i + 1  # 返回下一个位置
    
    def parse_monster_generation(self):
        """解析怪物刷新数据"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 清空现有数据
        cursor.execute(f"DELETE FROM {self.map_table}")
        
        # 更新现有记录的map_alias字段
        cursor.execute(f"UPDATE {self.map_table} SET map_alias = map_name WHERE map_alias IS NULL")
        
        processed_lines = 0
        try:
            with open(self.mon_gen_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(';'):
                        continue
                    
                    # 解析格式: "FOX02  	277	205	红狐狸          	400	300	15"
                    parts = re.split(r'\s+', line)
                    if len(parts) >= 7:
                        try:
                            map_name = parts[0]
                            x = int(parts[1])
                            y = int(parts[2])
                            monster_name = parts[3]
                            range_val = int(parts[4])
                            count = int(parts[5])
                            refresh_time = int(parts[6])
                            country = parts[7] if len(parts) > 7 else ""
                            color = parts[8] if len(parts) > 8 else ""
                            
                            # 获取地图别称
                            map_alias = self.map_aliases.get(map_name, map_name)
                            
                            cursor.execute(f'''
                                INSERT INTO {self.map_table} (map_name, map_alias, x, y, monster_name, range_val, count, refresh_time, country, color)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (map_name, map_alias, x, y, monster_name, range_val, count, refresh_time, country, color))
                            
                            processed_lines += 1
                            
                        except (ValueError, IndexError):
                            continue
        
        except UnicodeDecodeError:
            try:
                with open(self.mon_gen_file, 'r', encoding='gbk') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith(';'):
                            continue
                        
                        # 解析格式: "FOX02  	277	205	红狐狸          	400	300	15"
                        parts = re.split(r'\s+', line)
                        if len(parts) >= 7:
                            try:
                                map_name = parts[0]
                                x = int(parts[1])
                                y = int(parts[2])
                                monster_name = parts[3]
                                range_val = int(parts[4])
                                count = int(parts[5])
                                refresh_time = int(parts[6])
                                country = parts[7] if len(parts) > 7 else ""
                                color = parts[8] if len(parts) > 8 else ""
                                
                                # 获取地图别称
                                map_alias = self.map_aliases.get(map_name, map_name)
                                
                                cursor.execute(f'''
                                    INSERT INTO {self.map_table} (map_name, map_alias, x, y, monster_name, range_val, count, refresh_time, country, color)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (map_name, map_alias, x, y, monster_name, range_val, count, refresh_time, country, color))
                                
                                processed_lines += 1
                                
                            except (ValueError, IndexError):
                                continue
            except:
                return "错误: 无法读取MonGen.txt文件"
        
        conn.commit()
        conn.close()
        return f"怪物刷新数据解析完成，处理了 {processed_lines} 条记录"
    
    def initialize_data(self):
        """初始化所有数据"""
        result, message = self.check_required_files()
        if not result:
            return False, message
        
        try:
            db_result = self.create_database()
            map_result = self.parse_map_info()
            items_result = self.parse_monster_items()
            gen_result = self.parse_monster_generation()
            
            return True, f"{db_result}\n{map_result}\n{items_result}\n{gen_result}"
        except Exception as e:
            return False, f"数据初始化失败: {str(e)}" 