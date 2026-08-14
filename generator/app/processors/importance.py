"""0-100 综合重要性评分与等级标签。

score = 机构权威 + 引用数对数归一化 + 时效连续衰减 + 论文类型
默认权重（config 可调）：机构 32 / 引用 30 / 时效 26 / 类型 12
标签：>=80 🔥热点 / >=60 ⭐重要 / <60 📄普通

设计原则（回应「区分度」与「真实有效」）：
- 引用分：log1p 映射，基准 C0=100（经济学论文 100 引用即高引），饱和前连续展开；
  无引用数据按 0 计并在构成中标注「未知」，绝不虚构影响力；
- 时效分：连续指数衰减（26×exp(-age/45)），避免分档导致的同分聚集；
- 总分保留 1 位小数，构成逐项可查（详情页展示）。
"""
from datetime import datetime

AUTHORITY_SCORES = {"A": 1.0, "B": 0.62, "C": 0.25}   # 机构权威（占 institution 权重比例）
CITATION_BASE = 100.0                                   # 引用分饱和基准（引用数达到该值时打满）
RECENCY_DECAY = 45.0                                    # 时效半衰期（天）


def recency_points(published: datetime, today: datetime, weight: int) -> float:
    """时效分：连续指数衰减（0 天=满权重，45 天≈1/e，90 天≈13%）。"""
    if not published:
        return 0.0
    days = (today - published).days
    if days < 0:
        return float(weight)
    return round(weight * 2.718281828 ** (-days / RECENCY_DECAY), 1)


def citation_points(citations, weight: int) -> float:
    """引用分：log1p 归一化至 weight 分（c=100 打满；0/未知 = 0）。"""
    if citations is None:
        return 0.0
    c = max(0, int(citations))
    if c == 0:
        return 0.0
    import math

    return round(min(weight, weight * math.log1p(c) / math.log1p(CITATION_BASE)), 1)


def compute_score(
    credibility: str,
    paper_type: str,
    citations,
    published_at: datetime,
    today: datetime,
    weights: dict,
) -> float:
    """返回 1 位小数总分。"""
    institution = round(weights["institution"] * AUTHORITY_SCORES.get(credibility, 0.25), 1)
    cites = citation_points(citations, weights["citations"])
    recency = recency_points(published_at, today, weights["recency"])
    ptype = float(weights["paper_type"]) if paper_type == "journal" else max(2.0, round(weights["paper_type"] / 3, 1))
    return round(min(100.0, institution + cites + recency + ptype), 1)


def score_breakdown(
    credibility: str,
    paper_type: str,
    citations,
    published_at: datetime,
    today: datetime,
    weights: dict,
) -> dict:
    """评分构成（详情页透明展示）。"""
    institution = round(weights["institution"] * AUTHORITY_SCORES.get(credibility, 0.25), 1)
    cites = citation_points(citations, weights["citations"])
    recency = recency_points(published_at, today, weights["recency"])
    ptype = float(weights["paper_type"]) if paper_type == "journal" else max(2.0, round(weights["paper_type"] / 3, 1))
    return {
        "institution": institution,
        "citations": cites,
        "recency": recency,
        "paper_type": ptype,
        "total": round(min(100.0, institution + cites + recency + ptype), 1),
    }


def label_for(score: float) -> str:
    if score >= 80:
        return "🔥热点"
    if score >= 60:
        return "⭐重要"
    return "📄普通"
