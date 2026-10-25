# 博主日报杂志

把选定的 B 站博主的最新一期视频，自动变成一本英文科普小刊：
**下载 → 转写 → 清洗 → 中文摘要 → 六级词汇密度的英文科普短文 → 杂志风格 HTML**。

跑在本机 `localhost`，无服务器、无域名、无数据库。

---

## 现在能跑到哪一步

| 环节 | 状态 |
|---|---|
| 订阅管理 / 手动 BV / 历史 / 预览 | ✅ 可用 |
| 22:30 定时 + 补跑 | ✅ 可用 |
| `processed.json` 去重（原子写 + 损坏自愈） | ✅ 可用 |
| 单视频元信息 / 封面下载 | ✅ 可用（免登录） |
| 杂志渲染（自包含 HTML，封面内联） | ✅ 可用 |
| 中文摘要 + 六级改写 | ⚠️ 需要 `LLM_API_KEY`，未配置时走**演示样例** |
| B 站「最新一期」列表 | ⚠️ 需要 `BILI_COOKIE`，否则被风控（HTTP 412） |
| whisper.cpp 本地转写 | ⚠️ 需要手动放可执行文件与模型（官方 release 无 Windows 预编译包） |

**当前是演示模式**：`data/demo/llm_cache.json` 里是我按需求书 F4 标准手写的 3 篇样例文案，
配合 3 个真实 B 站视频（真实标题/UP 主/封面）。界面上有明确标注，不会冒充真实模型输出。

## 快速开始

```bat
run.bat
```

然后打开 <http://127.0.0.1:8000>。

手动跑（不用 run.bat）：

```bash
python -m pip install -r requirements.txt
python scripts/seed_demo.py          # 可选：生成演示数据（拉真实封面）
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 配置

复制 `.env.example` 为 `.env`，按需填写：

```ini
# 真实 LLM（DeepSeek）
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxxx

# B 站登录态：浏览器登录后复制整条 Cookie（至少含 SESSDATA）
# 没有它，「自动检查最新一期」会被风控挡住，只能手动贴 BV 号
BILI_COOKIE=SESSDATA=xxx; bili_jct=xxx; buvid3=xxx
```

其余项（转写引擎、whisper 路径、调度时间）见 `.env.example` 注释。

## 目录

```
app/
  main.py         FastAPI 路由 + APScheduler（22:30）
  runner.py       pipeline 编排、运行日志、失败不写 processed
  source.py       B 站接口（wbi 签名、视频信息、字幕、封面）
  fetch.py        yt-dlp 音频下载
  transcribe.py   字幕优先 / whisper.cpp，统一入口
  clean.py        转写文本清洗（时间戳、口癖、重复句）
  llm.py          摘要 / 改写 / 刊名 / 导语（deepseek | mock）
  magazine.py     自包含 HTML 渲染（内联 CSS + base64 封面）
  store.py        JSON 原子写、订阅、processed、杂志索引
  config.py       .env 读取
prompts/          四份 prompt（摘要、六级改写、刊名、导语）
templates/        dashboard.html、magazine.html
static/app.css    控制台样式
scripts/          seed_demo.py（演示数据）、setup_whisper.sh（whisper 下载）
data/             运行时数据（已 gitignore）
```

## 几个设计取舍

- **只按 BV 去重，不按日期**：跨天更新、一天多期都不会漏；失败不写 `processed.json`，下次自动重试。
- **「补跑」就是「跑一次全部订阅」**：逻辑与定时任务完全一致，已处理的自动跳过。
- **封面失败不阻塞**：拿不到封面就退化成色块，杂志照常生成。
- **六级词汇是调味，不是主菜**：prompt 里明确「可读性优先」，冲突时牺牲词汇难度。
- **封面做降饱和处理**（`saturate(.72)`）：B 站封面通常是高对比标题字，不压一压会盖过正文。

## 已知问题

- 首字下沉用的是「上标式」而非浮动下沉：浮动版本在 Chromium 下会与相邻段落产生错位。
- 控制台「本次运行」只显示最近一次汇总，完整明细在 `data/runs/*.json`。
- whisper.cpp 需要手动准备：`bash scripts/setup_whisper.sh` 只覆盖模型下载，Windows 二进制要自行编译或找第三方构建。

## 下一步（v2）

- CET-6 三层着色 + 两个独立释义按钮
- 评论 `#reply` 锚点（PC 精确、App 兜底原视频）
