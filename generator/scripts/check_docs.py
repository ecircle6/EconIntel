"""README 与代码配置一致性检查。

每次推送代码时由 GitHub Actions 自动运行：若 README 声称的关键数值
（评分权重 / 导出窗口 / 更新频率 / stale 阈值）与代码实际配置不一致，
本脚本 exit 1 → 构建失败 → 邮件告警，强制功能变更同步更新文档。

本地运行：.venv/Scripts/python.exe generator/scripts/check_docs.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
GENERATOR = ROOT / "generator"
README = ROOT / "README.md"
WORKFLOW = ROOT / ".github" / "workflows" / "daily.yml"

sys.path.insert(0, str(GENERATOR))
from app.config import Config  # noqa: E402


def _check(label: str, found, expected) -> bool:
    ok = found == expected
    mark = "✅" if ok else "❌"
    print(f"{mark} {label}: README={found!r}  |  代码={expected!r}")
    return ok


def main() -> int:
    cfg = Config()
    readme = README.read_text(encoding="utf-8")
    wf = WORKFLOW.read_text(encoding="utf-8")
    results = []

    # 1) 评分权重
    m = re.search(r"机构权威\s*(\d+)\s*\+\s*引用\s*(\d+)\s*\+\s*时效\s*(\d+)\s*\+\s*论文类型\s*(\d+)", readme)
    if m:
        readme_w = tuple(int(x) for x in m.groups())
        code_w = tuple(cfg.importance_weights[k] for k in ("institution", "citations", "recency", "paper_type"))
        results.append(_check("评分权重（机构/引用/时效/类型）", readme_w, code_w))
    else:
        print("❌ README 中未找到评分权重公式（机构权威 X + 引用 X + 时效 X + 论文类型 X）")
        results.append(False)

    # 2) 导出窗口 HISTORY_DAYS（匹配主文档的「默认 N 天」表述，避开扩展路线的示例）
    m = re.search(r"默认\s*(\d+)\s*天", readme)
    if m:
        results.append(_check("导出窗口 HISTORY_DAYS", int(m.group(1)), cfg.history_days))
    else:
        print("❌ README 中未找到 HISTORY_DAYS 数值（主文档应有『默认 90 天』）")
        results.append(False)

    # 3) 更新频率 cron（README 与 workflow 一致）
    m = re.search(r'cron:\s*"([^"]+)"', wf)
    cron = m.group(1) if m else "?"
    readme_says = "每 6 小时" in readme
    code_is_6h = cron == "0 */6 * * *"
    results.append(_check("更新频率（README 声称『每 6 小时』）", readme_says, code_is_6h))

    # 3b) 各处更新频率文案不得残留过时的「每天 08:00」表述
    frontend_html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    exporter_src = (GENERATOR / "app" / "exporters" / "site.py").read_text(encoding="utf-8")
    stale_in_readme = "每天北京时间 08:00" in readme or "每日北京时间 08:00" in readme
    stale_in_frontend = "08:00 自动更新" in frontend_html
    stale_in_exporter = "08:00 自动更新" in exporter_src
    results.append(_check("README 无过时『每天 08:00』表述", not stale_in_readme, True))
    results.append(_check("前端页脚更新频率文案（含『每 6 小时』）",
                          "每 6 小时自动更新" in frontend_html, True))
    results.append(_check("状态页 update_schedule 文案（含『每 6 小时』）",
                          "每 6 小时自动更新" in exporter_src, True))

    # 4) stale 阈值
    m = re.search(r"EI_STALE_HOURS[^\d]*(\d+)", readme)
    if m:
        results.append(_check("--if-stale 阈值 EI_STALE_HOURS", int(m.group(1)), int(cfg.stale_hours)))
    else:
        print("❌ README 中未找到 EI_STALE_HOURS 数值")
        results.append(False)

    ok = all(results)
    print("=" * 50)
    print("文档一致性检查：通过 ✅" if ok else "文档一致性检查：失败 ❌（请同步更新 README 后重新推送）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
