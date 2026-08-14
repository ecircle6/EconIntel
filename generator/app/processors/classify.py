"""研究领域自动分类：规则关键词词典（标题命中加权 2 倍）。

规则优先、确定性输出；LLM 配置后由 summarize 阶段补充 JEL 细化。
中英双语关键词：覆盖英文摘要与偶见的少量中文摘要。
"""
import re

# (领域, [关键词...]) —— 关键词小写匹配
FIELDS = [
    ("宏观", [
        "monetary policy", "inflation", "fiscal policy", "business cycle", "economic growth",
        "recession", "gdp", "interest rate", "unemployment", "exchange rate", "aggregate",
        "macroeconom", "central bank", "output gap", "deflation", "supply shock",
        "demand shock", "okun", "phillips", "quantitative easing", "unconventional monetary",
        "potential output", "real activity", "monetary economics", "monetary shock",
        "货币政策", "通货膨胀", "财政政策", "经济周期", "经济增长", "汇率", "失业",
    ]),
    ("金融", [
        "asset pricing", "stock market", "credit", "bank", "liquidity", "portfolio",
        "derivative", "risk premium", "financial", "leverage", "default", "bond", "equity",
        "market microstructure", "hedge fund", "volatility", "capm", "mutual fund",
        "corporate finance", "financing", "loan", "fintech", "banking", "systemic risk",
        "shadow bank", "stock return", "cryptocurrency", "stablecoin", "initial coin",
        "股票市场", "银行", "金融", "债券", "风险", "信贷",
    ]),
    ("微观理论", [
        "game theory", "mechanism design", "auction", "bargaining", "contract theory",
        "incentive", "matching", "equilibrium", "utility", "preference", "information economics",
        "screening", "signaling", "market design", "principal-agent", "mechanism",
        "博弈", "机制设计", "拍卖", "契约",
    ]),
    ("计量", [
        "causal inference", "identification", "regression", "panel", "instrumental",
        "difference-in-differences", "randomized", "field experiment", "natural experiment",
        "structural estimation", "machine learning", "econometric", "synthetic control",
        "regression discontinuity", "event study", "heterogeneity", "treatment effect",
        "bootstrap", "bayesian", "randomized controlled", "quasi-experimental",
        "causal effect", "selection bias", "garch", "var model",
        "计量", "因果推断", "回归", "面板", "实验",
    ]),
    ("劳动", [
        "labor market", "wage", "employment", "job", "human capital", "education",
        "migration", "immigration", "retirement", "gender", "discrimination", "union",
        "occupation", "childcare", "pension", "labor force", "unemployment insurance",
        "workforce", "workers", "earnings", "labor supply", "labor demand", "minimum wage",
        "劳动", "工资", "就业", "教育", "移民", "退休",
    ]),
    ("发展", [
        "development", "poverty", "africa", "india", "rural", "household", "microfinance",
        "aid", "child health", "developing countr", "inequality of opportunity",
        "schooling", "malnutrition", "sustainable development", "emerging market",
        "发展中国家", "贫困", "农村", "小额信贷",
    ]),
    ("公共", [
        "tax", "taxation", "government spending", "public good", "social security",
        "welfare", "redistribution", "transfer", "healthcare", "medicare", "medicaid",
        "public finance", "subsidy", "social insurance", "income tax", "corporate tax",
        "government debt", "public policy", "公共服务", "税收", "福利", "社保",
    ]),
    ("国际", [
        "trade", "tariff", "export", "import", "foreign direct investment", "international",
        "global value chain", "terms of trade", "protectionism", "gravity", "offshoring",
        "current account", "capital flow", "globalization", "trade war", "trade policy",
        "multinational", "sovereign debt", "foreign exchange", "贸易", "关税", "出口", "进口", "全球化",
    ]),
    ("产业组织", [
        "market power", "competition", "antitrust", "monopoly", "oligopoly", "entry",
        "platform", "network effect", "pricing", "firm", "industry", "concentration",
        "collusion", "vertical integration", "innovation and market",
        "市场势力", "竞争", "反垄断", "平台", "定价",
    ]),
    ("环境", [
        "climate", "environment", "pollution", "carbon", "energy", "renewable", "emission",
        "natural resource", "environmental regulation", "green", "sustainability",
        "global warming", "climate change", "weather", "环境", "气候", "碳", "污染", "能源",
    ]),
    ("健康", [
        "health", "mortality", "disease", "epidemic", "pandemic", "vaccination",
        "health insurance", "obesity", "mental health", "medical", "healthcare",
        "covid", "health economics", "健康", "疾病", "医疗", "疫情", "疫苗",
    ]),
    ("政治经济", [
        "political economy", "election", "voting", "democracy", "corruption", "conflict",
        "institution", "media", "polarization", "political", "government accountability",
        "authoritarian", "civil war", "政治", "选举", "民主", "腐败", "冲突",
    ]),
    ("行为与实验", [
        "behavioral", "experiment", "nudge", "prospect theory", "preference elicitation",
        "laboratory", "choice", "experimental economics", "cognitive", "psychology",
        "行为", "实验经济学", "偏好",
    ]),
    ("数据与方法", [
        "big data", "text analysis", "web scraping", "nowcasting", "forecast",
        "index", "measurement", "survey data", "administrative data", "data science",
        "大数据", "预测", "文本分析",
    ]),
]

# 领域 → 近似 JEL 大类（规则降级用；LLM 配置后输出精确码）
FIELD_JEL = {
    "宏观": "E", "金融": "G", "微观理论": "D", "计量": "C", "劳动": "J",
    "发展": "O", "公共": "H", "国际": "F", "产业组织": "L", "环境": "Q",
    "健康": "I", "政治经济": "P", "行为与实验": "D", "数据与方法": "C",
}

FIELD_ORDER = [f[0] for f in FIELDS]


def _hit_count(text: str, keywords: list) -> int:
    low = text.lower()
    return sum(1 for k in keywords if k in low)


def classify(title: str, abstract: str = "") -> str:
    """标题/摘要 → 研究领域（中文）。标题命中加权 2 倍。"""
    if not title and not abstract:
        return "其他"
    best_field, best_score = "其他", 0
    for field, kws in FIELDS:
        score = _hit_count(title, kws) * 2 + _hit_count(abstract, kws)
        if score > best_score:
            best_field, best_score = field, score
    return best_field


def approx_jel(field: str) -> list:
    """规则降级：领域 → 近似 JEL 大类。"""
    letter = FIELD_JEL.get(field)
    return [letter] if letter else []
