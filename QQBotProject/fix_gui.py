import re
c = open("D:/wangsiProject/web注册程序/QQBotProject/gui.py", encoding="utf-8").read()

# Add OFFICIAL_SITE_URL before class definition
# Check if it already exists
if "OFFICIAL_SITE_URL = " not in c and "OFFICIAL_SITE_URL=" not in c:
    c = c.replace("class App:", "OFFICIAL_SITE_URL = \"https://dyznb.com/\"\n\nclass App:")
    print("Added OFFICIAL_SITE_URL")

# Add ttk style configuration for notebook tabs
# Find the setup_ui method and add style config
old_setup = "    def setup_ui(self):\n        # 创建主分页控件\n        self.notebook = ttk.Notebook(self.root)"
new_setup = """    def setup_ui(self):
        # 配置分页样式使标签更明显
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#3a3a3a", borderwidth=2, relief="solid")
        style.configure("TNotebook.Tab", background="#555555", foreground="white",
                        padding=[20, 6], borderwidth=2, font=("", 10, "bold"),
                        relief="raised")
        style.map("TNotebook.Tab",
                   background=[("selected", "#2a7a3a"), ("active", "#666666")],
                   foreground=[("selected", "white")])
        # 创建主分页控件
        self.notebook = ttk.Notebook(self.root)"""

if old_setup in c:
    c = c.replace(old_setup, new_setup, 1)
    print("Updated notebook styling")
else:
    print("Could not find old setup pattern")
    # Try to find what's there
    for line in c.split(chr(10)):
        if "Notebook(self.root)" in line:
            print(f"Found: {line}")

open("D:/wangsiProject/web注册程序/QQBotProject/gui.py", "w", encoding="utf-8").write(c)
print("File updated successfully")
