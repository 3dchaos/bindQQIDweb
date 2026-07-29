import re
import math

class MonGenData:
    def __init__(self):
        self.lines = []

    def load(self, filepath):
        self.lines.clear()
        try:
            with open(filepath, 'r', encoding='gbk') as f:
                content = f.readlines()
        except UnicodeDecodeError:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.readlines()
                
        for i, line in enumerate(content):
            ls = line.strip()
            if not ls or ls.startswith(';'):
                self.lines.append({"type": "comment", "raw": line})
            else:
                parts = re.split(r'\s+', ls)
                while len(parts) < 8: parts.append("0")
                self.lines.append({
                    "type": "data", "id": i,
                    "map": parts[0], "x": parts[1], "y": parts[2], "name": parts[3],
                    "range": parts[4], "count": parts[5], "time": parts[6], "other": " ".join(parts[7:])
                })

    def save(self, filepath):
        with open(filepath, 'w', encoding='gbk') as f:
            for d in self.lines:
                if d["type"] == "comment":
                    f.write(d["raw"])
                else:
                    line = f"{d['map']}\t{d['x']}\t{d['y']}\t{d['name']}\t{d['range']}\t{d['count']}\t{d['time']}\t{d['other']}\n"
                    f.write(line)

    @staticmethod
    def calculate_new_val(original_val, operator, operand):
        val = int(original_val)
        op = float(operand)
        if operator == "set": res = op
        elif operator == "add": res = val + op
        elif operator == "sub": res = val - op
        elif operator == "mul": res = val * op
        elif operator == "div": res = val / op if op != 0 else val
        return max(1, math.floor(res))