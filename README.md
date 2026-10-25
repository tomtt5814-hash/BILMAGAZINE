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
| 本地转写（SenseVoice-Small ONNX，CPU） | ✅ 可用，实测 **40x 实时**（43 分钟视频 68 秒） |
| 中文摘要 + 六级改写（DeepSeek） | ✅ 可用 |
| 双语（标题 + 逐段中文） | ✅ 可用，右下角「双语」按钮 |
| 自动取四个 UP 主的最新一期 | ✅ 借本机浏览器的登录态（`bsk` CLI），**不需要 Cookie** |
| 杂志渲染（自包含 HTML，封面内联） | ✅ 可用 |
| V2 三层词汇（CET-6 / 正常 / 超纲）+ 两个按钮 | ✅ 可用 |
| B 站「最新一期」列表 | ✅ 走浏览器登录态（默认）；配了 `BILI_COOKIE` 则走接口 |
| whisper.cpp（Vulkan） | ⚠️ 官方无 Windows 预编译包，暂用 faster-whisper CPU 顶替 |

真实链路已验证：`BV1GDHA6HEHu`（章北海official，9 分钟）→ 音频 6.6MB → small 模型转写 86 秒 →
DeepSeek 摘要与改写 → 带三层词汇标注的杂志。CPU 转写速度 7 倍实时，四个 UP 主（约 84 分钟音频）
合计约 12 分钟，落在 22:30–23:35 的窗口内。

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

# 转写模型：可以是模型名（走 HF 下载），也可以是本地目录
FASTER_MODEL=tools/fw-small
```

其余项（转写引擎、whisper 路径、调度时间）见 `.env.example` 注释。

### 词表与模型准备

```bash
python scripts/fetch_vocab.py --proxy http://127.0.0.1:7897   # 七个词表 -> data/vocab/
```

faster-whisper 模型建议直接下到本地目录（避免 HF 下载卡住）：

```bash
mkdir -p tools/fw-small
for f in config.json tokenizer.json vocabulary.txt; do
  curl -L -o tools/fw-small/$f https://hf-mirror.com/Systran/faster-whisper-small/resolve/main/$f
done
curl -L -o tools/fw-small/model.bin https://hf-mirror.com/Systran/faster-whisper-small/resolve/main/model.bin
```

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

## V2 词汇层怎么工作

三层判定（`app/vocab.py`）：

1. 命中 CET-6 词表（3991 词）→ **蓝色**，可点击，点了原地出中文；
2. 命中基础词表（初中 3223 + 高中 6008 + 四级 7508）→ **常规字重**，不标注；
3. 其余且词长 ≥ 6 → **细体（超纲）**，中文来自考研/托福/SAT 三张补充表。

查不到的（如 `thermostat`、`chitosan`）交给 DeepSeek 按语境补一个简短中文，
结果缓存到 `data/vocab/glossary.json`，同一次请求最多补 40 个词。

两个按钮独立：`CET-6 释义`批量展开蓝词，`超纲词释义`批量展开超纲词（默认关闭）。
缩写（`you're`）、所有格（`tesla's`）、句中首字母大写的专有名词不参与分级。

## 全自动是怎么做到的

B 站空间投稿接口对未登录请求返回 412 风控，但**你的浏览器里本来就有登录态**。
所以「自动检查」走的是这条路：

1. 用 `bsk` 命令开一个 Agent Window，依次打开四个 UP 主的投稿页；
2. 在页面里用 JS 读出最新一条视频的 BV 号（不碰风控接口）；
3. 关掉窗口，把 BV 交给正常 pipeline；
4. 后续下载、转写、摘要、改写、排版全自动。

实测四个 UP 主约 15 秒抓完，窗口会闪现一下随即关闭。配了 `BILI_COOKIE` 的话会跳过浏览器直接走接口。

## 转写引擎基准（同一台机器实测）

用同一条 43.5 分钟音频 / 300 秒切片对照，跑在 RX 7650 GRE + RDNA3 上：

| 引擎 | 300 秒音频 | 倍率 | 中文表现 | 结论 |
|---|---|---|---|---|
| **SenseVoice-Small（ONNX，CPU）** | **7.4 秒** | **40.6x** | 中国互联网 / 陈俊杰 / 学养 / 泛突厥主义 全对 | **采用** |
| faster-whisper small（CPU int8） | 36.8 秒 | 8.2x | 中国国联报 / 陈宗杰 / 血氧 / 犯突厥主义 | 回退方案 |
| whisper.cpp Vulkan（预编译包） | 50.2 秒 | 6.0x | — | 慢于 CPU，已删除 |
| Const-me DirectML（第三方参考值） | ≈43 分钟音频 325 秒 | ≈8x | — | 与 CPU 持平，无收益 |

真实端到端：43.5 分钟视频用 SenseVoice 转写 **67.9 秒**（Whisper 是 324 秒），四篇合计约 2 分钟。

为什么 SenseVoice 更快更准：它是非自回归结构，一次前向出整句，不像 Whisper 逐 token 解码；
且训练数据里中文占比高。代价是对长音频不友好，所以配了能量 VAD 切段（每段 ≤28 秒）。

模型：`tools/sensevoice/model.int8.onnx`（229MB）+ `tokens.txt`，来自
`csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17`。

## 几个设计取舍

- **只按 BV 去重，不按日期**：跨天更新、一天多期都不会漏；失败不写 `processed.json`，下次自动重试。
- **「补跑」就是「跑一次全部订阅」**：逻辑与定时任务完全一致，已处理的自动跳过。
- **封面失败不阻塞**：拿不到封面就退化成色块，杂志照常生成。
- **六级词汇是调味，不是主菜**：prompt 里明确「可读性优先」，冲突时牺牲词汇难度。
- **封面做降饱和处理**（`saturate(.72)`）：B 站封面通常是高对比标题字，不压一压会盖过正文。

## 已知问题

- 首字下沉用「上标式」而非浮动下沉：浮动版在 Chromium 下会和相邻段落错位。
- 词义脱离语境：`can → 装罐头`、`dry → 干巴巴的` 这类熟词僻义会误标，靠 LLM 补词救不了。
- 专有名词判定是启发式（句中大写 + 不在词典），个别缩写仍可能被当成超纲词。
- whisper.cpp 的 Vulkan 路线不成立：官方 release 没有 Windows 二进制，A 卡在 Windows 上
  只能用 faster-whisper 的 CPU 路径。实测 7 倍实时，够用。
- 转写用的 base 模型中文质量差（「生育率」→「预论」），必须用 small 及以上。

## 下一步（v2）

- CET-6 三层着色 + 两个独立释义按钮
- 评论 `#reply` 锚点（PC 精确、App 兜底原视频）
