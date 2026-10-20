# -*- coding: utf-8 -*-
"""产业链深耕产物（多链条版）：手工链条档案 + 阶段等权指数 + 相关期货行情。

CHAINS 配置三个链条：lithium 锂电 / pv 光伏 / semi 半导体。每个链条产出：

  data/chain/{key}.json   链条档案 + 阶段趋势：
                          {schemaVersion, generatedAt, key, title, titleEn,
                           sub, subEn,
                           stages:[{key,name,nameEn,desc,descEn,
                                    companies:[{code,name}]}],
                           trends:{dates:[...], stages:{key:[指数序列]}}}
                          阶段指数复用 build_trends 的等权逻辑（基期 100，
                          停牌前值填充，单日 |r|>30% 剔除）；成员日线缺文件
                          容错跳过，可随 data/h 补抓反复重跑。
  data/price/{key}.json   链条相关期货主力日线（akshare 新浪日线，近 250 个
                          交易日），与 data/h 同格式 {name, points:[[date,close]]}。
                          价格线为可选：price 配置里 symbols 按序探测，全失败
                          就不生成/保留旧文件，只 warning 不报错（前端降级）。

公司名优先从 data/index.json 读（data/p 档案无 name 字段），常量里的手工名
仅作兜底；代码先按 data/p/{code}.json 是否存在校验，缺档案打印 warning 并剔除。
个别公司跨阶段重复出现（如格林美/华友钴业兼在锂电前驱体与回收、通威股份兼在
硅料与电池片、隆基绿能兼在硅片与组件），属预期内。

用法：python build_chains.py
"""

import json
import os
import sys
from datetime import date

import build_trends as bt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

PRICE_POINTS = 250       # 期货日线保留的交易日数

