# BILMAGAZINE

**博主日报杂志** · 把 B 站博主的最新视频，做成一本人愿意读下去的英文小刊。

每天，它把选定的 UP 主的新视频拆成文字，提炼中文摘要，再用贴近 CET-6 密度的英文重新写一遍，
最后排成一本可以翻阅、可以离线、可以装进手机的杂志。

- 线上阅读：<https://bilmagazine.pages.dev>
- 本机后台：<http://127.0.0.1:8000/manage>（只绑 `127.0.0.1`，不对外）
- 当前最终版：`main`
- 归档版本：`纸浆风格版`（早期奶白纸面实验，保留作对照）

## 不是摘要，是一本小刊

它不想把一天看过的视频压缩成几条 bullet。它更想做的是：给每期一个像样的封面、一个能读进去的版心、
一层不打扰阅读的中文注脚，让你愿意在第二天早上把它当作一本小杂志翻完。

阅读页是这张纸；首页是编辑部；控制台是本机的印刷机。

## 每天发生什么

1. 从订阅的 B 站 UP 主 / 公众号拿到最新内容
2. 本地 SenseVoice-Small 转写，不把音频送去云端语音 API
3. DeepSeek 提炼中文摘要，再改写成英文科普
4. 自动标出 CET-6 / 超纲词，生成双语段落和语境注释
5. Jinja 排成自包含 HTML，封面内联，一页可离线打开
6. 导出静态站，按需自动部署到 Cloudflare Pages

## 这一版有什么

- **两种气质，一套内容**：夜间是近黑编辑室 + 酸性绿；白天切到粗野主义纸张、墨黑硬边、硬阴影和酸绿色块。导航栏一键切换，阅读页跟着全局主题走。
- **阅读优先**：桌面正文默认 74ch（可在工具箱里 56–92ch 之间调），手机收窄到 30ch 居中；行高、段距、双语注脚都为长文调过。
- **往期是一组会转的封面**：5 张 3D 卡片持续匀速旋转，鼠标移上去暂停、抬升、随指针倾斜；手机上横向滑动，不依赖 3D。
- **可安装、可离线**：manifest + Service Worker；主屏安装，断网也能读已看过的刊。
- **本机后台**：订阅、补跑、进度日志只在本机 `127.0.0.1:8000`，公开站不暴露 `/manage`。
- **每天自动上线**：成功生成一期后自动导出并部署 Pages；发布失败只记录，不影响已经生成的杂志。

## 架构

```text
Bilibili / 公众号订阅
        ↓
本地 FastAPI 管线（下载 → 转写 → 摘要 → 改写 → 标注）
        ↓
Jinja 杂志 HTML（自包含 CSS / 封面）
        ↓
scripts/export_pages.py → site/
        ↓
Cloudflare Pages（静态、免费、PWA）
```

生成、转写、调度和控制台都在本机；云端只托管已经生成好的首页与杂志。Cloudflare 免费版每天一期
远用不完额度：约 30 次部署/月，对 500 次/月的免费额度来说很宽裕。

## 部署到 Cloudflare Pages

```bash
python scripts/export_pages.py
npx wrangler pages deploy site --project-name bilmagazine --branch main
```

- 第一次需要 `npx wrangler login`，浏览器授权后即可；免费地址是
  `https://bilmagazine.pages.dev`。
- `scripts/export_pages.py` 会把首页、各期杂志、封面缩略图、`static/app.css`、
  `static/shell.js`、`robots.txt`、`404.html` 以及 PWA 的 `manifest.webmanifest`、`sw.js`、
  `offline.html`、`static/icons/` 导出到 `site/`；`site/` 和 `.wrangler/` 已忽略，不进入 Git。
- 公开站用 `public_site` 渲染：隐藏「订阅 / 控制台 / 生成新一期 / 管理订阅」，只保留阅读、
  往期和主题切换；本机后台仍完整保留。
- Pages 上的是导出那一刻的内容；以后生成新一期，重新导出并部署即可。
- **PWA**：`manifest.webmanifest` 提供独立窗口、图标和主题色；`sw.js` 缓存应用外壳与访问过的
  杂志页，断网时回落到 `offline.html`。修改缓存策略后记得提升 `static/sw.js` 里的 `VERSION`。
