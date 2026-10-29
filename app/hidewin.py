"""Windows 上悄悄跑子进程：不要在用户桌面上弹黑框。

从 pythonw.exe（无控制台）启动的子进程，如果它自己是控制台程序（yt-dlp、
ffmpeg、whisper.cpp、bsk…），Windows 会给它**新开一个控制台窗口**，于是定时任务
一到点，屏幕上就冒出一片黑框，还会抢焦点。

统一从这里拿参数：CREATE_NO_WINDOW 让它根本没有窗口，STARTUPINFO 再把
显示方式设成 SW_HIDE 兜底（CREATE_NO_WINDOW 已足够，双保险防某些启动方式）。
"""

from __future__ import annotations

import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0


def quiet_kwargs() -> dict:
    """传给 subprocess.run / Popen 的隐藏窗口参数（非 Windows 返回空字典）。"""
    if sys.platform != "win32":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= STARTF_USESHOWWINDOW
    si.wShowWindow = SW_HIDE
    return {"creationflags": CREATE_NO_WINDOW, "startupinfo": si}
