# # 先卸载现有版本
# pip uninstall pyinstaller -y

# # 安装稳定无坑的旧版（兼容性最好）
# pip install pyinstaller==5.13.0

#pyinstaller -F --win-private-assemblies app.py

import os
import threading
import socket
from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for

app = Flask(__name__)
app.secret_key = os.urandom(24)

# 全局配置
APP_PASSWORD = ""
TEXT_FILE_PATH = ""
FILE_LOCK = threading.Lock()

# ==================== 核心逻辑：文件解析与处理 ====================

def process_file():
    """
    读取并解析文件
    返回: (headers_before, server_list, records)
    headers_before: 服务器列表行之前的注释行
    server_list: 提取出来的服务器列表
    records: 注册数据行
    """
    headers_before = []
    server_list = []
    records = []
    
    if not os.path.exists(TEXT_FILE_PATH):
        return headers_before, server_list, records

    with FILE_LOCK:
        try:
            with open(TEXT_FILE_PATH, 'r', encoding='gbk', errors='ignore') as f:
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

def save_all(server_list, records):
    """
    按照格式回写文件，确保编码为 ANSI (GBK)
    """
    # 固定的头部注释，你可以根据需要修改
    default_headers = [";同区版本"] 
    
    with FILE_LOCK:
        try:
            with open(TEXT_FILE_PATH, 'w', encoding='gbk') as f:
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

