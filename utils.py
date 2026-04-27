import socket

def is_port_in_use(port):
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0
