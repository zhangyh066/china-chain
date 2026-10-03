# 链谱 ChainAtlas · 前端设计契约 v3.1（终端风 · 双主题 · 仪式感层）

> 本文档是当前前端设计的**唯一权威说明**。改样式前必读；改完后必须同步本文档。
> 历史版本：v1 橄榄绿（已废弃）→ v2 白场藏青（保留为浅色主题）→ v3 深色终端默认 + 浅色研报可选 → **v3.1 叠加仪式感/效率/材质/排版四层**（视觉语言不变）。

## 设计参照与定位

- **默认主题 = 深色终端**：参照 Bloomberg Terminal / 交易台界面——深底、琥珀高亮、等宽数字、1px 细线、锐利边角（3px 半径）。终端界面的权威感来自"信息密度 + 克制用色"，不是装饰。
- **浅色主题 = 白场研报**：即 v2 的券商研报风——纯白场、深藏青强调、衬线标题。设置 → 主题 → 浅色 切换，localStorage 持久化（`cnchain.settings.theme`）。
- 切换即时生效、刷新不闪：`<html data-theme="light">` 由 index.html 内联脚本在首帧前打出（深色是 `:root` 默认，不打属性）。

## 核心规则（不可违反）

1. **组件不写死颜色**。一切颜色走 CSS 变量；canvas/SVG 内联生成处用 `cssVar()` 运行时读取（`app.js` 里 `partCycle()`、`tintFor()`、`bandColor()`、`owlSVG()` 是范例）。新增颜色必须先加令牌再用。
2. **四套色彩语义互不重叠**：
   - 价格涨跌 → 涨红 `--rise` / 跌绿 `--fall`（A股惯例；深色下提亮到 #F6465D/#2FB67C）
   - 供应链方向 → 上游蓝 `--up1/up2` / 下游古铜 `--dn1/dn2`（固定语义，深浅两版只调明度）
   - 强调色 → 深色固定琥珀 `#E8A33D`（终端标志色，不可换）；浅色藏青 `#0A2540`（设置里可换松绿/石墨，选择器是 `:root[data-theme="light"][data-accent=...]`）
   - 数据图表 → `--data-1/2/3/other` 明度阶，**不含红绿**，避免与涨跌混淆
3. **标题字体随主题走 `--font-d`**：深色=无衬线（终端感），浅色=衬线（研报感）。画布里的标题（行业大环中心字）也读这个变量，不写死 serif。
4. 强调色不承担数据含义；红色系只允许出现在"涨跌"和"破坏性操作 hover"（`--rise-soft/--rise-line`）。
5. 数字一律 `font-variant-numeric: tabular-nums` + `var(--mono)`，这是金融版面专业感的底线。

## 主题令牌速查

| 令牌族 | 深色（默认） | 浅色（data-theme="light"） |
|---|---|---|
| `--bg / --surface` | `#0D1117 / #12161F` | `#FFFFFF` |
| `--text / --text-soft / --text-faint` | `#D8DFE9 / #93A0B0 / #5E6B7C` | `#111418 / #49515A / #8A919B` |
| `--border / --border-strong` | `#232C3B / #38445A` | `#E4E7EB / #C7CDD5` |
| `--primary`（强调） | `#E8A33D` 琥珀 | `#0A2540` 藏青 |
| `--on-primary` | `#171206` | `#FFFFFF` |
| `--rise / --fall` | `#F6465D / #2FB67C` | `#AE2A1E / #0E6B4A` |
| `--up1/up2 / --dn1/dn2` | `#5B9BD5/#7FA9D4 / #C08A4E/#A87A44` | `#1D4E7C/#3E6E9C / #9C5A2C/#7C4520` |
| `--data-*` | `#5C7DA3/#A8BCD0/#33455E/#232C3A` | `#0F3460/#6E86A3/#363D46/#C9CFD7` |
| 价值链衬底 `--tint-*` / `--band-*` | 深青灰/深棕两组 | 淡蓝/淡米色两组 |
| 空状态猫头鹰 `--owl-*` | 深灰身亮眼 | 浅灰身深眼 |

`--gold*` 是历史别名，映射到强调色（深色=琥珀，浅色=藏青），仅为兼容旧选择器保留，**新代码不要再用 gold 命名**。

## v3.1 新增机制

### 终端启动序列（`#boot-console`）
- 当天首次访问播放：`index.html` 首帧内联脚本判定（`localStorage["cnchain.bootDay"] !== 本地今天` 且非 reduced-motion 且 `settings.animations !== false`），通过才打 `<html data-boot="on">`；不打时元素 `display:none`，零成本。
- `app.js` 的 `startBootConsole()` 驱动：LOAD 两行**等真实数据落定**才填 `4,071 COMPANIES OK` / `199 BOARDS OK`（不是假进度）；最短驻留 900ms；`done()` 在 `await route()` 之前被等待，所以 hero 打字机/数字滚动/大环扫入都在揭幕后才开始。
- 兜底：CSS `boot-failsafe` 9s 强制淡出（JS 异常也盖不死页面）；`done()` 里先 `getAnimations().forEach(cancel)` 摘掉兜底再用 `.out` 类淡出。
- 启动屏永远是深色 `#0D1117`，不随主题——它是一台"终端"在开机。

