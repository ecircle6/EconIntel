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
ABSTRACT_RE = re.compile(r"Abstract:\s*(.*?)(?=\s*(?:Keywords|Date|Note)\s*:|$)", re.DOTALL | re.IGNORECASE)


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
            page_entries = self._parse_listing(resp.text)
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

        # 并发抓详情页：摘要 + 月份日期
        drafts = []
        with ThreadPoolExecutor(max_workers=self.entry.get("workers", 6)) as pool:
            futures = {}
            for num, title, authors, year in uniq:
                if year < start_year:
                    continue
                detail_url = f"https://econpapers.repec.org/paper/{short}/{num}.htm"
                futures[pool.submit(self._fetch_detail, detail_url)] = (num, title, authors)
            for fut, (num, title, authors) in futures.items():
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

    def _fetch_detail(self, url: str):
        """EconPapers 详情页：返回 (abstract, published)。失败返回 (None, None)。"""
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
        except Exception:
            return None, None
        text = BeautifulSoup(resp.text, "html.parser").get_text(" ")
        text = re.sub(r"\s+", " ", text)
        abstract = _parse_abstract(text)
        published = _parse_month_date(text)
        return (abstract or None), published


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
        soup = BeautifulSoup(resp.text, "html.parser")
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
        soup = BeautifulSoup(resp.text, "html.parser")
        published = datetime.strptime(date_str, "%Y-%m-%d")
        drafts = []
        # 论文条目锚点：id="pN"（排除页面其他 id 干扰）
        for div in soup.select("div[id]"):
            if not re.fullmatch(r"p\d+", div.get("id", "")):
                continue
            a = div.find("a", href=re.compile(r"econpapers\.repec\.org/RePEc:"))
            a = div.find("a", href=re.compile(r"econpapers\.repec\.org/RePEc:"))
            if not a:
                continue
            title = clean_text(a.get_text())
            if not title:
                continue
            handle = a["href"].split("RePEc:")[-1].split("?")[0]  # e.g. drm:wpaper:2026-16
            authors = []
            abstract = ""
            for td in div.select("td.fiva"):
                label = td.find_previous_sibling("td")
                lbl = clean_text(label.get_text()) if label else ""
                if lbl.startswith("By"):
                    authors = split_authors(td.get_text("; "))
                elif lbl.startswith("Abstract"):
                    abstract = clean_text(td.get_text(" "))
            path = handle.replace(":", "/")
            drafts.append(
                PaperDraft(
                    title=title,
                    authors=authors,
                    url=f"https://ideas.repec.org/p/{path}.html",
                    published=published,
                    source=self.key,
                    paper_type="working",
                    abstract=abstract or None,
                    abstract_source="source" if abstract else None,
                )
            )
        return drafts
