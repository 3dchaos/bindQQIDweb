import os

# SQLite 数据库连接 URL
DB_URL = "sqlite:///qqbot.db"

# 默认的私聊注册目录文本路径
DEFAULT_BIND_FILE = os.path.join(os.getcwd(), "bind_records.txt")

# 默认的 WebSocket 连接地址
DEFAULT_WS_URL = "ws://127.0.0.1:3001"