- **生成后自动上线**：用户环境变量设 `AUTO_PUBLISH=1` 后，每次成功生成一期（非演示模式）会依次
  执行导出和 Pages 部署；需要本机已登录 `wrangler` 且 Node.js 在 PATH 里。发布失败只写进运行记录，
  不会把已经生成的杂志标成失败。

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

1. 服务在跑 —— 已注册到启动文件夹（`shell:startup\BILMAGAZINE Server.vbs`），登录后隐藏拉起；
   启动器带单实例检查，不会重复开第二个进程。它不负责崩溃守护，进程异常退出后重新登录，
   或手动双击 `scripts/start_server.bat` 即可恢复。
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
- **双主题，不是两套页面**：全站主题存在 `bilmag.siteTheme`，首次访问默认 `day`；导航栏的
  太阳/月亮按钮切换，`?theme=day|night` 可直接预览。白天只覆盖颜色、边框、阴影和部分布局，
  HTML 与交互保持一致，避免维护两份页面。
- **控制台固定白纸主题**：`/manage` 是本机专用页面，固定 `data-theme="day"`，不跟随公开站的
  黑夜主题；今日杂志预览也强制 `theme=day`。手机只访问云端阅读站，控制台不对外暴露。
- **往期不是列表，是一条卡片轨道**：前 5 期在 3D 舞台上连续、匀速旋转（每 2.6 秒转过一张），
  不再逐张停顿；鼠标进入舞台暂停、移出继续。悬停某张卡片时它放大到 1.5 倍、上浮，并随指针
  左右/上下四向倾斜。点击进入对应一期；移动端自动降级为横向滑动，不依赖 3D，也不显示翻页按钮。
- **手机阅读页是满宽纸张、窄栏正文**：900px 以下隐藏页面统计，阅读纸张去掉边框、阴影和留白，
  `100vw` 铺满屏幕；640px 以下再收成单栏，隐藏左侧期号栏，正文限制在约 30ch 并居中，
  避免横向溢出和过长的行。手机工具箱不显示行宽滑杆，行宽由版式固定。
- **阅读页跟随全站主题**：顶栏也有切换按钮；黑夜是深色纸面，白天是奶白纸面。阅读页自己的
  字号/行宽仍存在 `bilmag.prefs`，主题同时写入 `bilmag.siteTheme`，三个页面不会各说各话。
- **阅读页是一张纸，不是一栏文字**：最终版把正文包在最大 `1180px` 的纸张里；白天桌面
  是近白底 + 浅色顶栏，黑夜才是深色桌面。手机上纸张满宽，边距收窄，不出现横向滚动。
- **行宽由读者决定（桌面）**：正文默认 74ch（落在 65–75 的舒适区），工具箱里的「行宽」滑杆
  可在 56–92ch 之间调整，偏好存在 `bilmag.prefs`。中文注释、双语行、公众号正文共用同一个
  `--measure`；手机端隐藏该滑杆，固定为约 30ch 的舒适窄栏。
- **阅读页有下一篇按钮**：按钮显示当前文章序号（1、2、3…），点击后序号递增并跳到下一篇；
  手动滚动到下一篇时数字也会自动更新，最后一篇循环回第一篇。桌面显示「下一篇 + 数字」，
  手机只显示圆形数字按钮；工具箱打开时按钮自动隐藏，避免和面板叠在一起。
- **密度优先于留白**：阅读页正文行高 1.62、段间距 0.82em，中文注释 1.75，`text-wrap:pretty`
  避免孤字；图片段落单独居中，公众号原文里的 `text-align:justify` 会被强制改回左对齐，
  否则窄屏会出现大词缝。
- **工具箱按「阅读设置」面板处理**：有标题和关闭按钮，主题、字号、行宽分组；轨道保持中性，
  避免控件抢正文注意力；数值带 `px` / `ch`，行宽保留「窄 / 宽」与 65–75 字符提示。普通开关
  用酸性强调色，「工具箱」和「CET-6 释义」这两个常用按钮用天蓝色区分。
- **动效分层**：首页/控制台用幕布、按词入场、磁吸按钮、封面 tilt、数字滚动、光标环等高频
  动效；阅读页只做报头/章节错峰入场、滚动进度和按钮反馈，正文不参与动画。
  `prefers-reduced-motion: reduce` 下全部关闭；首页幕布和阅读页入场都有 CSS/JS 兜底，
  脚本异常时不会永久遮住内容。
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
