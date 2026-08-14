"""0-100 综合重要性评分与等级标签。

score = 机构权威(25) + 引用数对数归一化(45) + 时效分段(24) + 论文类型(6)
标签：>=80 🔥热点 / >=60 ⭐重要 / <60 📄普通
权重与分档均在 config 中可调。
"""
from datetime import datetime, timedelta

AUTHORITY_SCORES = {"A": 1.0, "B": 0.6, "C": 0.25}   # 机构权威（占 institution 权重比例）


def recency_points(published: datetime, today: datetime) -> int:
    """时效分段：越新分越高（满分 recency 权重）。"""
    if not published:
        return 0
    days = (today - published).days
    if days < 0:
        return 24
    if days <= 14:
        return 24
    if days <= 30:
        return 19
    if days <= 60:
        return 12
    if days <= 90:
        return 6
    return 0


def citation_points(citations, weight: int) -> int:
    """引用数对数归一化：log1p 缩放至 weight 分。"""
    if citations is None:
        return 0
    c = max(0, int(citations))
    if c == 0:
        return 0
    scaled = min(weight, round((c ** 0.35) * weight / (200 ** 0.35)))
    return scaled


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
    recency = recency_points(published_at, today)
    ptype = weights["paper_type"] if paper_type == "journal" else 2
    return min(100, institution + cites + recency + ptype)


def label_for(score: int) -> str:
    if score >= 80:
        return "🔥热点"
    if score >= 60:
        return "⭐重要"
    return "📄普通"
