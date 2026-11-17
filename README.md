# 非遗视频标注集 · 使用说明

已经抓好一批非物质文化遗产的视频，切成了可以直接标注的短片段，并配好了 Label Studio 的标注模板和导入脚本。

---

## 数据概况

| 指标 | 值 |
|---|---|
| 源视频 | 10 条（哔哩哔哩，共约 52 分钟） |
| 标注片段 | **40 个**（每条源视频取 4 个镜头） |
| 片段总时长 | **17.0 分钟** |
| 单片段时长 | 9 ~ 45 秒，中位数 26 秒 |
| 分辨率 / 帧率 | 长边 1280，**恒定 25 fps**，短 GOP（`-g 25`） |
| 总体积 | 208 MB |

**门类覆盖**：传统技艺 ×20（毛笔、木雕、苗银、竹编、油纸伞）、传统美术 ×12（剪纸、苏绣）、传统戏剧 ×4（皮影戏）、民俗 ×4（打铁花）。

| # | 素材 | 门类 | 源时长 | 片段数 |
|---|---|---|---|---|
| 01 | 毛笔制作 | 传统技艺 | 217s | 4 |
| 02 | 剪纸工具与材料 | 传统美术 | 280s | 4 |
| 03 | 剪纸剪法与刀法 | 传统美术 | 90s | 4 |
| 04 | 苏绣刺绣 | 传统美术 | 132s | 4 |
| 05 | 传统木雕 | 传统技艺 | 331s | 4 |
| 06 | 苗银头饰制作 | 传统技艺 | 285s | 4 |
| 07 | 传统竹编 | 传统技艺 | 752s | 4 |
| 08 | 油纸伞制作 | 传统技艺 | 770s | 4 |
| 09 | 皮影戏 | 传统戏剧 | 182s | 4 |
| 10 | 打铁花 | 民俗 | 259s | 4 |

---

## 先看一眼

- **`data/preview_world.jpg`** —— 预标注效果总览（YOLO-World 版，看这张）
- `data/preview_predictions.jpg` —— 同上，YOLOv8n 版（历史对照）
- **`contact_sheet.html`** —— 每个片段 3 张缩略图（取 20% / 50% / 80% 处），判断内容是否适合做检测与跟踪

---

## 目录结构

```
.
├── 非遗视频-LabelStudio预标注方案.md   # 完整方案（标签体系、三档路径、成本、排期）
├── contact_sheet.html                # 片段预览页（先看这个）
├── data/
│   ├── raw/        # 10 条转码前的源视频（418 MB）
│   ├── clips/      # 40 个标注片段 ← 要标注的就是这些
│   └── thumbs/     # 预览缩略图
├── labelstudio/
│   ├── label_config.xml   # 标注模板：VideoRectangle + 19 个层级标签
│   ├── tasks.json         # 可直接导入的任务（40 条）
│   └── setup_project.py   # 建项目 + 导入任务
├── manifest.json          # 源视频来源、作者、时长、版权说明
├── clips_manifest.json    # 片段元数据（起止时间、内容评分、体积）
└── scripts/
    ├── find_videos.py       # 按门类检索候选片源
    ├── download_videos.py   # 下载选定视频
    ├── build_dataset.py     # 转码 + 镜头切分 + 内容打分筛选
    ├── finalize.py          # 以磁盘为准对齐清单与任务
    ├── make_contact_sheet.py    # 生成预览页
    ├── prelabel_world.py        # 预标注（YOLO-World 开放词汇，推荐用这个）
    ├── prelabel_local.py        # 预标注（YOLOv8n，仅人物，已被上面取代）
    ├── prelabel_video.py        # 预标注（接云端多模态 API）
    ├── viz_predictions.py       # 把预标注画到帧上，拼总览图
    ├── purge_predictions.py     # 按 model_version 清理预标注
    ├── e2e_test.py              # API 链路自检（19 项）
    └── check_ui.py              # 浏览器层自检，需经 label-studio shell 执行（8 项）
```

本目录还会生成这些中间产物：

| 文件 | 内容 |
|---|---|
| `preds_world.jsonl` | YOLO-World 预标注（8 条） |
| `preds_local.jsonl` | YOLOv8n 预标注（8 条，历史） |
| `data/preview_world.jpg` | YOLO-World 效果总览图 |
| `data/preview_predictions.jpg` | YOLOv8n 效果总览图 |

---

## 已经在跑了

服务已启动：**http://localhost:8080**

| 项 | 值 |
|---|---|
| 登录邮箱 | `annotator@example.com` |
| 密码 | `ich2026` |
| API Token | `894e56cecc3cbed62f49ecddb9efe226d1dde987` |
| 标注页 | http://localhost:8080/projects/2/data |
| 数据库 | `.tmp/lsdata/ls.sqlite3`（改到工作区，避开沙箱对用户目录的限制） |

直接打开标注页就能标。任务已全部导入，40 个视频都验证过可读。

---

## 服务器部署（8.160.123.92）

同一套东西也部署到了远程服务器，内容和本地一致（40 视频 / 293 轨迹 / e2e 19 项全通过）。

| 项 | 值 |
|---|---|
| **访问地址** | **http://ich.8.160.123.92.nip.io** |
| 登录邮箱 | `annotator@example.com` |
| 密码 | `ich2026` |
| API Token | `81ee86fd05b977f9deacae689afccc72e866c3e1` |
| 项目 | id=1，「非遗视频 · 目标检测与跨帧跟踪」 |
| 部署目录 | `/root/project/ich-prelabel` |
| LS 监听 | `127.0.0.1:8089`（不对外） |
| 数据目录 | `/root/project/ich-prelabel/.lsdata` |

### 为什么是 80 端口 + 域名，不是 8089

云安全组只放行了 80 和 8080，8089 从外网直连必超时（服务器本机 curl 8089 是好的，
iptables 全 ACCEPT、firewalld 未启用，所以确定是安全组）。而 8080 上跑着 nginx 通用网关，
不能占用。所以加了独立 server 块反代：

```
ich.8.160.123.92.nip.io(:80)  ->  127.0.0.1:8089
```

配置文件：`/etc/nginx/conf.d/ich-prelabel.conf`（新增，没动任何现有站点）。
`nip.io` 会把 `*.8.160.123.92.nip.io` 解析到 `8.160.123.92`，省得配 hosts。

以后若去控制台放行了 8089，也能直连 `http://8.160.123.92:8089`，两者共存。

### 重启服务

```bash
/root/project/ich-prelabel/start_ls.sh
```

幂等：已在运行就只打印地址；没运行才拉起，并等到 `/api/health` 通为止。
日志 `/root/project/ich-prelabel/ls.log`。nginx 若改过配置记得 `nginx -t && nginx -s reload`。

### 服务器上的自检

```bash
cd /root/project/ich-prelabel
export LS_URL=http://127.0.0.1:8089 \
       LS_TOKEN=81ee86fd05b977f9deacae689afccc72e866c3e1 LS_PROJECT=1

.venv/bin/python3 scripts/e2e_test.py        # 19 项，覆盖鉴权/视频读取/schema/导出
.venv/bin/python3 verify_lifespan.py         # 模拟前端可见性，确认框会消失
```

`verify_lifespan.py` 的输出应当与本地一致：

```
服务端轨迹 293 条
末尾缺哨兵的      2 条
结束后仍显示 >2 帧的 0 条
```

（末尾缺哨兵 2 条是轨迹本身就贴着视频最后一帧，补不进哨兵，不影响。）

### 换机器部署时，服务器上额外踩到的坑

1. **传大文件别用 rsync** —— 沙箱里的 rsync 传 199M 视频会段错误（`child exited with status 11`），
   改 `scp -r` 一次成功。
2. **`POST /api/projects/{id}/import` 500** —— `AttributeError: 'NoneType' object has no attribute 'created_by'`，
   项目没挂 organization。用 Django shell 给 project 补 `organization` 并设 `user.active_organization`。
3. **随后所有 API 变 401** —— `legacy token authentication has been disabled for this organization`。
   这是上面第 2 步自己引入的：该校验只在 `active_organization` 非 None 时触发，而新建的
   organization 默认关闭 legacy token。补 `org.jwt.legacy_api_tokens_enabled = True` 恢复。
4. **`GET /api/projects` 500** —— `get_user_repr` 里 `'NoneType' object has no attribute 'email'`，
   organization 缺 `created_by`，设 `org.created_by = user`。
5. **端口**：8080 是 nginx、8000 被别的 python 占着，LS 选了 8089。
6. **ffmpeg**：服务器上走 PyPI `imageio-ffmpeg`（自带静态二进制），不用装系统包。
   注意 macOS 上 `brew install ffmpeg` 会卡死（GitHub 被代理拦）。

