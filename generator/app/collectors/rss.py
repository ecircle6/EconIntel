"""通用 RSS 采集器。

已验证数据源（2026-08）：
- NBER: https://www.nber.org/rss/new.xml —— description 含完整摘要；
  标题格式 "Title -- by A, B, C"；链接 /papers/wNNNNN 可推导 DOI 10.3386/wNNNNN。
"""
import feedparser

from .base import (
    BaseCollector,
    PaperDraft,
    clean_text,
    extract_doi,
    nber_doi_from_url,
    parse_feed_date,
    split_authors,
    strip_html,
)


class RSSCollector(BaseCollector):
    source_type = "rss"

    def fetch(self, start, end):
        resp = self.session.get(self.entry["url"], timeout=self.timeout)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        drafts = []
        for e in feed.entries:
            title = clean_text(e.get("title", ""))
            if not title:
                continue
            link = (e.get("link") or "").strip()
            guid = (e.get("guid") or "").strip()

            # NBER 标题："Fortunate Sons: ... -- by James J. Feigenbaum, ..."
            authors = []
            if " -- by " in title:
                title, _, author_str = title.partition(" -- by ")
                authors = [a.strip() for a in author_str.split(",") if a.strip()]
            if not authors:
                authors = split_authors("; ".join(a.get("name", "") for a in (e.get("authors") or [])))
            if not authors:
                for k in ("author", "creator", "dc:creator"):
                    v = e.get(k)
                    if v:
                        authors = split_authors(str(v))
                        break

            abstract = strip_html(e.get("summary", ""))
            doi = extract_doi(link, guid) or nber_doi_from_url(link)

            drafts.append(
                PaperDraft(
                    title=title,
                    authors=authors,
                    url=link,
                    published=parse_feed_date(e),
                    source=self.key,
                    paper_type=self.entry.get("paper_type", "working"),
                    doi=doi,
                    abstract=abstract or None,
                    abstract_source="source" if abstract else None,
                )
            )
        return drafts
