import os
import threading

FILE_LOCK = threading.Lock()

def process_file(file_path):
    """
    读取并解析文件
    返回: (headers_before, server_list, records)
    """
    headers_before = []
    server_list = []
    records = []
    
    if not os.path.exists(file_path):
        return headers_before, server_list, records

    with FILE_LOCK:
        try:
            with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                lines = f.readlines()
                
            found_server_line = False
            for line in lines:
                line = line.strip()
                if not line: continue
                
                if line.startswith(";区列表:"):
                    # 提取服务器：;区列表:区1|区2|区3
                    parts = line.replace(";区列表:", "").split('|')
                    server_list = [p.strip() for p in parts if p.strip()]
                    found_server_line = True
                elif line.startswith(";"):
                    # 其他注释行
                    if not found_server_line:
                        headers_before.append(line)
                else:
                    # 普通注册数据
                    records.append(line)
        except Exception as e:
            print(f"读取错误: {e}")
            
    return headers_before, server_list, records

def save_all(file_path, server_list, records):
    """
    按照格式回写文件，确保编码为 ANSI (GBK)
    """
    default_headers = [";同区版本"] 
    
    with FILE_LOCK:
        try:
            with open(file_path, 'w', encoding='gbk', errors='replace') as f:
                # 1. 写入固定头
                for h in default_headers:
                    f.write(h + "\n")
                
                # 2. 写入服务器列表
                server_line = ";区列表:" + "|".join(server_list)
                f.write(server_line + "\n")
                
                # 3. 写入注册数据
                for r in records:
                    f.write(r + "\n")
            return True
        except Exception as e:
            print(f"写入错误: {e}")
            return False
