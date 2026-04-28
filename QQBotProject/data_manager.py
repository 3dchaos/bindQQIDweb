import os

def read_file_data(filepath):
    """读取指定路径的文本，返回 开区列表(zones) 和 注册记录(records)"""
    zones, records = [], []
    if not filepath or not os.path.exists(filepath):
        return zones, records
    try:
        with open(filepath, 'r', encoding='gbk') as f:
            lines = f.readlines()
            if not lines: return zones, records
            
            first_line = lines[0].strip()
            if first_line.startswith(';区列表:'):
                z_str = first_line.replace(';区列表:', '')
                if z_str: zones = z_str.split('|')
                
            for line in lines[1:]:
                line = line.strip()
                if line and not line.startswith(';'): 
                    records.append(line)
    except Exception as e:
        print(f"读取文件错误: {e}")
    return zones, records

def write_file_data(filepath, zones, records):
    """将数据写入指定的文本文件，保持 GBK 编码"""
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