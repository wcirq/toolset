from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np

EXAMPLE_PLUGIN = '''import cv2

def process(frame, context):
    """在 BGR 视频帧上绘制；必须返回 HxWx3 uint8 数组。"""
    text = f"SSKJ  {context['frame_index']}"
    cv2.putText(frame, text, (32, 56), cv2.FONT_HERSHEY_SIMPLEX,
                1.0, (80, 213, 183), 2, cv2.LINE_AA)
    return frame
'''


def load_plugin(code: str):
    namespace: dict[str, Any] = {"__name__": "mfvc_user_plugin"}
    compiled = compile(code, "<camera-plugin>", "exec")
    exec(compiled, namespace, namespace)
    function = namespace.get("process")
    if not callable(function):
        raise ValueError("插件必须定义可调用的 process(frame, context) 函数")
    return function


def validate_code(code: str) -> dict[str, Any]:
    try:
        function = load_plugin(code)
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        context = {"frame_index": 0, "timestamp": 0.0, "fps": 30.0,
                   "width": 640, "height": 360}
        result = function(frame, context)
        if not isinstance(result, np.ndarray):
            raise TypeError("process 必须返回 numpy.ndarray")
        if result.dtype != np.uint8 or result.ndim != 3 or result.shape[2] != 3:
            raise ValueError("返回帧必须是 uint8 HxWx3 BGR 数组")
        if result.shape[0] < 1 or result.shape[1] < 1:
            raise ValueError("返回帧尺寸不能为空")
        return {"ok": True, "message": f"验证通过，输出 {result.shape[1]}×{result.shape[0]}"}
    except Exception:
        return {"ok": False, "message": traceback.format_exc()}


def validate_in_subprocess(code: str, timeout: float = 5.0) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mfvc-plugin-") as folder:
        source = Path(folder) / "plugin.py"
        output = Path(folder) / "result.json"
        source.write_text(code, encoding="utf-8")
        command = ([sys.executable, "--validate-plugin", str(source), "--validation-result", str(output)] if getattr(sys, "frozen", False)
                   else [sys.executable, "-m", "mf_virtual_camera.desktop.app",
                         "--validate-plugin", str(source)])
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=timeout,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            return {"ok": False, "message": f"插件验证超过 {timeout:g} 秒，已终止"}
        for _ in range(10):
            if output.exists():
                try:
                    return json.loads(output.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
            time.sleep(0.05)
        if result.returncode == 0 and getattr(sys, "frozen", False):
            return validate_code(code)
        try:
            return json.loads(result.stdout or "")
        except (json.JSONDecodeError, TypeError):
            detail = result.stderr or result.stdout or f"验证进程退出码 {result.returncode}"
            return {"ok": False, "message": detail}
