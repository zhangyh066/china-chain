# -*- coding: utf-8 -*-
"""基于原简历 docx，生成咨询方向 / 数据方向两个版本，保留原排版格式。"""
import shutil
import copy
import docx

SRC = r"C:\Users\ZYH200269\.kimi-code\sessions\wd_china-chain_d6ab5a9db713\session_284b0610-8143-4e22-9bbc-62bda1e937d2\attachments\f_37d20a90-0855-4316-b213-b3310df50a9f-张宇辉_东北财经大学_简历_财务数字化_修正版.docx"

# 段落改写规则：
#   ("single", 新全文)          -> 段落只有有效单 run，整体替换
#   ("tworun", 新label, 新body) -> run0 为加粗 label，run1 为正文
#   ("bullet", 新label, 新body) -> run0 为符号，run1 为加粗 label，run2 为正文（多余 run 清空）
#   ("title", 新标题)           -> 项目标题段落，只替换 run0
CONSULTING = {
    3: ("single", "金融科技方向硕士在读，具备数字化转型与行业研究的复合背景：在西门子战略发展部实习期间参与政策情报监测、行业知识图谱与知识库平台建设，擅长从业务痛点出发完成需求调研、方案设计与数据驱动的落地验证，具备“问题拆解 → 方案设计 → 开发交付 → 评测迭代”完整闭环经验；熟练使用 Python 与 SQL 进行商业数据分析，熟悉 AI Agent、RAG 等工具在行业研究与知识管理场景的落地，正在探索 AI 在管理咨询与产业研究环节的赋能方式。"),
    14: ("bullet", "行业研究与政策情报采集", "基于 AI Agent 搭建国家级政策监测与拟在建项目自动化采集体系，聚焦国家宏观经济方向与民生消费相关政策并做重点监控，覆盖政策更新追踪、文件下载、内容归纳与行业分类；对项目文件完成批量爬取、OCR 与大模型识别，通过 Python 关键字匹配抽取结构化字段，并同步收集行业周评、月度监测与宏观解读报告，累计整理政策数据 60 余条、项目数据百余条，形成可检索行业情报知识库，为行业趋势研判及内部研究提供语料支持。"),
    15: ("bullet", "流程诊断与优化迭代", "围绕政策文件字段抽取建立覆盖 5 类文件、58 个样本的质量评测体系，从字段级抽取准确率、任务完成率、平均处理耗时与文件级一次性通过率四项指标开展评估，采用模型自动判分与人工抽检双轨校准；基于评测结果定位流程瓶颈并持续迭代方案，形成“失败案例归集 → 改进建议生成 → 人工确认 → 更新提示与工具 → 重跑回归”闭环；经 5 轮迭代，文件级一次性通过率由 40% 提升至 95%，单批次处理耗时由 1 小时缩短至 20 分钟。"),
    16: ("bullet", "制造业设备知识图谱建设", "以国家设备标准文件为数据源，解析标准文本并结构化提取设备实体，借助 AI Agent 流水线生成、校验行业设备别名，累计入库 11,000 余台设备与 83,000 余条别名；参与行业设备分析平台的需求梳理与领域建模，基于 Neo4j 构建设备、别名与标准的关联图谱，支持别名归一、多跳关联与影响范围追溯，为设备行业研究提供数据底座。"),
    17: ("bullet", None, "负责内部知识库分区建设与语料治理，将行业标准、研究报告等 PDF 资料按业务分区管理，完成文件归类、命名规范、解析状态与切块结果校验，累计入库 500 余份可检索文档；参与“分区隔离 → 抽取清洗 → 带重叠切块 → 文件/页码/块号元数据标注 → 向量化建索引 → Top-K 召回 → 带来源引用与防幻觉约束的提示词拼装”链路验证，反馈解析异常与召回偏差；结合大语言模型与 GraphRAG（图谱检索 + 向量检索混合召回），以子图作为上下文驱动分析推理，实现根因定位与多跳关联分析，50 道测试题 Top-1 命中率 70%、Top-3 命中率 95%。"),
    18: ("bullet", None, "参与第三方行业研究机构合作，针对现有行业研报在数据口径与覆盖范围上不满足业务需求的问题，参与需求梳理与拓展方案讨论，推动制造业生产设备相关研究内容与数据维度的补充延伸，沉淀合作需求与交付标准。"),
    21: ("bullet", "另类数据研究与因子构建", "围绕“卫星遥感数据挖掘上市公司投资价值”课题，聚合夜间灯光、热效应特征等另类数据，基于 GDAL 与 SAM 搭建半自动化遥感标注与特征聚合流程，构建量化因子并验证其与股价的关联，挖掘上市公司股价 Alpha。"),
    26: ("title", "金融数据仓库与上市公司行业分析平台"),
    29: ("bullet", "数据底座架构设计", "采用规范数仓建模思想，独立搭建 ODS（贴源层）→ DWD（明细层）→ DWS（服务层）→ ADS（应用层）四层架构；ADS 层落地为行业聚合集市、全市场概览与数据质量质检报告，实现原始数据到分析服务数据的清晰解耦，为行业研究与对标分析提供统一数据底座。"),
    30: ("bullet", "指标体系与 ETL 管线", "基于 Python + DuckDB 构建高性能数据流，覆盖财务三大报表核心科目，利用 SQL 窗口函数计算盈利能力、成长性、偿债能力、营运能力五大类 20+ 核心指标，内置杜邦分解因子、Altman Z 财务困境预警模型与多期滞后项（L / L2 / F）；同步执行 10 项会计勾稽关系自动校验，千万级数据查询响应达毫秒级。"),
    31: ("bullet", "分析服务接口开发", "使用 FastAPI 开发 18 个核心业务接口，集成数据缩尾（Winsorize）、动态样本筛选、行业聚合统计、行业对标分析（分位数排名）、Pearson 相关性矩阵、数据质量校验、变量数据字典等分析逻辑，支持在线海量样本分析，为行业专题研究提供标准化数据服务。"),
    33: ("bullet", "可视化看板交付", "自主开发前后端分离 Web 看板，提供变量可视化、行业分布统计、杜邦分解、Altman Z 风险预警、行业对标分析、相关性热力矩阵、变量数据字典与数据质量校验台；支持一键导出含中文的 Stata（.dta）及 CSV 格式数据集，可直接用于实证回归与专题研究；API 数据接口可直接对接 Tableau / Power BI 搭建管理层汇报看板。"),
    52: ("single", "编程语言：Python（Pandas / FastAPI / SciPy）、SQL、R、Excel、JavaScript（基础，可读懂代码逻辑并简单调试）"),
    54: ("single", "商业分析：行业研究、政策分析、竞争对标、指标体系设计、数据可视化与商业报告撰写；熟悉财务共享服务中心（SSC）、费用报销、对账、发票识别等流程的数字化与自动化场景设计；RPA（影刀 / UiPath）与低代码平台应用"),
    58: ("tworun", "数据分析与可视化", "时间序列分析、假设检验、无监督聚类（K-Means）、降维分析（t-SNE）、数据可视化（Matplotlib、Tableau / Power BI）"),
}
CONSULTING_INSERT = [
    "咨询工具与方法：金字塔原理、MECE 任务拆解、市场规模测算（Top-down / Bottom-up）、竞品分析与对标框架；熟练使用 Wind 金融终端与 Excel 高级功能（数据透视表、Power Query），可快速产出管理层汇报 PPT 与研究报告",
]