### 动画系统约定
- **数字滚动**：元素带 `data-count="终值"`（HTML 里同时写着终值做兜底），`countUpIn(root)` 在渲染后调用；`motionOff()` 时直接删属性显示终值。首页 hero / 行业页 / 行业环图页的统计都接了。
- **大环扫入**：`cv._introT ∈ [0,1]`，12 点顺时针展开，中心读数等 `intro >= 1` 才画；悬停重画共享 `_introT`（中途鼠标上来不跳变）。驱动器在 `afterHomeBody()` / `renderIndustryRingPage()`，720ms ease-out cubic。
- **价值链连接线生长**：`<path pathLength="100">` 归一化 + `.vcm-links.animate` 的 dashoffset 动画；只在首次绘制放一次（`svg._drew` 标志），展开分组/切缩放/resize 重画时不重放；最后一条 path 的 `animationend` 才摘类（早摘会把还没轮到的线切成瞬间到位）。
- **全景图谱卡片**：`.pies .pie-card` 用 `animation-delay: calc(var(--i) * 26ms)` 交错入场，`--i` 在渲染时写入。
- **主题切换过渡**：`onSettingsClick` 的 theme 分支先给 `<html>` 加 `.theme-anim`（全元素 220ms 颜色过渡），260ms 后摘掉——不摘的话后续 hover 变色也会被拖慢。

### 命令面板（⌘K）
- 打开：`⌘K` / `Ctrl-K` 切换、`/`（非输入框时）打开、点搜索框里的 `<kbd id="search-kbd">` 键帽（非 Mac 显示 "Ctrl K"）。
- 内容四组：页面（空查询也列，带 g h/g m/g v 提示）/ 行业（≤4）/ 产业链环节（≤4，`goToSearch()` 落地为首页搜索词）/ 公司（复用 `searchMatches`，≤6）。
- 键盘：↑↓ 移动、Enter 执行、Esc 关闭；`g` 后 1.5s 内 `h/m/v` 直达路由。输入框里一律不抢键（`e.target.closest("input,textarea,select,[contenteditable]")` 守卫）；修饰键按下时不触发单键快捷键；`e.key` 要 `toLowerCase()`（Shift 按下时是大写）。
- `closePalette()` 必须 `palInput.blur()`——焦点留在隐藏输入框里，全局快捷键会被守卫吞掉。
- 语言切换时 `destroyPalette()` 销毁，下次打开按新语言重建（面板文案跟语言包走）。
- Esc 关闭顺序：命令面板 > 设置模态（搜索下拉的 Esc 由搜索框自己处理）。

### 材质层（仅深色生效）
`--inset-hi`（卡片顶缘高光）、`--glow-amber`（选中态琥珀辉光）、`--glow-green`（状态灯荧光）、`--hero-grid`（hero 区 2.4% 网格衬底，向下渐隐 mask，`z-index:-1` 才不盖字）——浅色主题把这四个令牌置空，同一套选择器自动失效，不用写分支。

### 排版细节
`::selection` 用强调色；`body { text-autospace: normal }` 中西文自动留隙（Chrome/Safari 支持，其余静默无操作）；`::-webkit-scrollbar` 细滚动条贴主题。

### 价值链数据的折中口径（重要）
原则：**界面只呈现可辩护的真实数据，公司间的供货关系一律不虚构。**
- **151 家手工梳理公司**（`data/{代码}.json`，`info.curated=true`）→ 显示真实「价值链地图」（`curatedMapSection`），口径注记"手工梳理档案"。
- **其余 ~3,920 家** → 显示「产业链位置图」（`posMapHTML`）：左栏上游行业、中间本公司+所属环节、右栏下游行业/终端市场。数据只来自两处真实来源：`data/chain_steps.json`（行业级步进表，53 条人工整理的"上游行业→下游行业+角色"）+ graph.json 环节归属。**没有公司节点、没有供货连线。**
- `chains.json`（852KB 推断数据）已从界面彻底撤下（不再加载），文件保留在仓库仅作存档；`loadChains()/chainNodes()` 已删除。
- 环节芯片点击 → `goToSearch()` 落地为首页搜索结果（真实环节成员）。
- 同步范围：`pipeline/build_chain.py` 与 `data/index.json` 的 disclaimer、`locales` 的 footer/home.sub/home.note、`pipeline/prerender.py` + 4,095 个 SEO 静态页——全部改为"行业级公开关系示意（151 家手工梳理档案除外），不代表具体公司间的供货关系"。
- 改口径时五处必须一起改：build_chain.py 模板、index.json、zh/en locales、prerender.py、（若重跑）静态页。漏一处就会出现两种口径并存。

