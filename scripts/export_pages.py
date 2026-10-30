"""Export the public reading site for Cloudflare Pages.

The generator, dashboard, scheduler and local pipeline stay on this machine.
Only the already generated magazines and the public home page are exported.

Usage:
    python scripts/export_pages.py
    npx wrangler pages deploy site --project-name bilmagazine
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402

from app import store  # noqa: E402

SITE = ROOT / "site"


def _render_home(mags: list[dict]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        autoescape=select_autoescape(("html", "xml")),
    )
    template = env.get_template("index.html")
    html = template.render(
        request=None,
        mags=mags,
        active_run=None,
        public_site=True,
    )
    # Static hosts do not have the FastAPI thumbnail route.
    html = re.sub(r"/magazine-thumb/(\d{4}-\d{2}-\d{2})", r"/thumbs/\1.jpg", html)
    # Use directory indexes for the generated magazine pages.
    html = re.sub(
        r'href="/magazine/(\d{4}-\d{2}-\d{2})(\?v=\d+)?"',
        lambda m: f'href="/magazine/{m.group(1)}/{"?v=" + m.group(2)[3:] if m.group(2) else ""}"',
        html,
    )
    return html


def main() -> int:
    mags = store.list_magazines()
    if not mags:
        print("no magazines found; nothing to export")
        return 1

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "static").mkdir(parents=True)
    (SITE / "thumbs").mkdir(parents=True)
    (SITE / "magazine").mkdir(parents=True)

    (SITE / "index.html").write_text(_render_home(mags), encoding="utf-8")

    for m in mags:
        day = m["day"]
        src = ROOT / "data" / "magazines" / m["file"]
        out = SITE / "magazine" / day / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, out)
        thumb = ROOT / "data" / "magazines" / f"thumb-{day}.jpg"
        if thumb.exists():
            shutil.copyfile(thumb, SITE / "thumbs" / f"{day}.jpg")

    for name in ("app.css", "shell.js"):
        src = ROOT / "static" / name
        if src.exists():
            shutil.copyfile(src, SITE / "static" / name)

    # PWA：manifest 与 service worker 必须放在站点根路径，图标沿用 /static/icons。
    for name in ("manifest.webmanifest", "sw.js", "offline.html"):
        src = ROOT / "static" / name
        if src.exists():
            shutil.copyfile(src, SITE / name)
    icons = ROOT / "static" / "icons"
    if icons.exists():
        shutil.copytree(icons, SITE / "static" / "icons", dirs_exist_ok=True)

    (SITE / "_headers").write_text(
        "/*\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: strict-origin-when-cross-origin\n"
        "  Permissions-Policy: camera=(), microphone=(), geolocation=()\n"
        "  X-Frame-Options: SAMEORIGIN\n"
        "  Content-Security-Policy: frame-ancestors 'self'\n"
        "\n"
        "/sw.js\n"
        "  Cache-Control: no-cache\n"
        "\n"
        "/manifest.webmanifest\n"
        "  Content-Type: application/manifest+json\n"
        "  Cache-Control: public, max-age=3600\n",
        encoding="utf-8",
    )
    (SITE / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    (SITE / "404.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>404</title>'
        '<body style="font:16px/1.6 system-ui;padding:10vh 8vw;background:#08090b;color:#f4f1e8">'
        '<p style="color:#dfff3f;letter-spacing:.16em">BILMAGAZINE / 404</p>'
        '<h1>这一页没有收进存档。</h1><p><a style="color:#dfff3f" href="/">回到首页</a></p>',
        encoding="utf-8",
    )

    print(f"exported {len(mags)} issues -> {SITE}")
    for m in mags:
        print(f"  /magazine/{m['day']}/  {m['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
