"""modules 级 conftest：确保根目录在 sys.path 中。

子目录测试文件的 ``from conftest import next_seq`` 等导入需要根 nb-tests/
在 sys.path 中；pytest 只自动添加测试文件的直接父目录。
"""

import sys
from pathlib import Path

# 把 nb-tests/ 根目录加到 sys.path，使 "from conftest import ..." 指向根 conftest。
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