---

## 界面中文化（社区版没有内置中文）

**结论先说：Label Studio 社区版 1.23.x 没有中文界面，官方也没留开关。**

不是没找到配置项，是压根没有这套东西。查证过程：

- 后端 `label_studio/core/settings/base.py` 里没有 `USE_I18N` / `LANGUAGE_CODE` / `LANGUAGES`，
  全仓搜不到 `zh-hans` / `zh_CN`，也没有任何 `locale/` 翻译文件。
- 前端 LSF 同样没有 i18n 系统。翻 sourcemap 的 `sourcesContent`，
  与语言相关的源文件只有 antd / date-fns / d3 / rc-pagination 这些第三方库自带的 locale，
  而且只打包了 `en_US` —— 那是它们的默认语言，不是 LS 的语言包。

> 网上（尤其某些 CSDN 文章）说"把 `USE_I18N = True`、`LANGUAGE_CODE = 'zh-hans'` 就能汉化"，
> 是错的。按它改完不会有任何变化，因为没有对应的翻译文件可加载。别浪费时间。

想用中文界面，只有三条路：换第三方汉化 fork（要换掉整个 LS 包，有风险）、
用浏览器自带翻译（会把菜单和你的数据一起翻，不推荐）、或者用下面的脚本。

### 框上为什么不显示标签名

`showLabels` 这个开关 **LSF 默认是关的** —— 见
`libs/editor/src/stores/SettingsStore.js` 第 56 行：`showLabels: types.optional(types.boolean, false)`。
关着的时候 `LabelOnRegion.jsx` 直接 `return null`，框上就只有框、没有字。

整份设置存在 **localStorage 的 `labelStudio:settings`**（`SettingsStore.js` 里的 `lsKey`），
per-user、per-browser，**服务端改不了**。

所以脚本里加了 `ensureShowLabels()`：**第一次打开时自动把它设为 true**，
并刷新一次让已经初始化的 LSF 读到新值。标注员什么都不用做。

只修正一次（写 `lsZhLabelsFixed` 标记），之后用户在设置里怎么改都尊重，不会反复抢方向盘。
已用 jsdom 验证三种场景：

| 场景 | 结果 |
|---|---|
| 全新用户 | 写入 `showLabels: true` |
| LSF 已写入 `false` | 改为 `true`，**保留其他设置**（如 `enableHotkeys`） |
| 已修正过、用户手动关掉 | 保持 `false`，不干预 |

若想手动操作：底部齿轮 → Settings → General → **显示区域标签**（原文 Show region labels）。

### 我们采用的方案：服务端注入，标注员什么都不用装

文件：`labelstudio/ls-zh.user.js`（词典 629 条）

**现在打开 http://ich.8.160.123.92.nip.io 就是中文界面，不需要装任何插件。**
由 nginx 在每个 HTML 页面里自动注入一行 `<script src="/ls-zh.user.js" defer></script>`。

**词典不是手抄的，是从 LSF 前端源码里刨出来的。** `web/dist/apps/labelstudio/*.js.map`
的 `sourcesContent` 里是**未压缩的原始源码**，所以能拿到真实的 UI 字符串。
`labelstudio/extract_ui_strings.py` 干的就是这件事：从 `title:` / `description:` / `tooltip:` /
`placeholder:` / `aria-label:` / `alt:` 这些属性位，以及 `>文本<` 这类 JSX 文本位，
把所有英文文案全量提取出来，再跟现有词典做差集、按出现频率排序。

补词条时用这个脚本看差集，比"想到哪儿翻到哪儿"靠谱得多，
也能量化覆盖率——当前已覆盖 542 条候选里的绝大部分，
剩下的 25 条是代码标识符（`IteratorResult`、`ReturnType`）、格式名（JSON / JSONL / HTML）
和示例文案，有意保留英文（翻了反而更看不懂）。

补的时候顺手发现一个盲区：**LS 把大量工具说明写在 `title` 属性里**，
鼠标悬停才看得到。之前完全没翻，等于标注员把鼠标移到工具上还是一片英文。
这批悬浮提示（`Select the rectangle annotation tool`、`Delete currently selected region`、
`Jump to next keyframe` 等）已经补齐。

> 一开始只提供了油猴版本，但那样每个标注员都要装扩展、装脚本，太麻烦。
> 改成服务端注入后，谁打开都是中文，且以后改词典只要改服务器上的一份文件。

nginx 侧的三个关键点（`/etc/nginx/conf.d/ich-prelabel.conf`）：

```nginx
# 1. sub_filter 的前提：让上游别压缩，否则匹配不到 </head>
proxy_set_header Accept-Encoding "";

# 2. sub_filter 需要 nginx 能缓冲响应 —— 所以这里绝不能写 proxy_buffering off
sub_filter '</head>' '<script src="/ls-zh.user.js" defer></script></head>';
sub_filter_once on;
```

第 3 点是**视频路径要单独拆出来**：`proxy_buffering off` 和 `sub_filter` 互斥，
而视频拖动/加载需要流式转发。所以加了

```nginx
location /data/local-files/ {   # 视频媒体：流式，不缓冲也不替换
    proxy_buffering off;
    ...
}
```

让视频走自己的 location，`location /` 才做缓冲 + 替换。两者都保住。

**还有一条同样重要：必须开 gzip。**

LS 的 `/react-app/main.js` 有 2.5MB，而 Django dev server **不做压缩**，
再加上它代理大文件本来就慢，页面会长时间白屏，前端超时重试 ——
表现就是「登录之后疯狂刷新」「一直重新进入」，而且因为 JS 压根没加载完，
连注入的中文脚本都不会生效（界面自然还是英文）。

```nginx
gzip on;
gzip_proxied any;          # 关键：让代理响应也被压缩
gzip_min_length 1024;
gzip_types application/javascript ...;
```

实测：`main.js` 2.5MB → 731KB、`vendor.js` 280KB → 85KB，整体减少 71%。
`gzip` 在 nginx filter 链中位于 `sub_filter` 之后，所以「先替换再压缩」互不冲突。

> 排查时的一个坑：nginx 的 access log 在**请求完成后**才写入。
> 用户每次刷新都会打断尚未完成的 JS 下载，于是日志里只看到 HTML 请求、
> 看不到任何 `/react-app/*.js`，很容易误判成「浏览器没请求静态资源」。
> 实际上是因为请求从未完成。

**按 `Ctrl + \` 可切回英文**（写 localStorage 后刷新）。想恢复中文再按一次。
万一中文界面在某台机器上出问题，用 **`?nozh=1`** 强制英文，
不至于完全干不了活：http://ich.8.160.123.92.nip.io/?nozh=1

### 脚本自带的三重保护（防止它把页面搞崩）

浏览器端改 DOM 天生要和 React 抢方向盘，所以加了三道闸：

1. **单节点熔断** —— 同一文本节点最多翻译 3 次就永久跳过。
   否则会出现「我们改中文 → React 改回英文 → 我们再改」的拉锯，页面疯狂重绘。
2. **单次预算** —— 一轮最多扫 1500 个节点，防抖放宽到 120ms。
   LS 标注页 DOM 很大，视频时间轴每帧都在更新，不设上限会把 CPU 打满。
3. **重载自检** —— 8 秒内启动超过 4 次就判定为刷新循环，**自动永久停用自己**。
   真出问题时能自己止损，不需要用户干预。

### 本地也要中文：内联进 Django 模板

本地没有 nginx，所以改成把脚本**直接内联进 LS 的页面模板**，效果一样（打开即中文）。

```bash
python3 - <<'PY'
# 把 labelstudio/ls-zh.user.js 内联到模板的 </body> 之前
# 模板目录随环境而变，本地是：
#   ~/.workbuddy/binaries/python/envs/labelstudio/lib/python3.13/
#     site-packages/label_studio/
PY
```

**模板继承关系（改错就不生效）**：

| 页面 | 该改哪个模板 |
|---|---|
| 项目页 / 标注页 | `templates/base.html` |
| **登录页 / 注册页** | `templates/simple.html` ← 不是 base.html |

登录页走的是 `users/templates/users/user_base.html`，而它 `{% extends 'simple.html' %}`，
自身没有 `</body>`（是片段模板）—— 所以登录页要注入的是 **`simple.html`**。
这一步容易漏，漏了的表现是「登录后才有中文，登录页还是英文」。

注意事项：

- 改完**必须重启 LS**，Django 的 cached template loader 不会热加载模板。
- 每个模板都留了 `.bak_before_zh` 备份。
- **升级 label-studio 后模板会被覆盖，需要重新注入。**
- 脚本顶部有 `window.__lsZhLoaded` 防重复标记。多个模板都可能注入同一份脚本，
  没有这个标记会跑出多个 `MutationObserver`，白白翻倍开销。

本地地址：**http://127.0.0.1:8080**，project id=2，
token `894e56cecc3cbed62f49ecddb9efe226d1dde987`，账号同样是 `annotator@example.com` / `ich2026`。
本地 e2e 19/19 通过。

### 实现要点（要改这个脚本的话先看这段）

- **词典不是拍脑袋写的**，是从 LSF 前端 sourcemap 的 `sourcesContent` 里
  实际提取的 UI 字符串（匹配 `title:` / `description:` / `tooltip:` / JSX 文本等位置），
  所以 `Show region labels`、`Playback speed`、`Group by Label` 这类原文都对得上。
  用 `.tmp/extract_ui_strings.py` 可以重新提取并查看差集。
- **去标点容错匹配。** LS 里 `Saved!`、`Total:`、`URL:` 这类带标点的文案很常见，
  不可能每个变体都单列词条。所以匹配时先按「首尾标点 + 正文」拆开，
  只比正文、命中后把**原标点原样拼回去**。
  注意是保留原标点而不是统一改成全角——脚本不该擅自改写标点。
- **必须持续监听，不能只翻译一次。** LS 是 React SPA，重渲染会把 DOM 里的文本
  改回英文。所以用 `MutationObserver` 盯着 `document.body`，每次 React 渲染出英文就再翻一遍。
- **不会死循环。** 翻译结果是中文，不再命中英文词典，替换自然停止。
  另外翻译期间先 `disconnect()`、翻完再 `observe()`，避免自己触发自己。
- **只替换"完全相等"的文本节点**（去空白后比对），并且 `contenteditable` 内的文本跳过，
  所以任务数据、文件名、你自己的标注内容不会被误翻。
- 同时翻译 `title` / `placeholder` / `aria-label` / `alt` 四个属性——LS 大量用 `title` 做悬浮提示。
- 词典里有小写索引，用来兜住全大写按钮（`SAVE` / `DELETE` 也能翻）。

### 汉化自检（改完词典跑一遍）

```bash
npm i jsdom --legacy-peer-deps   # 首次需要；canvas 依赖冲突所以要加这个参数

