# BILMAGAZINE

**博主日报杂志** · 把 B 站博主的最新视频，做成一本人愿意读下去的英文小刊。

线上阅读：<https://bilmagazine.pages.dev>  
本机控制台：<http://127.0.0.1:8000/manage>（只绑 `127.0.0.1`，不对外）

## 现在只有两个页面

这套东西已经收敛成很简单的两层：

```text
你的 Windows 电脑
├─ 本地管线：下载 / 转写 / 摘要 / 英文改写 / 词汇标注 / 排版
├─ 本地控制台：http://127.0.0.1:8000/manage
└─ 22:00 定时生成 → 导出静态站 → 自动部署
                 ↓
Cloudflare Pages
└─ 公开阅读站：https://bilmagazine.pages.dev
   （首页 / 往期 / 5 期阅读页 / PWA）
```

- **云端只有一个阅读网页**：静态、只读、可安装，不含控制台，也没有任何后台接口。
- **本地只有一个控制台网页**：订阅、补跑、进度日志、今日预览都在这里；只有这台电脑能打开。
- 生成和转写都在本机完成，音频不上传云端。

## 每天发生什么

1. 从订阅的 B 站 UP 主 / 公众号取最新内容；
2. 本地 SenseVoice-Small 转写；
3. DeepSeek 提炼中文摘要，再改写成英文；
4. 标出 CET-6 / 超纲词，生成双语段落与语境注释；
5. Jinja 渲染成自包含 HTML，封面内联；
6. 导出静态站，自动部署到 Cloudflare Pages。

## 第一次准备

仓库里**不包含** `data/`（你的订阅、已生成杂志、运行日志）、`tools/`（229 MB 转写模型）
和 `.env`（密钥）。换一台电脑或别人 clone 之后，会得到一套干净的代码，但需要重新准备这些。

前提：Windows 10/11、Python 3.10+；如果要部署 Cloudflare，再加 Node.js 18+。

```bash
git clone https://github.com/tomtt5814-hash/BILMAGAZINE.git
cd BILMAGAZINE
python scripts/bootstrap.py
```

`bootstrap.py` 会：

1. 安装 `requirements.txt`；
2. 没有 `.env` 时从 `.env.example` 复制一份；
3. 下载 7 张词表到 `data/vocab/`；
4. 下载 SenseVoice-Small 模型到 `tools/sensevoice/`（约 229 MB）。

然后编辑 `.env`，至少填：

```ini
LLM_API_KEY=sk-...
```

如果你暂时没有 DeepSeek key，可以先把 `LLM_PROVIDER=mock`，再执行一次
`python scripts/seed_demo.py`（需要联网取 3 条样例），然后在控制台点「演示模式」，
先看完整页面和杂志效果；演示内容会标注为预置样例，不是真实新视频。

## 本机怎么跑

```bat
run.bat
```

打开 <http://127.0.0.1:8000/manage>。手动启动也可以：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

如果自动找最新一期时提示 `bsk` 不可用，不代表整站跑不起来：

- 在控制台直接贴 BV 号，可以绕过自动发现；
- 或者配 `BILI_COOKIE`，走接口；
- 下载、转写、生成、阅读都不依赖 `bsk`。

### 不打开 DSH 也常驻

这台电脑上，服务已经在 Windows 启动文件夹注册：

```text
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\BILMAGAZINE Server.vbs
```

它用 `pythonw` 隐藏拉起 `scripts/start_server.py`，登录 Windows 后自动运行。
新机器没有这个 VBS；可以双击 `scripts/start_server.bat` 手动跑，或者把它的快捷方式
放进 `shell:startup`。自动启动不是生成内容的必需项。

默认每天 **22:00** 自动跑一期。前提是电脑不睡眠、服务在跑，并且 Edge 里仍保持 B 站登录
（自动找最新一期要借浏览器的登录态）。

### 生成后自动上线

用户环境变量里设：

```ini
AUTO_PUBLISH=1
```

成功生成一期（非演示模式）后，`app/publish.py` 会依次执行导出和
`npx wrangler pages deploy site --project-name <PAGES_PROJECT> --branch <PAGES_BRANCH>`。
发布失败只会写进运行记录，不会把已经生成的杂志标成失败。

**如果你要部署到自己的 Cloudflare**，必须把 `PAGES_PROJECT` 改成你自己的 Pages 项目名，
不要照抄 `bilmagazine`：`bilmagazine.pages.dev` 已被本项目占用，Pages 子域名不能重复。
在 Cloudflare 控制台或 `npx wrangler pages project create <名字>` 建好项目再部署。

## 配置

