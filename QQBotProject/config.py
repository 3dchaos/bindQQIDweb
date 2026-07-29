import os, sys

def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

DB_URL = "sqlite:///qqbot.db"
DEFAULT_BIND_FILE = os.path.join(os.getcwd(), "bind_records.txt")
DEFAULT_WS_URL = "ws://127.0.0.1:3001"
MIR_TEXT_DIR = os.path.join(get_base_dir(), "Mir2Text")
MIR_FUNC_DIR = os.path.join(MIR_TEXT_DIR, "典狱长功能")
DEFAULT_UNUSED_CDK = os.path.join(MIR_FUNC_DIR, "未使用CDK.txt")
DEFAULT_USED_LOG = os.path.join(MIR_FUNC_DIR, "已使用.txt")
