"""测试配置：把项目根加入 sys.path，使 backend 包可被 pytest 导入。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
