import re
import os

class MirScriptEngine:
    """
    传奇脚本深度解析与模板注入引擎
    支持: 消除脏字符、构建AST逻辑块、提取自定义 *变量*、精准替换与重构。
    """
    def __init__(self, file_path):
        self.file_path = file_path
        # AST 存储结构: { "Login": [ {"type": "#ACT", "lines": [...]}, ... ] }
        self.ast = {} 
        self.ui_variables = {} # 存储提取出的 UI 模板变量
        
        # 严格正则：匹配 *变量名* 或 *变量名=默认值* # 限制内部不能有空格，防止误伤引擎原生的乘法运算 (例如 N1 * 10)
        self.var_pattern = re.compile(r'\*([a-zA-Z0-9_\u4e00-\u9fa5]+(?:=[^*]+)?)\*')

        self._parse()

    def _parse(self):
        """核心解析逻辑：读取文件并构建 AST"""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"找不到指定的脚本文件: {self.file_path}")

        with open(self.file_path, 'r', encoding='gb18030', errors='ignore') as f:
            lines = f.readlines()

        current_segment = "Global"
        current_block = "None"
        self.ast[current_segment] = []
        
        current_block_data = {"type": current_block, "lines": []}

        for line in lines:
            clean_line = line.strip()
            
            # 1. 忽略空行和分号注释 (保留界限标记)
            if not clean_line:
                continue
            if clean_line.startswith(';') and not clean_line.startswith(';==='):
                continue
                
            # 2. 压缩多余的空格和制表符
            clean_line = re.sub(r'\s+', ' ', clean_line)

            # 3. 提取并记录所有的 Python 自定义变量 (用于UI生成)
            self._extract_variables(clean_line)

            # 4. 识别 [@代码段]
            segment_match = re.match(r'^\[@(.*?)\]$', clean_line)
            if segment_match:
                # 保存上一个块
                if current_block_data["lines"]:
                    self.ast[current_segment].append(current_block_data)
                    
                current_segment = segment_match.group(1)
                self.ast[current_segment] = []
                current_block = "None"
                current_block_data = {"type": current_block, "lines": []}
                continue

            # 5. 识别逻辑控制块 (#IF, #ACT, #SAY, #ELSEACT, #ELSESAY)
            if clean_line.upper() in ["#IF", "#ACT", "#SAY", "#ELSEACT", "#ELSESAY"]:
                # 保存上一个块
                if current_block_data["lines"] or current_block_data["type"] != "None":
                    self.ast[current_segment].append(current_block_data)
                
                current_block = clean_line.upper()
                current_block_data = {"type": current_block, "lines": []}
                continue

            # 6. 常规指令压入当前逻辑块
            current_block_data["lines"].append(clean_line)

        # 循环结束后，保存最后一个块
        if current_block_data["lines"] or current_block_data["type"] != "None":
            self.ast[current_segment].append(current_block_data)


    def _extract_variables(self, line):
        """静默提取脚本中声明的模板变量"""
        matches = self.var_pattern.findall(line)
        for match in matches:
            if '=' in match:
                var_name, default_val = match.split('=', 1)
                self.ui_variables[var_name] = default_val
            else:
                if match not in self.ui_variables:
                    self.ui_variables[match] = ""


    def get_ui_schema(self):
        """返回给前端或 Web 框架渲染用的变量字典"""
        return self.ui_variables


    def build_script_content(self, user_inputs):
        """
        根据用户输入的字典，替换 AST 中的变量，并重构为标准传奇脚本字符串
        """
        def replacer(match):
            inner_text = match.group(1)
            if '=' in inner_text:
                var_name, default_val = inner_text.split('=', 1)
            else:
                var_name, default_val = inner_text, ""

            # 用户输入优先 -> 默认值兜底 -> 抛出异常
            if var_name in user_inputs and str(user_inputs[var_name]).strip() != "":
                return str(user_inputs[var_name]).strip()
            elif default_val != "":
                return default_val
            else:
                return f"*{inner_text}*" # 如果都没找到，保留原样 (或者报错)
                # raise ValueError(f"编译错误：模板变量 '{var_name}' 缺失实际赋值且无默认值！")

        # 重构脚本字符串
        final_script_lines = []
        
        for segment_name, blocks in self.ast.items():
            if segment_name != "Global":
                injected_segment = self.var_pattern.sub(replacer, segment_name)
                final_script_lines.append(f"\n[@{injected_segment}]")
                
            for block in blocks:
                if block["type"] != "None":
                    final_script_lines.append(block["type"])
                
                for line in block["lines"]:
                    # 执行注入替换
                    injected_line = self.var_pattern.sub(replacer, line)
                    final_script_lines.append(injected_line)

        return "\n".join(final_script_lines)


    def build_script(self, user_inputs, output_path):
        """
        根据用户输入的字典，替换 AST 中的变量，并重构为标准传奇脚本格式
        """
        content = self.build_script_content(user_inputs)
        # 输出为引擎可识别的 GB18030 编码文本 (兼容 GBK/GB2312)
        with open(output_path, 'w', encoding='gb18030', errors='ignore') as f:
            f.write(content)
            
        return True