# ---------------------------------------------------------------------------
# 链条定义。companies 为 (代码, 兜底名)；名称以 data/index.json 为准。
# sub/subEn 由 journey + 实际阶段数/成员数在构建期生成。
# ---------------------------------------------------------------------------
CHAINS = {
    "lithium": {
        "title": "锂电池产业链", "titleEn": "Lithium battery chain",
        "journey": "从锂矿到回收", "journeyEn": "From lithium mines to recycling",
        "price": {"symbols": ["LC0"], "name": "碳酸锂期货主力"},
        "stages": [
            {"key": "upstream_lithium", "name": "上游·锂资源",
             "nameEn": "Upstream · Lithium Resources",
             "desc": "锂辉石/盐湖/锂云母采选，碳酸锂、氢氧化锂等锂盐冶炼",
             "descEn": "Spodumene, salt-lake and lepidolite extraction; "
                       "lithium carbonate and hydroxide refining",
             "companies": [("002460", "赣锋锂业"), ("002466", "天齐锂业"), ("000792", "盐湖股份"),
                           ("002756", "永兴材料"), ("002738", "中矿资源"), ("002176", "江特电机"),
                           ("002192", "融捷股份"), ("300390", "天华新能"), ("002240", "盛新锂能"),
                           ("002497", "雅化集团")]},
            {"key": "precursor", "name": "中游·前驱体",
             "nameEn": "Midstream · Precursors",
             "desc": "三元前驱体、钴镍资源冶炼与材料一体化",
             "descEn": "Ternary precursors, cobalt and nickel refining integration",
             "companies": [("300919", "中伟股份"), ("603799", "华友钴业"), ("002340", "格林美")]},
            {"key": "cathode", "name": "中游·正极材料",
             "nameEn": "Midstream · Cathode Materials",
             "desc": "磷酸铁锂、三元正极材料及前驱体配套",
             "descEn": "LFP and ternary cathode materials",
             "companies": [("300073", "当升科技"), ("688005", "容百科技"), ("300769", "德方纳米"),
                           ("301358", "湖南裕能"), ("688779", "长远锂科"), ("688778", "厦钨新能"),
                           ("688707", "振华新材"), ("688275", "万润新能")]},
            {"key": "anode", "name": "中游·负极材料",
             "nameEn": "Midstream · Anode Materials",
             "desc": "人造石墨、天然石墨负极及硅基负极",
             "descEn": "Artificial and natural graphite anodes, silicon-based anodes",
             "companies": [("603659", "璞泰来"), ("600884", "杉杉股份"), ("300035", "中科电气"),
                           ("300890", "翔丰华"), ("001301", "尚太科技")]},
            {"key": "separator", "name": "中游·隔膜",
             "nameEn": "Midstream · Separators",
             "desc": "湿法/干法锂电隔膜及涂覆隔膜",
             "descEn": "Wet- and dry-process battery separators and coated separators",
             "companies": [("002812", "恩捷股份"), ("300568", "星源材质"), ("002080", "中材科技"),
                           ("002108", "沧州明珠")]},
            {"key": "electrolyte", "name": "中游·电解液",
             "nameEn": "Midstream · Electrolytes",
             "desc": "锂离子电池电解液、六氟磷酸锂及添加剂",
             "descEn": "Battery electrolytes, LiPF6 salt and additives",
             "companies": [("002709", "天赐材料"), ("300037", "新宙邦"), ("002407", "多氟多"),
                           ("002759", "天际股份"), ("603026", "石大胜华")]},
            {"key": "cell", "name": "中游·电芯",
             "nameEn": "Midstream · Battery Cells",
             "desc": "动力与储能电池电芯及 PACK 制造",
             "descEn": "EV and energy-storage battery cells and packs",
             "companies": [("300750", "宁德时代"), ("002594", "比亚迪"), ("300014", "亿纬锂能"),
                           ("002074", "国轩高科"), ("300207", "欣旺达"), ("688567", "孚能科技"),
                           ("300438", "鹏辉能源")]},
            {"key": "equipment", "name": "中游·锂电设备",
             "nameEn": "Midstream · Battery Equipment",
             "desc": "涂布机、卷绕机、化成分容等锂电池生产设备",
             "descEn": "Coaters, winders, formation and grading equipment",
             "companies": [("300450", "先导智能"), ("688006", "杭可科技"), ("300457", "赢合科技")]},
            {"key": "recycling", "name": "回收",
             "nameEn": "Recycling",
             "desc": "退役动力电池梯次利用与再生回收",
             "descEn": "Cascade utilization and recycling of retired EV batteries",
             "companies": [("002340", "格林美"), ("002741", "光华科技"), ("002009", "天奇股份"),
                           ("603799", "华友钴业")]},
        ],
    },
    "pv": {
        "title": "光伏产业链", "titleEn": "Photovoltaic chain",
        "journey": "从硅料到组件", "journeyEn": "From polysilicon to modules",
        "price": {"symbols": ["SI0", "si0"], "name": "工业硅期货主力"},
        "stages": [
            {"key": "poly_silicon", "name": "上游·硅料",
             "nameEn": "Upstream · Polysilicon",
             "desc": "多晶硅料生产与提纯",
             "descEn": "Polysilicon production and purification",
             "companies": [("600438", "通威股份"), ("688303", "大全能源"), ("600089", "特变电工")]},
            {"key": "wafer", "name": "中游·硅片",
             "nameEn": "Midstream · Wafers",
             "desc": "单晶硅拉棒、切片",
             "descEn": "Mono-crystalline ingot pulling and wafer slicing",
             "companies": [("601012", "隆基绿能"), ("002129", "TCL中环"), ("603185", "上机数控"),
                           ("600481", "双良节能"), ("601908", "京运通")]},
            {"key": "cell_pv", "name": "中游·电池片",
             "nameEn": "Midstream · Solar Cells",
             "desc": "PERC、TOPCon、HJT 等太阳能电池片",
             "descEn": "PERC, TOPCon and HJT solar cells",
             "companies": [("600438", "通威股份"), ("600732", "爱旭股份"), ("002865", "钧达股份"),
                           ("603398", "沐邦高科")]},
            {"key": "module", "name": "下游·组件",
             "nameEn": "Downstream · Modules",
             "desc": "光伏组件封装与系统集成",
             "descEn": "PV module lamination and system integration",
             "companies": [("601012", "隆基绿能"), ("002459", "晶澳科技"), ("688599", "天合光能"),
                           ("688223", "晶科能源"), ("688472", "阿特斯"), ("300118", "东方日升")]},
            {"key": "glass", "name": "辅材·光伏玻璃",
             "nameEn": "Materials · PV Glass",
             "desc": "光伏压延玻璃原片与深加工",
             "descEn": "Rolled PV glass, raw and processed",
             "companies": [("601865", "福莱特"), ("002623", "亚玛顿")]},
            {"key": "film", "name": "辅材·胶膜",
             "nameEn": "Materials · Encapsulant Film",
             "desc": "EVA/POE 封装胶膜",
             "descEn": "EVA and POE encapsulant films",
             "companies": [("603806", "福斯特"), ("688680", "海优新材"), ("603212", "赛伍技术")]},
            {"key": "inverter", "name": "配套·逆变器",
             "nameEn": "Balance of System · Inverters",
             "desc": "光伏逆变器与储能变流器",
             "descEn": "PV inverters and storage converters",
             "companies": [("300274", "阳光电源"), ("300763", "锦浪科技"), ("688390", "固德威"),
                           ("605117", "德业股份"), ("688032", "禾迈股份"), ("688348", "昱能科技")]},
            {"key": "equipment_pv", "name": "配套·设备",
             "nameEn": "Equipment · PV Equipment",
             "desc": "晶体生长炉、丝网印刷、激光设备等光伏产线装备",
             "descEn": "Crystal growers, screen printers, laser tools and other PV line equipment",
             "companies": [("300316", "晶盛机电"), ("300751", "迈为股份"), ("300724", "捷佳伟创"),
                           ("688516", "奥特维"), ("603396", "金辰股份")]},
        ],
    },
    "semi": {
        "title": "半导体产业链", "titleEn": "Semiconductor chain",
        "journey": "从设计到封测", "journeyEn": "From design to packaging & testing",
        "price": None,
        "stages": [
            {"key": "design", "name": "上游·设计",
             "nameEn": "Upstream · IC Design",
             "desc": "模拟、射频、存储、处理器等芯片设计",
             "descEn": "Analog, RF, memory and processor chip design",
             "companies": [("603501", "韦尔股份"), ("603986", "兆易创新"), ("300782", "卓胜微"),
                           ("300661", "圣邦股份"), ("002049", "紫光国微"), ("688008", "澜起科技"),
                           ("688256", "寒武纪"), ("688041", "海光信息")]},
            {"key": "foundry", "name": "中游·制造代工",
             "nameEn": "Midstream · Foundry",
             "desc": "晶圆制造与代工",
             "descEn": "Wafer fabrication and foundry services",
             "companies": [("688981", "中芯国际"), ("688347", "华虹公司"), ("600460", "士兰微"),
                           ("688396", "华润微")]},
            {"key": "osat", "name": "中游·封测",
             "nameEn": "Midstream · Packaging & Testing",
             "desc": "集成电路封装与测试",
             "descEn": "IC packaging and testing (OSAT)",
             "companies": [("600584", "长电科技"), ("002156", "通富微电"), ("002185", "华天科技"),
                           ("603005", "晶方科技")]},
            {"key": "equipment_semi", "name": "上游·设备",
             "nameEn": "Upstream · Semiconductor Equipment",
             "desc": "刻蚀、薄膜沉积、清洗、检测等半导体设备",
             "descEn": "Etch, deposition, cleaning and metrology equipment",
             "companies": [("002371", "北方华创"), ("688012", "中微公司"), ("688072", "拓荆科技"),
                           ("688120", "华海清科"), ("300567", "精测电子"), ("300604", "长川科技")]},
            {"key": "material", "name": "上游·材料",
             "nameEn": "Upstream · Semiconductor Materials",
             "desc": "硅片、光刻胶、抛光液、靶材、电子特气等",
             "descEn": "Silicon wafers, photoresist, CMP slurry, sputtering targets, "
                       "electronic specialty gases",
             "companies": [("688126", "沪硅产业"), ("605358", "立昂微"), ("300666", "江丰电子"),
                           ("688019", "安集科技"), ("300346", "南大光电"), ("002409", "雅克科技"),
                           ("300054", "鼎龙股份")]},
            {"key": "eda", "name": "上游·EDA/IP",
             "nameEn": "Upstream · EDA & IP",
             "desc": "EDA 设计工具与半导体 IP 授权",
             "descEn": "EDA tools and semiconductor IP licensing",
             "companies": [("301269", "华大九天"), ("688206", "概伦电子"), ("688521", "芯原股份")]},
        ],
    },
    "robot": {
        "title": "机器人产业链", "titleEn": "Robotics chain",
        "journey": "从核心零部件到本体", "journeyEn": "From core components to robot bodies",
        "price": None,
        "stages": [
            {"key": "reducer", "name": "上游·减速器",
             "nameEn": "Upstream · Reducers",
             "desc": "谐波减速器、RV 减速器等精密减速装置",
             "descEn": "Harmonic and RV precision reducers",
             "companies": [("688017", "绿的谐波"), ("002472", "双环传动"), ("002896", "中大力德")]},
            {"key": "servo", "name": "上游·伺服与电机",
             "nameEn": "Upstream · Servos & Motors",
             "desc": "伺服系统、步进与空心杯电机",
             "descEn": "Servo systems, stepper and coreless motors",
             "companies": [("300124", "汇川技术"), ("603728", "鸣志电器"), ("688160", "步科股份"),
                           ("688320", "禾川科技")]},
            {"key": "screw", "name": "上游·丝杠",
             "nameEn": "Upstream · Screws",
             "desc": "滚珠丝杠、行星滚柱丝杠等线性传动部件",
             "descEn": "Ball screws, planetary roller screws and linear transmission parts",
             "companies": [("601100", "恒立液压"), ("300580", "贝斯特"), ("603009", "北特科技")]},
            {"key": "sensor", "name": "上游·传感器",
             "nameEn": "Upstream · Sensors",
             "desc": "力矩/六维力传感器、MEMS 惯性器件",
             "descEn": "Torque and six-axis force sensors, MEMS inertial devices",
             "companies": [("603662", "柯力传感"), ("300007", "汉威科技"), ("688582", "芯动联科")]},
            {"key": "actuator", "name": "中游·执行器总成",
             "nameEn": "Midstream · Actuator Assemblies",
             "desc": "机电执行器与关节模组总成",
             "descEn": "Electromechanical actuators and joint module assemblies",
             "companies": [("002050", "三花智控"), ("601689", "拓普集团")]},
            {"key": "body", "name": "中游·机器人本体",
             "nameEn": "Midstream · Robot Bodies",
             "desc": "工业机器人与人形机器人本体制造",
             "descEn": "Industrial and humanoid robot manufacturing",
             "companies": [("002747", "埃斯顿"), ("300024", "机器人"), ("688165", "埃夫特")]},
        ],
    },
    "compute": {
        "title": "AI 算力产业链", "titleEn": "AI compute chain",
        "journey": "从芯片到整机", "journeyEn": "From chips to servers",
        "price": None,
        "stages": [
            {"key": "chip", "name": "上游·算力芯片",
             "nameEn": "Upstream · Compute Chips",
             "desc": "GPU 与 AI 训练/推理芯片",
             "descEn": "GPU and AI training/inference chips",
             "companies": [("688256", "寒武纪"), ("688041", "海光信息"), ("300474", "景嘉微")]},
            {"key": "optical", "name": "中游·光模块",
             "nameEn": "Midstream · Optical Modules",
             "desc": "高速光模块与光器件",
             "descEn": "High-speed optical modules and optical devices",
             "companies": [("300308", "中际旭创"), ("300502", "新易盛"), ("300394", "天孚通信")]},
            {"key": "pcb", "name": "中游·PCB",
             "nameEn": "Midstream · PCB",
             "desc": "高速高多层 PCB 与覆铜板",
             "descEn": "High-speed multilayer PCBs and copper-clad laminates",
             "companies": [("002463", "沪电股份"), ("300476", "胜宏科技"), ("600183", "生益科技"),
                           ("603228", "景旺电子")]},
            {"key": "server", "name": "中游·服务器",
             "nameEn": "Midstream · Servers",
             "desc": "AI 服务器整机与算力集群",
             "descEn": "AI server systems and compute clusters",
             "companies": [("601138", "工业富联"), ("000977", "浪潮信息"), ("603019", "中科曙光")]},
            {"key": "cooling", "name": "配套·液冷温控",
             "nameEn": "Thermal Management · Liquid Cooling",
             "desc": "数据中心液冷与精密温控",
             "descEn": "Data-center liquid cooling and precision thermal management",
             "companies": [("002837", "英维克"), ("301018", "申菱环境"), ("300990", "同飞股份")]},
            {"key": "power", "name": "配套·电源",
             "nameEn": "Power Supply",
             "desc": "服务器电源与功率变换设备",
             "descEn": "Server power supplies and power conversion equipment",
             "companies": [("002851", "麦格米特"), ("300820", "英杰电气")]},
        ],
    },
    "storage": {
        "title": "储能产业链", "titleEn": "Energy storage chain",
        "journey": "从电池到系统集成", "journeyEn": "From batteries to system integration",
        "price": None,
        "stages": [
            {"key": "battery", "name": "上游·储能电池",
             "nameEn": "Upstream · Storage Batteries",
             "desc": "储能电芯与电池系统",
             "descEn": "Energy-storage cells and battery systems",
             "companies": [("300750", "宁德时代"), ("300014", "亿纬锂能"), ("300438", "鹏辉能源"),
                           ("688063", "派能科技")]},
            {"key": "pcs", "name": "中游·变流器PCS",
             "nameEn": "Midstream · PCS",
             "desc": "储能变流器（PCS）与升压一体设备",
             "descEn": "Power conversion systems (PCS) and integrated step-up units",
             "companies": [("300274", "阳光电源"), ("300827", "上能电气"), ("002335", "科华数据")]},
            {"key": "tempctrl", "name": "配套·温控",
             "nameEn": "Thermal Management",
             "desc": "储能温控与液冷设备",
             "descEn": "Thermal management and liquid cooling for storage",
             "companies": [("002837", "英维克"), ("300990", "同飞股份"), ("301018", "申菱环境")]},
            {"key": "integrate", "name": "下游·系统集成",
             "nameEn": "Downstream · System Integration",
             "desc": "储能系统集成与电站建设运营",
             "descEn": "Storage system integration and plant construction & operation",
             "companies": [("688248", "南网科技"), ("002121", "科陆电子"), ("300693", "盛弘股份")]},
        ],
    },
    "pharma": {
        "title": "医药产业链", "titleEn": "Pharma chain",
        "journey": "从原料药到制剂", "journeyEn": "From APIs to formulations",
        "price": None,
        "stages": [
            {"key": "api", "name": "上游·原料药",
             "nameEn": "Upstream · APIs",
             "desc": "化学原料药与中间体生产",
             "descEn": "Active pharmaceutical ingredients and intermediates",
             "companies": [("600521", "华海药业"), ("000739", "普洛药业"), ("603456", "九洲药业")]},
            {"key": "innovative", "name": "中游·创新药",
             "nameEn": "Midstream · Innovative Drugs",
             "desc": "小分子与生物创新药研发及商业化",
             "descEn": "Small-molecule and biologic innovative drug R&D and commercialization",
             "companies": [("600276", "恒瑞医药"), ("688235", "百济神州"), ("688266", "泽璟制药"),
                           ("688331", "荣昌生物"), ("688180", "君实生物")]},
            {"key": "vaccine", "name": "中游·疫苗与生物制品",
             "nameEn": "Midstream · Vaccines & Biologics",
             "desc": "疫苗、血液制品与生长激素",
             "descEn": "Vaccines, blood products and growth hormones",
             "companies": [("300122", "智飞生物"), ("300142", "沃森生物"), ("000661", "长春高新")]},
            {"key": "tcm", "name": "中游·中药",
             "nameEn": "Midstream · Traditional Chinese Medicine",
             "desc": "中成药、中药饮片与品牌 OTC",
             "descEn": "Patent Chinese medicines, decoction pieces and branded OTC",
             "companies": [("600436", "片仔癀"), ("000538", "云南白药"), ("600085", "同仁堂"),
                           ("000999", "华润三九")]},
            {"key": "device", "name": "中游·医疗器械",
             "nameEn": "Midstream · Medical Devices",
             "desc": "影像设备、监护仪器与植介入器械",
             "descEn": "Imaging systems, patient monitors and implantable/interventional devices",
             "companies": [("300760", "迈瑞医疗"), ("688271", "联影医疗"), ("002223", "鱼跃医疗"),
                           ("300003", "乐普医疗")]},
            {"key": "cxo", "name": "配套·CXO 研发外包",
             "nameEn": "CXO · R&D Outsourcing",
             "desc": "药物研发、临床与生产外包服务",
             "descEn": "Drug discovery, clinical and manufacturing outsourcing (CRO/CMO/CDMO)",
             "companies": [("603259", "药明康德"), ("300347", "泰格医药"), ("002821", "凯莱英"),
                           ("300759", "康龙化成")]},
        ],
    },
    "auto": {
        "title": "汽车产业链", "titleEn": "Auto chain",
        "journey": "从零部件到整车", "journeyEn": "From components to vehicles",
        "price": None,
        "stages": [
            {"key": "lightweight", "name": "上游·轻量化结构件",
             "nameEn": "Upstream · Lightweight Structural Parts",
             "desc": "铝合金压铸结构件与轻量化底盘",
             "descEn": "Aluminum die-cast structural parts and lightweight chassis",
             "companies": [("601689", "拓普集团"), ("603305", "旭升集团"), ("603348", "文灿股份"),
                           ("002101", "广东鸿图")]},
            {"key": "thermal", "name": "上游·热管理",
             "nameEn": "Upstream · Thermal Management",
             "desc": "汽车热管理系统与换热部件",
             "descEn": "Automotive thermal management systems and heat-exchange parts",
             "companies": [("002050", "三花智控"), ("002126", "银轮股份"), ("002011", "盾安环境")]},
            {"key": "trim", "name": "上游·内外饰与轮胎",
             "nameEn": "Upstream · Trim & Tires",
             "desc": "汽车玻璃、车灯、内外饰与轮胎",
             "descEn": "Auto glass, lighting, interior/exterior trim and tires",
             "companies": [("600660", "福耀玻璃"), ("601799", "星宇股份"), ("601966", "玲珑轮胎"),
                           ("601058", "赛轮轮胎")]},
            {"key": "electronics", "name": "中游·汽车电子与智驾",
             "nameEn": "Midstream · Auto Electronics & ADAS",
             "desc": "智能座舱、智能驾驶与线控制动",
             "descEn": "Smart cockpits, autonomous driving and brake-by-wire",
             "companies": [("002920", "德赛西威"), ("002906", "华阳集团"), ("300496", "中科创达"),
                           ("002405", "四维图新"), ("603596", "伯特利"), ("688326", "经纬恒润")]},
            {"key": "oem", "name": "下游·整车",
             "nameEn": "Downstream · OEMs",
             "desc": "乘用车整车制造",
             "descEn": "Passenger vehicle manufacturing",
             "companies": [("002594", "比亚迪"), ("000625", "长安汽车"), ("601633", "长城汽车"),
                           ("600104", "上汽集团"), ("601127", "赛力斯"), ("601238", "广汽集团")]},
        ],
    },
}


