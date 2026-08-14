"""OpenAI 兼容 LLM 客户端（DeepSeek / OpenAI / 本地 Ollama 均可）。

未配置 EI_LLM_API_KEY 时客户端为 None，调用方自动降级到规则算法（summarize.py）。
"""
import json

PROMPT = """你是一名经济学论文分析助手。根据论文标题与摘要，输出严格的 JSON（不要输出任何其他内容）：
{
  "short_title": "10-15字的精简标题（中文，保留核心信息）",
  "contribution": "用1-2句中文概括论文的核心贡献或发现",
  "keywords": ["3-5个英文关键词"],
  "jel": ["1-3个JEL分类代码，如E52、G12；若无法判断则输出[]"]
}"""


def make_client(cfg):
    """返回 OpenAI 客户端或 None（未配置 Key）。"""
    if not cfg.llm_enabled:
        return None
    try:
        from openai import OpenAI

        return OpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url, timeout=cfg.llm_timeout)
    except ImportError:  # openai 未安装时静默降级
        return None


def summarize_with_llm(client, model: str, title: str, abstract: str, authors: list) -> dict | None:
    """LLM 生成 {short_title, contribution, keywords, jel}；任何失败返回 None。"""
    if client is None:
        return None
    abstract_part = abstract[:2000] if abstract else "（无摘要，请仅依据标题推断，并在返回的 keywords 中不做编造）"
    user = f"标题：{title}\n作者：{'、'.join(authors[:5]) or '未知'}\n摘要：{abstract_part}"
    for attempt in range(2):
        kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
            max_tokens=400,
        )
        if attempt == 0:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content or ""
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("not a dict")
            return {
                "short_title": str(data.get("short_title", ""))[:60],
                "contribution": str(data.get("contribution", ""))[:400],
                "keywords": [str(k)[:40] for k in (data.get("keywords") or [])][:6],
                "jel": [str(j)[:8].upper() for j in (data.get("jel") or [])][:4],
            }
        except Exception:
            continue
    return None
