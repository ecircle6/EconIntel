"""RePEc 生态采集器（IDEAS 系列页 + EconPapers 详情 / NEP 领域文摘）。

已验证（2026-08）：
- IDEAS 的 RSS 端点被验证码墙拦截（rss.pl 返回 404 反爬页），但系列 HTML 页面可正常抓取；
- 系列页 https://ideas.repec.org/s/{series}.html 列出 编号+标题+作者（按年份分页）；
- 详情页 https://econpapers.repec.org/paper/{short}/{num}.htm 含完整摘要与月份级日期；
- NEP 主题页 https://nep.repec.org/{topic}.html 归档各期文摘，
  期页面 https://nep.repec.org/{topic}/{date} 直接含每篇的完整摘要与来源 handle。
"""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseCollector, PaperDraft, clean_text, split_authors

DATE_RE = re.compile(r"Date:\s*(\d{4}(?:-\d{1,2})?)", re.IGNORECASE)
# 兼容 "Abstract: ..."（EconPapers）与 "Abstract ..."（IDEAS，无冒号）
ABSTRACT_RE = re.compile(r"Abstract:?\s*(.*?)(?=\s*(?:Keywords|Date|Note)\s*:?|$)", re.DOTALL | re.IGNORECASE)


def _parse_month_date(text: str) -> datetime | None:
    """EconPapers 详情页 'Date: 2026-08' → datetime（月级取月初）。"""
    m = DATE_RE.search(text)
    if not m:
        return None
    parts = [int(x) for x in m.group(1).split("-")]
    if len(parts) == 1:
        return datetime(parts[0], 1, 1)
    return datetime(parts[0], min(max(parts[1], 1), 12), 1)


def _parse_abstract(text: str) -> str:
    m = ABSTRACT_RE.search(text)
    return clean_text(m.group(1)) if m else ""


class RepecSeriesCollector(BaseCollector):
    """IDEAS 系列页 → EconPapers 详情页（摘要 + 月份日期）。

    entry 配置：series="cpr:ceprdp"（IDEAS handle）、series_short="cprceprdp"（EconPapers 路径段）。
    """

    source_type = "html"

    def fetch(self, start, end):
        series = self.entry["series"]
        short = self.entry["series_short"]
        start_year = start.year
        entries = []  # (number, title, authors, year)

        for page_no in range(1, 6):  # 最多翻 5 页（CEPR 每页约一年）
            url = f"https://ideas.repec.org/s/{series}.html" if page_no == 1 else f"https://ideas.repec.org/s/{series}{page_no}.html"
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            page_entries = self._parse_listing(resp.content)
            if not page_entries:
                break
            entries.extend(page_entries)
            oldest_year = min(y for _, _, _, y in page_entries)
            if oldest_year < start_year:
                break

        # 去重（同一编号只留一次）
        seen, uniq = set(), []
        for num, title, authors, year in entries:
            if num in seen:
                continue
            seen.add(num)
            uniq.append((num, title, authors, year))

        # 并发抓详情页：摘要 + 月份日期（EconPapers 主源；404 时回退 IDEAS 页，日期用系列年份兜底）
        drafts = []
        with ThreadPoolExecutor(max_workers=self.entry.get("workers", 6)) as pool:
            futures = {}
            for num, title, authors, year in uniq:
                if year < start_year:
                    continue
                ep_url = f"https://econpapers.repec.org/paper/{short}/{num}.htm"
                ideas_url = f"https://ideas.repec.org/p/{series}/{num}.html"
                futures[pool.submit(self._fetch_detail, ep_url, ideas_url, year)] = (num, title, authors, year)
            for fut, (num, title, authors, year) in futures.items():
                try:
                    abstract, published = fut.result()
                except Exception:
                    abstract, published = None, None
                # 月份级过滤：详情页日期早于抓取窗口的丢弃（系列页只有年份粒度）
                if published and (published.year, published.month) < (start.year, start.month):
                    continue
                drafts.append(
                    PaperDraft(
                        title=title,
                        authors=authors,
                        url=f"https://ideas.repec.org/p/{series}/{num}.html",
                        published=published,
                        source=self.key,
                        paper_type="working",
                        abstract=abstract,
                        abstract_source="source" if abstract else None,
                    )
                )
        return drafts

    def _parse_listing(self, html: str):
        """解析系列页：<h3>年份</h3> 分组下的论文条目。"""
        soup = BeautifulSoup(html, "html.parser")
        entries = []
        for li in soup.select("ul.paperlist li.list-group-item"):
            a = li.find("a", href=re.compile(r"/p/"))
            if not a:
                continue
            href = a["href"]
            num = href.rstrip(".html").rsplit("/", 1)[-1]
            title = clean_text(a.get_text())
            year_h3 = li.find_previous("h3")
            try:
                year = int(year_h3.get_text().strip())
            except (AttributeError, ValueError):
                year = datetime.now().year
            authors = []
            i_tag = li.find("i")
            if i_tag and i_tag.next_sibling:
                authors = split_authors(str(i_tag.next_sibling))
            entries.append((num, title, authors, year))
        return entries

    def _fetch_detail(self, ep_url: str, ideas_url: str, year: int):
        """双镜像详情页：返回 (abstract, published)。

        EconPapers 有月份级日期但部分系列未镜像（如 IMF）；IDEAS 有摘要但无日期。
        摘要取任一来源；日期 EconPapers 优先，缺失用系列年份年中兜底。
        """
        abstract, published = None, None
        try:
            resp = self.session.get(ep_url, timeout=self.timeout)
            if resp.status_code == 200:
                text = BeautifulSoup(resp.content, "html.parser").get_text(" ")
                text = re.sub(r"\s+", " ", text)
                abstract = _parse_abstract(text) or None
                published = _parse_month_date(text)
        except Exception:
            pass
        if not abstract:
            try:
                resp = self.session.get(ideas_url, timeout=self.timeout)
                if resp.status_code == 200:
                    text = BeautifulSoup(resp.content, "html.parser").get_text(" ")
                    text = re.sub(r"\s+", " ", text)
                    abstract = _parse_abstract(text) or None
            except Exception:
                pass
        if published is None and year:
            # 月份缺失时兜底：当年「今天」的近似日期（避免被窗口过滤误杀；跨年论文自然落入上年）
            today = datetime.now()
            published = datetime(min(year, today.year), today.month, today.day)
        return abstract, published


