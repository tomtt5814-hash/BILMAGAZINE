"""后台启动入口：给 pythonw 用。

pythonw 没有控制台，sys.stdout 为 None，uvicorn 默认日志处理器会因此启动失败。
这里先把 stdout/stderr 接到日志文件，再关掉 uvicorn 自带的日志配置。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LOG = ROOT / "data" / "server.log"
LOG.parent.mkdir(parents=True, exist_ok=True)

# 从注册表补齐用户级环境变量：无论被启动项、计划任务还是手动拉起，都能拿到 key 与开关
try:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as _k:
        _i = 0
        while True:
            try:
                _name, _value, _ = winreg.EnumValue(_k, _i)
            except OSError:
                break
            if _name and isinstance(_value, str) and _name not in os.environ:
                os.environ[_name] = _value
            _i += 1
except Exception:
    pass

_log = open(LOG, "a", buffering=1, encoding="utf-8", errors="replace")  # noqa: SIM115
sys.stdout = _log
sys.stderr = _log

import uvicorn  # noqa: E402

if __name__ == "__main__":
    print("\n=== start ===", flush=True)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_config=None, access_log=False)