# 1. 词典覆盖率：从 sourcemap 提取全部 UI 文案，列出还没翻的
python3 labelstudio/extract_ui_strings.py

# 2. 运行时逻辑：精确匹配 / 去标点容错 / contenteditable 跳过 /
#    属性翻译 / showLabels 三场景 / 单节点熔断 / ?nozh=1 逃生
node labelstudio/test_zh.js

# 3. 端到端：拉真实登录页执行内联脚本，断言界面确实变中文
node labelstudio/smoke_zh.js
```

`smoke_zh.js` 这一步不是多余的：node 的语法检查只能证明脚本「能解析」，
证明不了「注入进 Django 模板后仍然有效」——
注入位置错了、被模板语法转义、或脚本里的 `</script>` 把 HTML 截断，
都只有真跑一遍页面才暴露得出来。

跑出来会有 2 条 jsdom 环境限制报错（`location.reload()` 和 `fetch` 未实现），
脚本已自动识别为提示项，真实浏览器里不存在。

**同步时注意**：脚本在项目里的副本是 `/root/project/ich-prelabel/labelstudio/ls-zh.user.js`，
但 nginx 实际提供的是 `/usr/share/nginx/html/ls-zh.user.js`。改完要 copy 一份过去，
因为 `/root` 是 700 权限，nginx 的 `www-data` 用户读不到项目目录。

---

## 上传视频

### 为什么原来「找不到在哪上传」

Label Studio 的导入入口**只存在于数据管理器页面**（`/projects/{id}/data`）右上角。
一旦点进「标注」，就是全屏标注视图，那里**没有任何导入按钮**——
标注员从任务列表点进去，就再也回不到导入入口了，界面上也没有任何提示。
这不是配置错了，是社区版本身的交互设计。

### 解决办法：右下角常驻按钮

文件：`labelstudio/ls-tools.js`，由 nginx 和中文脚本一起注入，**标注员什么都不用装**。

打开 http://ich.8.160.123.92.nip.io 任意页面，右下角就有一个绿色的「＋ 上传视频」：

| 操作 | 效果 |
|---|---|
| 点按钮 | 弹文件选择框，可多选 |
| 把文件拖进窗口任意位置 | 整页变绿框，松手即传 |
| `Alt + U` | 同上，键盘党用 |
| 传完 | 自动跳回数据管理器，能看到新任务 |

细节：

- 项目 id 从当前网址 `/projects/{id}/` 里取；在项目列表页且只有一个项目时自动选中，多个则弹出序号让用户挑
- 串行上传，进度面板逐个显示「上传中 → ✓ 已导入 N 条 / ✗ 错误码 + 原因」，失败不会静默
- 只接视频扩展名（`.mp4/.mov/.avi/.mkv/.webm/.m4v/.flv/.wmv/.ts/.mpg`），拖错文件会提示跳过
- 认证用浏览器自己的 session cookie + `X-CSRFToken`，**不需要配 token，也不会多开账号**

### 实测数据

| 项 | 结果 |
|---|---|
| 接口直传（本机回环，1.9MB） | HTTP 200，`task_count=1`，落库字段 `video` |
| 经 nginx 公网 80 端口（63MB） | HTTP 201，9.1 秒，`task_number=1` |
| jsdom 冒烟（`node labelstudio/smoke_tools.js`） | **15 项全过** |

冒烟测试验的是「拖拽 → 真的发出 POST → 打对接口 → 带上 CSRF → 非视频被跳过」，
不只是语法检查。语法过了但事件没绑上，标注员看到的依然是「点了没反应」。

### 上传的文件落在哪

走这个按钮上传的文件进 `.lsdata/media/upload/{id}/`，任务数据是
`{"video": "/data/upload/3/xxx.mp4"}`——注意**和原有 40 条任务不一样**：
它们走的是本地文件存储，`{"video": "/data/local-files/?d=clips/xxx.mp4"}`。
两条路都能正常标注，互不干扰。

> 如果想批量把服务器上已有的视频加进来，别用 UI，直接拷进
> `/root/project/ich-prelabel/data/clips/` 再调存储的 sync 接口，
> 免得几百个文件在浏览器里一个个传。

### 同步脚本到服务器

```bash
scp labelstudio/ls-tools.js root@8.160.123.92:/usr/share/nginx/html/ls-tools.js
ssh root@8.160.123.92 'chmod 644 /usr/share/nginx/html/ls-tools.js'
# 改过 nginx 配置才需要：
ssh root@8.160.123.92 'nginx -t && nginx -s reload'
```

nginx 侧只需两处（已改好，备份在 `ich-prelabel.conf.bak.*`）：

```nginx
location = /ls-tools.js {
    alias /usr/share/nginx/html/ls-tools.js;
    default_type application/javascript;
    add_header Cache-Control "no-cache";
}
# sub_filter 里追加一个 script 标签
sub_filter '</head>' '<script src="/ls-zh.user.js" defer></script><script src="/ls-tools.js" defer></script></head>';
```

---

## 十二项文本标注项目（Qwen 预标注）

项目 id=6，标题「非遗影像 · 三层十二项（Qwen 预标注）」，
地址 http://ich.8.160.123.92.nip.io/projects/6/data

界面分两段：上半是视频 + 要素框（可自己拖框补漏），下半是十二项文本问答，
两段都由 Qwen 预填。

### 和项目 1 的区别

| | 项目 1 | 项目 5 |
|---|---|---|
| 标注方式 | `VideoRectangle` 画框 + 逐帧跟踪 | 十二项文本问答 |
| 对齐标准 | 早期自拟的检测标签 | 甲方 PPTX 的三层十二项 |
| 预标注来源 | `yolov8s-worldv2-openvocab-v1`（已清空） | `qwen3-vl-plus`（已挂上） |
| 任务数 | 40 | 4（测试片段） |

项目 1 保留不动，两套互不影响。

### 界面是怎么来的

`scripts/build_ls_config.py` 从 `refs/annotation_spec_v4.json` 生成
`labelstudio/label_config_t12.xml`：

```bash
python3 scripts/build_ls_config.py
# 111 个 <Choice>：75 个词表选项 + 36 个置信度选项（12 项 × 高/中/低）
```

十二项里 7 项有词表（T2-1 叙事 12、T2-2 空间 13、T2-3 角色 12、T2-4 门类 10、
T3-2 氛围 9、T3-3 价值 8、T3-4 关系 11），挂成 `Choices`；
T1-1~T1-4 和 T3-1 没有词表，只有文本框。
T2-3 / T3-3 / T3-4 允许多选（一个片段本来就可能同时有多个角色、多重价值），
其余单选；**T2-4 门类严格单选**，次选写进正文。

> 踩过的坑：`spec['tasks'][i]['label_vocab']` 里存的是**词表名**（`"T2-1"`、
> `"genre_taxonomy"`），不是选项列表。真选项在 `spec['vocab'][名字]['items'][*]['name']`。
> 一开始按前者生成，每个 Choices 只有一个叫 "T2-1" 的选项，界面上等于没法选。

### 预标注是怎么进去的

```bash
python3 scripts/ls_push_qwen.py --dry-run   # 预演，不写库
python3 scripts/ls_push_qwen.py             # 建项目 + 导入片段 + 挂预标注
```

`--run` 可以指定用第几轮的结果，默认 `.tmp/qwen4_run4.jsonl`。

转换要点（`answer_to_result()`）：

| Qwen 输出 | LS result |
|---|---|
| `label: "['传统戏剧']"` | `choices` 类型，`from_name=T2-4_label` |
| `out: "..."` | `textarea` 类型，`from_name=T2-4_out` |
| `conf: "高"` | `choices` 类型，`from_name=T2-4_conf` |
| `aux` / `alt` / `gender` | 拼进 `out` 正文的 `【补充】` 行 |

三个坑：

1. **Qwen 的 `label` 是 Python 列表的 `str()`**（`"['传统戏剧']"`），不是 JSON，
   `json.loads` 直接报错，得用 `ast.literal_eval`。
2. **标签不在词表里，LS 会拒收整条 prediction。** 所以先过滤，被滤掉的写进正文
   ——本轮只有 `T3-4: 社区成员内部互动` 一个，正好印证之前统计的
   「T3-4 有 19.3% 人工标注落在『其他』，词表本身不够用」。
3. **T2-3 的 `gender` 是跟 `label` 按下标对齐的**（`['角色[女]','不限']`），
   单独列出来没人看得懂。要配对成「表演者[女]、社区成员（不限）」。

### 结果

4 条片段 × 31 条 result（12 正文 + 12 置信度 + 7 标签），全部 201 成功。
`model_version=qwen3-vl-plus-run4`，`score=0.7`。

片段文件在服务器 `data/clips4/`，通过 `?d=clips4/xxx.mp4` 引用，
没走 `/data/upload/`，所以不额外占一份空间（实测 range 请求返回 206 video/mp4）。

### 画面里的框是怎么来的

`scripts/qwen_boxes.py`（跑在服务器上，因为视频和 cv2 都在那边）：

```bash
cd /root/project/ich-prelabel
QWEN_API_KEY=sk-xxx .venv/bin/python scripts/qwen_boxes.py \
    --clips data/clips4 --out .tmp/boxes4.jsonl --step 2 --workers 6
