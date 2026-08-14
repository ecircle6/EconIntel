"""摘要与引用富化：并发 + 硬超时预算 + 熔断 + 增量缓存。

摘要四级链：源自带 → CrossRef（有 DOI）→ OpenAlex（免费额度有限）→ Semantic Scholar（限速）。
引用链：CrossRef（有 DOI，免费无限）→ OpenAlex → Semantic Scholar。

关键工程约束（2026-08 实测）：
- OpenAlex 已商业化：每日免费额度极少，429 响应含 Retry-After（跨日时本轮直接放弃）；
- Semantic Scholar 未认证限 100 次/5 分钟（≈20/min），间隔必须 ≥3.2s；
- 连续失败 5 次即熔断（本轮不再调用该 API），避免浪费额度拖慢管线；
- 单篇硬预算 cfg.paper_budget 秒，超时立即返回已收集结果；
- 结果由主线程 as_completed 边完成边写库（SQLite WAL）。
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

import requests

from ..collectors.base import strip_html

log = logging.getLogger("econintel.enrich")

UA = "EconIntel/0.1 (economics paper aggregator)"


class Enricher:
    def __init__(self, cfg):
        self.cfg = cfg
        self._s2_lock = threading.Lock()
        self._s2_last = 0.0
        self._oa_lock = threading.Lock()
        self._oa_last = 0.0
        mailto = getattr(cfg, "openalex_mailto", "") or ""
        self._ua = f"EconIntel/0.1 (mailto:{mailto})" if mailto else UA
        self._api_state = {"openalex": {"ok": True, "fails": 0}, "s2": {"ok": True, "fails": 0}}

    # ---- 对外入口 ----

    def enrich(self, papers) -> dict:
        """并发富化一批论文；返回 {paper_id: {abstract, abstract_source, citations}}。"""
        results = {}
        with ThreadPoolExecutor(max_workers=self.cfg.enrich_workers) as pool:
            futures = {pool.submit(self._enrich_one, p): p for p in papers}
            for fut in as_completed(futures):  # 边完成边写，单个卡住不拖死整批
                try:
                    out = fut.result()
                    if out:
                        results[futures[fut].id] = out
                except Exception:
                    continue
        return results

    # ---- 熔断状态 ----

    def _api_failed(self, name: str) -> None:
        st = self._api_state[name]
        st["fails"] += 1
        if st["fails"] >= 5:
            st["ok"] = False
            log.warning("API %s 连续失败 %d 次，本轮熔断（下次运行自动恢复）", name, st["fails"])

    def _api_reset(self, name: str) -> None:
        st = self._api_state[name]
        st["fails"] = 0
        st["ok"] = True

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

        if need_abs and time.monotonic() < deadline and self._api_ok("openalex"):
            abstract = self._openalex_abstract(paper, deadline)
            if abstract:
                out["abstract"], out["abstract_source"] = abstract, "openalex"
                need_abs = False

        if need_abs and time.monotonic() < deadline and self._api_ok("s2"):
            abstract = self._s2_abstract(paper, deadline)
            if abstract:
                out["abstract"], out["abstract_source"] = abstract, "s2"

        if need_cites and time.monotonic() < deadline:
            cites = None
            if paper.doi:
                cites = self._crossref_citations(paper.doi)  # CrossRef 免费无限，主路径
            if cites is None and time.monotonic() < deadline and self._api_ok("openalex"):
                cites = self._openalex_citations(paper, deadline)
            if cites is None and time.monotonic() < deadline and self._api_ok("s2"):
                cites = self._s2_citations(paper, deadline)
            if cites is not None:
                out["citations"] = cites
        return out

    def _api_ok(self, name: str) -> bool:
        return self._api_state[name]["ok"]

    # ---- HTTP 基础 ----

    def _get(self, url, params=None):
        return requests.get(url, params=params, timeout=self.cfg.request_timeout,
                            headers={"User-Agent": self._ua})

    def _openalex_get(self, url, params=None, deadline=None):
        """OpenAlex 请求：全局限速 + 熔断 + Retry-After 感知（跨日额度直接放弃本轮）。"""
        if not self._api_ok("openalex"):
            return None
        for attempt in range(2):
            if deadline and time.monotonic() >= deadline:
                return None
            with self._oa_lock:
                wait = self.cfg.openalex_min_interval - (time.monotonic() - self._oa_last)
                if wait > 0:
                    time.sleep(wait)
                try:
                    r = requests.get(url, params=params, timeout=self.cfg.request_timeout,
                                     headers={"User-Agent": self._ua})
                finally:
                    self._oa_last = time.monotonic()
            if r.status_code == 200:
                self._api_reset("openalex")
                return r
            if r.status_code == 429:
                self._api_failed("openalex")
                retry_after = r.headers.get("Retry-After", "")
                try:
                    if retry_after and float(retry_after) > 30:
                        # 跨日额度耗尽：本轮放弃，避免空转
                        self._api_state["openalex"]["ok"] = False
                        log.warning("OpenAlex 额度耗尽（Retry-After=%ss），本轮跳过", retry_after)
                        return None
                except ValueError:
                    pass
                time.sleep(1.0 * (attempt + 1))
            else:
                self._api_failed("openalex")
                return r
        return None

    def _s2_call(self, params, deadline=None):
        """Semantic Scholar 请求：限速（≥3.2s/次）+ 熔断。"""
        if not self._api_ok("s2"):
            return None
        if deadline and time.monotonic() >= deadline:
            return None
        with self._s2_lock:
            wait = max(self.cfg.s2_min_interval, 3.2) - (time.monotonic() - self._s2_last)
            if wait > 0:
                time.sleep(wait)
            try:
                r = requests.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params=params, timeout=self.cfg.request_timeout, headers={"User-Agent": self._ua},
                )
            finally:
                self._s2_last = time.monotonic()
        if r.status_code == 200:
            self._api_reset("s2")
            return r
        if r.status_code == 429:
            self._api_failed("s2")
            retry_after = r.headers.get("Retry-After", "")
            try:
                if retry_after and float(retry_after) > 30:
                    self._api_state["s2"]["ok"] = False
                    return None
            except ValueError:
                pass
        else:
            self._api_failed("s2")
        return None

    # ---- CrossRef（免费无限）----

    def _crossref_abstract(self, doi):
        try:
            # 注意：单篇端点 /works/{doi} 不支持 select 参数（实测 400），直接取整条记录
            r = self._get(f"https://api.crossref.org/works/{quote(doi)}")
            if r.status_code != 200:
                return None
            abstract = strip_html((r.json().get("message") or {}).get("abstract", ""))
            return abstract or None
        except Exception:
            return None

    def _crossref_citations(self, doi):
        try:
            r = self._get(f"https://api.crossref.org/works/{quote(doi)}")
            if r.status_code != 200:
                return None
            return int((r.json().get("message") or {}).get("is-referenced-by-count") or 0)
        except Exception:
            return None

    # ---- OpenAlex（每日额度有限）----

    def _openalex_find(self, paper, deadline=None):
        """返回 OpenAlex work dict 或 None：优先 DOI 精确匹配，失败标题检索。"""
        if paper.doi:
            try:
                r = self._openalex_get(f"https://api.openalex.org/works/https://doi.org/{quote(paper.doi, safe='')}", deadline=deadline)
                if r is not None and r.status_code == 200 and r.json().get("id"):
                    return r.json()
            except Exception:
                pass
        if deadline and time.monotonic() >= deadline:
            return None
        try:
            r = self._openalex_get("https://api.openalex.org/works",
                                   {"search": paper.title_original[:200], "per-page": 1}, deadline=deadline)
            if r is not None and r.status_code == 200:
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

    def _openalex_abstract(self, paper, deadline=None):
        work = self._openalex_find(paper, deadline)
        if not work:
            return None
        abstract = self._reconstruct_abstract(work)
        return abstract or None

    def _openalex_citations(self, paper, deadline=None):
        work = self._openalex_find(paper, deadline)
        if not work:
            return None
        c = work.get("cited_by_count")
        return int(c) if isinstance(c, (int, float)) else None

    # ---- Semantic Scholar（限速）----

    def _s2_abstract(self, paper, deadline=None):
        r = self._s2_call({"query": paper.title_original[:200], "fields": "title,abstract", "limit": 1}, deadline)
        if r is None or r.status_code != 200:
            return None
        data = r.json().get("data") or []
        if not data:
            return None
        return data[0].get("abstract") or None

    def _s2_citations(self, paper, deadline=None):
        r = self._s2_call({"query": paper.title_original[:200], "fields": "title,citationCount", "limit": 1}, deadline)
        if r is None or r.status_code != 200:
            return None
        data = r.json().get("data") or []
        if not data:
            return None
        c = data[0].get("citationCount")
        return int(c) if isinstance(c, (int, float)) else None
