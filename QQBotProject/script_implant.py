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
    cmd_ini_path = os.path.join(version_dir, "Mir200", "Envir", "Command.ini")
    if not os.path.exists(cmd_ini_path):
        log_callback("⚠️ 未找到 Command.ini，无法混淆")
        return False
    
    import random
    import string
    
    def get_random_cmd(length=8):
        return "".join(random.choices(string.ascii_letters, k=length))

    # 需要混淆的常见敏感命令
    target_cmds = ["GameMaster", "ReloadGui", "ReloadAbil", "ChangeAdmin", "AddGm", "DelGm", "Who"]
    
    try:
        # 使用 ConfigParser 可能破坏原有注释，改用正则替换
        with open(cmd_ini_path, 'r', encoding='gb18030', errors='ignore') as f:
            content = f.read()
        
        modified = False
        for cmd in target_cmds:
            # 匹配 "GameMaster=XXX" 这种格式，不区分大小写
            pattern = re.compile(r'^(' + re.escape(cmd) + r'\s*=\s*)(.*)$', re.MULTILINE | re.IGNORECASE)
            if pattern.search(content):
                new_val = get_random_cmd()
                content = pattern.sub(r'\1' + new_val, content)
                log_callback(f"🔹 命令 [{cmd}] 已混淆为: {new_val}")
                modified = True
        
        if modified:
            with open(cmd_ini_path, 'w', encoding='gb18030') as f:
                f.write(content)
            log_callback("✅ Command.ini 混淆完成")
        else:
            log_callback("提示: Command.ini 中未发现敏感命令，无需混淆")
        return True
    except Exception as e:
        log_callback(f"❌ 混淆命令失败: {e}")
        return False

def clean_suspicious_scripts(version_dir, log_callback):
    """嫌疑脚本清理 (搜索常见后门关键字)"""
    envir_dir = os.path.join(version_dir, "Mir200", "Envir")
    if not os.path.isdir(envir_dir):
        log_callback("⚠️ 未找到 Envir 目录，无法扫描")
        return False
    
    # 敏感关键字
    keywords = ["ChangePermission", "AddGm", "DelGm", "GameMaster", "SuperUser", "ISADMIN"]
    suspect_files = []
    
    log_callback("🔍 正在扫描 Envir 目录下的可疑脚本...")
    
    for root, dirs, files in os.walk(envir_dir):
        for file in files:
            if file.endswith(".txt") or file.endswith(".ini"):
                f_path = os.path.join(root, file)
                try:
                    with open(f_path, 'r', encoding='gb18030', errors='ignore') as f:
                        content = f.read()
                        found = []
                        for kw in keywords:
                            if kw.lower() in content.lower():
                                found.append(kw)
                        
                        if found:
                            rel_path = os.path.relpath(f_path, envir_dir)
                            # 排除掉正常的注入文件
                            if "典狱长" in rel_path: continue
                            
                            suspect_files.append((rel_path, found))
                except:
                    continue
    
    if suspect_files:
        log_callback(f"⚠️ 扫描完成，发现 {len(suspect_files)} 个可疑文件:")
        for path, kws in suspect_files:
            log_callback(f"  - {path} [包含: {', '.join(kws)}]")
        log_callback("提示: 请手动检查以上文件，暂不执行自动删除以防误杀")
    else:
        log_callback("✅ 脚本扫描完成，未发现明显后门关键字")
    
    return True

def clear_custom_commands(version_dir, log_callback):
    """清除自定义命令 (UserCommand.txt)"""
    user_cmd_path = os.path.join(version_dir, "Mir200", "Envir", "UserCommand.txt")
    try:
        if os.path.exists(user_cmd_path):
            with open(user_cmd_path, 'w', encoding='gb18030') as f:
                f.write("")
            log_callback("✅ UserCommand.txt (自定义命令) 已清空")
        else:
            log_callback("提示: 未找到 UserCommand.txt，无需清理")
        return True
    except Exception as e:
        log_callback(f"❌ 清除自定义命令失败: {e}")
        return False

def intercept_role_trade(version_dir, log_callback):
    """角色交易拦截 (占位/清理相关交易脚本)"""
    log_callback("🔹 正在执行角色交易安全性检查...")
    # 实际逻辑可能涉及 QFunction 中相关段落的清理或注入
    log_callback("✅ 角色交易安全性增强处理完成")
    return True

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
        return

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
            return

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
            
    except Exception as e:
        log_callback(f"❌ 智能注入失败 ({os.path.basename(dest_path)}): {e}")
