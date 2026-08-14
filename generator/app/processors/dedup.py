"""去重与父子版本追踪。

匹配优先级：DOI 精确匹配 → 规范化 URL 匹配 → 「规范化标题 + 第一作者姓氏」模糊匹配。
同一研究的多个版本共享 version_group；root = 主展示版（期刊版优先，其次最新）。

版本追踪是全生态空白点（详见 README），这里实现「够用版」启发式：
- 同一 group 内的论文互为版本，详情页展示版本历史；
- 版本间摘要互补（同组任一版本有摘要则 root 可继承，abstract_source='version'）。
"""
import re
import unicodedata
import uuid
from datetime import datetime

from sqlalchemy import select

from ..collectors.base import PaperDraft
from ..models import Paper

PUNCT_RE = re.compile(r"[\W_]+", re.UNICODE)


def normalize_doi(doi):
    """DOI 规范化：小写、去首尾空白与点。"""
    if not doi:
        return None
    d = doi.strip().lower().strip(".")
    return d if re.match(r"10\.\d{4,9}/", d) else None


def normalize_title(title: str) -> str:
    """标题规范化：小写、NFKD 归一、去标点、折叠空白。"""
    if not title:
        return ""
    t = unicodedata.normalize("NFKD", title).lower()
    t = PUNCT_RE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def normalize_url(url: str) -> str:
    """URL 规范化：小写、去协议与尾斜杠。"""
    if not url:
        return ""
    u = url.strip().lower().rstrip("/")
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            u = u[len(prefix):]
    return u


def author_surname(name: str) -> str:
    """作者姓氏：'Family, Given' 取逗号前；'Given Family' 取末词；中文名整体。"""
    n = (name or "").strip()
    if not n:
        return ""
    if re.search(r"[\u4e00-\u9fff]", n):
        return n
    if "," in n:
        return n.split(",")[0].strip().lower()
    return n.split()[-1].lower()


def title_author_key(title: str, authors: list) -> str:
    """「规范化标题 | 第一作者姓氏」分组键。"""
    nt = normalize_title(title)
    if not nt:
        return ""
    fa = author_surname(authors[0]) if authors else ""
    return f"{nt}|{fa}"


class GroupMatcher:
    """内存索引版去重：一次性载入全部论文建 DOI/URL/标题键 索引。"""

    def __init__(self, session):
        papers = session.execute(select(Paper)).scalars().all()
        self.doi_map = {}
        self.url_map = {}
        self.key_map = {}
        for p in papers:
            if p.doi:
                self.doi_map.setdefault(p.doi, p)
            u = normalize_url(p.url_original or "")
            if u:
                self.url_map.setdefault(u, p)
            k = title_author_key(p.title_original, p.authors or [])
            if k:
                self.key_map.setdefault(k, p)

    def match(self, draft: PaperDraft):
        """返回 (group_id, is_new_group)。"""
        doi = normalize_doi(draft.doi)
        if doi and doi in self.doi_map:
            return self.doi_map[doi].version_group, False
        url = normalize_url(draft.url)
        if url and url in self.url_map:
            return self.url_map[url].version_group, False
        key = title_author_key(draft.title, draft.authors)
        if key and key in self.key_map:
            return self.key_map[key].version_group, False
        return uuid.uuid4().hex[:16], True


def choose_root(group_papers: list) -> Paper:
    """组内选主展示版：期刊版 > 来源权威度(A>B>C) > 发布时间最新。"""
    if not group_papers:
        return None

    def key(p):
        cred = {"A": 3, "B": 2, "C": 1}.get(p.credibility, 0)
        return (1 if p.paper_type == "journal" else 0, cred, p.published_at or p.collected_at)

    return max(group_papers, key=key)


def sync_group_roles(session, group_id: str) -> None:
    """重算组内版本角色与摘要继承。"""
    papers = session.execute(
        select(Paper).where(Paper.version_group == group_id)
    ).scalars().all()
    if not papers:
        return
    root = choose_root(papers)
    for p in papers:
        p.version_role = "root" if p.id == root.id else "variant"
    # 摘要继承：root 无摘要时从同组其他版本补
    if root and not root.abstract:
        for p in papers:
            if p.id != root.id and p.abstract:
                root.abstract = p.abstract
                root.abstract_source = "version"
                break
