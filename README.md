# 链谱 ChainAtlas

A 股上市公司产业链知识图谱：**4,071 家公司**、**24 个申万一级行业**、**199 个产业链环节**。
零框架、零运行时依赖、零构建步骤——原生 ES Module + 静态 JSON，浏览器直接运行。

![技术栈](https://img.shields.io/badge/stack-vanilla%20ES%20Module-13375E)
![数据](https://img.shields.io/badge/companies-4071-A8863F)

---

## 功能

| 路由 | 页面 | 说明 |
|---|---|---|
| `#/` | 首页 | 行业总览：24 张产业链概览卡（公司数 / 环节数 / 市值 / 平均涨跌 / 环节分布 / 龙头）；全局搜索支持公司名、代码、行业与产业链环节 |
| `#/i/{行业}` | 行业页 | 行业统计、环节分布筛选、公司列表（搜索 / 板块筛选 / 分页加载） |
| `#/c/{代码}` | 公司页 | 行情与财务指标、所属产业链环节、共享环节的同行、五列价值链地图 |
| `#/worldmap` | 全景图谱 | 24 张行业小圆饼：扇形 = 产业链环节，面积 = 公司数（兼容旧路由 `#/atlas`） |
| `#/m/{行业}` | 行业环图 | 单行业大图：环上公司点（大小 = 市值、颜色 = 涨跌），外圈弧段 = 环节，悬停点亮链条 |
| `#/vision` | 观点 | Markdown 正文渲染 |

其他特性：

- **中英双语**一键切换（`locales/` 加语言文件即可扩展，双层 fallback 缺词不炸）
- **自选股**：加入 / 移除 / 抽屉管理，本地持久化
- **三档主色主题**（藏青 / 松绿 / 石墨），首屏绘制前注入、不闪主题
- **响应式**：移动端专用布局与悬浮搜索，13 处 `prefers-reduced-motion` 适配
- Canvas 图表用固定种子渲染，同一数据每次布局一致

## 快速开始

静态站点需要一个 HTTP 服务（`file://` 下 ES Module 会被 CORS 拦截）。仓库自带 `serve.py`，
对所有响应加 `Cache-Control: no-store`，避免开发时命中浏览器启发式缓存。

**Windows**：双击 `serve.bat`，然后访问 http://127.0.0.1:8123/

**命令行**：

```bash
python serve.py 8123
```

无构建步骤，修改源码刷新即可。构建产物（`dist/`）可用 `python build_dist.py` 重新生成。

## 数据口径与免责声明

项目数据分四层，真实程度各不相同，页面上逐层标注：

| 层 | 内容 | 性质 | 来源 |
|---|---|---|---|
| 行情与财务 | 价格 / 涨跌幅 / 市值 / PE(TTM) / 毛利率 / 净利率 / 营收增速 / EPS | **真实** | akshare · 东方财富（2026-09-22） |
| 行业与环节归属 | 24 个申万一级行业、199 个产业链环节 | **真实** | 申万宏源行业分类 + 公开概念板块归类（人工审核） |
| 上下游连线 | 每家公司至多 4 家上游 + 4 家下游 | **推断的模拟数据，未经核实** | 行业步进表 + 环节归属推导 |
| 手工价值链 | 151 家公司的五列地图 | 手工梳理（页面有标注） | 人工整理 |

**两点语义边界**：

1. **"同属一条产业链环节"不等于存在供货关系**——首页与公司页的"产业链环节"均为归属口径。
2. **上下游连线是结构化推断，不是事实**——"谁给谁供货"没有开源数据源（A 股无标准化供应链披露，
   可靠来源仅为年报"前五大供应商/客户"）。推断规则、实测数字与接入真实数据的路径见
   [docs/data-provenance.md](docs/data-provenance.md)。

**本项目不构成任何投资依据。**

## 项目结构

```
china-chain/
├── index.html          页面外壳：顶栏 / 页脚 / 设置模态 / 自选抽屉
├── styles.css          设计系统：CSS 变量 + 组件类
├── app.js              路由 + 六个页面的渲染逻辑
├── i18n.js             t() + Intl 格式化
├── serve.py / serve.bat  本地静态服务（no-store，开发用）
├── build_dist.py       构建 dist/ 静态产物
├── locales/            zh.json / en.json / manifest.json
├── content/            观点页 Markdown 正文（中/英）
├── data/               全部由 pipeline 生成，前端只读
│   ├── index.json          4,071 家公司索引：身份 + 行业 + 环节数
│   ├── fundamentals.json   行情与财务（真实数据）
│   ├── graph.json          行业→公司、环节→公司二分图成员表
│   ├── chains.json         推断的上下游连线（仅公司页按需加载）
│   ├── chain/chain.json    行业步进表等链数据
│   └── {代码}.json         151 家手工价值链公司卡片
└── pipeline/           数据管线（fetch → select → build）
    ├── fetch_real.py       拉取行情/财务（akshare，全市场仅 4 次请求）
    ├── fetch_industries.py 拉取申万一级行业成分股
    ├── fetch_concepts.py   拉取产业链概念成分股
    ├── chain_concepts.py   产业链概念白名单（规则本体）
    ├── select_companies.py 三道判据筛选 → 入图清单 + 可审计剔除记录
    ├── build_chain.py      组装 data/ 全市场数据层
    ├── fabricate_chains.py 推断上下游连线（步进表 + 方向裁决）
    ├── 筛选标准.md          筛选规则、实测数字与验证指标
    ├── palette_search.py   行业配色搜索（色盲安全约束下的优化）
    ├── palette_check.py    配色校验：两两色差 + 红绿色盲模拟
    └── bronze_check.py     通用 WCAG 对比度检查器
```

## 数据管线

按顺序执行（Windows 下将 `python` 换成 `.venv/Scripts/python.exe`）：

```bash
cd pipeline
python fetch_real.py         # ① 行情/财务
python fetch_industries.py   # ② 申万一级行业
python fetch_concepts.py all # ③ 产业链概念
python select_companies.py   # ④ 筛选 → 入图清单
python build_chain.py        # ⑤ 组装 data/*.json
python fabricate_chains.py   # ⑥ 推断上下游 → chains.json
```

①②③ 均有磁盘缓存，只需联网跑一次；之后改口径从第 ④ 步重跑即可。
管线细节：两级上下游推导、`via` 经由标注、真实财务优先（取不到退回固定种子模拟并逐条标注）、
TTM 净利润按累计口径相减真算。

## 技术要点

- **构建期干重活，运行期只读 JSON**——前端零聚合零计算，这是零框架的前提
- **数据按变化节奏切文件**——目录、结构、行情分离，互不牵连
- **每层数据都可失败**——行情缺失时卡片照常渲染，不白屏
- 手写 hash 路由：旧路由兼容、异步竞态保护、手动滚动恢复
- Canvas 固定种子随机 + 按连接度数排序布局，图表具有一致"地图感"
- 字符串模板经统一 `esc()` 转义；带 `<b>` 的富文本走 `richNote()`

设计系统（三层语义配色、11 个色盲安全行业色的搜索优化、版式细节）与参考站设计模式的取舍，
见 [docs/design.md](docs/design.md)。端到端验证记录见 [docs/verification.md](docs/verification.md)。

## 已知限制

- 上下游连线为推断的模拟数据，**不应作为事实引用**（口径见上）
- 4,071 家为筛选结果而非全 A 股；约 0.3% 的公司在现有步进表下推不出上下游
- 无路由级代码分割（六个页面共享单个 `app.js`）；测试为端到端测试，无单元测试
- 公司页"原始尺寸"模式下价值链地图需横向平移查看
- 环图对超大行业自动分圈绘制；窄屏（<520px）仅绘制市值前 90 家

## 文档

| 文件 | 内容 |
|---|---|
| [docs/data-provenance.md](docs/data-provenance.md) | 数据口径详解：筛选判据、连线推断规则、真实供应链数据路径 |
| [docs/design.md](docs/design.md) | 设计系统：配色语义、行业色优化、版式细节、与参考站的差异 |
| [docs/verification.md](docs/verification.md) | 端到端验证记录：覆盖范围与测试抓出的真实缺陷 |
| [ROADMAP.md](ROADMAP.md) | 迭代计划 |

## 许可

代码部分暂未选择开源许可证；数据来源于公开渠道，其权利归原数据提供方所有。
本项目不构成投资建议。