DATA = {
    3: ("single", "金融科技方向硕士在读，主攻数据工程与 AI 数据管线：具备数据采集、清洗、数仓建模、指标计算、服务接口到可视化交付的全链路实战能力，独立完成 ODS → DWD → DWS → ADS 四层数仓与 ETL 管线搭建，千万级数据查询毫秒级响应；熟练使用 Python 与 SQL，熟悉主流数据加工与质量管控工具链，具备 RAG / GraphRAG 检索系统与 LangGraph 多智能体工作流开发经验，探索大模型时代的数据基础设施落地。"),
    21: ("bullet", "遥感数据管线与因子构建", "基于 GDAL 与 SAM 搭建半自动化标注管线，聚合夜间灯光、热效应特征等另类数据，设计半自动化遥感标注与特征聚合流程，挖掘上市公司股价 Alpha。"),
    26: ("title", "金融数据仓库与指标服务平台"),
    53: ("single", "数据库：MySQL、SQL Server、DuckDB（窗口函数、索引与查询优化，千万级数据查询毫秒级响应）"),
    54: ("single", "数据质量：评测集构建、字段级抽取准确率评估、数据口径与数据定义核查、数据产品说明书审核；熟悉财务数据加工与勾稽校验场景"),
    55: ("tworun", "数据工程", "ETL 管线设计、数据仓库架构（ODS / DWD / DWS / ADS）、数据清洗、特征工程、数据质量管控、API 开发"),
    29: ("bullet", None, "采用规范数仓建模思想，独立搭建 ODS（贴源层）→ DWD（明细层）→ DWS（服务层）→ ADS（应用层）四层架构；ADS 层落地为行业聚合集市、全市场概览与财务勾稽质检报告，实现原始只读数据到高度聚合服务数据的清晰解耦；接入层基于 Airflow 定时调度并支持失败重试，整体 Docker 容器化一键部署。"),
    58: ("tworun", "数据分析与机器学习", "时间序列分析、假设检验、无监督聚类（K-Means）、降维分析（t-SNE）、机器学习建模（scikit-learn：回归 / 分类 / 特征筛选）、数据可视化（Matplotlib）"),
}
DATA_INSERT = [
    "部署与协作：Linux 常用命令与 Shell 脚本、Docker 容器化部署、Git 协作与 GitHub Actions CI/CD",
    "大数据生态：Spark 批处理、Hive / Hadoop 基础、Kafka 消息队列、Airflow 任务调度、dbt 数据建模",
]