## 已踩过的坑（改代码前看）

- **canvas 不读主题自动变**：所有画布颜色是绘制时 `cssVar()` 取的快照，切主题必须重渲染——`onSettingsClick` 里 theme 分支调 `route()` 干这件事，别绕开。
- **index.html 内联首帧脚本**与 `applyTheme()/applyAccent()` 用同一个 storage key，两处逻辑必须保持一致（accent 默认 "navy"，之前写成 "forest" 导致默认色闪烁）。
- 主题切换后 hero 打字机会重放、价值链地图连接线（SVG 用 `var(--up1)` 等）自动跟随——这两者是预期行为，不是 bug。
- `.badge`、`.peer-row` 斑马纹、`.vcm-cluster-head:hover` 这类"衬底上的小变化"不能用 `rgba(255,255,255,x)` 或 `rgba(0,0,0,x)` 写死——深浅总有一边看不见；用 `color-mix(in srgb, var(--text) N%, transparent)`。
- 设置面板的色板 `.swatch` 必须带 `border`（浅色主题的白色圆点、深色主题的近黑圆点否则看不见）。
- **index.json 的公司字段是 `industry` 不是 `sector`**——`searchMatches`/搜索下拉/命令面板都踩过 `c.sector` → 显示 `sector.undefined` 的坑，取行业名一律 `c.industry`。
- 公司页的图形属性（`cv._introT`、`svg._drew`、`cv._dots` 等）挂在 DOM 元素上：整页 innerHTML 重建时自动清零，同页重画时保留——"每次进公司页播一次、同页重画不重播"就靠这个，别改成模块级变量。

## 文件地图

- `styles.css` — 全部设计令牌 + 组件样式；主题块在文件顶部（`:root` 深色 / `:root[data-theme="light"]` 浅色 / accent 三组仅浅色）
- `app.js` — `applyTheme()`、`partCycle()/partOther()`、`tintFor()/bandColor()`、`owlSVG()`、`onSettingsClick` 的 theme 分支
- `index.html` — 首帧内联脚本（防闪烁）、`<meta name="theme-color">`、内联 favicon（深色底琥珀圈）
- `locales/zh.json` / `en.json` — `settings.theme*` 三个键 + `palette.*` 七个键
- `_design_preview/` — 三个风格样稿（A 白场研报 / B 深色终端=现行 / C 杂志编辑），仅本地参考，不入库

## 验证清单（改样式后必跑）

1. `python build_dist.py` 构建通过
2. 本地 `python serve.py 8123`，双主题各走一遍：`#/`（hero + 大环）、`#/worldmap`（小圆饼）、`#/i/电子`、`#/m/电子`（大环图）、`#/c/000063`（价值链地图衬底）、`#/vision`
3. 设置面板切换主题后画布颜色跟随（不跟随 = 哪里写死了颜色）
4. 刷新后主题保持（不保持 = 首帧脚本和 applyTheme 不一致）
5. v3.1 专项：清掉 `localStorage.cnchain.bootDay` 后刷新看启动序列（真实加载行 + 落幕）；`Ctrl+K` 开面板搜"电子"（四组结果，公司行是"代码 · 行业"而非 sector.undefined）；Enter 跳转后按 `g h` 能回首页（不能 = 焦点没 blur）；切换主题时全站颜色 220ms 过渡

## 部署（本机网络限制）

本机 `github.com:443` 被阻断，`git push` 不可用；`api.github.com` 正常。
推送流程：本地正常 `git commit` → 用 Git Data API 推送（脚本模板在会话 `/tmp/gh_push2.py`，
要点：逐文件从 `git cat-file blob HEAD:<path>` 取规范化字节建 blob → 建树 → 建提交 →
PATCH `refs/heads/main`；blob 必须取 git 对象而不是工作区文件，因为 `locales/*.json` 和
`pages/style.css` 工作区是 CRLF；**不要用 `gh api --input -` 传中文 payload**——
Windows 下 stdin 会被按 GBK 重编码，提交消息变乱码，一律用 urllib 发请求）。
推送后把 API 返回的提交对象按 `tree/parents/author/committer/message` 重建字节、
`git hash-object -t commit -w --stdin` 写入本地对象库，再 `git update-ref` 对齐两端。
注意两个坑：① GitHub 存储时**保留推送方发送的时区**——本机提交是 `+0800`，
重建字节时必须也用 `+0800`（API 响应里显示成 Z 结尾是 UTC 呈现，照抄会让 sha 对不上）；
② 脚本里 print 中文前先 `sys.stdout.reconfigure(encoding="utf-8")`，
否则 cp936 控制台输出再被工具按 UTF-8 读就是乱码。
