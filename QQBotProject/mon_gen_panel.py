import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from mon_gen_data import MonGenData

# 可选拖拽支持
try:
    from tkinterdnd2 import DND_FILES
    _HAVE_DND = True
except ImportError:
    DND_FILES = None
    _HAVE_DND = False


class MonGenPanel(ttk.Frame):
    """MonGen.txt 刷怪编辑器嵌入式面板"""

    def __init__(self, parent):
        super().__init__(parent)
        self.data_manager = MonGenData()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.create_widgets()
        self.setup_dnd()

    def setup_dnd(self):
        if _HAVE_DND:
            try:
                self.drop_target_register(DND_FILES)
                self.dnd_bind("<<Drop>>", self.on_file_drop)
            except Exception:
                pass

    def on_file_drop(self, event):
        filepath = event.data.strip("{}")
        self.load_file(filepath)

    def create_widgets(self):
        # ================= 左侧大列表 =================
        left_frame = tk.Frame(self)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(4, 2), pady=4)
        left_frame.rowconfigure(0, weight=1)
        left_frame.columnconfigure(0, weight=1)

        columns = ("行号", "地图代码", "坐标X", "坐标Y", "怪物名称", "范围", "数量", "时间(m)", "优先/其他")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings")

        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=80, anchor=tk.CENTER)

        self.tree.tag_configure("excluded", foreground="#A0A0A0", background="#F0F0F0")
        self.tree.tag_configure("active", foreground="black", background="white")
        self.tree.bind("<ButtonRelease-1>", self.on_tree_select)

        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.grid(row=0, column=0, sticky="nsew")

        # ================= 右侧操作区 =================
        right_frame = tk.Frame(self, width=340)
        right_frame.grid(row=0, column=1, sticky="ns", padx=(2, 4), pady=4)
        right_frame.grid_propagate(False)

        # 1. 文件操作
        file_lf = tk.LabelFrame(right_frame, text="文件操作 (支持拖入 .txt)", padx=8, pady=8)
        file_lf.pack(fill=tk.X, pady=2)
        tk.Button(file_lf, text="加载文件", command=lambda: self.load_file()).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        tk.Button(file_lf, text="保存修改", command=self.save_file).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # 2. 过滤逻辑
        filter_lf = tk.LabelFrame(right_frame, text="过滤逻辑 (三选一模式)", padx=8, pady=8)
        filter_lf.pack(fill=tk.BOTH, expand=True, pady=2)

        self.filter_mode = tk.StringVar(value="none")
        mode_frame = tk.Frame(filter_lf)
        mode_frame.pack(fill=tk.X, pady=2)
        for text, mode in [("不使用规则", "none"), ("仅包含列表", "include"), ("排除列表", "exclude")]:
            tk.Radiobutton(mode_frame, text=text, variable=self.filter_mode,
                           value=mode, command=self.apply_filters).pack(side=tk.LEFT, expand=True)

        input_frame = tk.Frame(filter_lf)
        input_frame.pack(fill=tk.X, pady=2)
        self.filter_field = ttk.Combobox(input_frame, values=["地图代码", "怪物名称"],
                                          state="readonly", width=10)
        self.filter_field.current(1)
        self.filter_field.pack(side=tk.LEFT)
        self.filter_keyword = tk.Entry(input_frame)
        self.filter_keyword.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        tk.Button(filter_lf, text="添加至规则列表", command=self.add_rule,
                  bg="#e6f2ff").pack(fill=tk.X)

        tk.Label(filter_lf, text="当前规则 (严格匹配 | 双击删除):",
                 anchor=tk.W).pack(fill=tk.X, pady=(6, 0))
        self.rule_listbox = tk.Listbox(filter_lf, height=8)
        self.rule_listbox.pack(fill=tk.BOTH, expand=True, pady=2)
        self.rule_listbox.bind("<<ListboxSelect>>", self.on_rule_select)
        self.rule_listbox.bind("<Double-Button-1>", self.remove_rule)
        tk.Button(filter_lf, text="清空所有规则", command=self.clear_rules).pack(fill=tk.X)

        # 3. 批量修改区
        batch_lf = tk.LabelFrame(right_frame, text="批量修改区 (仅修改白底行)", padx=8, pady=8)
        batch_lf.pack(fill=tk.X, pady=2)
        self.setup_batch_widgets(batch_lf)

    def setup_batch_widgets(self, parent):
        v_frame = tk.Frame(parent)
        v_frame.pack(fill=tk.X)
        tk.Label(v_frame, text="数量:").pack(side=tk.LEFT)
        self.mod_count_var = tk.StringVar()
        tk.Entry(v_frame, textvariable=self.mod_count_var, width=8).pack(side=tk.LEFT, padx=4)
        tk.Label(v_frame, text="时间:").pack(side=tk.LEFT, padx=(8, 0))
        self.mod_time_var = tk.StringVar()
        tk.Entry(v_frame, textvariable=self.mod_time_var, width=8).pack(side=tk.LEFT, padx=4)

        self.op_var = tk.StringVar(value="set")
        op_frame = tk.Frame(parent)
        op_frame.pack(fill=tk.X, pady=4)
        for op_text, op_val in [("=赋值", "set"), ("+加", "add"), ("-减", "sub"),
                                 ("*乘", "mul"), ("/除", "div")]:
            tk.Radiobutton(op_frame, text=op_text, variable=self.op_var,
                           value=op_val).pack(side=tk.LEFT)

        chk_frame = tk.Frame(parent)
        chk_frame.pack(fill=tk.X, pady=2)
        self.do_count = tk.BooleanVar(value=False)
        self.do_time = tk.BooleanVar(value=False)
        tk.Checkbutton(chk_frame, text="修改数量",
                       variable=self.do_count).pack(side=tk.LEFT, expand=True)
        tk.Checkbutton(chk_frame, text="修改时间",
                       variable=self.do_time).pack(side=tk.LEFT, expand=True)
        tk.Button(parent, text="执行批量修改", bg="lightblue",
                  command=self.execute_batch).pack(fill=tk.X, pady=6)

    # ---------------- 业务逻辑 ----------------
    def on_tree_select(self, event):
        selected = self.tree.selection()
        if selected:
            vals = self.tree.item(selected[0], "values")
            if len(vals) >= 5:
                self.filter_keyword.delete(0, tk.END)
                if self.filter_field.get() == "地图代码":
                    self.filter_keyword.insert(0, vals[1])
                elif self.filter_field.get() == "怪物名称":
                    self.filter_keyword.insert(0, vals[4])

    def add_rule(self):
        kw = self.filter_keyword.get().strip()
        if kw:
            rule = f"[{self.filter_field.get()}] {kw}"
            if rule not in self.rule_listbox.get(0, tk.END):
                self.rule_listbox.insert(tk.END, rule)
                self.apply_filters()

    def remove_rule(self, event):
        idx = self.rule_listbox.curselection()
        if idx:
            self.rule_listbox.delete(idx)
            self.apply_filters()

    def clear_rules(self):
        self.rule_listbox.delete(0, tk.END)
        self.apply_filters()

    def on_rule_select(self, event):
        idx = self.rule_listbox.curselection()
        if not idx:
            return
        rule_str = self.rule_listbox.get(idx[0])
        self.tree.selection_remove(self.tree.selection())
        for iid in self.tree.get_children():
            row = self.data_manager.lines[int(iid)]
            if row["type"] != "data":
                continue
            kw = rule_str.split("] ")[1].strip()
            target = (row["map"] if "[地图代码]" in rule_str else row["name"]).strip()
            if kw == target:
                self.tree.selection_add(iid)
                self.tree.see(iid)

    def apply_filters(self):
        mode = self.filter_mode.get()
        rules = self.rule_listbox.get(0, tk.END)
        self.tree.selection_remove(self.tree.selection())
        for iid in self.tree.get_children():
            row = self.data_manager.lines[int(iid)]
            if row["type"] != "data":
                continue
            is_matched = False
            for r in rules:
                kw = r.split("] ")[1].strip()
                target = (row["map"] if "[地图代码]" in r else row["name"]).strip()
                if kw == target:
                    is_matched = True
                    break
            if mode == "none":
                is_active = True
            elif mode == "include":
                is_active = is_matched
            else:
                is_active = not is_matched
            self.tree.item(iid, tags=("active" if is_active else "excluded",))

    def load_file(self, path=None):
        if not path:
            path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if path:
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.data_manager.load(path)
            for d in self.data_manager.lines:
                if d["type"] == "data":
                    self.tree.insert("", tk.END, iid=d["id"], tags=("active",), values=(
                        d["id"], d["map"], d["x"], d["y"], d["name"],
                        d["range"], d["count"], d["time"], d["other"]
                    ))
            self.apply_filters()

    def execute_batch(self):
        if not self.do_count.get() and not self.do_time.get():
            return messagebox.showwarning("提示", "请勾选【修改数量】或【修改时间】")
        try:
            mod_cnt = float(self.mod_count_var.get()) if self.do_count.get() else 0
            mod_tm = float(self.mod_time_var.get()) if self.do_time.get() else 0
        except ValueError:
            return messagebox.showerror("错误", "修改值必须是数字！")
        modify_count = 0
        op = self.op_var.get()
        for iid in self.tree.get_children():
            if "excluded" in self.tree.item(iid, "tags"):
                continue
            row_id = int(iid)
            data_row = self.data_manager.lines[row_id]
            if self.do_count.get():
                data_row["count"] = str(self.data_manager.calculate_new_val(
                    data_row["count"], op, mod_cnt))
            if self.do_time.get():
                data_row["time"] = str(self.data_manager.calculate_new_val(
                    data_row["time"], op, mod_tm))
            self.tree.item(iid, values=(
                data_row["id"], data_row["map"], data_row["x"], data_row["y"],
                data_row["name"], data_row["range"], data_row["count"],
                data_row["time"], data_row["other"]))
            modify_count += 1
        messagebox.showinfo("成功", f"成功修改了 {modify_count} 条非灰色状态的记录。")

    def save_file(self):
        if not self.data_manager.lines:
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt")
        if path:
            self.data_manager.save(path)
            messagebox.showinfo("成功", "文件保存成功！")