优先使用 **Windows 用户级环境变量**，`scripts/start_server.py` 会从注册表补齐：

```ini
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-...
SCHEDULE_ENABLED=1
SCHEDULE_TIME=22:00
AUTO_PUBLISH=1
```

可选：

```ini
# 没有 BILI_COOKIE 时，自动找最新一期走本机浏览器登录态
BILI_COOKIE=SESSDATA=...; bili_jct=...
COMMENTS_ENABLED=1
COMMENTS_TOP_N=5
```

也可以复制 `.env.example` 为 `.env` 做本地覆盖；不要提交真实 key。
`data/` 是运行时数据（订阅、杂志、processed、日志），已被 Git 忽略。

## 云端怎么发布

```bash
python scripts/export_pages.py
npx wrangler pages deploy site --project-name <你的项目名> --branch main
```

第一次需要 `npx wrangler login`，并且要登录**你自己的** Cloudflare 账号。`scripts/export_pages.py` 会导出：

- 首页、各期杂志、封面缩略图；
- `static/app.css`、`static/shell.js`；
- PWA：`manifest.webmanifest`、`sw.js`、`offline.html`、`static/icons/`；
- `robots.txt`、`404.html`、`_headers`。

`site/` 和 `.wrangler/` 不进入 Git。公开站用 `public_site` 渲染，隐藏「订阅 / 控制台 /
生成新一期 / 管理订阅」，只保留阅读、往期和主题切换。

### PWA

从线上站可以「安装到手机主屏」。`sw.js` 缓存应用外壳与访问过的杂志页，断网回落到
`offline.html`；修改缓存策略后记得提升 `static/sw.js` 里的 `VERSION`。

## 目录

```text
app/
  main.py          FastAPI 路由 + APScheduler（22:00）
  runner.py        管线编排、运行记录
  publish.py       导出 site/ 并部署 Pages
  source.py        B 站接口（wbi、视频信息、字幕、封面）
  fetch.py         yt-dlp 音频下载
  transcribe.py    字幕优先 / SenseVoice 转写
  clean.py         转写文本清洗
  llm.py           摘要 / 改写 / 刊名 / 导语
  magazine.py      自包含 HTML 渲染
  store.py         JSON 原子写、订阅、processed、杂志索引
  vocab.py         三层词汇
templates/         index.html、dashboard.html、magazine.html
static/            app.css、shell.js、sw.js、manifest、icons
scripts/           bootstrap.py、fetch_models.py、export_pages.py、start_server.py 等
data/              运行时数据（已忽略）
```

## 内容与阅读

- **三层词汇**：CET-6 蓝色可点；基础词不标；其余长词做超纲细体，中文来自补充词表或 DeepSeek。
- **主题**：首次访问默认白天；导航栏切换白天/黑夜，阅读页跟随全站主题。
- **行宽**：桌面默认 74ch，工具箱可调 56–92ch；手机隐藏行宽滑杆，固定约 30ch 居中。
- **图片**：正文配图（含公众号原文的 GIF）点击进入全屏预览，点遮罩、关闭按钮或 Esc 退出；
  公众号图片会从抓取代理还原成 `mmbiz.qpic.cn` 原图，避免代理拒绝浏览器热链导致整段空白。
  段落开头的公众号表情包会保留为行内小图，不参与放大，避免把正文段落撑成图片段。
- **往期**：5 张 3D 封面卡片持续匀速旋转；鼠标进入暂停，悬停放大、倾斜；手机横向滑动。
- **下一篇**：阅读页右下角显示当前文章数字，点击跳到下一篇，手动滚动时数字同步。
- **交互**：非全屏浮层默认点击外部 / Esc / 再点触发按钮关闭；全屏阅读页与批量开关除外。

## 已知边界

- 自动找最新一期依赖 `bsk` 浏览器登录态；无人值守时若浏览器守护进程启动失败，该源会被跳过，
  但不影响其他源生成和发布。
- 电脑睡眠、退出 B 站登录或服务未启动，22:00 这一期就不会自动生成。
- 公众号按名称搜索会遇到搜狗限流，失败时该次跳过；贴文章链接更稳。
- 云端是纯静态站，不能在线触发补跑；所有生成操作都回本机控制台。

## 分支

- `main`：最终版（当前高动效 + 双主题 + PWA）。
- `纸浆风格版`：早期奶白纸面实验，保留作对照，不再维护。
- `高动效版`：开发分支，内容与 `main` 同步。

## 链接

- 线上：<https://bilmagazine.pages.dev>
- 仓库：<https://github.com/tomtt5814-hash/BILMAGAZINE>
- 本机控制台：<http://127.0.0.1:8000/manage>