class NEPCollector(BaseCollector):
    """RePEc NEP 领域文摘（按主题抓最近几期，期页面直接含摘要）。"""

    source_type = "html"

    def fetch(self, start, end):
        # 文摘期为周报，取最近 K 期（K 随抓取窗口增长）；论文日期近似为期日期
        window_days = max(1, (end - start).days)
        issues_needed = max(2, min(15, window_days // 7 + 1))
        drafts = []
        for topic in self.entry.get("topics", []):
            issue_dates = self._recent_issue_dates(topic, issues_needed)
            for d in issue_dates:
                try:
                    drafts.extend(self._fetch_issue(topic, d))
                except Exception as exc:
                    # 单期失败不影响其他期/其他主题（NEP 偶有缺期）
                    import logging

                    logging.getLogger("econintel.collectors").warning("NEP %s/%s 跳过：%s", topic, d, exc)
        return drafts

    def _recent_issue_dates(self, topic: str, k: int) -> list:
        """主题页归档 → 最近 k 期日期（新→旧）。"""
        resp = self.session.get(f"https://nep.repec.org/{topic}.html", timeout=self.timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        dates = []
        for a in soup.select(f'a[href^="/{topic}/"]'):
            href = a["href"]
            m = re.search(r"(\d{4}-\d{2}-\d{2})$", href)
            if m and m.group(1) not in dates:
                dates.append(m.group(1))
        return dates[:k]

    def _fetch_issue(self, topic: str, date_str: str) -> list:
        resp = self.session.get(f"https://nep.repec.org/{topic}/{date_str}", timeout=self.timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")  # content：自动识别 UTF-8
        drafts = []
        # 条目结构：<div id="pN">标题链接</div> + 紧邻 <table class="basit"> 明细表
        # （By / Abstract / Keywords / JEL / Date / URL 行）
        for div in soup.select("div[id]"):
            if not re.fullmatch(r"p\d+", div.get("id", "")):
                continue
            a = div.find("a", href=re.compile(r"econpapers\.repec\.org/RePEc:"))
            if not a:
                continue
            title = clean_text(a.get_text())
            if not title:
                continue
            handle = a["href"].split("RePEc:")[-1].split("?")[0]  # e.g. cpr:ceprdp:21842
            authors, abstract, jel, published, url_original = [], "", [], None, None
            table = div.find_next_sibling("table")
            if table:
                for tr in table.select("tr"):
                    cells = tr.select("td")
                    if len(cells) < 2:
                        continue
                    label = clean_text(cells[0].get_text())
                    value = cells[1].get_text("; ")
                    if label.startswith("By"):
                        authors = [re.sub(r"\s*\(.*?\)\s*$", "", a) for a in split_authors(value)]
                    elif label.startswith("Abstract"):
                        abstract = clean_text(value)
                    elif label.startswith("JEL"):
                        jel = re.findall(r"[A-Z]\d{2}", value)  # 只取标准 JEL 码（如 E52）
                    elif label.startswith("Date"):
                        m = re.search(r"(\d{4})\s*[–-]\s*(\d{1,2})", value)
                        if m:
                            try:
                                published = datetime(int(m.group(1)), min(max(int(m.group(2)), 1), 12), 1)
                            except ValueError:
                                published = None
                    elif label.startswith("URL"):
                        hm = re.search(r"RePEc:([\w.:/-]+)", value)
                        if hm:
                            url_original = f"https://ideas.repec.org/p/{hm.group(1).replace(':', '/')}.html"
            if not url_original:
                url_original = f"https://ideas.repec.org/p/{handle.replace(':', '/')}.html"
            drafts.append(
                PaperDraft(
                    title=title,
                    authors=authors,
                    url=url_original,
                    published=published,
                    source=self.key,
                    paper_type="working",
                    abstract=abstract or None,
                    abstract_source="source" if abstract else None,
                    jel=jel,
                )
            )
        return drafts
