# pip install PyQt6 websockets
# pyinstaller -F --win-private-assemblies QQbot.py
import sys
import json
import asyncio
import websockets
import re
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit,
                             QListWidget, QSpinBox, QMessageBox, QGroupBox, QSplitter)
from PyQt6.QtCore import QThread, pyqtSignal, Qt

DATA_FILE = "bind_records.txt"

# ----------------- 数据读写核心逻辑 -----------------
def read_file_data():
    """读取文本，返回 开区列表(list) 和 注册记录(list)。强制使用 GBK (ANSI) 编码"""
    zones = []
    records = []
    if not os.path.exists(DATA_FILE):
        return zones, records
    try:
        with open(DATA_FILE, 'r', encoding='gbk', errors='replace') as f:
            lines = f.readlines()
            if not lines:
                return zones, records
            
            # 第一行必须是区列表
            first_line = lines[0].strip()
            if first_line.startswith(';区列表:'):
                z_str = first_line.replace(';区列表:', '')
                if z_str:
                    zones = z_str.split('|')
            
            # 读取后续的账号记录
            for line in lines[1:]:
                line = line.strip()
                if line and not line.startswith(';'):
                    records.append(line)
    except Exception as e:
        print(f"读取文件错误: {e}")
    return zones, records

def write_file_data(zones, records):
    """将数据写入文本，保证第一行格式和整体 GBK 编码"""
    try:
        with open(DATA_FILE, 'w', encoding='gbk', errors='replace') as f:
            f.write(f";区列表:{'|'.join(zones)}\n")
            for r in records:
                f.write(f"{r}\n")
        return True
    except Exception as e:
        print(f"写入文件错误: {e}")
        return False

# ----------------- Bot 核心线程 -----------------
class BotThread(QThread):
    log_signal = pyqtSignal(str)

    def __init__(self, ws_url, max_binds):
        super().__init__()
        self.ws_url = ws_url
        self.max_binds = max_binds # 由主界面传入的最大注册数
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

        # 实时读取最新数据
        zones, records = read_file_data()

        # ----------------- 指令：开区列表 -----------------
        if msg_text == "开区列表":
            self.log_signal.emit(f"收到指令 [开区列表] <- QQ:{qq_num}")
            counts = {z: 0 for z in zones}
            for r in records:
                try:
                    acc_zone = r.split('|')[0]
                    zone = acc_zone.split(':')[1]
                    if zone in counts:
                        counts[zone] += 1
                except:
                    pass
            
            if not zones:
                reply = "目前暂无开放的区服。"
            else:
                reply = "【目前开区列表及注册人数】\n"
                for z in zones:
                    reply += f"- {z} : {counts.get(z, 0)}人\n"
            await self.send_private_msg(websocket, qq_num, reply.strip())
            return

        # ----------------- 指令：查下名下账号 -----------------
        if msg_text == "查下名下账号":
            self.log_signal.emit(f"收到指令 [查下名下账号] <- QQ:{qq_num}")
            found = []
            for r in records:
                try:
                    parts = r.split('|')
                    if len(parts) >= 2 and parts[1] == str(qq_num):
                        acc_zone = parts[0]
                        acc, zone = acc_zone.split(':')
                        found.append(f"账号：{acc} ({zone})")
                except:
                    pass
            
            if found:
                reply = "【您名下已绑定的账号】\n" + "\n".join(found)
            else:
                reply = "未查询到您名下有任何绑定记录。"
            await self.send_private_msg(websocket, qq_num, reply)
            return

        # ----------------- 指令：绑定账号 -----------------
        # 正则匹配：绑定(任意区名)，账号：(任意账号)  兼容全半角逗号冒号
        match = re.match(r"^绑定(.+?)[，,]\s*账号[：:](.+)$", msg_text)
        if match:
            zone_name = match.group(1).strip()
            account = match.group(2).strip()
            self.log_signal.emit(f"绑定请求 -> QQ:{qq_num} | 区:{zone_name} | 账号:{account}")
            
            # 1. 检查区服是否存在
            if zone_name not in zones:
                reply = f"绑定失败：【{zone_name}】不存在，请发送“开区列表”查看当前有效区服。"
                await self.send_private_msg(websocket, qq_num, reply)
                return

            # 2. 查重及计算注册次数
            my_binds = 0
            account_registered = False
            
            for r in records:
                try:
                    parts = r.split('|')
                    record_acc_zone = parts[0]
                    record_qq = parts[1]
                    
                    if record_acc_zone == f"{account}:{zone_name}":
                        account_registered = True
                    if record_qq == str(qq_num):
                        my_binds += 1
                except:
                    continue

            if account_registered:
                reply = f"绑定失败：账号【{account}】在【{zone_name}】已被注册过！"
                await self.send_private_msg(websocket, qq_num, reply)
                return

            if my_binds >= self.max_binds:
                reply = f"绑定失败：您的QQ号已达到最大绑定限制（{self.max_binds}次）。"
                await self.send_private_msg(websocket, qq_num, reply)
                return

            # 3. 写入记录 (格式：账号:区名|QQ号|QQ昵称)
            new_record = f"{account}:{zone_name}|{qq_num}|{nickname}"
            records.append(new_record)
            if write_file_data(zones, records):
                success_reply = f"已经成功绑定老登群服~\n绑定内容：账号：{account}，绑定区：{zone_name}，绑定QQ号：{qq_num}，QQ昵称：{nickname}！"
                await self.send_private_msg(websocket, qq_num, success_reply)
                self.log_signal.emit(f"✅ 绑定成功: {new_record}")
            else:
                await self.send_private_msg(websocket, qq_num, "服务器内部错误：无法写入文件。")
                self.log_signal.emit(f"❌ 写入文件失败: {new_record}")
            return

        # ----------------- 未知指令处理 -----------------
        default_reply = (
            "无法识别，如果需要绑定群服账号请发送。绑定XXX区，账号：123123\n"
            "────────────\n"
            "【其他可用命令】\n"
            "▶ 开区列表\n"
            "▶ 查下名下账号"
        )
        await self.send_private_msg(websocket, qq_num, default_reply)
        self.log_signal.emit(f"收到未知指令，已回复提示。内容: {msg_text}")

