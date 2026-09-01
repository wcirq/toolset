from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path


def app_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))


class CameraManager:
    def __init__(self):
        self.root = app_root()
        self.state_file = Path(os.environ.get("APPDATA", Path.home())) / "SSKJCameraStudio" / "instances.json"

    @staticmethod
    def _quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    @classmethod
    def _format_arguments(cls, arguments: list[str]) -> str:
        """Keep PowerShell parameter names executable; quote only their values."""
        parts = []
        for argument in arguments:
            if argument.startswith("-") and argument[1:].isalnum():
                parts.append(argument)
            else:
                parts.append(cls._quote(argument))
        return " ".join(parts)

    def _elevated_script(self, script: str, arguments: list[str]) -> str:
        path = self.root / "scripts" / script
        if not path.exists():
            raise FileNotFoundError(f"安装资源不存在：{path}")
        result_dir = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "SSKJVirtualCamera" / "ui-results"
        log = result_dir / f"admin-{uuid.uuid4().hex}.txt"
        try:
            invocation = "& " + self._quote(str(path)) + " " + self._format_arguments(arguments)
            inner = (
                "$ErrorActionPreference='Stop'; $resultDir=" + self._quote(str(result_dir)) + "; "
                "New-Item -ItemType Directory -Force -Path $resultDir | Out-Null; "
                "& $env:SystemRoot\\System32\\icacls.exe $resultDir /grant "
                "'*S-1-5-32-545:(OI)(CI)M' /T /C | Out-Null; try { " + invocation +
                " *>&1 | Out-File -LiteralPath " + self._quote(str(log)) +
                " -Encoding utf8; if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}; exit 0 } "
                "catch { $_ | Out-String | Out-File -LiteralPath " + self._quote(str(log)) +
                " -Encoding utf8; exit 1 }"
            )
            encoded = base64.b64encode(inner.encode("utf-16-le")).decode("ascii")
            wrapper = (
                "$p=Start-Process powershell.exe -Verb RunAs -Wait -PassThru "
                "-ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand','" +
                encoded + "'); exit $p.ExitCode"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", wrapper], cwd=str(self.root),
                capture_output=True, text=True, errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            try:
                detail = log.read_text(encoding="utf-8-sig", errors="replace") if log.exists() else ""
            except OSError as exc:
                detail = f"管理员操作已结束，但无法读取日志：{exc}"
            if result.returncode:
                fallback = result.stderr.strip() or "用户取消了 UAC，或管理员进程启动失败。"
                raise RuntimeError((detail.strip() or fallback) + f"\n退出码：{result.returncode}")
            return detail.strip()
        finally:
            try:
                log.unlink(missing_ok=True)
            except OSError:
                pass

    def install_primary(self):
        return self._elevated_script("install-dev.ps1", ["-SkipBuild", "-RefreshFrameServer", "-PruneOldVersions"])

    def uninstall_primary(self):
        return self._elevated_script("uninstall-dev.ps1", ["-RefreshFrameServer"])

    def remove_wecom_test(self):
        return self._elevated_script("wecom-enumeration-test.ps1", ["-Remove", "-RefreshFrameServer"])

    def add_instance(self, name: str, instance_id: str):
        output = self._elevated_script("manage-instance.ps1", ["-Name", name, "-InstanceId", instance_id,
                                                               "-RefreshFrameServer"])
        items = self.saved_instances()
        items[instance_id] = name
        self._save(items)
        return output

    def remove_instance(self, name: str, instance_id: str):
        output = self._elevated_script("manage-instance.ps1", ["-Name", name, "-InstanceId", instance_id,
                                                               "-Remove", "-RefreshFrameServer"])
        items = self.saved_instances(); items.pop(instance_id, None); self._save(items)
        return output

    def saved_instances(self) -> dict[str, str]:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, items: dict[str, str]):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_system(self) -> list[str]:
        probe = self.root / "build" / "windows-x64" / "tools" / "frame_probe" / "Release" / "SSKJVirtualCameraProbe.exe"
        if not probe.exists():
            return []
        result = subprocess.run([str(probe), "--list"], capture_output=True, text=True,
                                errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
        import re
        return [re.sub(r"\\u([0-9A-Fa-f]{4})", lambda match: chr(int(match.group(1), 16)), line.strip())
                for line in result.stdout.splitlines() if "Camera" in line or "SSKJ" in line]