```

不用 YOLO-World 的原因：那套要 torch + ultralytics（2GB 起），而且开放词表检测对
「唐卡、经幡、芦笙」这类非遗专属物件召回很差。Qwen3-VL 本身支持 grounding，
直接问「框住画面里的人与物」就给坐标，口径还能和 T1 对齐。

流程：每 2 秒抽一帧 → Qwen 出框（0-1000 归一化）→ 贪心匹配串成轨迹 → 转 LS 的
`videorectangle`。

| 片段 | 时长 | 采样帧 | 检测框 | 成轨迹 |
|---|---:|---:|---:|---:|
| `4823…_raw`（藏族草原演出） | 81.1s | 41 | 321 | 55 |
| `SD0012…0003`（门口烧纸） | 35.7s | 18 | 82 | 16 |
| `SD0022…0044`（苗族芦笙） | 100.6s | 50 | 656 | 73 |
| `ea9f…_raw`（手工织机） | 71.3s | 36 | 144 | 29 |

四个必须处理的坑：

1. **没有跟踪**。逐帧独立检测出来的框是散的，LS 的 `sequence` 要求同一条轨迹用同一个
   id 贯穿。用贪心匹配（同类 + IoU≥0.15），IoU 失配时退一步看中心点距离（≤140/1000）。
   只靠 IoU 会把同一个人拆成好几条轨迹——实测单帧轨迹从 26 条降到 12 条。
2. **轨迹 id 会撞车**。多条轨迹完全可能从同一帧开始（一帧里本来就有好几个人），
   只用「标签_起始帧」当 id，LS 会把它们当成同一条、只显示一个框。要加序号。
3. **帧率不统一**。素材有一条是 **44.5fps**，而 `label_config` 写的是 `frameRate="25"`，
   LS 按 25 解读帧号，框会整体跑偏。所以关键帧存 `time`（秒），推之前统一按 25fps
   重算帧号（`normalize_box_timeline()`，这次修正了 432 个关键帧，
   该片段 framesCount 从 3174 变成 1782）。
4. **框得太大没有信息量**。模型偶尔把整片背景圈成一个「场所元素」（覆盖 75% 画面），
   会把真要素盖住，超过 65% 面积的框直接丢。

框的标签沿用 T1 的口径，只放「画面上真能圈出来」的：人物、工具、材料、乐器、
法器/仪式物、服饰/头饰、设备、场所元素。「传承」「仪式功能」这类抽象概念不给框——
那属于 T2/T3，圈不出来。

### 第二轮修正：框不会消失了

第一版推上去之后，画面里明明只有两个人，却挂着三十多个框，而且越到后面越多。

**根因在跟踪器**：贪心匹配时**只比 IoU 和中心距，没检查「上次出现是多久以前」**。
一个框在两秒后消失、三十秒后又撞上另一个人，就被接成同一条轨迹；LSF 从首关键帧
插值到末关键帧，于是整条片子都挂着一个早已离开的目标。检测框越多，这种「跨时空续接」
越容易出现，所以越到后面越乱。

两处改动：

1. **`max_age`**：只允许和最近 `max_age` 个采样点内出现过的轨迹续接。
   间隔 2 秒、`max_age=1` 就是「消失超过 4 秒另起一条」。
2. **末尾补 `enabled: false` 关键帧**：LSF 各版本对「只在关键帧区间内显示」的解释
   不完全一致，补一个关闭帧，无论按哪种规则，目标离开后框都会消失。

同时加了同帧 NMS（同标签 IoU>0.7 去重）和检测结果缓存（`--cache`），
调跟踪参数不再重复调 API。

修正前后对比：

| 片段 | 轨迹（前→后） | 并发中位数（前→后） | 并发峰值 |
|---|---|---:|---:|
| 藏族草原演出 | 55 → 94 | 40+ → **4** | 29 |
| 门口烧纸 | 16 → 17 | 40+ → **3** | 5 |
| 苗族芦笙 | 73 → 153 | 40+ → **10** | 21 |
| 手工织机 | 29 → 41 | 40+ → **2** | 9 |

轨迹条数变多是对的——目标离开再回来就该是两条，不该串成一条。关键是**任一瞬间**只有
真实在场的那些框可见，中位数 2~10 与画面上实际人数吻合。

调参入口：

```bash
--max-age 0     # 最严：必须逐帧连续，断一帧就切断
--step 1        # 采样加密到 1 秒，插值更准，但 API 调用翻倍
```

改完重跑时因为读 `--cache`，不会重复计费。

合并推送：

```bash
python3 scripts/ls_push_qwen.py --boxes .tmp/boxes4.jsonl
```

会给每条任务生成一条 `prediction`，里面同时含 31 条文本 result 和 N 条
`videorectangle`。重推时先删掉 `model_version` 以 `qwen3-vl-plus` 开头的旧预测，
不会叠成两条；`import_tasks()` 也会跳过已存在的片段，不会重复导入任务。

---

## 重新启动（下次要用时）

> 2026-11-09 更新：**8080 已被本机 token-gateway 占用，Label Studio 改用 8081**；
> `envs/ls` venv 曾被清空，重启前若 `envs/ls/bin/label-studio` 不存在，先装一次：
> `uv pip install --python envs/ls/bin/python label-studio`（装的是 1.23.2）。

```bash
cd /Users/lixin/WorkBuddy/2026-10-24-20-33-54
export LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true
export LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT=$PWD/data
export LABEL_STUDIO_BASE_DATA_DIR=$PWD/.tmp/lsdata
export LABEL_STUDIO_ENABLE_LEGACY_API_TOKEN=true
envs/ls/bin/label-studio start --port 8081 --no-browser \
  --enable-legacy-api-token \
  --database $PWD/.tmp/lsdata/ls.sqlite3
