"""滚动分片静态站点导出器。

产物（site/）：
- meta.js：版本号、真实生成时间、窗口起止、分片清单、源状态（含摘要覆盖率）、筛选选项
- index-b1~bN.js：轻量索引（列表/筛选/搜索用；首屏只载 b1，其余后台补载）
- detail-b1~bN.js：全字段详情（点开才加载，内存缓存）
- scholars.js：学者画像聚合（窗口内 ≥2 篇论文的作者）
- index.html/css/js：从 frontend/ 拷贝，__VERSION__ 令牌替换为生成版本
- EconIntel-离线版.html：全部内联的单文件离线版（附带产物，方便无网/无 URL 场景）
"""
import json
import shutil
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import select

from ..collectors.registry import SOURCES as REGISTRY
from ..models import Paper, Scholar, Source

BLOCK_DAYS = 30


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%d") if dt else ""


def block_index(age_days: int, num_blocks: int) -> int:
    """滚动分片下标：b1=最近 30 天，b2=31-60 天，…… 越界论文归入最旧分片。"""
    return max(0, min(age_days // BLOCK_DAYS, num_blocks - 1))


def _author_key(name: str) -> str:
    """学者聚合键：姓氏 + 名字首字母（容忍格式差异）。"""
    n = (name or "").strip()
    if not n:
        return ""
    if "," in n:  # "Family, Given"
        family, _, given = n.partition(",")
        return f"{family.strip().lower()} {given.strip()[:1].lower()}"
    parts = n.split()
    if len(parts) == 1:
        return n.lower()
    return f"{parts[-1].lower()} {parts[0][:1].lower()}"


class SiteExporter:
    def __init__(self, cfg):
        self.cfg = cfg
        self.version = datetime.utcnow().strftime("%Y%m%d%H%M")
        self.today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # ---- 入口 ----

    def export(self, session) -> dict:
        site = self.cfg.site_dir
        if site.exists():
            shutil.rmtree(site)
        (site / "data").mkdir(parents=True)
        (site / "css").mkdir(parents=True)
        (site / "js").mkdir(parents=True)

        papers = session.execute(select(Paper)).scalars().all()
        window_start = self.today - timedelta(days=self.cfg.history_days)

        # 组内任一版本在窗口内即导出该组（root 展示，variants 进版本历史）
        in_window = [p for p in papers if (p.published_at or p.collected_at) >= window_start]
        group_ids = {p.version_group for p in in_window}
        roots = [p for p in papers if p.version_role == "root" and p.version_group in group_ids]

        num_blocks = max(1, (self.cfg.history_days + BLOCK_DAYS - 1) // BLOCK_DAYS)
        blocks = [f"b{i + 1}" for i in range(num_blocks)]
        self._num_blocks = num_blocks

        # 版本历史：组 → 成员映射
        group_map = {}
        for p in papers:
            group_map.setdefault(p.version_group, []).append(p)
        self._group_map = group_map
        self._registry = REGISTRY
        self._weights = self.cfg.importance_weights

        index, detail = self._split_blocks(roots, blocks)
        self._write_meta(session, roots, blocks, window_start)
        self._write_index(index)
        self._write_detail(detail)
        self._write_scholars(session, roots)
        self._copy_frontend()
        self._build_offline()
        return {"papers": len(roots), "blocks": blocks, "version": self.version}

    # ---- 分片 ----

    def _block_of(self, published) -> int:
        age = (self.today - (published or self.today)).days
        return block_index(age, self._num_blocks)

    def _split_blocks(self, roots, blocks):
        index = {b: [] for b in blocks}
        detail = {b: {} for b in blocks}
        for p in roots:
            bi = min(self._block_of(p.published_at or p.collected_at), len(blocks) - 1)
            b = blocks[bi]
            index[b].append(self._index_entry(p, b))
            detail[b][p.id] = self._detail_entry(p, self._group_map.get(p.version_group, []))
        for b in blocks:
            index[b].sort(key=lambda e: e["d"], reverse=True)
        return index, detail

    def _index_entry(self, p, block_name) -> dict:
        """紧凑键：t=标题 d=日期 s=评分 l=标签 f=领域 src=来源 ty=类型 a=作者 k=关键词 b=分片"""
        title = p.title_short or p.title_original
        return {
            "id": p.id,
            "t": title[:120],
            "d": _fmt(p.published_at or p.collected_at),
            "s": p.importance_score,
            "l": p.importance_label,
            "f": p.field,
            "src": p.source,
            "ty": "jr" if p.paper_type == "journal" else "wp",
            "a": (p.authors or [])[:6],
            "k": (p.keywords or [])[:3],
            "b": block_name,
        }

    def _detail_entry(self, p, members) -> dict:
        from ..processors.importance import score_breakdown

        abstract = (p.abstract or "")[:600]
        bd = score_breakdown(
            p.credibility, p.paper_type, p.citations, p.published_at,
            self.today, self._weights,
        )
        return {
            "id": p.id,
            "t": p.title_original,
            "st": p.title_short,
            "c": p.contribution,
            "abs": abstract,
            "k": p.keywords or [],
            "jel": p.jel or [],
            "a": p.authors or [],
            "src": p.source,
            "sn": self._source_name(p.source),
            "d": _fmt(p.published_at or p.collected_at),
            "s": p.importance_score,
            "l": p.importance_label,
            "f": p.field,
            "doi": p.doi or "",
            "url": p.url_original or "",
            "ct": p.citations,
            "cs": p.citation_source or "",
            "cr": p.credibility,
            "as": p.abstract_source or "",
            "bd": bd,  # 评分构成（详情页透明展示）
            "vs": self._versions(p, members),
        }

    def _versions(self, p, members) -> list:
        """同组其他版本（版本历史）。"""
        out = []
        for v in members:
            if v.id == p.id:
                continue
            out.append({
                "t": v.title_original,
                "src": v.source,
                "sn": self._source_name(v.source),
                "ty": "jr" if v.paper_type == "journal" else "wp",
                "url": v.url_original or "",
                "d": _fmt(v.published_at or v.collected_at),
                "root": False,
            })
        return out

    # ---- 文件写出 ----

    def _write_meta(self, session, roots, blocks, window_start) -> None:
        source_rows = {s.key: s for s in session.execute(select(Source)).scalars().all()}
        sources = []
        per_src_total = Counter(p.source for p in roots)
        per_src_abs = Counter(p.source for p in roots if p.abstract)
        for key, total in per_src_total.most_common():
            s = source_rows.get(key)
            sources.append({
                "key": key,
                "name": s.name if s else key,
                "credibility": s.credibility if s else "B",
                "status": (s.last_fetch_status if s else "") or "unknown",
                "last_fetch": _fmt(s.last_fetch_at) if s and s.last_fetch_at else "",
                "count": total,
                "abstract_coverage": round(per_src_abs[key] / total, 3) if total else 0,
            })
        # 注册表中但窗口内无论文的源也展示
        known = {x["key"] for x in sources}
        for s in source_rows.values():
            if s.key not in known:
                sources.append({
                    "key": s.key, "name": s.name, "credibility": s.credibility,
                    "status": (s.last_fetch_status or "") or "unknown",
                    "last_fetch": _fmt(s.last_fetch_at) if s.last_fetch_at else "",
                    "count": 0, "abstract_coverage": 0,
                })
        fields = Counter(p.field for p in roots if p.field)
        meta = {
            "version": self.version,
            "generated_at": datetime.utcnow().isoformat(),
            "window_start": _fmt(window_start),
            "window_end": _fmt(self.today),
            "history_days": self.cfg.history_days,
            "blocks": blocks,
            "blocks_info": [
                {
                    "name": blocks[i],
                    "start": _fmt(self.today - timedelta(days=BLOCK_DAYS * (i + 1))),
                    "end": _fmt(self.today - timedelta(days=BLOCK_DAYS * i)),
                    "count": sum(1 for p in roots if block_index((self.today - (p.published_at or p.collected_at)).days, len(blocks)) == i),
                }
                for i in range(len(blocks))
            ],
            "sources": sources,
            "fields": [f for f, _ in fields.most_common()],
            "totals": {
                "papers": len(roots),
                "hot": sum(1 for p in roots if p.importance_score >= 80),
                "important": sum(1 for p in roots if 60 <= p.importance_score < 80),
                "journal": sum(1 for p in roots if p.paper_type == "journal"),
                "working": sum(1 for p in roots if p.paper_type != "journal"),
            },
            "update_schedule": "每 6 小时自动更新",
        }
        self._write_js("data/meta.js", "window.EI_META = " + _json(meta) + ";")

    def _write_index(self, index: dict) -> None:
        for b, entries in index.items():
            self._write_js(f"data/index-{b}.js",
                           f"window.EI_INDEX = window.EI_INDEX || {{}}; window.EI_INDEX.{b} = " + _json(entries) + ";")

    def _write_detail(self, detail: dict) -> None:
        for b, entries in detail.items():
            self._write_js(f"data/detail-{b}.js",
                           f"window.EI_DETAIL = window.EI_DETAIL || {{}}; window.EI_DETAIL.{b} = " + _json(entries) + ";")

    def _write_scholars(self, session, roots) -> None:
        # 聚合：作者 → 论文数/领域/来源/均分/高分论文
        by_key = {}
        for p in roots:
            for name in p.authors or []:
                key = _author_key(name)
                if not key:
                    continue
                item = by_key.setdefault(key, {"name": name, "papers": [], "fields": [], "sources": []})
                if name not in item["name"].split(";;"):
                    item["name"] = item["name"] + ";;" + name  # 保留原始名变体
                item["papers"].append((p.importance_score, p.id, p.field))
                if p.field:
                    item["fields"].append(p.field)
                item["sources"].append(p.source)
        scholars = []
        for item in by_key.values():
            if len(item["papers"]) < 2:
                continue
            names = item["name"].split(";;")
            display = max(names, key=len)  # 展示最完整的名字
            scores = [s for s, _, _ in item["papers"]]
            fields = Counter(item["fields"])
            sources = Counter(item["sources"])
            top = sorted(item["papers"], reverse=True)[:5]
            scholars.append({
                "n": display,
                "c": len(item["papers"]),
                "f": [f for f, _ in fields.most_common(3)],
                "src": [s for s, _ in sources.most_common(3)],
                "avg": round(sum(scores) / len(scores), 1),
                "top": [pid for _, pid, _ in top],
            })
        scholars.sort(key=lambda x: x["c"], reverse=True)
        self._write_js("data/scholars.js", "window.EI_SCHOLARS = " + _json(scholars) + ";")

    def _write_js(self, rel: str, content: str) -> None:
        (self.cfg.site_dir / rel).write_text(content, encoding="utf-8")

    def _source_name(self, key: str) -> str:
        for e in self._registry:
            if e["key"] == key:
                return e["name"]
        return key

    # ---- 前端拷贝与离线版 ----

    def _copy_frontend(self) -> None:
        src = self.cfg.frontend_dir
        dst = self.cfg.site_dir
        num_blocks = max(1, (self.cfg.history_days + BLOCK_DAYS - 1) // BLOCK_DAYS)
        blocks_js = json.dumps([f"b{i + 1}" for i in range(num_blocks)])
        for f in src.rglob("*"):
            if f.is_file():
                rel = f.relative_to(src)
                target = dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                content = f.read_text(encoding="utf-8")
                content = content.replace("__VERSION__", self.version)
                content = content.replace("__BLOCKS__", blocks_js)
                content = content.replace("__HISTORY_DAYS__", str(self.cfg.history_days))
                target.write_text(content, encoding="utf-8")

    def _build_offline(self) -> None:
        """单文件离线版：CSS/JS/数据全部内联（App.init 移到全部脚本之后执行）。"""
        import re

        site = self.cfg.site_dir
        index_html = (site / "index.html").read_text(encoding="utf-8")
        css = (site / "css" / "style.css").read_text(encoding="utf-8")
        js_files = sorted((site / "js").glob("*.js"))
        data_files = sorted((site / "data").glob("*.js"))
        parts = ["<!DOCTYPE html>", '<html lang="zh-CN"><head><meta charset="utf-8">',
                 '<meta name="viewport" content="width=device-width, initial-scale=1">',
                 f"<title>EconIntel · 经济学前沿论文（离线版）</title><style>{css}</style></head>",
                 "<body>"]
        # 抽取 body 内容：去掉外部 link/script 与 App.init 调用（稍后追加）
        body = index_html.split("</head>", 1)[-1]
        body = re.sub(r'<link[^>]*href="css/[^"]*"[^>]*>', "", body)
        body = re.sub(r'<script[^>]*src="[^"]*"[^>]*></script>', "", body)
        body = re.sub(r"<script>App\.init\(\);</script>", "", body)
        parts.append(body)
        parts.append("<script>window.EI_OFFLINE = true;</script>")
        for f in data_files:
            parts.append(f"<script>{f.read_text(encoding='utf-8')}</script>")
        for f in js_files:
            parts.append(f"<script>{f.read_text(encoding='utf-8')}</script>")
        parts.append("<script>App.init();</script>")
        parts.append("</body></html>")
        (site / "EconIntel-离线版.html").write_text("\n".join(parts), encoding="utf-8")
