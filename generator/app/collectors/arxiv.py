"""arXiv API 采集器（econ.* 与 q-fin.* 分类，按提交时间倒序）。"""
import time
from urllib.parse import urlencode

import feedparser

from .base import BaseCollector, PaperDraft, clean_text, extract_doi, parse_feed_date


class ArxivCollector(BaseCollector):
    source_type = "api"

    def fetch(self, start, end):
        query = self.entry.get("query", "(cat:econ.* OR cat:q-fin.*)")
        start_str = start.strftime("%Y%m%d%H%M")
        end_str = end.strftime("%Y%m%d%H%M")
        url = "https://export.arxiv.org/api/query?" + urlencode(
            {
                "search_query": f"{query} AND submittedDate:[{start_str} TO {end_str}]",
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": self.entry.get("max_results", 500),
            }
        )
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        time.sleep(3.0)  # arXiv 官方 API 要求请求间隔 ≥ 3 秒（按请求计，非按论文计）
        feed = feedparser.parse(resp.content)
        drafts = []
        for e in feed.entries:
            title = clean_text(e.get("title", "")).rstrip(".")
            if not title:
                continue
            authors = [a.get("name", "").strip() for a in e.get("authors", []) if a.get("name")]
            abstract = clean_text(e.get("summary", ""))
            link = (e.get("link") or "").strip()
            doi = extract_doi(link, e.get("arxiv_doi", ""))
            drafts.append(
                PaperDraft(
                    title=title,
                    authors=authors,
                    url=link,
                    published=parse_feed_date(e),
                    source=self.key,
                    paper_type="working",
                    doi=doi,
                    abstract=abstract or None,
                    abstract_source="source" if abstract else None,
                )
            )
        return drafts