def load_names():
    """data/index.json → {代码: 公司名}；读不到返回 {}（用手工兜底名）。"""
    try:
        with open(os.path.join(DATA, "index.json"), encoding="utf-8") as f:
            idx = json.load(f)
        return {c["ticker"]: c["name"] for c in idx.get("companies", [])
                if c.get("ticker") and c.get("name")}
    except Exception as e:
        print(f"!! data/index.json 读取失败，公司名全部走手工兜底：{e}")
        return {}


def build_stages(cfg, names):
    """校验档案、组装 stages，返回 (stages, 有效代码集合, 剔除代码列表)。"""
    stages = []
    valid, dropped = set(), []
    for st in cfg["stages"]:
        companies = []
        for code, fallback in st["companies"]:
            if not os.path.exists(os.path.join(DATA, "p", f"{code}.json")):
                print(f"!! {code}（{fallback}）缺 data/p 档案，从「{st['name']}」剔除")
                dropped.append(code)
                continue
            companies.append({"code": code, "name": names.get(code) or fallback})
            valid.add(code)
        stages.append({"key": st["key"], "name": st["name"], "nameEn": st["nameEn"],
                       "desc": st["desc"], "descEn": st["descEn"],
                       "companies": companies})
    return stages, valid, dropped


def build_stage_trends(stages, valid):
    """对每阶段有日线的成员算等权指数；data/h 缺文件的成员容错跳过。

    返回 (trends, covered)：covered = 有日线数据的代码集合（供汇总打印）。
    """
    empty = {"dates": [], "stages": {st["key"]: [] for st in stages}}
    if not os.path.isdir(bt.H_DIR):
        print("!! data/h/ 不存在，trends 输出为空（先跑 fetch_history.py）")
        return empty, set()
    series = bt.load_history(valid)
    if not series:
        print("!! 链条成员暂无日线数据，trends 输出为空")
        return empty, set()
    axis, returns = bt.build_returns(series)
    n = len(axis)
    out = {}
    for st in stages:
        members = [c["code"] for c in st["companies"] if c["code"] in returns]
        out[st["key"]] = bt.index_series(members, returns, n) if members else []
    return {"dates": axis, "stages": out}, set(returns)


