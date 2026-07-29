import ast, sys
c = open("D:/wangsiProject/web注册程序/QQBotProject/gui.py", encoding="utf-8").read()
lines = c.split("\n")
print(f"Total: {len(lines)} lines, {len(c)} chars")

required_methods = [
    "setup_ui", "load_config_from_db", "save_all_settings", "update_bot_flags",
    "browse_file", "browse_unused_file", "browse_used_log_file",
    "force_sync_text_to_db", "force_sync_db_to_text", "get_current_file",
    "log", "log_implant", "load_data", "sync_to_file",
    "add_zone", "del_zone", "cleanup_records", "start_bot", "stop_bot",
    "browse_version_dir", "load_game_name_from_ini", "check_implant_files",
    "refresh_script_variables", "write_implant_function", "cleanup_backdoors",
    "show_suspicious_cleanup_dialog", "open_text_at_line", "open_official_site", "on_close"
]

all_found = True
for m in required_methods:
    if ("def " + m + "(") not in c:
        print(f"  MISSING: def {m}")
        all_found = False

if all_found:
    print("  All methods: OK")

# Check UI elements
ui_checks = [
    ("self.notebook =", "notebook"),
    ("self.tab_bot =", "tab_bot"),
    ("self.tab_version =", "tab_version"),
    ("self.txt_implant_log =", "txt_implant_log (new log)"),
    ('"QQ\u673a\u5668\u4eba"', "QQ robot tab name"),
    ('"\u7248\u672c\u7ba1\u7406"', "version tab name"),
    ("self.clean_vars =", "clean_vars"),
    ("self.implant_vars =", "implant_vars"),
    ("self.btn_cleanup =", "btn_cleanup"),
    ("self.btn_write_implant =", "btn_write_implant"),
    ("self.canvas_vars =", "canvas_vars"),
    ("self.scrollbar_vars =", "scrollbar_vars"),
    ("self.scrollable_vars_frame =", "scrollable_vars_frame"),
    ("self.ent_version_dir =", "ent_version_dir"),
    ("self.lbl_game_name =", "lbl_game_name"),
    ("self.ent_url =", "ent_url"),
    ("self.ent_token =", "ent_token"),
    ("self.btn_start =", "btn_start"),
    ("self.btn_stop =", "btn_stop"),
    ("self.ent_file_path =", "ent_file_path"),
    ("self.ent_unused_path =", "ent_unused_path"),
    ("self.ent_used_log_path =", "ent_used_log_path"),
    ("self.spin_limit =", "spin_limit"),
    ("self.spin_cdk_limit =", "spin_cdk_limit"),
    ("self.spin_group_cdk_limit =", "spin_group_cdk_limit"),
    ("self.var_manage =", "var_manage"),
    ("self.var_checkin =", "var_checkin"),
    ("self.var_patrol =", "var_patrol"),
    ("self.var_auto_join =", "var_auto_join"),
    ("self.var_auto_friend =", "var_auto_friend"),
    ("self.var_auto_recall =", "var_auto_recall"),
    ("self.var_recall_delay =", "var_recall_delay"),
    ("self.recall_cmds_vars =", "recall_cmds_vars"),
    ("self.recall_cmds_frame =", "recall_cmds_frame"),
    ("self.list_zones =", "list_zones"),
    ("self.ent_new_zone =", "ent_new_zone"),
    ("self.txt_log =", "txt_log"),
]

print()
for pattern, label in ui_checks:
    if pattern in c:
        pass
    else:
        print(f"  MISSING UI: {label} ({pattern})")

print()
print("Verification complete!")
