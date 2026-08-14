"""摘要与引用富化：并发 + 超时预算 + 短路 + 增量缓存。

摘要四级链：源自带 → CrossRef → OpenAlex（免费无 key）→ Semantic Scholar（限速）。
- 单请求超时 cfg.request_timeout；单篇总预算 cfg.paper_budget 秒，超时跳过（下次自动补）；
- 任一命中即短路；已有摘要的论文只补引用，不重查摘要；
- HTTP 全部在工作者线程执行，结果由主线程统一写库（SQLite WAL，避免写锁竞争）。
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

from ..collectors.base import strip_html

UA = "EconIntel/0.1 (economics paper aggregator)"


class Enricher:
    def __init__(self, cfg):
        self.cfg = cfg
        self._s2_lock = threading.Lock()
        self._s2_last = 0.0
        # OpenAlex 全局限速 + 429 退避（无 mailto 走共享池，必须限速）
        self._oa_lock = threading.Lock()
        self._oa_last = 0.0
        mailto = getattr(cfg, "openalex_mailto", "") or ""
        self._ua = f"EconIntel/0.1 (mailto:{mailto})" if mailto else UA

    # ---- 对外入口 ----

    def enrich(self, papers) -> dict:
        """并发富化一批论文；返回 {paper_id: {abstract, abstract_source, citations}}。"""
        results = {}
        with ThreadPoolExecutor(max_workers=self.cfg.enrich_workers) as pool:
            futures = {pool.submit(self._enrich_one, p): p for p in papers}
            for fut in futures:
                try:
                    out = fut.result()
                    if out:
                        results[futures[fut].id] = out
                except Exception:
                    continue
        return results

    # ---- 单篇流程 ----

    def _enrich_one(self, paper) -> dict:
        deadline = time.monotonic() + self.cfg.paper_budget
        out = {}
        need_abs = not paper.abstract
        need_cites = paper.citations is None

        if need_abs and paper.doi and time.monotonic() < deadline:
            abstract = self._crossref_abstract(paper.doi)
            if abstract:
                out["abstract"], out["abstract_source"] = abstract, "crossref"
                need_abs = False

        if need_abs and time.monotonic() < deadline:
            abstract = self._openalex_abstract(paper)
            if abstract:
                out["abstract"], out["abstract_source"] = abstract, "openalex"
                need_abs = False

        if need_abs and time.monotonic() < deadline:
            abstract = self._s2_abstract(paper)
            if abstract:
                out["abstract"], out["abstract_source"] = abstract, "s2"

        if need_cites and time.monotonic() < deadline:
            cites = None
            if paper.doi:
                cites = self._crossref_citations(paper.doi)
            if cites is None:
                cites = self._openalex_citations(paper)
            if cites is not None:
                out["citations"] = cites
        return out

    # ---- HTTP 基础 ----

    def _get(self, url, params=None):
        return requests.get(url, params=params, timeout=self.cfg.request_timeout,
                            headers={"User-Agent": self._ua})

    def _openalex_get(self, url, params=None):
        """OpenAlex 请求：全局限速 + 429 指数退避重试。"""
        r = None
        for attempt in range(3):
            with self._oa_lock:
                wait = self.cfg.openalex_min_interval - (time.monotonic() - self._oa_last)
                if wait > 0:
                    time.sleep(wait)
                try:
                    r = requests.get(url, params=params, timeout=self.cfg.request_timeout,
                                     headers={"User-Agent": self._ua})
                finally:
                    self._oa_last = time.monotonic()
            if r.status_code != 429:
                return r
            time.sleep(1.5 * (attempt + 1))  # 1.5s / 3s 退避
        return r

    # ---- CrossRef ----

    def _crossref_abstract(self, doi):
        try:
            r = self._get(f"https://api.crossref.org/works/{quote(doi)}", {"select": "abstract"})
            if r.status_code != 200:
                return None
            abstract = strip_html((r.json().get("message") or {}).get("abstract", ""))
            return abstract or None
        except Exception:
            return None

    def _crossref_citations(self, doi):
        try:
            r = self._get(f"https://api.crossref.org/works/{quote(doi)}", {"select": "is-referenced-by-count"})
            if r.status_code != 200:
                return None
            return int((r.json().get("message") or {}).get("is-referenced-by-count") or 0)
        except Exception:
            return None

    # ---- OpenAlex ----

    def _openalex_find(self, paper):
        """返回 OpenAlex work dict 或 None：优先 DOI 精确匹配，失败标题检索。"""
        if paper.doi:
            try:
                r = self._openalex_get(f"https://api.openalex.org/works/https://doi.org/{quote(paper.doi, safe='')}")
                if r.status_code == 200 and r.json().get("id"):
                    return r.json()
            except Exception:
                pass
        try:
            r = self._openalex_get("https://api.openalex.org/works",
                                   {"search": paper.title_original[:200], "per-page": 1})
            if r.status_code == 200:
                results = r.json().get("results") or []
                if results:
                    return results[0]
        except Exception:
            pass
        return None

    @staticmethod
    def _reconstruct_abstract(work: dict) -> str:
        """OpenAlex 倒排索引 → 原文。"""
        inv = work.get("abstract_inverted_index") or {}
        if not inv:
            return ""
        pos = {}
        for word, idxs in inv.items():
            for i in idxs:
                pos[i] = word
        return " ".join(pos[i] for i in sorted(pos))[:4000]

    def _openalex_abstract(self, paper):
        work = self._openalex_find(paper)
        if not work:
            return None
        abstract = self._reconstruct_abstract(work)
        return abstract or None

    def _openalex_citations(self, paper):
        work = self._openalex_find(paper)
        if not work:
            return None
        c = work.get("cited_by_count")
        return int(c) if isinstance(c, (int, float)) else None

    # ---- Semantic Scholar（未认证 1 req/s，限速）----

    def _s2_abstract(self, paper):
        with self._s2_lock:
            wait = self.cfg.s2_min_interval - (time.monotonic() - self._s2_last)
            if wait > 0:
                time.sleep(wait)
            try:
                r = requests.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params={"query": paper.title_original[:200], "fields": "title,abstract", "limit": 1},
                    timeout=self.cfg.request_timeout,
                    headers={"User-Agent": self._ua},
                )
                self._s2_last = time.monotonic()
                if r.status_code != 200:
                    return None
                data = (r.json().get("data") or [])
                if not data:
                    return None
                return data[0].get("abstract") or None
            except Exception:
                return None
