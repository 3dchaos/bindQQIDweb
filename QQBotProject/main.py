import tkinter as tk
from gui import App

if __name__ == "__main__":
    # 创建 Tkinter 主窗口
    root = tk.Tk()
    
    # 实例化我们的应用
    app = App(root)
    
    # 启动界面事件循环
    root.mainloop()