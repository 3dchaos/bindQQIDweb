import os
import sys
import re
import configparser
from mir_script_engine import MirScriptEngine

def get_base_dir():
    """获取程序运行的基础目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

def get_mir_path():
    """获取 Mir2Text 模板目录路径"""
    return os.path.join(get_base_dir(), "Mir2Text")

def check_templates(mir_path, items_to_check):
    """
    检查模板文件是否存在
    :param mir_path: Mir2Text 目录路径
    :param items_to_check: 列表，每个元素为 (显示名称, 文件名/目录名)
    :return: 字典 {显示名称: 是否存在}
    """
    results = {}
    for name, fname in items_to_check:
        f_path = os.path.join(mir_path, fname)
        if name == "功能": # 检查子目录
            results[name] = os.path.isdir(f_path)
        else:
            results[name] = os.path.exists(f_path)
    return results

def get_unified_variables(mir_path, log_callback=None):
    """
    从所有模板文件中提取并去重变量
    """
    if not os.path.exists(mir_path):
        if log_callback: log_callback("❌ 找不到 Mir2Text 目录")
        return {}

    all_files = []
    # QF.txt, QM.txt, 典狱长.txt
    for f in ["QF.txt", "QM.txt", "典狱长.txt"]:
        p = os.path.join(mir_path, f)
        if os.path.exists(p): all_files.append(p)

    # 典狱长功能/*.txt
    func_dir = os.path.join(mir_path, "典狱长功能")
    if os.path.isdir(func_dir):
        for f in os.listdir(func_dir):
            if f.endswith(".txt"):
                all_files.append(os.path.join(func_dir, f))

    unified_vars = {}
    for f_path in all_files:
        try:
            engine = MirScriptEngine(f_path)
            file_vars = engine.get_ui_schema()
            for var_name, def_val in file_vars.items():
                if var_name not in unified_vars or (not unified_vars[var_name] and def_val):
                    unified_vars[var_name] = def_val
        except Exception as e:
            if log_callback: log_callback(f"⚠️ 解析文件 {os.path.basename(f_path)} 失败: {e}")

    return unified_vars

def get_game_name(version_dir, log_callback=None):
    """从 Config.ini 中读取游戏名称"""
    ini_path = os.path.join(version_dir, "Config.ini")
    if os.path.exists(ini_path):
        try:
            cp = configparser.ConfigParser()
            try:
                cp.read(ini_path, encoding="gbk")
            except:
                cp.read(ini_path, encoding="utf-8")

            return cp.get("GameConf", "GameName", fallback="未知")
        except Exception as e:
            if log_callback: log_callback(f"⚠️ 读取 Config.ini 异常: {e}")
            return "读取失败"
    return "找不到 Config.ini"

def implant_scripts(version_dir, mir_path, user_inputs, log_callback, selected_items=None):
    """执行脚本注入核心逻辑"""
    if selected_items is None:
        selected_items = ["QF", "QM", "NPC", "功能"]

    try:
        # 1. QFunction-0.txt 注入
        if "QF" in selected_items:
            qf_dest = os.path.join(version_dir, "Mir200", "Envir", "Market_Def", "QFunction-0.txt")
            if os.path.exists(qf_dest):
                try:
                    qf_engine = MirScriptEngine(os.path.join(mir_path, "QF.txt"))
                    qf_content = qf_engine.build_script_content(user_inputs)
                    smart_implant_to_file(qf_dest, qf_content, log_callback)
                    log_callback("✅ QFunction-0.txt 智能注入成功")
                except Exception as e:
                    log_callback(f"❌ QFunction-0.txt 注入异常: {e}")

        # 2. QManage.txt 注入
        if "QM" in selected_items:
            qm_dest = os.path.join(version_dir, "Mir200", "Envir", "MapQuest_def", "QManage.txt")
            if os.path.exists(qm_dest):
                try:
                    qm_engine = MirScriptEngine(os.path.join(mir_path, "QM.txt"))
                    qm_content = qm_engine.build_script_content(user_inputs)
                    smart_implant_to_file(qm_dest, qm_content, log_callback)
                    log_callback("✅ QManage.txt 智能注入成功")
                except Exception as e:
                    log_callback(f"❌ QManage.txt 注入异常: {e}")

        # 3. 典狱长.txt 替换
        if "NPC" in selected_items:
            npc_dest = os.path.join(version_dir, "Mir200", "Envir", "Market_Def", "典狱长.txt")
            npc_src = os.path.join(mir_path, "典狱长.txt")
            if os.path.exists(npc_src):
                try:
                    npc_engine = MirScriptEngine(npc_src)
                    npc_engine.build_script(user_inputs, npc_dest)
                    log_callback("✅ 典狱长.txt (NPC) 写入成功")
                except PermissionError:
                    log_callback("❌ 典狱长.txt 写入失败: 文件被占用")
                except Exception as e:
                    log_callback(f"❌ 典狱长.txt 写入异常: {e}")

        # 4. 典狱长功能目录替换
        if "功能" in selected_items:
            func_dest_dir = os.path.join(version_dir, "Mir200", "Envir", "QuestDiary", "典狱长功能")
            func_src_dir = os.path.join(mir_path, "典狱长功能")
            if os.path.isdir(func_src_dir):
                if not os.path.exists(func_dest_dir):
                    os.makedirs(func_dest_dir)

                for f_name in os.listdir(func_src_dir):
                    if f_name.endswith(".txt"):
                        src_f = os.path.join(func_src_dir, f_name)
                        dest_f = os.path.join(func_dest_dir, f_name)
                        try:
                            f_engine = MirScriptEngine(src_f)
                            f_engine.build_script(user_inputs, dest_f)
                        except PermissionError:
                            log_callback(f"⚠️ 拒绝访问 (文件被占用): {f_name}，已跳过")
                        except Exception as e:
                            log_callback(f"⚠️ 同步文件 {f_name} 失败: {e}")

                log_callback("✅ 典狱长功能 目录同步完成 (增量覆盖模式)")

        return True

    except Exception as e:
        log_callback(f"❌ 注入失败: {e}")
        import traceback
        log_callback(traceback.format_exc())
        return False

def clear_gm_list(version_dir, log_callback):
    """清理 GM 列表 (AdminList.txt)"""
    admin_list_path = os.path.join(version_dir, "Mir200", "Envir", "AdminList.txt")
    try:
        if os.path.exists(admin_list_path):
            with open(admin_list_path, 'w', encoding='gb18030') as f:
                f.write("") # 清空
            log_callback("✅ AdminList.txt 已清空")
        else:
            log_callback("⚠️ 未找到 AdminList.txt，无需清理")
        return True
    except Exception as e:
        log_callback(f"❌ 清理 GM 列表失败: {e}")
        return False

def obfuscate_gm_commands(version_dir, log_callback):
    """混淆 GM 命令 (Command.ini)"""
    # 优先使用 Mir200 根目录下的 Command.ini
    cmd_ini_path = os.path.join(version_dir, "Mir200", "Command.ini")
    if not os.path.exists(cmd_ini_path):
        # 兼容性检查 Envir 目录
        alt_path = os.path.join(version_dir, "Mir200", "Envir", "Command.ini")
        if os.path.exists(alt_path):
            cmd_ini_path = alt_path
        else:
            log_callback("⚠️ 未找到 Command.ini，无法混淆")
            return False

    import random
    import string
    import shutil

    def get_random_cmd(length=13):
        return "".join(random.choices(string.ascii_letters + string.digits, k=length))

    try:
        # 备份原始文件
        backup_path = os.path.join(os.path.dirname(cmd_ini_path), "Command备份.ini")
        try:
            shutil.copy2(cmd_ini_path, backup_path)
            log_callback(f"🔹 已创建备份: {os.path.basename(backup_path)}")
        except Exception as e:
            log_callback(f"⚠️ 备份失败 (尝试继续): {e}")

        with open(cmd_ini_path, 'r', encoding='gb18030', errors='ignore') as f:
            lines = f.readlines()

        new_lines = []
        in_command_section = False
        obfuscated_count = 0

        for line in lines:
            stripped = line.strip()
            # 识别段落头部
            if stripped.startswith('[') and stripped.endswith(']'):
                if stripped.lower() == '[command]':
                    in_command_section = True
                else:
                    in_command_section = False
                new_lines.append(line)
                continue

            # 如果在 [Command] 段落内，且行包含 '=' 且不以分号开头（非注释）
            if in_command_section and '=' in line and not stripped.startswith(';'):
                # 分割 Key 和 Value
                parts = line.split('=', 1)
                key = parts[0]
                # 生成 13 位随机乱码 (字母+数字)
                new_val = get_random_cmd()
                # 拼接回行，注意保留原始换行符
                newline_char = "\n" if line.endswith("\n") else ""
                new_lines.append(f"{key}={new_val}{newline_char}")
                obfuscated_count += 1
            else:
                new_lines.append(line)

        if obfuscated_count > 0:
            with open(cmd_ini_path, 'w', encoding='gb18030') as f:
                f.writelines(new_lines)
            log_callback(f"✅ Command.ini 混淆完成 (路径: Mir200), 共处理 {obfuscated_count} 个项目")
        else:
            log_callback("提示: Command.ini 中未发现 [Command] 节点或有效指令")

        return True
    except Exception as e:
        log_callback(f"❌ 混淆命令异常: {e}")
        return False

# 嫌疑关键字列表
SUSPICIOUS_KEYWORDS = [
    "CHANGEPERMISSION", "SETPERMISSION", "GMEXECUTE", "CHANGEMODE",
    "<$PASSWORD>", "<$BIRTHDAY>", "<$ACCOUNTUSERNAME>", "<$QUIZ1>",
    "<$ANSWER1>", "<$QUIZ2>", "<$ANSWER2>", "<$PHONE>",
    "<$MOBILEPHONE>", "<$EMAIL>", "[A,B,C", "$sjkk-1"
]
SUSPICIOUS_CLEANED_MARKER = "Suspicious script segment removed"

BINARY_EXTENSIONS = {
    ".bmp", ".dat", ".db", ".dll", ".exe", ".gif", ".idx", ".jpg", ".jpeg",
    ".map", ".png", ".rle", ".so", ".wav", ".wil", ".wis", ".wix", ".zip"
}

def _read_text_lines(file_path):
    """读取传奇脚本文本，兼容 UTF-8 和 Windows ANSI/GBK 系编码。"""
    try:
        with open(file_path, 'rb') as f:
            raw = f.read()
    except Exception:
        return None, None

    encodings = []
    if raw.startswith(b'\xef\xbb\xbf'):
        encodings.append('utf-8-sig')
    elif any(byte >= 0x80 for byte in raw):
        encodings.extend(('utf-8', 'gb18030', 'mbcs'))
    else:
        encodings.append('gb18030')

    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            return text.splitlines(True), encoding
        except (UnicodeDecodeError, LookupError):
            continue

    try:
        text = raw.decode('gb18030', errors='ignore')
        return text.splitlines(True), 'gb18030'
    except Exception:
        return None, None

def _is_probably_text_file(file_name):
    return os.path.splitext(file_name)[1].lower() not in BINARY_EXTENSIONS

def _find_suspicious_keywords(content):
    if SUSPICIOUS_CLEANED_MARKER.lower() in content.lower():
        return []

    lower_content = content.lower()
    return [kw for kw in SUSPICIOUS_KEYWORDS if kw.lower() in lower_content]

def scan_for_suspicious_segments(version_dir, log_callback):
    """扫描嫌疑脚本段落，返回结构化数据"""
    envir_dir = os.path.join(version_dir, "Mir200", "Envir")
    if not os.path.isdir(envir_dir):
        log_callback("⚠️ 未找到 Envir 目录，扫描中止")
        return []

    results = []
    log_callback("🔍 正在深度扫描脚本段落...")

    for root, dirs, files in os.walk(envir_dir):
        for file in files:
            if not _is_probably_text_file(file):
                continue

            f_path = os.path.join(root, file)
            rel_path = os.path.relpath(f_path, envir_dir)

            # 排除掉自己注入的文件
            if "典狱长" in rel_path:
                continue

            try:
                lines, encoding = _read_text_lines(f_path)
                if lines is None:
                    continue

                # 分段解析
                current_seg_name = "Global/Header"
                current_seg_lines = []
                current_start_line = 1

                def check_and_add(name, lines_list, path, start_line):
                    content = "".join(lines_list)
                    matched_keywords = _find_suspicious_keywords(content)
                    if matched_keywords:
                        results.append({
                            'path': path,
                            'rel_path': os.path.relpath(path, envir_dir),
                            'segment': name,
                            'content': content,
                            'keyword': matched_keywords[0],
                            'keywords': matched_keywords,
                            'start_line': start_line,
                            'end_line': start_line + len(lines_list) - 1,
                            'encoding': encoding
                        })

                for index, line in enumerate(lines, start=1):
                    stripped = line.strip()
                    # 识别段落开始 [@Name] 或 [QuestNo]
                    if stripped.startswith('[') and stripped.endswith(']'):
                        # 先检查上一个段落
                        if current_seg_lines:
                            check_and_add(current_seg_name, current_seg_lines, f_path, current_start_line)

                        current_seg_name = stripped
                        current_seg_lines = [line]
                        current_start_line = index
                    else:
                        current_seg_lines.append(line)

                # 检查最后一个段落
                if current_seg_lines:
                    check_and_add(current_seg_name, current_seg_lines, f_path, current_start_line)

            except Exception as e:
                log_callback(f"⚠️ 扫描文件失败，已跳过: {rel_path} ({e})")

    log_callback(f"✅ 扫描完成，共发现 {len(results)} 处嫌疑代码段")
    return results

def delete_script_segments(targets, log_callback):
    """
    删除指定的脚本段落
    targets: [{path, segment, content}, ...]
    """
    # 按文件分组处理，避免重复读写
    file_groups = {}
    for t in targets:
        if t['path'] not in file_groups:
            file_groups[t['path']] = []
        file_groups[t['path']].append(t)

    success_count = 0
    for f_path, segs in file_groups.items():
        try:
            lines, encoding = _read_text_lines(f_path)
            if lines is None:
                log_callback(f"❌ 无法读取文件，已跳过: {os.path.basename(f_path)}")
                continue

            modified = False
            ordered_segs = sorted(segs, key=lambda item: item.get('start_line', 0), reverse=True)
            for s in ordered_segs:
                start = int(s.get('start_line', 0)) - 1
                end = int(s.get('end_line', 0))
                if start < 0 or end <= start or end > len(lines):
                    log_callback(f"⚠️ 行号已变化，跳过: {os.path.basename(f_path)} {s.get('segment', '')}")
                    continue

                current_content = "".join(lines[start:end])
                matched_keywords = _find_suspicious_keywords(current_content)
                if matched_keywords:
                    marker = f"; --- {SUSPICIOUS_CLEANED_MARKER} ---\n"
                    lines[start:end] = [marker]
                    modified = True
                    success_count += 1
                else:
                    log_callback(f"⚠️ 段落内容已变化，跳过: {os.path.basename(f_path)} {s.get('segment', '')}")

            if modified:
                with open(f_path, 'w', encoding=encoding or 'gb18030', newline='') as f:
                    f.writelines(lines)
                log_callback(f"🛡️ 已处理文件: {os.path.basename(f_path)}")

        except Exception as e:
            log_callback(f"❌ 处理文件 {os.path.basename(f_path)} 失败: {e}")

    return success_count

def clear_custom_commands(version_dir, log_callback):
    """清除自定义命令 (UserCmd.txt, UserCmds.txt)"""
    envir_dir = os.path.join(version_dir, "Mir200", "Envir")
    targets = ["UserCmd.txt", "UserCmds.txt", "UserCommand.txt"]

    success = True
    found_any = False

    for filename in targets:
        f_path = os.path.join(envir_dir, filename)
        if os.path.exists(f_path):
            try:
                with open(f_path, 'w', encoding='gb18030') as f:
                    f.write("")
                log_callback(f"✅ {filename} (自定义命令) 已清空")
                found_any = True
            except Exception as e:
                log_callback(f"❌ 清除 {filename} 失败: {e}")
                success = False

    if not found_any:
        log_callback("提示: 未发现任何自定义命令配置文件 (UserCmd/UserCmds)，无需清理")

    return success

def intercept_role_trade(version_dir, log_callback):
    """将角色交易拦截脚本注入 QFunction-0.txt"""
    mir_path = get_mir_path()
    template_path = os.path.join(mir_path, "QF拦截角色交易.txt")
    qf_dest = os.path.join(version_dir, "Mir200", "Envir", "Market_Def", "QFunction-0.txt")

    log_callback("🔹 正在注入角色交易拦截脚本...")

    if not os.path.exists(template_path):
        log_callback(f"❌ 未找到角色交易拦截模板: {template_path}")
        return False

    if not os.path.exists(qf_dest):
        log_callback(f"❌ 未找到 QFunction-0.txt，无法注入: {qf_dest}")
        return False

    try:
        template_lines, _ = _read_text_lines(template_path)
        if template_lines is None:
            log_callback(f"❌ 无法读取角色交易拦截模板: {template_path}")
            return False
        template_content = "".join(template_lines)

        if not smart_implant_to_file(qf_dest, template_content, log_callback):
            return False
        log_callback("✅ 角色交易拦截脚本已注入 QFunction-0.txt")
        return True
    except Exception as e:
        log_callback(f"❌ 角色交易拦截脚本注入失败: {e}")
        return False

def smart_implant_to_file(dest_path, built_content, log_callback):
    """
    智能注入逻辑：支持 追加、指定段落头部植入、指定段落覆盖。
    协议格式:
    - 追加: ;=== 描述开始 === ... ;=== 描述结束 ===
    - 植入: ;=== 植入@段名=描述开始 === ... ;=== 植入@段名=描述结束 ===
    - 覆盖: ;=== 覆盖@段名=描述开始 === ... ;=== 覆盖@段名=描述结束 ===
    """
    if not os.path.exists(dest_path):
        log_callback(f"⚠️ 目标文件不存在，无法注入: {os.path.basename(dest_path)}")
        return False

    try:
        with open(dest_path, 'r', encoding='gb18030', errors='ignore') as f:
            target_content = f.read()

        # 1. 提取所有协议块
        # 匹配 ;==== 描述开始 ==== ... ;==== 描述结束 ====
        # 分组1: 完整块(含标记); 分组2: 指令内容(描述)
        block_pattern = re.compile(r'(;[=]{10,}(.*?)开始[=]{10,}.*?;[=]{10,}\2结束[=]{10,})', re.DOTALL)
        blocks = block_pattern.findall(built_content)

        if not blocks:
            log_callback(f"⚠️ 模板内未发现协议标记，跳过智能注入: {os.path.basename(dest_path)}")
            return False

        for full_block, instruction in blocks:
            # a. 先清理掉旧的同名块 (根据标记描述识别)
            clean_pattern = re.escape(";") + r"[=]{10,}" + re.escape(instruction) + r"开始[=]{10,}.*?" + re.escape(";") + r"[=]{10,}" + re.escape(instruction) + r"结束[=]{10,}"
            target_content = re.sub(clean_pattern, "", target_content, flags=re.DOTALL)

            # b. 解析指令
            action = "追加"
            segment = None

            # 匹配 "植入@Login=..." 或 "覆盖@Help=..."
            m = re.match(r"(植入|覆盖)@([^=]+)=", instruction)
            if m:
                action = m.group(1)
                segment = m.group(2).strip()

            # c. 执行动作
            full_block_str = full_block.strip()
            if action == "覆盖" and segment:
                # 覆盖模式: 替换掉 [@段名] 及其后续内容直到下一个段落 (增强识别：支持 [ @段名 ] 等变体)
                seg_pattern = re.compile(r'^\[\s*@\s*' + re.escape(segment) + r'\s*\]\s*.*?(?=^\[\s*@|\Z)', re.MULTILINE | re.DOTALL | re.IGNORECASE)
                if seg_pattern.search(target_content):
                    target_content = seg_pattern.sub(full_block_str + "\n", target_content, count=1)
                else:
                    target_content = target_content.strip() + "\n\n" + full_block_str
            elif action == "植入" and segment:
                # 植入模式: 在 [@段名] 头部插入 (紧跟在头部行之后) (增强识别：支持 [ @段名 ] 等变体)
                header_pattern = re.compile(r'^\[\s*@\s*' + re.escape(segment) + r'\s*\]', re.MULTILINE | re.IGNORECASE)
                if header_pattern.search(target_content):
                    target_content = header_pattern.sub(f"[@{segment}]\n{full_block_str}", target_content, count=1)
                else:
                    # 找不到段落则新建
                    target_content = target_content.strip() + "\n\n" + f"[@{segment}]\n" + full_block_str
            else:
                # 追加模式: 默认追加到文件末尾
                target_content = target_content.strip() + "\n\n" + full_block_str

        # 写入文件
        with open(dest_path, 'w', encoding='gb18030') as f:
            f.write(target_content.strip() + "\n")

        return True
    except Exception as e:
        log_callback(f"❌ 智能注入失败 ({os.path.basename(dest_path)}): {e}")
        return False
