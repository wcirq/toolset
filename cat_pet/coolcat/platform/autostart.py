from ..runtime import *

# ======================== 开机自启动 ========================
AUTOSTART_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_REG_NAME = "CoolCat"

def _autostart_command():
    """构造注册表里写入的启动命令 (exe 模式直接 exe 路径; 源码模式用 pythonw)"""
    if getattr(sys, "frozen", False):
        # exe: "C:\...\CoolCat.exe"
        exe = os.path.abspath(sys.executable)
        return f'"{exe}"'
    # 源码: pythonw "...\main.py"
    py = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(py):
        py = sys.executable
    return f'"{py}" "{os.path.join(BASE_DIR, "main.py")}"'

def is_autostart_enabled():
    """读取注册表, 返回开机启动是否已开启"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, AUTOSTART_REG_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception as e:
        _log(f"读取开机启动状态失败: {e}")
        return False

def set_autostart(enabled):
    """写入/删除注册表项, 开启/关闭开机启动"""
    try:
        if enabled:
            cmd = _autostart_command()
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, AUTOSTART_REG_NAME, 0, winreg.REG_SZ, cmd)
            _log(f"已开启开机启动: {cmd}")
        else:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, AUTOSTART_REG_NAME)
            except FileNotFoundError:
                pass
            _log("已关闭开机启动")
        return True
    except Exception as e:
        _log(f"设置开机启动失败: {e}")
        return False

__all__ = [name for name in globals() if not name.startswith('__')]
