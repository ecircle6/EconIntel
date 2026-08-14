"""每日更新入口：采集 → 处理 → 导出静态站点。

用法：
  python generator/scripts/daily.py                 # 增量更新 + 导出
  python generator/scripts/daily.py --full          # 首跑全量回填 + 导出
  python generator/scripts/daily.py --if-stale      # 今日已跑则跳过（Actions 兜底 job 用）
  python generator/scripts/daily.py --no-export     # 只更新数据库不导出
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # generator/

from app.config import config  # noqa: E402
from app.database import get_session  # noqa: E402
from app.exporters.site import SiteExporter  # noqa: E402
from app.services.pipeline import Pipeline  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")


def main() -> int:
    ap = argparse.ArgumentParser(description="EconIntel 每日更新")
    ap.add_argument("--full", action="store_true", help="全量回填（首跑用）")
    ap.add_argument("--if-stale", action="store_true",
                    help="最近 EI_STALE_HOURS（默认 5）小时内已成功运行过则跳过（定时任务防重复）")
    ap.add_argument("--force", action="store_true", help="忽略 stale 检查强制运行（手动触发用）")
    ap.add_argument("--no-export", action="store_true", help="只更新数据库，不导出站点")
    args = ap.parse_args()

    if_stale = args.if_stale and not args.force
    try:
        stats = Pipeline(config).run(full=args.full, if_stale=if_stale)
    except Exception:
        logging.exception("pipeline 失败")
        print("RESULT=ERROR")
        return 1

    if stats.get("skipped"):
        print("最近 EI_STALE_HOURS 小时内已成功运行过，跳过本次（防重复）")
        print("RESULT=SKIPPED")
        return 0

    print("—" * 50)
    print(f"采集：共 {stats['drafts_total']} 篇草稿；成功源 {len(stats['sources_ok'])} 个，失败源 {len(stats['sources_fail'])} 个")
    print(f"入库：新增 {stats['new_papers']} 篇，更新 {stats['updated_papers']} 篇")
    print(f"富化：{stats['enriched']} 篇；精简：LLM {stats['summarized_llm']} 篇 / 规则 {stats['summarized_rule']} 篇")
    if stats.get("sources_fail"):
        print(f"⚠ 失败源：{', '.join(stats['sources_fail'])}（详见站内「状态」页）")

    if not args.no_export:
        session = get_session()
        result = SiteExporter(config).export(session)
        print(f"导出完成：{result['papers']} 篇 → {config.site_dir}（分片 {', '.join(result['blocks'])}）")
    print("RESULT=OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
