# 设计系统 v2：白场 · 藏青 · 细线（机构风改版）

> 本文档记录 2026-10-03 完成的前端整体重设计，替代旧的配色交接方案。
> 目标：从"暖纸博客感"升级为顶级投行/咨询（McKinsey / Goldman / FT 白版）的机构版面。
> 本文档同时作为后续维护的**设计契约**：新组件必须遵守这里的规则。

## 1. 设计方向

**「白场藏青」**：纯白底 + 深藏青唯一强调色 + 1px 冷灰细线 + 锐利边角。

与旧版的本质区别不是换了几个颜色，而是换了整套气质来源：

| 维度 | 旧版（纸与墨） | v2（白场藏青） |
|---|---|---|
| 底色 | 米白纸 `#F5F3EE`（暖） | 纯白 `#FFFFFF`（画廊白） |
| 中性色 | 暖灰（米色调） | 冷灰（蓝灰调） |
| 强调色 | 松绿 `#1E4A3C` + 金色 `#A8863F` 双彩色 | 深藏青 `#0A2540` 单彩色 |
| 边角 | 圆角 6px + 胶囊芯片 | 直角 2–3px 矩形芯片 |
| 导航 | 衬线 16px | 无衬线 14px |
| 首页标题区 | 金色短横装饰 | kicker 眉线标签（等宽字体、大写字距） |
| 免责声明框 | 黄底金框 | 浅灰底 + 藏青左边条 |

## 2. 不变的语义色（设计契约，勿动）

- **涨红 `#AE2A1E` / 跌绿 `#0E6B4A`**：A 股惯例，全站只有它们能表达涨跌。
- **上游藏青蓝 `#1D4E7C/#3E6E9C`、下游古铜 `#9C5A2C/#7C4520`**：价值链地图的方向语义。
- 行业 11 色（`pipeline/palette_check.py` 校验）。
- 原则：**一个颜色只表达一件事**。任何新彩色都必须先回答"它和红/绿/蓝/古铜谁冲突"。

## 3. 核心令牌（styles.css `:root`）

```
--bg        #FFFFFF    画廊白
--surface   #FFFFFF
--surface-soft #F6F7F9  极轻填充
--hover     #EEF1F5
--text      #111418    近黑
--text-soft #49515A
--text-faint #8A919B
--border    #E4E7EB    细线
--border-strong #C7CDD5
--primary   #0A2540    深藏青（Stripe 式机构蓝黑）
--primary-dark  #061829
--primary-soft  #E7EDF4
--radius    3px / --radius-sm 2px
```

`--gold*` 四个变量是**历史别名**，值已映射到藏青/中性灰，仅为兼容旧选择器引用保留；新代码一律用 `--primary*` 或中性色。

主题切换（设置 → 主色）：`navy`（默认）/ `forest` / `graphite` 三套仍可选，默认 navy。

## 4. 本次改动的文件清单

- `styles.css` — `:root` 令牌全换；hero 区重构（kicker + 大标题 + 统计行细线）；导航改无衬线；芯片/标签/按钮全部直角化；区块标题线改冷灰；免责声明框中性化
- `app.js` — hero 新增 `.hero-kicker` 标记；圆饼数据色 `PART_CYCLE = ["#0F3460","#6E86A3","#363D46"]`、`PART_OTHER = "#C9CFD7"`；`OWL_PAL` 调冷；全部 cssVar 回退值同步；设置面板藏青色板值更新
- `locales/zh.json` / `locales/en.json` — 新增 `home.kicker`；`settings.note` 配色约定文案更新
- `pages/style.css` — 静态 SEO 页令牌同步（白底/藏青/冷灰线）
- `manifest.webmanifest` / `index.html` — `theme_color`/`background_color` 更新

## 5. 构建与验证

```bash
python build_dist.py    # 同步 dist/
python serve.py 8123    # 本地预览（no-store）
```

验证路由：`#/`、`#/worldmap`、`#/i/电子`、`#/c/000063`、`#/m/电子`、`#/vision` + 设置面板主题切换。

## 6. 后续维护规则

1. 新组件先从中性色（`--surface-soft`/`--border`/`--text-soft`）里选，不够再考虑 `--primary`，永远不要轻易引入新彩色。
2. 阴影只允许 `--shadow` / `--shadow-lift` 两档；层次优先用细线和留白。
3. 直角是默认；圆形只留给头像级元素（星标按钮、计数气泡）。
4. 数字一律 `font-variant-numeric: tabular-nums`（已有集中规则，新数字组件把选择器加进去）。
