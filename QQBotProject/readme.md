QQBotProject/
│
├── config.py         # ⚙️ 配置模块：存放全局常量、数据库路径等
├── data_manager.py   # 💾 数据模块：负责处理 TXT 文件的读写操作
├── bot_core.py       # 🤖 核心模块：专门处理 WebSocket 连接和群/私聊逻辑
├── gui.py            # 🖥️ 界面模块：只负责 Tkinter 界面展示和按钮事件
└── main.py           # 🚀 入口模块：程序的启动点


触发此：授权凭证

pip install websockets dataset pycryptodome
pyinstaller -F -w main.py -n "老登群服管理中心"