# ==================== HTML 前端界面 ====================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>游戏注册管理系统</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #eef2f7; padding: 20px; color: #333; }
        .container { max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 15px; box-shadow: 0 8px 30px rgba(0,0,0,0.1); }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #007bff; margin-bottom: 25px; padding-bottom: 10px; }
        .row { display: flex; gap: 20px; margin-bottom: 20px; }
        .col { flex: 1; }
        .box { background: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #dee2e6; }
        h3 { margin-top: 0; font-size: 18px; color: #0056b3; }
        input, select, button { padding: 12px; margin: 8px 0; width: 100%; box-sizing: border-box; border: 1px solid #ccc; border-radius: 6px; font-size: 14px; }
        button { background: #007bff; color: white; border: none; cursor: pointer; font-weight: bold; transition: 0.2s; }
        button:hover { background: #004a9b; }
        .btn-refresh { background: #28a745; width: auto; padding: 10px 20px; margin: 0; }
        .btn-refresh:hover { background: #218838; }
        .btn-danger { background: #dc3545; }
        .btn-edit { background: #ffc107; color: #212529; }
        
        ul { list-style: none; padding: 0; border: 1px solid #ddd; background: #fff; border-radius: 6px; max-height: 450px; overflow-y: auto; }
        li { padding: 12px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
        li:hover { background: #f1f1f1; }
        .record-info { font-family: 'Consolas', monospace; color: #444; }
        .btns { display: flex; gap: 8px; width: 140px; }
        .btns button { padding: 6px; font-size: 12px; margin: 0; }
    </style>
</head>
<body>
    {% if not session.get('logged_in') %}
    <div style="max-width:350px; margin: 150px auto;" class="container">
        <h2 style="text-align:center">管理登录</h2>
        <form method="POST" action="/login">
            <input type="password" name="password" placeholder="请输入系统密码" required>
            <button type="submit">进入系统</button>
            {% if error %}<p style="color:red; text-align:center;">{{ error }}</p>{% endif %}
        </form>
    </div>
    {% else %}
    <div class="container">
        <div class="header">
            <h2 style="margin:0;">注册数据管理面板</h2>
            <div>
                <button class="btn-refresh" onclick="loadData()">🔄 刷新列表</button>
                <a href="/logout" style="margin-left:20px; color:#666; text-decoration:none;">退出登录</a>
            </div>
        </div>
        
        <div class="row">
            <div class="col box">
                <h3>新建注册信息</h3>
                <label>游戏服务器:</label>
                <select id="serverSelect"></select>
                <input type="text" id="acc" placeholder="游戏账号 (必填)">
                <input type="text" id="qq" placeholder="QQ号码 (必填)">
                <button onclick="doRegister()">确认提交</button>
            </div>

            <div class="col box">
                <h3>服务器列表管理</h3>
                <div style="display:flex; gap:5px;">
                    <input type="text" id="newSvr" placeholder="输入新服务器名">
                    <button onclick="addServer()" style="width:80px;">添加</button>
                </div>
                <ul id="serverUl" style="max-height:160px; margin-top:10px;"></ul>
            </div>
        </div>

        <div class="box">
            <h3>已注册数据 (实时读取自文本)</h3>
            <ul id="recordUl"></ul>
        </div>
    </div>

    <script>
        // 获取数据并渲染
        function loadData() {
            fetch('/api/get_all').then(res => res.json()).then(data => {
                // 1. 服务器下拉
                const sel = document.getElementById('serverSelect');
                sel.innerHTML = '<option value="">-- 请选择服务器 --</option>';
                data.servers.forEach(s => {
                    sel.innerHTML += `<option value="${s}">${s}</option>`;
                });

                // 2. 服务器列表管理
                const sUl = document.getElementById('serverUl');
                sUl.innerHTML = '';
                data.servers.forEach(s => {
                    sUl.innerHTML += `<li>${s} <button class="btn-danger" style="width:40px;padding:2px;" onclick="delServer('${s}')">×</button></li>`;
                });

                // 3. 注册数据列表
                const rUl = document.getElementById('recordUl');
                rUl.innerHTML = '';
                data.records.forEach(r => {
                    rUl.innerHTML += `
                        <li>
                            <span class="record-info">${r}</span>
                            <div class="btns">
                                <button class="btn-edit" onclick="editRec('${r}')">修改</button>
                                <button class="btn-danger" onclick="delRec('${r}')">删除</button>
                            </div>
                        </li>`;
                });
            });
        }

        // 注册功能
        function doRegister() {
            const server = document.getElementById('serverSelect').value;
            const account = document.getElementById('acc').value.trim();
            const qq = document.getElementById('qq').value.trim();
            if(!server || !account || !qq) return alert("所有字段均为必填！");

            fetch('/api/add_record', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({server, account, qq})
            }).then(res => res.json()).then(data => {
                if(data.success) {
                    alert("注册成功！");
                    document.getElementById('acc').value = '';
                    document.getElementById('qq').value = '';
                    loadData();
                } else alert(data.msg);
            });
        }

        // 删除数据记录
        function delRec(line) {
            if(!confirm("确定删除此行吗？")) return;
            fetch('/api/del_record', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({line})
            }).then(() => loadData());
        }

        // 修改数据记录
        function editRec(line) {
            const newLine = prompt("请编辑该行文本:", line);
            if(!newLine || newLine === line) return;
            fetch('/api/edit_record', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({old: line, new: newLine})
            }).then(res => res.json()).then(data => {
                if(data.success) loadData(); else alert(data.msg);
            });
        }

        // 管理服务器列表
        function addServer() {
            const name = document.getElementById('newSvr').value.trim();
            if(!name) return;
            fetch('/api/manage_server', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action:'add', name})
            }).then(() => { document.getElementById('newSvr').value=''; loadData(); });
        }

        function delServer(name) {
            fetch('/api/manage_server', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action:'del', name})
            }).then(() => loadData());
        }

        // 初始加载
        loadData();
    </script>
    {% endif %}
</body>
</html>
"""

# ==================== 后端 API 接口 ====================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('password') == APP_PASSWORD:
        session['logged_in'] = True
        return redirect(url_for('index'))
    return render_template_string(HTML_TEMPLATE, error="密码不正确")

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

@app.route('/api/get_all')
def api_get_all():
    if not session.get('logged_in'): return jsonify({"error": 1})
    _, servers, records = process_file()
    return jsonify({"servers": servers, "records": records})

@app.route('/api/add_record', methods=['POST'])
def api_add_record():
    if not session.get('logged_in'): return jsonify({"error": 1})
    d = request.json
    # 组合规则：账号+服务器|QQ号
    new_line = f"{d['account']}{d['server']}|{d['qq']}"
    
    _, servers, records = process_file()
    if new_line in records:
        return jsonify({"success": False, "msg": "该数据已存在，请勿重复注册！"})
    
    records.append(new_line)
    save_all(servers, records)
    return jsonify({"success": True})

@app.route('/api/del_record', methods=['POST'])
def api_del_record():
    if not session.get('logged_in'): return jsonify({"error": 1})
    target = request.json.get('line')
    _, servers, records = process_file()
    if target in records:
        records.remove(target)
        save_all(servers, records)
    return jsonify({"success": True})

@app.route('/api/edit_record', methods=['POST'])
def api_edit_record():
    if not session.get('logged_in'): return jsonify({"error": 1})
    old_line = request.json.get('old')
    new_line = request.json.get('new').strip()
    _, servers, records = process_file()
    if old_line in records:
        idx = records.index(old_line)
        records[idx] = new_line
        save_all(servers, records)
        return jsonify({"success": True})
    return jsonify({"success": False, "msg": "原记录查找失败"})

@app.route('/api/manage_server', methods=['POST'])
def api_manage_server():
    if not session.get('logged_in'): return jsonify({"error": 1})
    action = request.json.get('action')
    name = request.json.get('name')
    _, servers, records = process_file()
    
    if action == 'add' and name not in servers:
        servers.append(name)
    elif action == 'del' and name in servers:
        servers.remove(name)
        
    save_all(servers, records)
    return jsonify({"success": True})

def is_port_in_use(port):
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0
# ==================== 程序启动引导 ====================

if __name__ == '__main__':
    print("--- 启动初始化 ---")
    APP_PASSWORD = input("1. 设置系统进入密码: ").strip()
    
    while not TEXT_FILE_PATH:
        path = input("2. 输入文本文件路径 (如 db.txt): ").strip()
        if path:
            TEXT_FILE_PATH = path

    # 检查并初始化文件
    if not os.path.exists(TEXT_FILE_PATH):
        with open(TEXT_FILE_PATH, 'w', encoding='gbk') as f:
            f.write(";同区版本\n")
            f.write(";区列表:默认一区|默认二区\n")
        print(f"[*] 已创建新文件: {TEXT_FILE_PATH}")

    # --- 端口冲突处理逻辑 ---
    current_port = 5000
    while True:
        if is_port_in_use(current_port):
            print(f"\n[!] 警告: 端口 {current_port} 已被占用。")
            user_input = input(f"请输入新端口号 (直接按回车尝试 {current_port + 1}): ").strip()
            if user_input == "":
                current_port += 1
            else:
                try:
                    current_port = int(user_input)
                except ValueError:
                    print("[!] 输入无效，请输入数字。")
                    continue
        else:
            # 端口可用，尝试启动
            print(f"\n[OK] 端口 {current_port} 可用，正在启动服务...")
            print(f"请在浏览器访问: http://127.0.0.1:{current_port}")
            try:
                # 关闭 debug 模式以确保端口检测逻辑更稳健
                app.run(host='0.0.0.0', port=current_port, debug=False)
                break 
            except Exception as e:
                print(f"[!] 启动失败: {e}")
                current_port += 1 # 发生意外错误时自动跳下一个