def write_price(chain_key, price_cfg):
    """期货主力日线 → data/price/{chain_key}.json。symbols 按序探测，全失败保留旧文件。"""
    out_path = os.path.join(DATA, "price", f"{chain_key}.json")
    points = None
    try:
        import akshare as ak
    except Exception as e:
        print(f"!! akshare 不可用（{e}），{chain_key} 价格线跳过")
    else:
        for sym in price_cfg["symbols"]:
            try:
                df = ak.futures_zh_daily_sina(symbol=sym)
                if df is None or df.empty:
                    raise RuntimeError("返回空数据")
                df = df.tail(PRICE_POINTS)
                points = [[str(d), float(c)] for d, c in zip(df["date"], df["close"])
                          if c == c and float(c) > 0]      # 拦 NaN
                if len(points) < 2:
                    raise RuntimeError(f"有效数据点不足：{len(points)}")
                break
            except Exception as e:
                print(f"!! {chain_key} 价格线 {sym} 探测失败：{e}")
                points = None
    if points is None:
        if os.path.exists(out_path):
            print(f"!! {chain_key} 价格线保留旧文件 {out_path}")
        else:
            print(f"!! {chain_key} 价格线本次不生成（前端降级处理）")
        return None
    obj = {"schemaVersion": 1, "generatedAt": date.today().isoformat(),
           "name": price_cfg["name"], "points": points}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    return obj