```

然后重建项目（脚本幂等，重复跑不会重复导入）：

```bash
export LS_URL=http://127.0.0.1:8081 LS_TOKEN=894e56cecc3cbed62f49ecddb9efe226d1dde987
export NO_PROXY=localhost,127.0.0.1
envs/ls/bin/python labelstudio/setup_project.py
```

> 注：用 curl 直接测 `/data/local-files/?d=...` 时中文文件名必须 URL 编码，
> 不编码会返回 400；浏览器/前端会自动编码，不影响实际使用。

### 踩过的坑（换机器部署时对照）

1. **1.23 默认关闭 legacy token**，API 会报 `legacy token authentication has been disabled`。
   启动加 `--enable-legacy-api-token`，或对组织执行 `org.jwt.legacy_api_tokens_enabled = True`。
2. **光开 `LOCAL_FILES_SERVING_ENABLED` 不够**，`/data/local-files/` 会一律 404。
   视图还要求请求文件目录落在某个 `LocalFilesImportStorage.path` 之下 —— 也就是必须给项目登记本地存储（`setup_project.py` 已自动处理）。
4. **用户邮箱必须带点号的域名**。Label Studio 登录表单用的是 `forms.EmailField`，
   Django 的邮箱校验器要求域名含 `.` —— 用 `annotator@local` 建账号时，表单在校验邮箱
   这一步就被拒，报的却是「The email and password you entered don't match」，非常误导。
   已改为 `annotator@example.com`。
5. **用户必须有 `active_organization`**，否则导入任务报 `'NoneType' object has no attribute 'created_by'`。
6. **Label Studio 的 `/import` 不做去重**，脚本重跑一次任务就翻倍一次。
   `setup_project.py` 里加了 `existing_videos()` 前置过滤才做到幂等。
7. **任务已存在时，`/import` 带 `predictions` 字段是无效的** —— 它只对新任务生效。
   给存量任务灌预标注要走 `POST /api/predictions/`，对应 `--predictions-only`。
   该模式会先删掉同 `model_version` 的旧预测，避免叠加。

以下两条是本沙箱环境特有的，换台机器通常遇不到：

8. **shell 的 `mkdir` 不可用**：其 shim 内部用 here-document，需写 `/private/var/tmp` 被拒绝。
   建目录一律改用 Python 的 `Path.mkdir()`（`scripts/prelabel_local.py` 与 `.tmp/pipinstall.py` 都是这么做的）。
9. **`tempfile` 探测临时目录会失败**：它靠「写个文件再删」判断目录是否可用，而删除操作被安全护栏拦截，
   于是把 `/tmp`、工作区等所有候选全判为不可用，抛
   `FileNotFoundError: No usable temporary directory found`。
   解法是显式赋值 `tempfile.tempdir = '<某个已存在的目录>'` 跳过探测。
   pip 走这条路装包：`.tmp/pipinstall.py <包名>`。

### 标注操作

按 `←` `→` 逐帧移动，框选后按标签键打类。

**标注规范**（建议先跟标注员对齐）：
- 框贴目标可见轮廓，外扩 2~3 px
- 遮挡 > 50% 标 `enabled: false`（保留位置不画框），< 50% 标完整框
- 出画目标框到画面边缘，不猜画外部分
- 面积 < 画面 2% 的目标不标
- 同一物理对象全程一个 tracklet；离开画面再回来 → 新建 ID

---

## 预标注

### 现状：YOLO-World 开放词汇版

`model_version = yolov8s-worldv2-openvocab-v1`。已开启轨迹断裂切割（`--max-gap 15`），见下节说明。

**全量 40 段已跑完**（CPU 耗时 36 分钟），产出 **293 条轨迹**，覆盖全部 10 个门类。

| 门类 | 编号 | 片段 | 轨迹 | 备注 |
|---|---|---|---|---|
| 毛笔制作 | 01 | 4 | 52 | 检出最丰富：人物、手部、毛笔、刻刀、木料 |
| 皮影戏 | 09 | 4 | 77 | 人物框最多的一类，多人在场也稳 |
| 苗银头饰制作 | 06 | 4 | 31 | |
| 打铁花 | 10 | 4 | 28 | 10_01 夜间片段零检出，其余 3 段正常 |
| 油纸伞制作 | 08 | 4 | 26 | |
| 传统竹编 | 07 | 4 | 25 | |
| 传统木雕 | 05 | 4 | 17 | |
| 剪纸工具与材料 | 02 | 4 | 16 | |
| 剪纸剪法与刀法 | 03 | 4 | 16 | 特写镜头多，检出偏少 |
| 苏绣刺绣 | 04 | 4 | 5 | **最弱**，4 段里有 2 段零检出 |

标签分布：人物 128、手部 107、竹编 17、纸张 13、剪刀 13、木料 7、毛笔 4、刻刀 2、剪纸 1、泥坯 1。

**零检出的 5 段**（打开会看到空白，属实检不出，不是没跑）：
`04_传统美术_02`、`04_传统美术_03`、`05_传统技艺_04`、`06_传统技艺_04`、`10_民俗_01`。

质量指标：最大关键帧间隔 15 帧，**>1 秒的时间断裂 0 条**（幽灵框已消除，见下节）。
自检 `scripts/e2e_test.py` **19/19 通过**。

| task | 片段 | 门类 | 轨迹 | 标签分布 |
|---|---|---|---|---|
| 1 | 01_传统技艺_01 | 毛笔制作 | 12 | 人物×4、手部×4、刻刀×1、木料×1、剪纸×1、竹编×1 |
| 5 | 02_传统美术_01 | 剪纸工具与材料 | 6 | 纸张×4、人物×1、木料×1 |
| 9 | 03_传统美术_01 | 剪纸剪法与刀法 | 11 | 人物×3、手部×4、剪刀×2、纸张×2 |
| 17 | 05_传统技艺_01 | 传统木雕 | 1 | 人物×1 |
| 21 | 06_传统技艺_01 | 苗银头饰制作 | 3 | 人物×1、手部×2 |
| 25 | 07_传统技艺_01 | 传统竹编 | 11 | 人物×7、竹编×2、手部×1、泥坯×1 |
| 33 | 09_传统戏剧_01 | 皮影戏 | 21 | 手部×11、人物×8、剪刀×1、纸张×1 |
| 37 | 10_民俗_01 | 打铁花 | 0 | 夜间场景，无召回 |

（上表为全量结果。早期的 8 段 Demo 已被这次全量覆盖。）

早先还有一版 `yolov8n-cpu-bytetrack-v1`（37 条轨迹**全是人物**），已被上面这版取代并清理，
产出文件 `preds_local.jsonl` 仍保留，需要对照时可重新灌入。

轨迹数对比（同一片段，同样后处理参数）：

| 片段 | YOLOv8n | YOLO-World | YOLO-World 给出的标签 |
|---|---|---|---|
| 01 毛笔制作 | 6（全人物） | 12 | 人物×3、手部×5、刻刀×1、木料×1、剪纸×1、竹编×1 |
| 02 剪纸工具与材料 | 1 | 6 | 人物×1、纸张×4、木料×1 |
| 03 剪纸剪法与刀法 | 3（全人物） | 12 | 人物×3、**剪刀×2**、手部×5、纸张×2 |
| 05 传统木雕 | 1 | 1 | 人物×1 |
| 06 苗银头饰制作 | 2 | 3 | 人物×1、手部×2 |
| 07 传统竹编 | 13 | 11 | 人物×7、竹编×2、手部×1、泥坯×1 |
| 09 皮影戏 | 11 | 21 | 人物×8、手部×11、剪刀×1、纸张×1 |
| 10 打铁花 | 0 | 0 | 夜间场景，两版都无召回 |

### 提示词选错会直接导致零检出（毛笔就是这么丢的）

开放词汇检测里，**提示词的措辞比阈值重要得多**。同一个模型、同一段视频，
换个词，置信度能差 16 倍：

| 提示词 | 最高置信度 | 24 采样帧命中 |
|---|---|---|
| `writing brush`（**v1 用的**） | **0.041** | 2 |
| `毛笔` | 0.017 | 1 |
| `Chinese brush` | 0.054 | 3 |
| `ink brush` | 0.062 | 4 |
| `brush pen` | 0.133 | 6 |
| `paintbrush` | 0.144 | 3 |
| `brush` | 0.166 | 5 |
| `Chinese calligraphy brush` | 0.222 | 4 |
| `calligraphy brush` | 0.245 | 5 |
| **`brush in hand`** | **0.687** | **14** |

阈值是 0.20，而 `writing brush` 只有 0.041 —— 差 5 倍，所以
**v1 在毛笔制作 4 段里一条毛笔都没检出**，反而因为竞争关系误报了
「成品/竹编」「成品/剪纸」「工具/刻刀」「材料/木料」。

换成 `brush in hand` 后（`MODEL_VERSION` 同步升到 `...-v2`）：

| 片段 | v1 毛笔 | v2 毛笔 |
|---|---|---|
| 01_传统技艺_01 | 0 | 0 |
| 01_传统技艺_02 | 0 | **1** |
| 01_传统技艺_03 | 0 | **1** |
| 01_传统技艺_04 | 0 | **2** |
| 05_传统技艺_02（对照，非毛笔制作） | 3 条误检 | 2 条误检 |

毛笔 0 → 4 条，而对照门类的误检没有增加（3 → 2），说明换词是安全的。

**教训**：遇到某类别零检出，先别急着调阈值 —— 测一下这组词的真实响应强度。
如果最高置信度连阈值的 1/3 都不到，那是词不对，不是阈值不对。

复现这个探针：

```bash
~/.workbuddy/binaries/python/envs/ultra/bin/python .tmp/probe_brush.py
```

**跑预标注一律用这个解释器**：

```bash
~/.workbuddy/binaries/python/envs/ultra/bin/python scripts/prelabel_world.py --all
```

`ultralytics`（8.4.188）+ `torch`（2.14.1）+ `clip` 都装在 `envs/ultra`，
MPS 可用。系统 `python3`、`python3.11`、`envs/labelstudio` 里都**没有**，
误用会直接 `ModuleNotFoundError: No module named 'ultralytics'`。

> 补记：`ultralytics` 首次 `set_classes()` 时会去 GitHub 拉 CLIP 文本编码器
> （`pip install git+https://github.com/ultralytics/CLIP.git`）。如果沙箱拦截了
> SSL 校验，会自动安装失败。`envs/ultra` 里 `clip` 已就位，所以不需要联网。
> 换环境时若报 `No module named 'clip'`，手动装一次即可，注意给 pip 加
> `PIP_TRUSTED_HOST`，否则它派生的子进程 pip 过不了证书校验。

