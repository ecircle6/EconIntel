"""采集 → 去重 → 富化 → 分类 → 评分 → 精简 的端到端编排。

幂等设计：重复运行不产生重复数据；富化/精简只处理未完成论文；
单源失败不影响整体（源状态与连续错误计数入库，状态页可见）。
"""
import logging
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import select

from ..collectors.registry import SOURCES, build_collector
from ..database import init_db, get_session
from ..models import MetaKV, Paper, Source
from ..processors import dedup, importance
from ..processors.classify import classify
from ..processors.dedup import GroupMatcher, sync_group_roles
from ..processors.enrich import Enricher
from ..processors.summarize import summarize_paper

log = logging.getLogger("econintel.pipeline")

_CRED_RANK = {"A": 3, "B": 2, "C": 1}  # 来源权威度（用于同记录多源命中时的归属）


class Pipeline:
    def __init__(self, cfg):
        self.cfg = cfg
        init_db(cfg.db_path)

    # ---- 入口 ----

    def run(self, full: bool = False, if_stale: bool = False) -> dict:
        """执行一轮完整更新。full=True 表示首跑全量回填；if_stale=True 今日已跑则跳过。"""
        if if_stale and self._ran_recently(self.cfg.stale_hours):
            return {"skipped": True}
        session = get_session()
        stats = {
            "sources_ok": [], "sources_fail": [],
            "drafts_total": 0, "new_papers": 0, "updated_papers": 0,
            "enriched": 0, "summarized_llm": 0, "summarized_rule": 0,
        }
        try:
            self._ensure_sources(session)
            fetch_days = self.cfg.fetch_days_first if (full or not self._has_data(session)) \
                else self.cfg.fetch_days_incremental
            end = datetime.utcnow()
            start = end - timedelta(days=fetch_days)
            log.info("抓取窗口：%s ~ %s（%d 天）", start.date(), end.date(), fetch_days)

            drafts, stats = self._collect(session, start, end, stats)
            stats = self._store(session, drafts, stats)
            stats = self._post_process(session, stats)

            self._set_meta("last_run_at", datetime.utcnow().isoformat())
            self._set_meta("last_run_status", "ok")
            session.commit()
            log.info("完成：新增 %d、更新 %d、富化 %d、AI 精简 %d / 规则 %d",
                     stats["new_papers"], stats["updated_papers"], stats["enriched"],
                     stats["summarized_llm"], stats["summarized_rule"])
            stats["RESULT"] = "OK"
            return stats
        except Exception as exc:
            log.exception("pipeline 失败")
            self._set_meta("last_run_status", f"error: {exc}")
            session.rollback()
            raise

    # ---- 各阶段 ----

    def _ensure_sources(self, session) -> None:
        for entry in SOURCES:
            src = session.get(Source, entry["key"])
            if src is None:
                session.add(Source(
                    key=entry["key"], name=entry["name"], source_type=entry["type"],
                    url=entry.get("url", ""), credibility=entry["credibility"], enabled=True,
                ))
        session.commit()

    def _collect(self, session, start, end, stats) -> tuple:
        """逐个源抓取；每源状态写库，单源失败不影响整体。"""
        drafts = []
        for entry in SOURCES:
            src = session.get(Source, entry["key"])
            if not src or not src.enabled:
                continue
            try:
                collector = build_collector(entry, self.cfg.request_timeout)
                collected = collector.fetch(start, end)
                src.last_fetch_at = datetime.utcnow()
                src.last_fetch_status = "ok"
                src.last_fetch_count = len(collected)
                src.error_count = 0
                src.last_error = ""
                stats["sources_ok"].append((entry["key"], len(collected)))
                stats["drafts_total"] += len(collected)
                drafts.extend(collected)
                log.info("源 %s：%d 篇", entry["key"], len(collected))
            except Exception as exc:
                src.last_fetch_at = datetime.utcnow()
                src.last_fetch_status = "error"
                src.error_count = (src.error_count or 0) + 1
                src.last_error = str(exc)[:300]
                stats["sources_fail"].append(entry["key"])
                log.warning("源 %s 失败：%s", entry["key"], exc)
            session.commit()
        return drafts, stats

    def _store(self, session, drafts, stats) -> dict:
        """去重 + 入库。DOI 命中→更新原记录；URL/标题命中→新增为同组版本。"""
        if not drafts:
            return stats
        matcher = GroupMatcher(session)
        touched_groups = set()
        now = datetime.utcnow()

        for d in drafts:
            group_id, is_new = matcher.match(d)
            touched_groups.add(group_id)
            if not is_new:
                # 组内已有论文：DOI 或 URL 精确命中则原位更新；否则新增为变体（标题+作者命中）
                existing = session.execute(
                    select(Paper).where(Paper.version_group == group_id)
                ).scalars().all()
                paper = None
                if d.doi:
                    paper = next((p for p in existing
                                  if p.doi and dedup.normalize_doi(p.doi) == dedup.normalize_doi(d.doi)), None)
                if paper is None:
                    d_url = dedup.normalize_url(d.url)
                    paper = next((p for p in existing
                                  if d_url and dedup.normalize_url(p.url_original or "") == d_url), None)
                if paper is not None:
                    self._update_paper(paper, d)
                    stats["updated_papers"] += 1
                    continue
                # 无 DOI/URL 精确命中 → 新增为同组版本（例如 NBER WP ↔ NEP 文摘同篇论文）
                paper = Paper(
                    doi=dedup.normalize_doi(d.doi),
                    title_original=d.title,
                    authors=d.authors,
                    url_original=d.url,
                    published_at=d.published,
                    source=d.source,
                    paper_type=d.paper_type,
                    abstract=d.abstract or "",
                    abstract_source=d.abstract_source or ("source" if d.abstract else ""),
                    jel=d.jel or [],
                    credibility=next((s["credibility"] for s in SOURCES if s["key"] == d.source), "B"),
                    collected_at=now,
                    version_group=group_id,
                    version_role="variant",
                )
            else:
                paper = Paper(
                    doi=dedup.normalize_doi(d.doi),
                    title_original=d.title,
                    authors=d.authors,
                    url_original=d.url,
                    published_at=d.published,
                    source=d.source,
                    paper_type=d.paper_type,
                    abstract=d.abstract or "",
                    abstract_source=d.abstract_source or ("source" if d.abstract else ""),
                    jel=d.jel or [],
                    credibility=next((s["credibility"] for s in SOURCES if s["key"] == d.source), "B"),
                    collected_at=now,
                    version_group=group_id,
                    version_role="root",
                )
            session.add(paper)
            stats["new_papers"] += 1
        session.commit()

        for gid in touched_groups:
            sync_group_roles(session, gid)
        session.commit()
        return stats

    def _update_paper(self, paper, d) -> None:
        """原位更新既有记录（保留来源归属与已完成的富化结果）。"""
        paper.title_original = d.title
        paper.authors = d.authors or paper.authors
        paper.url_original = d.url or paper.url_original
        paper.published_at = d.published or paper.published_at
        paper.paper_type = d.paper_type or paper.paper_type
        if d.abstract and not paper.abstract:
            paper.abstract = d.abstract
            paper.abstract_source = d.abstract_source or "source"
        # 来源归属：同一记录被多源命中时，权威度更高者优先（A官方 > B学术库 > C预印本）
        draft_cred = next((s["credibility"] for s in SOURCES if s["key"] == d.source), "B")
        if _CRED_RANK.get(draft_cred, 0) > _CRED_RANK.get(paper.credibility, 0):
            paper.source = d.source
            paper.credibility = draft_cred

    def _post_process(self, session, stats) -> dict:
        """富化 → 领域分类 → 评分 → 精简。"""
        # 1) 富化：仅处理 缺摘要 或 缺引用 的论文（增量缓存；每轮限量，最新论文优先，剩余下轮自动补）
        papers = session.execute(select(Paper)).scalars().all()
        need_enrich = [p for p in papers if (not p.abstract or p.citations is None)]
        need_enrich.sort(key=lambda p: p.published_at or datetime.min, reverse=True)
        need_enrich = need_enrich[: self.cfg.enrich_max_papers]
        if need_enrich:
            enricher = Enricher(self.cfg)
            results = enricher.enrich(need_enrich)
            now = datetime.utcnow()
            for p in need_enrich:
                r = results.get(p.id)
                if not r:
                    continue
                if r.get("abstract"):
                    p.abstract, p.abstract_source = r["abstract"], r["abstract_source"]
                if "citations" in r:
                    p.citations = r["citations"]
                stats["enriched"] += 1
                p.enriched_at = now
            session.commit()

        # 2) 领域分类（未分类或摘要变化时重算）
        for p in papers:
            if not p.field or (p.enriched_at and p.updated_at < p.enriched_at):
                p.field = classify(p.title_original, p.abstract)

        # 3) 重要性评分（全窗口重算，内存内秒级）
        today = datetime.utcnow()
        for p in papers:
            p.importance_score = importance.compute_score(
                p.credibility, p.paper_type, p.citations, p.published_at,
                today, self.cfg.importance_weights,
            )
            p.importance_label = importance.label_for(p.importance_score)
        session.commit()

        # 4) 精简（LLM 优先，规则降级）；每批限速，失败论文下次再试
        from ..processors.llm import make_client

        llm_client = make_client(self.cfg)
        for p in papers:
            if p.summarized_at:
                continue
            try:
                used_llm = summarize_paper(self.cfg, p, llm_client)
                if used_llm:
                    stats["summarized_llm"] += 1
                else:
                    stats["summarized_rule"] += 1
            except Exception as exc:
                log.warning("精简失败 paper=%s: %s", p.id, exc)
        session.commit()
        return stats

    # ---- 元信息辅助 ----

    def _ran_recently(self, hours: float) -> bool:
        """最近 hours 小时内是否已成功运行（--if-stale 判定）。"""
        session = get_session()
        row = session.get(MetaKV, "last_run_at")
        if not row:
            return False
        try:
            last = datetime.fromisoformat(row.value)
        except ValueError:
            return False
        return (datetime.utcnow() - last).total_seconds() < hours * 3600

    def _has_data(self, session) -> bool:
        return session.execute(select(Paper.id).limit(1)).first() is not None

    def _set_meta(self, key: str, value: str) -> None:
        session = get_session()
        row = session.get(MetaKV, key)
        if row is None:
            session.add(MetaKV(key=key, value=value))
        else:
            row.value = value
        session.commit()
