"""采集器基类：统一 PaperDraft 结构、HTTP 重试会话、文本清洗工具。

架构说明（借鉴 Roundup 的采集模式，MIT 许可）：
- 每个数据源实现一个采集器，输出统一 PaperDraft；
- 抓取层内置指数退避重试；源状态（成功/失败/错误计数）由 pipeline 统一记录。
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup
from urllib3.util.retry import Retry

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
NBER_PAPER_RE = re.compile(r"/papers/(w\d+)", re.IGNORECASE)


@dataclass
class PaperDraft:
    """采集器产出的统一论文草稿。"""

    title: str
    authors: list
    url: str
    published: Optional[datetime]
    source: str
    paper_type: str = "working"          # working / journal
    doi: Optional[str] = None
    abstract: Optional[str] = None
    abstract_source: Optional[str] = None  # 摘要来源（source 表示源自数据源本身）


class FetchError(Exception):
    """抓取失败（网络/解析/超时等）。"""


def make_session(timeout: float = 8.0, retries: int = 3, backoff: float = 0.8) -> requests.Session:
    """带指数退避重试的 HTTP 会话（429/5xx 重试；支持环境代理 PROXY_URL）。"""
    s = requests.Session()
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = requests.adapters.HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": "EconIntel/0.1 (economics paper aggregator; +github.com/econintel)"})
    return s


def clean_text(text: str) -> str:
    """去 HTML 标签、去首尾空白、折叠空白。"""
    if not text:
        return ""
    text = HTML_TAG_RE.sub(" ", text)
    text = BeautifulSoup(text, "html.parser").get_text(" ") if "<" in text else text
    text = WS_RE.sub(" ", text)
    return text.strip()


def strip_html(text: str) -> str:
    """剥离 HTML 标签（保留文本内容）。"""
    if not text:
        return ""
    return clean_text(BeautifulSoup(text, "html.parser").get_text(" ")) if "<" in text else clean_text(text)


def normalize_doi(doi: str) -> Optional[str]:
    """DOI 规范化：小写、去空白/首尾点。"""
    if not doi:
        return None
    doi = doi.strip().lower().strip(".")
    return doi if DOI_RE.match(doi) else None


def extract_doi(*texts: str) -> Optional[str]:
    """从文本中提取第一个 DOI。"""
    for t in texts:
        if not t:
            continue
        m = DOI_RE.search(t)
        if m:
            return normalize_doi(m.group(0))
    return None


def nber_doi_from_url(url: str) -> Optional[str]:
    """NBER 链接 /papers/wNNNNN → DOI 10.3386/wNNNNN。"""
    m = NBER_PAPER_RE.search(url or "")
    if m:
        return f"10.3386/{m.group(1).lower()}"
    return None


def parse_feed_date(entry) -> Optional[datetime]:
    """feedparser entry → datetime（published_parsed 优先，其次 updated_parsed）。"""
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        st = entry.get(key)
        if st:
            try:
                return datetime(*st[:6])
            except (TypeError, ValueError):
                continue
    return None


def split_authors(text: str) -> list:
    """按 & / ; / 逗号切分作者串并清理。"""
    if not text:
        return []
    parts = re.split(r"&|;|\band\b", text)
    out = []
    for p in parts:
        name = clean_text(p).strip(" ,;")
        if name and name not in out:
            out.append(name)
    return out


class BaseCollector:
    """采集器基类。子类实现 fetch()，pipeline 负责状态记录与入库。"""

    key: str = ""
    source_type: str = ""            # rss / api / html

    def __init__(self, entry: dict, timeout: float = 8.0):
        self.entry = entry
        self.key = entry.get("key", "")   # 数据源标识（注册表为准）
        self.timeout = timeout
        self.session = make_session(timeout=timeout)

    def fetch(self, start: datetime, end: datetime) -> list:
        """抓取 [start, end) 窗口内的论文，返回 PaperDraft 列表。"""
        raise NotImplementedError
