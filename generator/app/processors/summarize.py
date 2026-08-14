"""AI 精简编排：LLM 优先，规则降级兜底（系统始终可用）。

规则降级：
- 精简标题：去前导冠词后截断（英文按词、中文按字）；
- 核心贡献：摘要首句（无摘要则置空，不编造）；
- 关键词：英文词频（去停用词，长词加权）；含中文时用 jieba；
- JEL：由领域映射近似大类。
"""
import re
from collections import Counter
from datetime import datetime

from .classify import approx_jel
from .llm import make_client, summarize_with_llm

STOPWORDS = set("""
a an the and or but if then else for of to in on at by with from as into over under
about against between through during before after above below up down out off
this that these those it its is are was were be been being have has had do does did
will would shall should can could may might must not no nor too very just also
more most less least such only own same than so what which who whom whose when
where why how all any both each few other some per etc e g i ii iii
we our you your they their he she his her them study paper using use used
""".split())

PUNCT_RE = re.compile(r"[^\w\s\-\u4e00-\u9fff]")


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def rule_short_title(title: str) -> str:
    """规则精简标题：去前导冠词，英文截 10 词、中文截 14 字。"""
    t = title.strip()
    if not t:
        return ""
    if len(t) <= 15:
        return t
    t = re.sub(r"^(the|a|an|on|toward|towards|about|into)\s+", "", t, flags=re.IGNORECASE)
    if _has_cjk(t):
        return t[:14] + "…"
    words = t.split()
    if len(words) <= 10:
        return t.rstrip(" ,;:")[:60]
    return " ".join(words[:10]).rstrip(" ,;:") + "…"


def rule_contribution(abstract: str) -> str:
    """规则核心贡献：摘要首句（不编造；无摘要返回空）。"""
    if not abstract:
        return ""
    first_sent = re.split(r"(?<=[.!?])\s+", abstract.strip(), maxsplit=1)[0]
    first_sent = first_sent.strip()
    return first_sent[:150] if first_sent else ""


def rule_keywords(title: str, abstract: str) -> list:
    """规则关键词：中文走 jieba，英文走词频（长词加权）。"""
    text = f"{title} {abstract or ''}"
    if not text.strip():
        return []
    if _has_cjk(text):
        try:
            import jieba.analyse

            return jieba.analyse.extract_tags(text, topK=5)[:5]
        except ImportError:
            pass
    tokens = re.findall(r"[A-Za-z][A-Za-z\-']{3,}", text.lower())
    tokens = [t for t in tokens if t not in STOPWORDS]
    freq = Counter()
    for t in tokens:
        freq[t] += 1 + min(len(t), 8) / 8.0  # 长词更具体，加权
    return [w for w, _ in freq.most_common(5)]


def summarize_paper(cfg, paper, llm_client=None) -> bool:
    """为论文生成 精简标题/贡献/关键词/JEL。返回 True 表示由 LLM 生成。"""
    if llm_client is None:
        llm_client = make_client(cfg)
    result = None
    if llm_client is not None:
        result = summarize_with_llm(
            llm_client, cfg.llm_model, paper.title_original, paper.abstract, paper.authors or []
        )
    used_llm = result is not None
    if not result:
        result = {
            "short_title": rule_short_title(paper.title_original),
            "contribution": rule_contribution(paper.abstract),
            "keywords": rule_keywords(paper.title_original, paper.abstract),
            "jel": approx_jel(paper.field),
        }
    paper.title_short = (result["short_title"] or paper.title_original)[:60]
    paper.contribution = result["contribution"]
    paper.keywords = result["keywords"]
    paper.jel = result["jel"]
    paper.summarized_at = datetime.utcnow()
    return used_llm
