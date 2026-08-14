"""0-100 综合重要性评分与等级标签。

score = 机构权威 + 引用数对数归一化 + 时效分段 + 论文类型
默认权重（config 可调）：机构 32 / 引用 30 / 时效 26 / 类型 12
标签：>=80 🔥热点 / >=60 ⭐重要 / <60 📄普通

评分语义（无引用时也有区分度）：
- A 官方机构最新工作论文 ≈ 62 ⭐重要（顶级机构新论文）
- 🔥热点需要引用/期刊支撑（≥80）
- C 预印本 / 旧论文 / 低权威源 → 📄普通
"""
from datetime import datetime

AUTHORITY_SCORES = {"A": 1.0, "B": 0.62, "C": 0.25}   # 机构权威（占 institution 权重比例）


def recency_points(published: datetime, today: datetime, weight: int) -> int:
    """时效分段：越新分越高（按权重比例分档）。"""
    if not published:
        return 0
    days = (today - published).days
    if days < 0 or days <= 14:
        return weight
    if days <= 30:
        return round(weight * 0.8)
    if days <= 60:
        return round(weight * 0.5)
    if days <= 90:
        return round(weight * 0.25)
    return 0


def citation_points(citations, weight: int) -> int:
    """引用数对数归一化：c^0.35 缩放至 weight 分（0 引用 = 0 分）。"""
    if citations is None:
        return 0
    c = max(0, int(citations))
    if c == 0:
        return 0
    return min(weight, round((c ** 0.35) * weight / (200 ** 0.35)))


def compute_score(
    credibility: str,
    paper_type: str,
    citations,
    published_at: datetime,
    today: datetime,
    weights: dict,
) -> int:
    institution = round(weights["institution"] * AUTHORITY_SCORES.get(credibility, 0.25))
    cites = citation_points(citations, weights["citations"])
    recency = recency_points(published_at, today, weights["recency"])
    ptype = weights["paper_type"] if paper_type == "journal" else max(2, round(weights["paper_type"] / 3))
    return min(100, institution + cites + recency + ptype)


def label_for(score: int) -> str:
    if score >= 80:
        return "🔥热点"
    if score >= 60:
        return "⭐重要"
    return "📄普通"
