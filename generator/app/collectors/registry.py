"""8 个核心数据源注册表 + 采集器工厂。

可信度分级：A 官方机构 > B 学术数据库 > C 预印本。
扩展方式：在此追加一条 entry 并在 COLLECTORS 注册对应采集器类即可（参考 README 扩展路线）。
"""
from .arxiv import ArxivCollector
from .base import BaseCollector
from .crossref import CrossrefCollector
from .repec import NEPCollector, RepecSeriesCollector
from .rss import RSSCollector

SOURCES = [
    {
        "key": "nber",
        "name": "NBER 工作论文",
        "type": "rss",
        "url": "https://www.nber.org/rss/new.xml",
        "credibility": "A",
        "collector": "rss",
        "paper_type": "working",
    },
    {
        "key": "cepr",
        "name": "CEPR 讨论论文",
        "type": "html",
        "series": "cpr/ceprdp",
        "series_short": "cprceprdp",
        "credibility": "A",
        "collector": "repec_series",
        "workers": 6,
    },
    {
        "key": "fed",
        "name": "美联储 FEDS 工作论文",
        "type": "html",
        "series": "fip/fedgfe",
        "series_short": "fipfedgfe",
        "credibility": "A",
        "collector": "repec_series",
        "workers": 6,
    },
    {
        "key": "worldbank",
        "name": "世界银行工作论文",
        "type": "html",
        "series": "wbk/wbrwps",
        "series_short": "wbkwbrwps",
        "credibility": "A",
        "collector": "repec_series",
        "workers": 6,
    },
    {
        "key": "imf",
        "name": "IMF 工作论文",
        "type": "html",
        "series": "imf/imfwpa",
        "series_short": "imfimfwpa",
        "credibility": "A",
        "collector": "repec_series",
        "workers": 6,
    },
    {
        "key": "arxiv",
        "name": "arXiv 经济学与金融",
        "type": "api",
        "query": "(cat:econ.* OR cat:q-fin.*)",
        "credibility": "C",
        "collector": "arxiv",
        "max_results": 500,
        "paper_type": "working",
    },
    {
        "key": "nep",
        "name": "RePEc/NEP 领域文摘",
        "type": "html",
        "topics": ["nep-mac", "nep-mon", "nep-fin", "nep-mic", "nep-ecm", "nep-dev"],
        "issues": 2,
        "credibility": "B",
        "collector": "nep",
    },
    {
        "key": "crossref",
        "name": "TOP 经济学期刊",
        "type": "api",
        "issns": ["0002-8282", "0033-5533", "0022-3808", "0012-9682", "0034-6527", "0022-1082", "0304-405X"],
        "credibility": "B",
        "collector": "crossref",
    },
]

_COLLECTORS = {
    "rss": RSSCollector,
    "arxiv": ArxivCollector,
    "crossref": CrossrefCollector,
    "repec_series": RepecSeriesCollector,
    "nep": NEPCollector,
}


def build_collector(entry: dict, timeout: float) -> BaseCollector:
    cls = _COLLECTORS[entry["collector"]]
    collector = cls(entry, timeout=timeout)
    collector.key = entry["key"]  # 数据源标识（注册表为准）
    return collector
