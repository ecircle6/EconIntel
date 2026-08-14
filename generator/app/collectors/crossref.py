"""CrossRef API 采集器：TOP 经济学期刊期刊文章（按 ISSN 逐个查询）。

ISSN 列表：AER 0002-8282、QJE 0033-5533、JPE 0022-3808、ECMA 0012-9682、
REStud 0034-6527、JF 0022-1082、JFE 0304-405X。
引用数在富化阶段按 DOI 单独查询（is-referenced-by-count）。
"""
from .base import BaseCollector, PaperDraft, clean_text, extract_doi, strip_html


class CrossrefCollector(BaseCollector):
    source_type = "api"

    def fetch(self, start, end):
        drafts = []
        start_str = start.date().isoformat()
        end_str = end.date().isoformat()
        for issn in self.entry.get("issns", []):
            url = f"https://api.crossref.org/journals/{issn}/works"
            params = {
                "filter": f"from-pub-date:{start_str},until-pub-date:{end_str}",
                "rows": 100,
                "sort": "published",
                "order": "desc",
                "select": "DOI,title,author,abstract,issued,URL,container-title",
            }
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            items = resp.json().get("message", {}).get("items", [])
            for item in items:
                title = clean_text((item.get("title") or [""])[0])
                if not title:
                    continue
                doi = extract_doi(item.get("DOI", ""))
                authors = []
                for a in item.get("author") or []:
                    family = (a.get("family") or "").strip()
                    given = (a.get("given") or "").strip()
                    name = f"{given} {family}".strip() if family else given
                    if name:
                        authors.append(name)
                abstract = strip_html(item.get("abstract", ""))
                date_parts = (item.get("issued") or {}).get("date-parts") or [[None]]
                published = None
                try:
                    if date_parts and date_parts[0][0]:
                        y, m, d = (date_parts[0] + [1, 1])[:3]
                        published = __import__("datetime").datetime(int(y), int(m), int(d))
                except (TypeError, ValueError):
                    published = None
                url_link = (item.get("URL") or "").strip() or (f"https://doi.org/{doi}" if doi else "")
                drafts.append(
                    PaperDraft(
                        title=title,
                        authors=authors,
                        url=url_link,
                        published=published,
                        source=self.key,
                        paper_type="journal",
                        doi=doi,
                        abstract=abstract or None,
                        abstract_source="source" if abstract else None,
                    )
                )
        return drafts