def build_one(chain_key, cfg, names):
    """构建单个链条，返回汇总信息。"""
    print(f"\n=== {chain_key} {cfg['title']} ===")
    generated = date.today().isoformat()
    stages, valid, dropped = build_stages(cfg, names)
    trends, covered = build_stage_trends(stages, valid)

    n_companies = len({c["code"] for st in stages for c in st["companies"]})
    obj = {
        "schemaVersion": 1,
        "generatedAt": generated,
        "key": chain_key,
        "title": cfg["title"],
        "titleEn": cfg["titleEn"],
        "sub": f"{cfg['journey']}：{len(stages)} 个阶段 · {n_companies} 家核心公司",
        "subEn": f"{cfg['journeyEn']}: {len(stages)} stages · "
                 f"{n_companies} core companies",
        "stages": stages,
        "trends": trends,
    }
    out_path = os.path.join(DATA, "chain", f"{chain_key}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))

    price_obj = write_price(chain_key, cfg["price"]) if cfg.get("price") else None

    for st in stages:
        n_hist = sum(1 for c in st["companies"] if c["code"] in covered)
        print(f"  {st['key']:<18} {st['name']:<10} "
              f"{len(st['companies']):>2} 家 / {n_hist:>2} 家有日线，"
              f"指数序列 {len(trends['stages'].get(st['key'], []))} 天")
    if dropped:
        print(f"  被剔除代码（缺 data/p 档案）：{dropped}")
    print(f"  trends 日期轴 {len(trends['dates'])} 天"
          + (f"（{trends['dates'][0]} ~ {trends['dates'][-1]}）" if trends["dates"] else ""))
    print(f"  chain/{chain_key}.json {os.path.getsize(out_path)/1024:.1f} KB")
    price_path = os.path.join(DATA, "price", f"{chain_key}.json")
    if price_obj:
        print(f"  price/{chain_key}.json {os.path.getsize(price_path)/1024:.1f} KB，"
              f"{len(price_obj['points'])} 个点，最新 {price_obj['points'][-1][0]}")
    elif cfg.get("price") and os.path.exists(price_path):
        print(f"  price/{chain_key}.json 沿用旧文件 "
              f"{os.path.getsize(price_path)/1024:.1f} KB")
    return obj


def main():
    names = load_names()
    for chain_key, cfg in CHAINS.items():
        build_one(chain_key, cfg, names)
    return 0


if __name__ == "__main__":
    sys.exit(main())