### v3：词表按门类拆开——做到了去噪，但代价不小

v2 的做法是**所有片段统一喂 16 个词**，结果是跨门类串门：竹编片段里冒出「织机」、
油纸伞片段里冒出「竹编成品」、苗银片段里冒出「剪刀」。这些框标注员只能一条条删。

v3 改成**每个门类只喂它工艺上会用到的词**（`CATEGORY_PROMPTS`，按文件名前两位路由，
匹配不上回退全量）。去噪确实做到了，但**不是没有代价**，下面两节都要看。

#### 先说机制：为什么词表会影响每个类的分数

我一开始以为是 softmax 竞争（「词表越宽，每个词分到的概率越薄」）。**这个解释是错的**，
代码读下来不是这样：

```python
# nn/modules/block.py  ContrastiveHead.forward —— 逐类余弦相似度
x = F.normalize(x, dim=1, p=2)
w = F.normalize(w, dim=-1, p=2)
x = torch.einsum("bchw,bkc->bkhw", x, w)
return x * self.logit_scale.exp() + self.bias
```

这里各类**互不影响**，没有任何跨类归一。但上游还有一层：

```python
# nn/modules/block.py  ImagePoolingAttn.forward —— 用图像特征聚合文本嵌入
aw = F.softmax(torch.einsum("bnmc,bkmc->bmnk", q, k) / self.hc**0.5, dim=-1)
x = torch.einsum("bmnk,bkmc->bnmc", aw, v)
x = self.proj(x.reshape(bs, -1, self.ec))
return x * self.scale + text          # 残差：图像上下文 + 原文
```

聚合后的文本嵌入会被送进 `C2fAttn` 颈部，**反过来影响图像特征**。于是词表经由
图像特征间接改变了每一个类的分数。关键在于：**这个影响没有语义逻辑。**

实测（剪纸片段，同一批帧，只改词表）：

| 词表 | `red paper` 最高分 |
|---|---:|
| 只有 `["red paper"]` | 0.03 |
| v3 六词 | 0.23 |
| 六词 **+ 一个 `embroidery`（绣品，语义上八竿子打不着）** | **0.52** |
| v1 全量十六词 | 0.52 |

加一个语义无关的词，分数翻倍。所以「词表越窄分数越高」是错的，**方向完全不固定**。

#### 全量 40 段的真实得失

| 指标 | v1（16 词） | v3（按门类） |
|---|---:|---:|
| 轨迹总数 | 293 | 292 |
| 其中人物 | 128 | **184** |
| 非人物 | 165 | 108 |
| 其中串门框（必须删） | **32** | **0** |

拆开看：

- **收益**：串门框 32 条 → 0 条。这些是纯损耗，删掉就是净赚。
- **代价**：非人物合法轨迹 165 → 108，**掉了约 25 条**。具体是
  `材料/纸张` 13→0、`成品/竹编` 17→1、`工具/剪刀` 13→7、`工具/刻刀` 2→1。
- **副作用**：人物轨迹 128 → 184（+56）。总轨迹几乎不变（293→292），
  等于**把一半非人物框换成了人物框**。人物框多不一定是坏事，但也可能是
  轨迹碎片化（该是一条的拆成了几条），没有金标准就无法判定。

**结论：v3 是「更干净但更少」，不是无脑更好。** 按本项目自己定的标准
（「漏了比错了更贵」，见 `prelabel_world.py` 注释），这笔账**未必划算**——
删 32 条误框约省 1 分钟，补 25 条漏框约要多花 4 分钟。

#### 那怎么办：类词表只能实测，不能推理

上面的 `embroidery` 实验说明：**手工按语义裁词表是不可靠的**，局部最优只能靠试。
正确的做法是给每个门类标一小段金标准集，用召回率/精确率实测定谁好。
这也是不做微调时唯一能收敛的路径。

现在手上有两个工具可以支撑这件事：

```bash
# 同一片段跑两遍词表，看谁更准
~/.workbuddy/binaries/python/envs/ultra/bin/python scripts/ab_prompts.py \
  --clips "01_传统技艺_01.mp4" "07_传统技艺_01.mp4" \
          "10_民俗_01.mp4"  "04_传统美术_01.mp4" \
  --json /tmp/ab_v1_vs_v3.json

# 两版全量对账：串门框、逐标签框面积、零检出片段
~/.workbuddy/binaries/python/envs/ultra/bin/python scripts/compare_versions.py \
  --a preds_world_all.jsonl --b preds_world_v3.jsonl
```

> 看 A/B 结果**一定要读 `--json` 的产物**，不要看控制台。ultralytics 的进度条用
> `\r` 刷新，管道给 `grep` / `tail` 时会把长行搅乱，控制台表格可能张冠李戴
> （出现过「某标签既算 A 版串门框、又出现在两版共有列表里」这种自相矛盾的输出）。

#### 4 段抽样的 A/B（同一片段跑两遍）

同类比较——只统计两版都检出的标签，避免构成差异干扰：

| 标签 | v1 框面积 | v3 框面积 | 面积变化 | v1 置信度 | v3 置信度 |
|---|---:|---:|---:|---:|---:|
| 人物/传承人 | 27.4% | 27.2% | −1% | 0.704 | **0.738** |
| 工具/刻刀 | 11.3% | 11.6% | +2% | 0.292 | **0.397** |
| 成品/竹编 | 1.9% | 0.4% | **−76%** | 0.626 | **0.698** |
| 手部/左手 | 17.4% | 7.8% | **−55%** | 0.382 | **0.404** |

在这 4 段上串门框 4 条 → 0 条，且没丢标签——**但抽样恰好没踩到上面那个
`材料/纸张` / `成品/竹编` 的坑**。这正是「4 段抽样不足以定结论」的教训：
扩大到 40 段才暴露代价。别用小样本的乐观结果去替代全量对账。

#### 一个容易看错的指标：加权合计

如果把所有标签混在一起算加权均值，会得到「框面积 20.3% → 22.0%，变松 8%」的结论。
**这是辛普森悖论，不要信。**

原因是 v3 删掉了小散框、保留了更多的人形框（27% 面积那一类），混合物构成变了，
均值自然被抬高。**每个标签分开看，全部是变紧或持平的。** 比较框紧密度必须
按标签分组，这也是 `scripts/ab_prompts.py` 里 `measure()` 按 label 分开统计、
而不是只给一个总均值的原因。

#### 10 个门类各自用的词表

