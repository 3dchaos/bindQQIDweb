import os
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from logic import process_file, save_all
from utils import is_port_in_use

app = Flask(__name__)
app.secret_key = os.urandom(24)

# 全局配置（运行时初始化）
APP_CONFIG = {
    "password": "",
    "file_path": ""
}

# ==================== 后端 API 接口 ====================

@app.route('/admin')
def index():
    return render_template('index.html')

@app.route('/admin/login', methods=['POST'])
def login():
    if request.form.get('password') == APP_CONFIG["password"]:
        session['logged_in'] = True
        return redirect(url_for('index'))
    return render_template('index.html', error="密码不正确")

@app.route('/admin/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

@app.route('/api/get_all')
def api_get_all():
    if not session.get('logged_in'): return jsonify({"error": 1})
    _, servers, records = process_file(APP_CONFIG["file_path"])
    return jsonify({"servers": servers, "records": records})

@app.route('/api/add_record', methods=['POST'])
def api_add_record():
    if not session.get('logged_in'): return jsonify({"error": 1})
    d = request.json
    # 组合规则：账号+服务器|QQ号
    new_line = f"{d['account']}{d['server']}|{d['qq']}"
    
    _, servers, records = process_file(APP_CONFIG["file_path"])
    if new_line in records:
        return jsonify({"success": False, "msg": "该数据已存在，请勿重复注册！"})
    
    records.append(new_line)
    save_all(APP_CONFIG["file_path"], servers, records)
    return jsonify({"success": True})

@app.route('/api/del_record', methods=['POST'])
def api_del_record():
    if not session.get('logged_in'): return jsonify({"error": 1})
    target = request.json.get('line')
    _, servers, records = process_file(APP_CONFIG["file_path"])
    if target in records:
        records.remove(target)
        save_all(APP_CONFIG["file_path"], servers, records)
    return jsonify({"success": True})

@app.route('/api/edit_record', methods=['POST'])
def api_edit_record():
    if not session.get('logged_in'): return jsonify({"error": 1})
    old_line = request.json.get('old')
    new_line = request.json.get('new').strip()
    _, servers, records = process_file(APP_CONFIG["file_path"])
    if old_line in records:
        idx = records.index(old_line)
        records[idx] = new_line
        save_all(APP_CONFIG["file_path"], servers, records)
        return jsonify({"success": True})
    return jsonify({"success": False, "msg": "原记录查找失败"})

@app.route('/api/manage_server', methods=['POST'])
def api_manage_server():
    if not session.get('logged_in'): return jsonify({"error": 1})
    action = request.json.get('action')
    name = request.json.get('name')
    _, servers, records = process_file(APP_CONFIG["file_path"])
    
    if action == 'add' and name not in servers:
        servers.append(name)
    elif action == 'del' and name in servers:
        servers.remove(name)
        
    save_all(APP_CONFIG["file_path"], servers, records)
    return jsonify({"success": True})

# ==================== 程序启动引导 ====================

if __name__ == '__main__':
    print("--- 启动初始化 ---")
    APP_CONFIG["password"] = input("1. 设置系统进入密码: ").strip()
    
    while not APP_CONFIG["file_path"]:
        path = input("2. 输入文本文件路径 (如 db.txt): ").strip()
        if path:
            APP_CONFIG["file_path"] = path

    # 检查并初始化文件
    if not os.path.exists(APP_CONFIG["file_path"]):
        with open(APP_CONFIG["file_path"], 'w', encoding='gbk', errors='replace') as f:
            f.write(";同区版本\n")
            f.write(";区列表:默认一区|默认二区\n")
        print(f"[*] 已创建新文件: {APP_CONFIG['file_path']}")

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
