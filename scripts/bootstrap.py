"""第一次运行的一键准备（Windows / macOS / Linux 通用）。

做四件事：
1. 安装 Python 依赖；
2. 没有 .env 时从 .env.example 复制一份；
3. 下载七张词表到 data/vocab/；
4. 下载 SenseVoice-Small 模型到 tools/sensevoice/（约 229 MB）。

之后编辑 .env 填 LLM_API_KEY，再运行 run.bat（或 uvicorn）即可。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> None:
    print("\n$", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"命令失败（exit {proc.returncode}）：{' '.join(cmd)}")


def main() -> int:
    py = sys.executable
    print("BILMAGAZINE 第一次准备")
    print("Python:", sys.version.split()[0], py)

    run([py, "-m", "pip", "install", "-r", "requirements.txt"])

    env = ROOT / ".env"
    example = ROOT / ".env.example"
    if not env.exists() and example.exists():
        shutil.copyfile(example, env)
        print("\n已复制 .env.example -> .env；请编辑 .env，至少填 LLM_API_KEY。")
    elif not env.exists():
        print("\n没有找到 .env.example，请手动创建 .env。")

    run([py, "scripts/fetch_vocab.py"])

    model = ROOT / "tools" / "sensevoice" / "model.int8.onnx"
    if model.exists():
        print(f"\n  skip SenseVoice（已存在 {model.stat().st_size / 1e6:.1f} MB）")
    else:
        run([py, "scripts/fetch_models.py"])

    print(
        "\n准备完成。\n"
        "1) 编辑 .env，填 LLM_API_KEY（或把 LLM_PROVIDER 改为 mock 看演示）；\n"
        "2) 双击 run.bat，或运行 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000；\n"
        "3) 打开 http://127.0.0.1:8000/manage。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
