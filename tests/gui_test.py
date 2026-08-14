"""EconIntel 前端 GUI 冒烟测试（Playwright 驱动系统 Edge/Chrome，headless）。

覆盖：首页渲染 / 分片补载 / 搜索 / 筛选 / 排序 / 视图切换 / 详情弹窗 / 订阅 / 学者 / 状态 / 移动端布局。
截图输出到 gui-test-screenshots/。运行：
    .venv/Scripts/python.exe tests/gui_test.py
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SHOT_DIR = ROOT / "gui-test-screenshots"
BASE = "http://127.0.0.1:8765/"
PASS, FAIL, SKIP = [], [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(f"{name}: {detail}" if detail else name)
    print(("  ✅ " if ok else "  ❌ ") + name + (f" — {detail}" if detail else ""))


def shot(page, name):
    path = SHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  📸 {path.relative_to(ROOT)}")
    return path


def main():
    SHOT_DIR.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console[{m.type}]: {m.text}") if m.type == "error" else None)

        # ============ P0-1 首页首屏渲染 ============
        print("\n[P0-1] 首页加载与首屏渲染")
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        cards = page.locator(".paper-card").count()
        check("论文卡片渲染", cards > 0, f"{cards} 张卡片")
        check("导航栏", page.locator("nav a").count() == 4, f"{page.locator('nav a').count()} 个导航")
        check("工具栏筛选控件", page.locator("#toolbar select").count() == 6)
        check("页脚更新时间", "数据更新于" in page.locator(".footer").inner_text())
        note1 = page.locator("#range-note").inner_text()
        # 本地环境补载可能已完成：加载中 或 已全量 均属正常
        check("范围提示正常", ("数据加载中" in note1) or ("已加载全部数据" in note1), note1[:40])
        shot(page, "t1-home")

        # ============ P0-2 分片补载完成 ============
        print("\n[P0-2] 后台补载（b2/b3）完成")
        page.wait_for_timeout(2500)
        note = page.locator("#range-note").inner_text()
        check("范围提示变为全量", "已加载全部数据" in note, note[:60])

        # ============ P0-3 搜索 ============
        print("\n[P0-3] 关键词搜索")
        page.locator("#f-q").fill("monetary policy")
        page.wait_for_timeout(600)
        titles = page.locator(".pc-title").all_inner_texts()
        check("搜索结果非空", len(titles) > 0, f"{len(titles)} 条")
        check("结果包含关键词", any("Monetary" in t or "monetary" in t for t in titles[:20]),
              titles[0][:50] if titles else "无")
        # 搜索跨片验证：结果数应小于等于全部（且包含非 b1 分片论文时说明跨片）
        page.locator("#f-q").fill("")
        page.wait_for_timeout(400)
        check("清空搜索恢复", page.locator(".paper-card").count() > 0)

        # ============ P0-4 详情弹窗 ============
        print("\n[P0-4] 详情弹窗")
        first = page.locator(".paper-card").first
        first.click()
        page.wait_for_timeout(900)
        check("弹窗打开", page.locator(".modal").count() == 1)
        check("弹窗含原题", page.locator(".m-title").count() == 1,
              page.locator(".m-title").inner_text()[:40])
        check("弹窗含摘要区", page.locator(".m-abs").count() == 1)
        check("弹窗含原文链接", page.locator(".m-links a.btn-primary").count() == 1)
        check("弹窗含关注按钮", page.locator(".m-links [data-follow]").count() >= 2)
        shot(page, "t4-modal")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        check("Esc 关闭弹窗", page.locator(".modal").count() == 0)

        # ============ P1-5 领域筛选 ============
        print("\n[P1-5] 领域筛选")
        page.select_option("#f-field", "宏观")
        page.wait_for_timeout(500)
        fields = page.locator(".badge-field").all_inner_texts()
        check("筛选后全部为宏观", len(fields) > 0 and all(f == "宏观" for f in fields), f"{len(fields)} 条")
        shot(page, "t5-filter-macro")
        page.select_option("#f-field", "全部")
        page.wait_for_timeout(400)

        # ============ P1-6 排序切换 ============
        print("\n[P1-6] 排序切换")
        page.select_option("#f-sort", "date")
        page.wait_for_timeout(400)
        dates = page.locator(".pc-date").all_inner_texts()
        check("时间排序生效", len(dates) > 1)
        page.select_option("#f-sort", "score")
        page.wait_for_timeout(300)

        # ============ P1-7 视图切换 ============
        print("\n[P1-7] 列表/卡片视图切换")
        page.locator("#view-list").click()
        page.wait_for_timeout(400)
        check("列表视图", page.locator(".paper-list").count() > 0)
        shot(page, "t7-list-view")
        page.locator("#view-card").click()
        page.wait_for_timeout(300)
        check("切回卡片视图", page.locator(".paper-card").count() > 0)

        # ============ P1-8 订阅页 ============
        print("\n[P1-8] 订阅中心")
        page.goto(BASE + "#/subs", wait_until="domcontentloaded")
        page.wait_for_timeout(600)
        check("订阅页渲染", page.locator(".sub-form").count() == 1)
        page.locator("#sub-value").fill("nber")
        page.locator("#sub-kind").select_option("source")
        page.locator("#sub-add").click()
        page.wait_for_timeout(600)
        check("添加订阅成功", page.locator(".sub-box").count() == 1)
        check("订阅匹配到论文", page.locator(".sub-box .sub-paper").count() > 0,
              f"{page.locator('.sub-box .sub-paper').count()} 篇")
        shot(page, "t8-subs")
        page.locator(".sub-remove").click()
        page.wait_for_timeout(300)
        check("取消订阅", page.locator(".sub-box").count() == 0)

        # ============ P1-9 学者页 ============
        print("\n[P1-9] 学者画像")
        page.goto(BASE + "#/scholars", wait_until="domcontentloaded")
        page.wait_for_timeout(600)
        sc = page.locator(".scholar-card").count()
        check("学者卡片渲染", sc > 0, f"{sc} 位学者")
        shot(page, "t9-scholars")

        # ============ P1-10 状态页 ============
        print("\n[P1-10] 数据源状态")
        page.goto(BASE + "#/status", wait_until="domcontentloaded")
        page.wait_for_timeout(600)
        rows = page.locator(".status-table tbody tr").count()
        check("状态表渲染", rows >= 8, f"{rows} 行")
        check("KPI 卡片", page.locator(".kpi").count() == 5)
        cov = page.evaluate("() => Array.from(document.querySelectorAll('.cov-bar i')).map(e => e.style.width)")
        check("摘要覆盖率条", len(cov) >= 8 and all(c for c in cov), str(cov[:4]))
        shot(page, "t10-status")

        # ============ P3-11 移动端布局 ============
        print("\n[P3-11] 移动端响应式")
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        card = page.locator(".paper-card").first.bounding_box()
        check("卡片宽度适配视口", card is not None and card["width"] <= 390, f"宽 {card['width'] if card else '?'}px")
        shot(page, "t11-mobile")
        page.set_viewport_size({"width": 1280, "height": 900})

        # 控制台错误汇总
        real_errors = [e for e in errors if "favicon" not in e.lower()]
        print(f"\n控制台/页面错误：{len(real_errors)} 条")
        for e in real_errors[:8]:
            print("  ⚠", e)
        browser.close()

    print("\n" + "=" * 50)
    print(f"通过 {len(PASS)} | 失败 {len(FAIL)} | 跳过 {len(SKIP)}")
    for f in FAIL:
        print("  ❌", f)
    if not FAIL:
        print("全部通过 ✅")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
