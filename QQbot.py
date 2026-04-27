#pip install PyQt6 websockets
import sys
import json
import asyncio
import websockets
import re
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit)
from PyQt6.QtCore import QThread, pyqtSignal

# 模拟的配置数据，你可以根据需要将其做到 GUI 设置或读取配置文件中
VALID_ZONES = ["雷霆一区", "烈焰二区", "光芒三区"] # 严格匹配的区服列表
MAX_BIND_PER_QQ = 2 # 每个QQ号最大绑定次数
DATA_FILE = "bind_records.txt"

class BotThread(QThread):
    log_signal = pyqtSignal(str)

    def __init__(self, ws_url):
        super().__init__()
        self.ws_url = ws_url
        self.running = True
        self.loop = None

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.connect_bot())

    def stop(self):
        self.running = False
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

    async def connect_bot(self):
        self.log_signal.emit(f"正在连接 LLOneBot: {self.ws_url} ...")
        try:
            async with websockets.connect(self.ws_url) as websocket:
                self.log_signal.emit("✅ 成功连接到 LLOneBot WebSocket 服务！")
                while self.running:
                    try:
                        message = await websocket.recv()
                        data = json.loads(message)
                        
                        # 只处理私聊消息
                        if data.get("post_type") == "message" and data.get("message_type") == "private":
                            await self.handle_private_message(websocket, data)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            self.log_signal.emit(f"❌ 连接断开或失败: {e}")

    async def send_private_msg(self, websocket, user_id, text):
        payload = {
            "action": "send_private_msg",
            "params": {
                "user_id": user_id,
                "message": text
            }
        }
        await websocket.send(json.dumps(payload))

    async def handle_private_message(self, websocket, data):
        sender = data.get("sender", {})
        qq_num = sender.get("user_id")
        nickname = sender.get("nickname", "未知昵称")
        msg_text = data.get("raw_message", "").strip()

        # 使用正则解析指令：兼容全角/半角逗号和冒号
        # 格式：绑定XXX区，账号：123123
        match = re.match(r"^绑定(.*?)区[，,]?\s*账号[：:](.+)$", msg_text)

        if match:
            zone_name = match.group(1) + "区"
            account = match.group(2).strip()
            self.log_signal.emit(f"收到绑定请求 -> QQ:{qq_num} 尝试绑定区:{zone_name} 账号:{account}")
            
            # 1. 严格匹配判断区服是否存在
            if zone_name not in VALID_ZONES:
                reply = f"绑定失败：【{zone_name}】不存在，请检查区服名称是否正确。"
                await self.send_private_msg(websocket, qq_num, reply)
                return

            # 2 & 3. 读取本地记录，判断账号是否被注册，以及QQ注册次数限制
            account_registered = False
            qq_bind_count = 0
            
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in lines:
                        line = line.strip()
                        if not line: continue
                        
                        # 格式：账号XXX区|QQ号|QQ昵称
                        try:
                            record_acc_zone, record_qq, record_nick = line.split("|")
                            # 提取记录中的账号和区服
                            # 这里假设记录格式前缀是 "账号"，后缀是区名，例如 "账号123123雷霆一区"
                            # 为严谨起见，直接检查记录中是否包含当前账号和区服的组合
                            expected_record_prefix = f"账号{account}{zone_name}"
                            
                            if expected_record_prefix == record_acc_zone:
                                account_registered = True
                            if str(qq_num) == record_qq:
                                qq_bind_count += 1
                        except ValueError:
                            continue # 忽略格式损坏的行

            if account_registered:
                reply = f"绑定失败：账号【{account}】在【{zone_name}】已被绑定过！"
                await self.send_private_msg(websocket, qq_num, reply)
                return

            if qq_bind_count >= MAX_BIND_PER_QQ:
                reply = f"绑定失败：您的QQ号已达到最大绑定限制（{MAX_BIND_PER_QQ}次）。"
                await self.send_private_msg(websocket, qq_num, reply)
                return

            # 4. 全部条件符合，记录到文本文件
            record_line = f"账号{account}{zone_name}|{qq_num}|{nickname}\n"
            with open(DATA_FILE, "a", encoding="utf-8") as f:
                f.write(record_line)

            # 5. 回复成功消息
            success_reply = f"已经成功绑定老登群服~\n绑定内容：账号：{account}，绑定区：{zone_name}，绑定QQ号：{qq_num}，QQ昵称：{nickname}！"
            await self.send_private_msg(websocket, qq_num, success_reply)
            self.log_signal.emit(f"✅ 绑定成功并已记录: {record_line.strip()}")

        else:
            # 未知发言处理（不是绑定指令）
            # 简单判断一下是不是包含指令关键字，防止群聊混淆，这里仅处理私聊，所以直接回复即可
            default_reply = "无法识别，如果需要绑定群服账号请发送。绑定XXX区，账号：123123"
            await self.send_private_msg(websocket, qq_num, default_reply)
            self.log_signal.emit(f"收到未知指令，已回复提示。内容: {msg_text}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("老登群服 - 账号绑定管理 Bot")
        self.resize(600, 400)
        
        self.bot_thread = None

        # 主控件与布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 顶部设置区
        settings_layout = QHBoxLayout()
        self.url_input = QLineEdit("ws://127.0.0.1:3001")
        self.start_btn = QPushButton("启动 Bot")
        self.stop_btn = QPushButton("停止 Bot")
        self.stop_btn.setEnabled(False)

        settings_layout.addWidget(QLabel("LLOneBot WS 地址:"))
        settings_layout.addWidget(self.url_input)
        settings_layout.addWidget(self.start_btn)
        settings_layout.addWidget(self.stop_btn)

        # 日志区
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)

        main_layout.addLayout(settings_layout)
        main_layout.addWidget(QLabel("运行日志:"))
        main_layout.addWidget(self.log_output)

        # 绑定事件
        self.start_btn.clicked.connect(self.start_bot)
        self.stop_btn.clicked.connect(self.stop_bot)

    def log(self, text):
        self.log_output.append(text)
        # 滚动到底部
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def start_bot(self):
        ws_url = self.url_input.text().strip()
        self.bot_thread = BotThread(ws_url)
        self.bot_thread.log_signal.connect(self.log)
        self.bot_thread.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.url_input.setEnabled(False)

    def stop_bot(self):
        if self.bot_thread:
            self.bot_thread.stop()
            self.bot_thread.quit()
            self.bot_thread.wait()
        
        self.log("Bot 已停止。")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.url_input.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())