# ----------------- GUI 主窗口 -----------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("老登群服 - 账号绑定管理中心")
        self.resize(800, 500)
        self.bot_thread = None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # ====== 顶部网络设置区 ======
        network_group = QGroupBox("LLOneBot 连接设置")
        network_layout = QHBoxLayout()
        
        self.url_input = QLineEdit("ws://127.0.0.1:3001")
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("填入 Access Token (选填)")
        
        self.start_btn = QPushButton("启动 Bot")
        self.stop_btn = QPushButton("停止 Bot")
        self.stop_btn.setEnabled(False)

        network_layout.addWidget(QLabel("WS 地址:"))
        network_layout.addWidget(self.url_input, stretch=2)
        network_layout.addWidget(QLabel("Token:"))
        network_layout.addWidget(self.token_input, stretch=1)
        network_layout.addWidget(self.start_btn)
        network_layout.addWidget(self.stop_btn)
        network_group.setLayout(network_layout)
        main_layout.addWidget(network_group)

        # ====== 主体内容区 ======
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, stretch=1)

        # --- 左侧：设置与区服管理 ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 注册上限设置
        limit_layout = QHBoxLayout()
        limit_layout.addWidget(QLabel("每QQ最大注册上限:"))
        self.limit_spinbox = QSpinBox()
        self.limit_spinbox.setRange(1, 100)
        self.limit_spinbox.setValue(2) # 默认2个
        self.limit_spinbox.valueChanged.connect(self.update_max_binds_in_thread)
        limit_layout.addWidget(self.limit_spinbox)
        limit_layout.addStretch()
        left_layout.addLayout(limit_layout)

        # 区服列表管理
        zone_group = QGroupBox("区服列表管理")
        zone_layout = QVBoxLayout()
        
        self.zone_list_widget = QListWidget()
        zone_layout.addWidget(self.zone_list_widget)

        input_layout = QHBoxLayout()
        self.new_zone_input = QLineEdit()
        self.new_zone_input.setPlaceholderText("输入新开区名...")
        self.add_zone_btn = QPushButton("添加")
        input_layout.addWidget(self.new_zone_input)
        input_layout.addWidget(self.add_zone_btn)
        zone_layout.addLayout(input_layout)

        btn_layout = QHBoxLayout()
        self.del_zone_btn = QPushButton("删除选中区服")
        self.refresh_btn = QPushButton("🔃 从文本重新读取")
        btn_layout.addWidget(self.del_zone_btn)
        btn_layout.addWidget(self.refresh_btn)
        zone_layout.addLayout(btn_layout)

        zone_group.setLayout(zone_layout)
        left_layout.addWidget(zone_group)
        splitter.addWidget(left_widget)

        # --- 右侧：运行日志 ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("运行日志:"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        right_layout.addWidget(self.log_output)
        splitter.addWidget(right_widget)

        # 设置左右比例
        splitter.setSizes([300, 500])

        # ====== 绑定事件 ======
        self.start_btn.clicked.connect(self.start_bot)
        self.stop_btn.clicked.connect(self.stop_bot)
        self.add_zone_btn.clicked.connect(self.add_zone)
        self.del_zone_btn.clicked.connect(self.del_zone)
        self.refresh_btn.clicked.connect(self.load_data_to_gui)

        # 初始化读取文本
        self.load_data_to_gui()

    def log(self, text):
        self.log_output.append(text)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # --- 数据交互逻辑 ---
    def load_data_to_gui(self):
        self.zone_list_widget.clear()
        zones, records = read_file_data()
        self.zone_list_widget.addItems(zones)
        self.log(f"已读取数据：当前配置了 {len(zones)} 个区服，共有 {len(records)} 条注册记录。")

    def sync_zones_to_file(self):
        """将 GUI 上的区服列表覆盖写入到文件的第一行"""
        zones = [self.zone_list_widget.item(i).text() for i in range(self.zone_list_widget.count())]
        _, records = read_file_data() # 读取旧记录保留
        if write_file_data(zones, records):
            self.log("配置已更新并保存至文本。")
        else:
            QMessageBox.critical(self, "错误", "无法保存区服列表到文本！")

    def add_zone(self):
        new_zone = self.new_zone_input.text().strip()
        if not new_zone: return
        
        # 查重
        existing = [self.zone_list_widget.item(i).text() for i in range(self.zone_list_widget.count())]
        if new_zone in existing:
            QMessageBox.warning(self, "提示", "该区服已存在！")
            return

        self.zone_list_widget.addItem(new_zone)
        self.new_zone_input.clear()
        self.sync_zones_to_file()

    def del_zone(self):
        selected = self.zone_list_widget.currentRow()
        if selected >= 0:
            self.zone_list_widget.takeItem(selected)
            self.sync_zones_to_file()

    def update_max_binds_in_thread(self, value):
        """动态将限制同步给运行中的 Bot"""
        if self.bot_thread:
            self.bot_thread.max_binds = value

    # --- Bot 启停 ---
    def start_bot(self):
        base_url = self.url_input.text().strip()
        token = self.token_input.text().strip()
        
        # 拼装带 token 的 WS URL
        ws_url = f"{base_url}?access_token={token}" if token else base_url
        
        max_binds = self.limit_spinbox.value()

        self.bot_thread = BotThread(ws_url, max_binds)
        self.bot_thread.log_signal.connect(self.log)
        self.bot_thread.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.url_input.setEnabled(False)
        self.token_input.setEnabled(False)

    def stop_bot(self):
        if self.bot_thread:
            self.bot_thread.stop()
            self.bot_thread.quit()
            self.bot_thread.wait()
        
        self.log("Bot 已停止。")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.url_input.setEnabled(True)
        self.token_input.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())