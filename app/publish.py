"""生成完成后的发布：导出静态站并部署到 Cloudflare Pages。

只在本机运行；依赖已经登录的 wrangler 和可用的 Node.js。
失败不会影响本期杂志本身，调用方只把结果记到运行记录里。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from . import config

ROOT = Path(__file__).resolve().parent.parent


def publish_pages() -> tuple[bool, str]:
    if not config.AUTO_PUBLISH:
        return False, "AUTO_PUBLISH 未开启"

    npx = shutil.which("npx.cmd") or shutil.which("npx") or "npx.cmd"
    steps = [
        [sys.executable, str(ROOT / "scripts" / "export_pages.py")],
        [
            npx,
            "--yes",
            "wrangler@latest",
            "pages",
            "deploy",
            "site",
            "--project-name",
            config.PAGES_PROJECT,
            "--branch",
            config.PAGES_BRANCH,
            "--commit-dirty=true",
        ],
    ]
    logs: list[str] = []
    for cmd in steps:
        try:
            proc = subprocess.run(
                cmd,
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
        except Exception as exc:  # noqa: BLE001 - 发布失败不能让生成流程崩掉
            return False, f"{' '.join(cmd)}: {exc}"
        out = (proc.stdout or "") + (proc.stderr or "")
        logs.append(out.strip()[-1200:])
        if proc.returncode != 0:
            return False, "\n".join(x for x in logs if x)
    return True, (logs[-1] if logs else "published")