def apply(rules, insert_lines, out_path):
    shutil.copy(SRC, out_path)
    d = docx.Document(out_path)
    for idx, rule in rules.items():
        p = d.paragraphs[idx]
        kind = rule[0]
        runs = p.runs
        if kind == "single":
            runs[0].text = rule[1]
            for r in runs[1:]:
                r.text = ""
        elif kind == "title":
            runs[0].text = rule[1]
        elif kind == "tworun":
            label = rule[1]
            runs[0].text = label if label.endswith("：") else label + "："
            runs[1].text = rule[2]
            for r in runs[2:]:
                r.text = ""
        elif kind == "bullet":
            label, body = rule[1], rule[2]
            if label is not None:
                runs[1].text = label if label.endswith("：") else label + "："
            runs[2].text = body
            for r in runs[3:]:
                r.text = ""
    # 在“语言”一行（末段）之前插入新技能行，完整复制模板段落的格式
    for text in insert_lines:
        template_p = d.paragraphs[52]._p  # 任一已有技能行的 XML 作为格式模板
        ref_p = d.paragraphs[59]._p      # “语言：”段
        new_p = copy.deepcopy(template_p)
        ref_p.addprevious(new_p)
        # 清空多余 run，只保留第一个并写入文本
        new_para = docx.text.paragraph.Paragraph(new_p, d.paragraphs[59]._parent)
        runs = new_para.runs
        runs[0].text = text
        for r in runs[1:]:
            r.text = ""
    d.save(out_path)
    print("saved:", out_path)


apply(CONSULTING, CONSULTING_INSERT, r"D:\workbuddy缓存\2026-09-21-15-03-14\china-chain\张宇辉_东北财经大学_简历_咨询方向.docx")
apply(DATA, DATA_INSERT, r"D:\workbuddy缓存\2026-09-21-15-03-14\china-chain\张宇辉_东北财经大学_简历_数据方向.docx")
