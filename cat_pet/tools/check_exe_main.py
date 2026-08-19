# -*- coding: utf-8 -*-
"""检查 CoolCat.exe 内嵌的 main 模块是否包含新的贴边逻辑"""
import os
import sys
from PyInstaller.archive.readers import CArchiveReader

project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
exe = os.path.join(project_dir, "dist", "CoolCat", "CoolCat.exe")
reader = CArchiveReader(exe)
names = list(reader.toc.keys()) if hasattr(reader, "toc") else []
print("TOC entries:", len(names))
target = None
for n in names:
    if "main" in str(n).lower():
        print("found main-ish entry:", n)
        target = n
if target is None:
    sys.exit("no main entry found")

data = reader.extract(str(target))
# data 是 pyc 或 py 源码
try:
    text = data.decode("utf-8", errors="ignore")
    for kw in ["_peek_amount", "半个猫头", "snap_indicator", "cat_scale"]:
        print(kw, "->", kw in text)
except Exception as e:
    print("decode failed:", e)
    for kw in [b"_peek_amount", "\u534a\u4e2a\u732b\u5934".encode("utf-8")]:
        print(kw, "->", kw in data)
