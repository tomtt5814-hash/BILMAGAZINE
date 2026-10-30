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

## 有人值守 / 无人值守

两种都能用：

**手动**：打开 <http://127.0.0.1:8000/manage>，点「自动检查并生成一期」。

**定时**：`scripts/start_server.py` 被 `pythonw` 拉起后，会常驻并按 `SCHEDULE_TIME`（默认 22:30）自动跑一次。
两个前提：

1. 服务在跑 —— 已注册到启动文件夹（`shell:startup\bili-magazine.bat`），登录后自动拉起，
   崩溃后重新登录即可恢复；也可以手动双击 `scripts/start_server.bat`。
2. 电脑不睡眠 —— 实测交流电源下睡眠超时为 0（不睡），电池下 10 分钟。

配置放在 **Windows 用户级环境变量**里（不是 `.env`，那个文件名写盘会被安全策略拦截）：

```
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-...
SCHEDULE_ENABLED=1
SCHEDULE_TIME=22:30
```

`scripts/start_server.py` 启动时会从注册表读取这些变量补齐环境，所以无论谁拉起服务都能拿到。

**定的一个前提**：自动检查最新一期是借浏览器登录态读 B 站空间页的，
所以 22:30 时 Edge 里要保持 B 站登录（浏览器可以最小化，但不能退出登录）。

## 篇幅怎么定的

不是固定 300–500 词，而是按**时长 × 信息密度**算出来的（`app/runner.py: _target_words`）：

| 视频时长 | 基础词数 |
|---|---|
| ≤ 5 分钟 | 300 |
| 5–15 分钟 | 420 |
| 15–30 分钟 | 520 |
| 30–60 分钟 | 620 |
| > 60 分钟 | 720 |

再按转写文本的密度调整（字/分钟）：≥300 加 120，≥200 加 60，≥120 不变，<120 减 60。
最后用「每 12 个中文字符支撑 1 个英文词」封顶——素材不够就写短，绝不注水。

实测：13 分钟「国产医疗设备」→ 462 词；14 分钟「韩国迁都」→ 470 词；
43 分钟「中土网友大战」按此规则会到 620～740 词。

## 公众号也能接

公众号没有公开 API，走两条路（`app/wechat_source.py`）：

1. **贴文章链接**（`mp.weixin.qq.com/s/...`）——最稳。直接抓页面里的 `js_content`，
   拿到标题、公众号名、作者、发布时间、封面和正文；**不需要转写**，反而更快更准。
2. **按公众号名订阅**——用搜狗微信搜索发现最新文章，再还原它跳转页里拼接的真实地址。
   这条路能跑，但搜狗会限流，取不到时该次运行会跳过并记一条提示。

处理链路和视频不同：抓正文 → 清洁 → 摘要 → 英文改写 → 双语，省掉下载和转写两步。
篇幅按「每 4 个中文字符支撑 1 个英文词」封顶（书面语比口播密），
实测 2959 字的文章 → 507 词。

## 几个设计取舍

- **只按 BV 去重，不按日期**：跨天更新、一天多期都不会漏；失败不写 `processed.json`，下次自动重试。
- **「补跑」就是「跑一次全部订阅」**：逻辑与定时任务完全一致，已处理的自动跳过。
- **封面失败不阻塞**：拿不到封面就退化成色块，杂志照常生成。
- **六级词汇是调味，不是主菜**：prompt 里明确「可读性优先」，冲突时牺牲词汇难度。
- **封面做降饱和处理**（`saturate(.72)`）：B 站封面通常是高对比标题字，不压一压会盖过正文。
- **宽屏版心取页面一半并居中**：视口 ≥1100px 时 `.wrap` 用 `width:clamp(1040px,50vw,1440px)`；
  手机上仍走 `@media (max-width:720px)` 的满宽与 22px 边距。
- **行宽由读者决定**：正文默认 74ch（落在 65–75 的舒适区），工具箱里的「行宽」滑杆可在
  56–92ch 之间调整，偏好存在 `bilmag.prefs`。中文注释、双语行、公众号正文共用同一个
  `--measure`，不会再出现正文窄、译文宽的两套栏宽。
- **密度优先于留白**：正文行高 1.62、段间距 0.82em，中文注释 1.75，`text-wrap:pretty`
  避免孤字；图片段落单独居中，公众号原文里的 `text-align:justify` 会被强制改回左对齐，
  否则窄屏会出现大词缝。
- **工具箱按「阅读设置」面板处理**：有标题和关闭按钮，主题、字号、行宽分组；滑杆统一用
  墨色/浅墨色，红色只留给报头与引用线，避免工具控件抢正文的注意力；数值带 `px` / `ch`，
  行宽保留「窄 / 宽」与 65–75 字符提示。
- **动效只做提示，不做干扰**：按钮有 hover 抬升、按下回弹、键盘焦点环；报头、每篇文章和
  页脚用 IntersectionObserver 错峰入场（70ms 递进）。`prefers-reduced-motion: reduce`
  下全部动画与入场关闭；主脚本异常时 2.5 秒兜底移除 `reveal-ready`，内容不会永久隐藏。
- **已生成的杂志要同步**：`data/magazines/*.html` 是自包含静态页，改完模板后必须重新生成
  或按块同步（`<style>`、head 入场脚本、工具箱、末尾脚本），否则旧期仍是旧交互。

## 界面交互规范

**非全屏的卡片、弹窗、浮层，默认都支持点击外部关闭。** 这是项目的硬性约定，
新做组件时直接照这个来，不要等用户提：

- 点击浮层以外的任何地方关闭；
- 按 `Esc` 关闭（多层时先关最上层）；
- 再点一次触发按钮也能关闭；
- 点击浮层内部不关闭，除非里面另有明确的操作按钮。

杂志页是自包含 HTML，所以这套逻辑内联在 `templates/magazine.html` 里（`dismissable`），
当前接入的是「工具箱」和可点击的 CET-6 词义卡片。未来新增浮层只需登记
`isOpen / inside / close` 三个回调，点击与 Esc 会自动生效。

例外只有两类：全屏阅读页（没有“外部”可言）和批量状态开关（`双语`、`CET-6 释义`、
`超纲词释义` 这类把整篇内容展开/收起的按钮，它们不是浮层）。如果要再开例外，
必须在代码注释里写清楚原因。

## 已知问题

- 首字下沉用「上标式」而非浮动下沉：浮动版在 Chromium 下会和相邻段落错位。
- 词义脱离语境：`can → 装罐头`、`dry → 干巴巴的` 这类熟词僻义会误标，靠 LLM 补词救不了。
- 专有名词判定是启发式（句中大写 + 不在词典），个别缩写仍可能被当成超纲词。
- whisper.cpp 的 Vulkan 路线不成立：官方 release 没有 Windows 二进制，A 卡在 Windows 上
  只能用 faster-whisper 的 CPU 路径。实测 7 倍实时，够用。
- 转写用的 base 模型中文质量差（「生育率」→「预论」），必须用 small 及以上。

## 评论区嵌入

每篇 B 站视频下方嵌一个「B 站热门讨论」框，取当天点赞最高的 5 条顶层评论
（`app/comments.py`，免登录，`ps` 最多 20 条）。是生成时的**快照**，不会自动刷新。

- `COMMENTS_ENABLED=0` 关掉，`COMMENTS_TOP_N` 改条数。
- 公众号文章没有公开评论接口，不嵌。

## 下一步（v2）

- CET-6 三层着色 + 两个独立释义按钮
- 评论 `#reply` 锚点（PC 精确、App 兜底原视频）