| 编号 | 门类 | 词数 | 词表 |
|---|---|---:|---|
| 01 | 毛笔制作 | 6 | person, hand, brush in hand, carving knife, bamboo strip, silk thread |
| 02 | 剪纸工具与材料 | 6 | person, hand, scissors, carving knife, red paper, paper cutting |
| 03 | 剪纸剪法与刀法 | 6 | 同 02 |
| 04 | 苏绣刺绣 | 6 | person, hand, embroidery needle, silk thread, embroidery, loom |
| 05 | 传统木雕 | 5 | person, hand, carving knife, hammer, wooden block |
| 06 | 苗银头饰制作 | 4 | person, hand, hammer, carving knife |
| 07 | 传统竹编 | 5 | person, hand, bamboo strip, bamboo basket, carving knife |
| 08 | 油纸伞制作 | 6 | person, hand, bamboo strip, red paper, brush in hand, wooden block |
| 09 | 皮影戏 | 2 | person, hand |
| 10 | 打铁花 | 5 | person, hand, hammer, wooden block, clay |

两个刻意的「不给词」：

- **06 不加 `clay`** —— 苗银是失蜡铸造，用蜡模不是泥坯。加了只会往工作台上乱框。
- **09 不加 `red paper`** —— 皮影是牛皮/驴皮制的。红纸是臆想，实测会框到布景上。

09 只剩 2 个词、06 的錾子只能靠 `carving knife` 近似顶上（錾子被锤击、刻刀手推，
形制不同会漏）——这暴露的不是词表问题，是**标签体系本身没覆盖这些工艺的关键对象**，
详见 `非遗视频-标签体系v2提案.md`。

### 为什么 YOLO-World 能行而 YOLOv8n 不行

YOLOv8n 只输出 COCO 固定的 80 类，里面跟非遗沾边的只有 person / knife / scissors 三个，
其余全是「剪刀之外的都不认识」。YOLO-World 的词表由**提示词现场指定**——你写什么它找什么。

提示词要用英文（文本塔源自 CLIP，训练语料以英文为主），检出后再映射回中文标签，
映射表在 `scripts/prelabel_world.py` 的 `WORLD_PROMPTS`，改它就能换词表：

```python
WORLD_PROMPTS = {
    "person": "人物/传承人",
    "hand": "手部/左手",
    "scissors": "工具/剪刀",
    "carving knife": "工具/刻刀",
    "bamboo strip": "材料/竹篾",
    "silk thread": "材料/丝线",
    ...
}
```

想加新目标（比如「陶轮」「染缸」），在字典里加一行提示词即可，不用重训模型。
实测提示词越具体越好：`carving knife` 比 `tool` 有效，`bamboo strip` 比 `bamboo` 有效。

### 阈值是分档的，别一刀切

```python
CONF_PERSON = 0.45   # 人物：YOLO-World 很有把握，可以卡高
CONF_TOOL   = 0.20   # 工具/材料/手部：开放词汇的弱项，实测多在 0.2~0.4
```

工具类卡到 0.5 就一个都剩不下。这里故意放低——**预标注的价值是给个起点，漏了比错了更贵**，
低分框让标注员自己判断，改一个框比从零画一个快得多。

### 怎么看结果

1. **标注页**：打开 http://localhost:8080/projects/2/data ，点任一任务进标注界面，
   预标注框会直接叠在视频上。右侧 **Regions** 面板里能看到每条轨迹；
   点 **Prediction** 分组下的 **Accept predictions**（或按 `Ctrl/Cmd + A`）把预标注转成自己的标注再改。

   > **框上没有字？** 这是 Label Studio 的默认行为，不是预标注出错。
   > `showLabels` 的默认值是 `false`（见 LSF `core/settings/editorsettings.js`），
   > 框照画、标签文字不画。
   > 打开方式：标注界面**底部操作栏**的齿轮图标（tooltip "Settings"）→
   > 弹窗「Labeling Interface Settings」→ **General** 页 → 打开 **Show region labels**。
   >
   > 该开关存在浏览器 localStorage，是**每个用户各自的**，服务端改不了，也没法预置。
2. **数据管理页筛选**：`Filters → Predictions`，可按 `model_version`、`score` 过滤，
   比如只看 `yolov8n-cpu-bytetrack-v1`、或只挑 score 高的先修。
3. **导出**：`Export → JSON / JSON-MIN`，`predictions` 字段就是预标注本体，
   跟人工标注的 `annotations` 并列，方便算一致率。

### 重跑 / 扩大范围

```bash
# YOLO-World 跑全部 40 个片段（CPU 实测 8 条约 7.5 分钟，40 条约 40 分钟）
/Users/lixin/.workbuddy/binaries/python/envs/ultra/bin/python \
  scripts/prelabel_world.py --all --step 3 --imgsz 640 \
  --min-frames 5 --max-gap 15 --out preds_world.jsonl

# 灌进 Label Studio（幂等：同 model_version 的旧预测会先删）
export LS_URL=http://127.0.0.1:8080 LS_TOKEN=894e56cecc3cbed62f49ecddb9efe226d1dde987
python labelstudio/setup_project.py --predictions preds_world.jsonl --predictions-only
```

### 自检（改完配置或换机器后跑一遍）

```bash
# A. API 链路 —— 19 项，覆盖鉴权、视频读取、预标注 schema、导出
export LS_URL=http://127.0.0.1:8080 LS_TOKEN=894e56cecc3cbed62f49ecddb9efe226d1dde987
python scripts/e2e_test.py

# B. 浏览器层 —— 8 项，覆盖登录与页面渲染
#    必须经 label-studio shell 执行：表单登录依赖 CSRF cookie，
#    从外部用 requests 模拟会撞到 CSRF/Host 检查（403/404），那是脚本的局限不是服务故障
echo "exec(open('scripts/check_ui.py').read())" | \
  label-studio shell --database .tmp/lsdata/ls.sqlite3

# C. 汉化 —— 25 项，见上文「汉化自检（改完词典跑一遍）」
python3 labelstudio/extract_ui_strings.py   # 覆盖率 / 差集
node labelstudio/test_zh.js                  # 17 项运行时逻辑
node labelstudio/smoke_zh.js                 # 8 项端到端
```

`e2e_test.py` 会**模拟人工接受预标注 → 导出 → 回滚**，
验证「预标注转人工标注」这条路真的走得通，而不只是数据灌进去了。跑完不会留下脏数据。

当前状态：A 19/19、B 8/8 全通过。

### 清理某个版本的预标注（可选）

以后灌了新版本想清掉旧的：

```bash
export LS_URL=http://127.0.0.1:8080 LS_TOKEN=894e56cecc3cbed62f49ecddb9efe226d1dde987
python scripts/purge_predictions.py --model-version <版本号> --dry-run   # 先看会删哪些
python scripts/purge_predictions.py --model-version <版本号>
```

只按 `model_version` 精确删除，不碰其它版本，也不碰人工标注。

四个后处理闸门（`--min-frames` / `--max-area` / `--max-gap` / `--step`）是质量关键，别去掉：

- `--max-area 0.6`：低分辨率推理最容易把整面墙判成 person，框糊满全屏。这种框进了界面比没有更糟
- `--min-frames 5`：ByteTrack 一旦目标被短暂遮挡就换 ID，30 秒视频能把一个人切成十几段，滤掉碎片
- `--max-gap 15`：轨迹内空档超过 15 帧就切断，否则 LS 会插值出幽灵框（详见上文）
- `--step 3`：每 3 帧记一次。跟踪器仍逐帧跑，只是记录稀疏，省 2/3 存储且不影响 ID 连续性

注意 `--step` 和 `--max-gap` 要配套：`--step 3` 时相邻关键帧间隔是 3 的倍数，
`--max-gap` 设 15 表示「连续漏检 5 个采样点就切断」。把 `--step` 调大时应同步调大 `--max-gap`，
否则正常轨迹会被切碎。

### 框一直存在：两个独立成因，都要修

「目标已经过去了，框还在」这件事在 VideoRectangle 上有**两个彼此独立的成因**，
只修一个不够，两个都得处理。

#### 成因二（更要命）：不补结束哨兵，框会一直挂到视频结尾

即便轨迹内部完全连续，只要**所有关键帧都是 `enabled: true`**，这个框就会从第一个
关键帧一路显示到**视频最后一帧**。这是 LSF 源码决定的：

```js
// libs/editor/src/regions/VideoRegion.js
closestKeypoint(targetFrame) {
  const keypoints = seq.filter(({ frame }) => frame <= targetFrame);
  return keypoints[keypoints.length - 1];   // 取 ≤ 当前帧的最后一个关键帧
}
isInLifespan(targetFrame) { return closestKeypoint(targetFrame).enabled; }

// libs/editor/src/regions/VideoRectangleRegion.js
getShape(frame) {
  ...
  if (!next) return onlyProps(self.props, prev);   // 超过最后一个关键帧后沿用最后的形状
}
```

过了最后一个关键帧，`closestKeypoint` 永远返回那个 `enabled: true` 的帧，
形状又一直沿用最后的值 —— 框就冻结在最后位置再也不消失。

