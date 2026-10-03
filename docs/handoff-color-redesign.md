# 链谱 ChainAtlas · 前端设计契约 v3（终端风 · 双主题）

> 本文档是当前前端设计的**唯一权威说明**。改样式前必读；改完后必须同步本文档。
> 历史版本：v1 橄榄绿（已废弃）→ v2 白场藏青（保留为浅色主题）→ **v3 深色终端默认 + 浅色研报可选**。

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

## 已踩过的坑（改代码前看）

- **canvas 不读主题自动变**：所有画布颜色是绘制时 `cssVar()` 取的快照，切主题必须重渲染——`onSettingsClick` 里 theme 分支调 `route()` 干这件事，别绕开。
- **index.html 内联首帧脚本**与 `applyTheme()/applyAccent()` 用同一个 storage key，两处逻辑必须保持一致（accent 默认 "navy"，之前写成 "forest" 导致默认色闪烁）。
- 主题切换后 hero 打字机会重放、价值链地图连接线（SVG 用 `var(--up1)` 等）自动跟随——这两者是预期行为，不是 bug。
- `.badge`、`.peer-row` 斑马纹、`.vcm-cluster-head:hover` 这类"衬底上的小变化"不能用 `rgba(255,255,255,x)` 或 `rgba(0,0,0,x)` 写死——深浅总有一边看不见；用 `color-mix(in srgb, var(--text) N%, transparent)`。
- 设置面板的色板 `.swatch` 必须带 `border`（浅色主题的白色圆点、深色主题的近黑圆点否则看不见）。

## 文件地图

- `styles.css` — 全部设计令牌 + 组件样式；主题块在文件顶部（`:root` 深色 / `:root[data-theme="light"]` 浅色 / accent 三组仅浅色）
- `app.js` — `applyTheme()`、`partCycle()/partOther()`、`tintFor()/bandColor()`、`owlSVG()`、`onSettingsClick` 的 theme 分支
- `index.html` — 首帧内联脚本（防闪烁）、`<meta name="theme-color">`、内联 favicon（深色底琥珀圈）
- `locales/zh.json` / `en.json` — `settings.theme*` 三个键
- `_design_preview/` — 三个风格样稿（A 白场研报 / B 深色终端=现行 / C 杂志编辑），仅本地参考，不入库

## 验证清单（改样式后必跑）

1. `python build_dist.py` 构建通过
2. 本地 `python serve.py 8123`，双主题各走一遍：`#/`（hero + 大环）、`#/worldmap`（小圆饼）、`#/i/电子`、`#/m/电子`（大环图）、`#/c/000063`（价值链地图衬底）、`#/vision`
3. 设置面板切换主题后画布颜色跟随（不跟随 = 哪里写死了颜色）
4. 刷新后主题保持（不保持 = 首帧脚本和 applyTheme 不一致）