**修法：每条轨迹末尾补一个 `enabled: false` 的哨兵关键帧**（`close_sequence()`）。
哨兵之后的帧 `closestKeypoint` 取到哨兵 → `isInLifespan` 为 false → 框消失。

不需要在开头补：第一个关键帧之前 `getShape()` 返回 `null`，框本来就不显示。

补完的验证方式是**照抄前端逻辑模拟一遍**，别靠肉眼看：

```bash
python .tmp/verify_lifespan.py    # 293 条轨迹，结束后仍显示 >2 帧的 0 条
```

已经生成过的 jsonl 不用重跑推理，直接补哨兵即可：

```bash
python .tmp/close_tracks.py preds_world_all.jsonl   # 幂等，会留 .bak
```

#### 成因一：轨迹内部的时间断裂被插值

这是 VideoRectangle 预标注最容易踩、也最容易被误判成「模型不准」的坑。

**根因不在模型，在 Label Studio 的插值机制。**

`videorectangle` 的 result 里只存**关键帧**，关键帧之间由 Label Studio 自动补间：
第 100 帧有个框、第 136 帧有个框，中间 35 帧它一律按匀速位移插过去。

于是只要一条轨迹内部存在长时间的空档 —— 比如目标被遮挡、走出画面、或者检测器中间漏了几帧 ——
前端就会自作主张补出一段「平滑运动」。看起来就是**目标已经过去了，框还在原地慢慢飘**。

诊断方式（`.tmp/diag_gap.py`），扫每条轨迹相邻关键帧的间隔。**首次发现问题时（8 段）**：

```
01_传统技艺_01.mp4  人物/传承人  18关键帧  最大间隔36   1.4s  151→256  ← 断裂
06_传统技艺_01.mp4  人物/传承人  20关键帧  最大间隔33   1.3s  292→400  ← 断裂
共 66 条轨迹，其中 2 条存在 >1 秒的时间断裂（3%）
```

**修复后**（`.tmp/verify_ls.py` 直接从 Label Studio 库里读回来验，不信任本地文件）：

```
间隔最大的 5 条轨迹（服务器上实际存的数据）：
    间隔 标签            总帧数  关键帧
      15 工具/刻刀         720     7
      15 人物/传承人       886    29
      15 人物/传承人       415    17
      12 人物/传承人       720    13
       9 材料/纸张        1019    20

共 65 条轨迹，>1 秒断裂 0 条  => 幽灵框已消除
```

全量 40 段复验（`.tmp/verify_ls.py`，从服务端读）：**293 条轨迹，>1 秒断裂 0 条，最大间隔 15 帧**。

切割是有代价的：切断后剩下的段如果太短（< `--min-frames`），会被碎片闸门滤掉。
8 段那次因此掉了 1 条轨迹，属预期内的取舍——宁可少一条，也不要一条飘忽的假轨迹。

**修法：在断裂处把轨迹切成两段**（`split_tracks()`，`scripts/prelabel_world.py`）。

```bash
--max-gap 15   # 相邻关键帧间隔超过 15 帧（约 0.6 秒）就切断，默认 15
```

切断后每一段内部都是连续记录的，插值出来的就是真实运动而非幽灵。
这也跟标注规范一致：**同一物理对象全程一个 tracklet，离开画面再回来应当新建 ID**。

调用顺序有讲究，别写反：

```python
tracks = run_one(...)                                  # 逐帧检测 + ByteTrack
tracks, cuts   = split_tracks(tracks, args.max_gap, args.min_frames)  # 先切断裂
tracks, dropped = prune_tracks(tracks, args.min_frames)               # 再滤碎片
```

先切后滤。反过来会先扔掉短轨迹，再切出一堆更短的段，最后全被碎片闸门干掉。

### 实际观感

预览图两张，对照着看更直观：

- **`data/preview_world.jpg`** —— YOLO-World 版（看这张）
- `data/preview_predictions.jpg` —— YOLOv8n 版（历史对照）

YOLO-World 版好在哪：03 剪纸片段里**剪刀的框非常准**，02 苏绣的人物框也很正，
09 皮影戏能出 8 个人物 + 11 个手部框。这些 YOLOv8n 一个都给不了。

仍然存在的问题：

- **手部框偏多且会串**。09 皮影戏出 11 个手部轨迹，实际画面里的手远没这么多，是同一只手被反复重识别
- **材料类误检较多**。01 毛笔片段把案板判成「竹编」、02 苏绣把绣布判成「纸张」（两者视觉上确实接近）。
  框位置大体合理，但语义要人工改
- **低分框不可尽信**。工具类置信度普遍在 0.2~0.4，这是开放词汇的固有弱点
- **夜间场景依旧零召回**（10 打铁花）。两版模型都失败，这是域差距，不是参数问题

一句话：**框的位置大致可信，标签的语义需要人工过一遍**。这已经达到预标注该有的水平——
把「画框」这件体力活干掉，把「判断」留给标注员。

好的部分：人物半身/全身镜头的框相当准（02 苏绣、05 木雕、07 竹编、09 皮影戏）。
皮影戏那种多人在场的画面，每一帧能稳定给出 3~4 个人物框。

明显的问题，别抱期待：

- **手部特写会被判成"人物"**。剪纸、苏绣那种只露手和工具的画面，YOLO 把「手 + 剪刀」整体框成 person（预览图第 3 格）。框位置不算离谱，但语义是错的
- **一个人可能被拆成两个重叠框**（第 1 格）。COCO 模型对「身体 + 手部」会重复触发
- **夜间/逆光场景一个框都出不来**（第 8 格打铁花，0 框）。不是参数问题，是 YOLOv8n 在这个域上就没有召回
- **工具、材料、成品全都没有**。这是最关键的缺口 —— 而这批非遗素材的核心标注对象恰恰是工具和手部动作

所以这批预标注的定位是：**验证链路 + 给人物框打底**，不是可用的生产结果。
真正要标工具/材料，必须走下面 A 或 B。

### 还能怎么提升

**A. 扩提示词（最省事，零成本）**
改 `WORLD_PROMPTS` 加新词就能覆盖新目标，比如「陶轮 `pottery wheel`」「染缸 `dye vat`」
「织梭 `shuttle`」「皮影 `shadow puppet`」「鼓 `drum`」。不用重训、不用重装。
建议一次只加 5~10 个，加完在一个片段上验证，词太多会互相干扰。

**B. 接云端多模态 API（需要 Key）**
```bash
export DASHSCOPE_API_KEY=sk-xxx
python scripts/prelabel_video.py run data/clips --out preds.jsonl
python labelstudio/setup_project.py --predictions preds.jsonl
```
云端 VLM 的优势是「理解」而不只是「识别」——它能说出「正在用刻刀修整竹篾」这种行为，
但给不了精确坐标。**理想组合是云端出语义、YOLO-World 出框**。

**C. 回流训练自有检测器（最准，需要人工标注打底）**
先用现有预标注改出 100~200 段真值，微调 YOLOv8，再挂 Label Studio ML Backend，
标注页实时出框。这条路的上限最高，但需要先有标注数据 —— 而做出第一批标注正是现在的任务。
方案文档里的 C 档有完整骨架。

优先级建议：**A 立刻做 → C 在标完成首批后做 → B 有 Key 再说**。

---

## 素材是怎么筛的

源视频是纪录片式的，直接均匀切片会混进大量念稿访谈和字幕卡。`build_dataset.py` 用三个轻量信号打分（不需要模型、不需要 GPU）：

| 信号 | 作用 |
|---|---|
| **运动量**（相邻采样帧灰度差） | 最强信号。手在动 = 真在操作；念稿/PPT/字幕卡几乎静止，一刀切掉 |
| 边缘密度（拉普拉斯方差） | 过滤纯色、黑场、整体虚焦 |
| 平均亮度 | 过滤过暗/过曝，标注时看不清工具 |

然后按 25 秒最小间隔贪心挑选，避免 4 个片段全来自同一场戏。

**已知局限**：纯启发式判别不了「手部特写」和「人物中景」——两者都有运动、都清晰。所以这批片段里混了一部分访谈和作品展示镜头。建议：

- 先翻 `contact_sheet.html`，把不适合的片段告诉我，我剔掉重出一版
- 或者你有自己的非遗素材，替换 `data/raw/` 后重跑 `build_dataset.py` 即可，参数都在文件头

---

## 版权声明

素材来自哔哩哔哩（bilibili.com），**版权归原作者所有**，来源链接记录在 `manifest.json` 的 `source_url` 字段。

本数据集仅限**本地标注练习与标注流程验证**使用，**禁止商用、禁止再分发**。

如果要用于正式项目，请替换为有授权的素材（馆藏数字化资源、自采视频、CC 授权素材），重跑 `build_dataset.py`，流程完全一致。
