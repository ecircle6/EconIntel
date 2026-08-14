# EconIntel · 工作区说明

经济学前沿论文聚合平台：Python 采集管道 + 原生 HTML/CSS/JS 静态站点，由 GitHub Actions 每 6 小时自动「采集 → 生成 → 部署」到 GitHub Pages。**仓库所有文档、注释、提交信息、UI 均为中文**，请保持一致。

## 架构与目录

- `generator/app/collectors/` — 8 个数据源采集器（RSS/API/HTML），新增源在 `registry.py` 注册
- `generator/app/processors/` — 去重 `dedup.py` / 分类 `classify.py` / 富化 `enrich.py` / 评分 `importance.py` / AI 精简 `llm.py`+`summarize.py`
- `generator/app/exporters/site.py` — 导出滚动分片静态站点；数据经 `<script>` 注入、**无 fetch**，必须兼容 `file://` 双击打开
- `generator/app/config.py` — 集中配置，全部走 `EI_*` 环境变量（默认值见 `.env.example`；Actions 中对应同名 Secrets，可留空）
- `generator/data/econintel.db` — SQLite 库，**必须提交**（兼作异地备份）；`site/`、`.venv/`、`gui-test-screenshots/` 为生成物不提交
- `frontend/` — 无构建工具，原生 JS 五模块：`app`/`papers`/`scholars`/`status`/`subs`
- `tests/` — `test_core.py`（无网络单测）+ `gui_test.py`（Playwright 驱动系统 Edge）

## 常用命令（Windows，venv 在仓库根 `.venv/`）

- 增量更新：`python generator/scripts/daily.py`（首跑 `--full`；`--force` 跳过 stale 检查）
- 核心单测：`.venv/Scripts/python.exe -m unittest discover -s tests`
- GUI 测试：`.venv/Scripts/python.exe tests/gui_test.py`（28 项断言，需已装 Edge）
- 文档一致性检查：`.venv/Scripts/python.exe generator/scripts/check_docs.py`

## 关键约束（违反会导致 CI 失败或数据失真）

- **check_docs.py 是 CI 硬门槛**：改动评分权重、HISTORY_DAYS、更新频率、EI_STALE_HOURS 时，必须同步更新 README 的对应数值与「每 6 小时」文案（前端页脚和 site.py 状态页文案也逐字校验，不得出现过时的「08:00 自动更新」）。
- **数据真实性铁律**：绝不编造摘要/引用数/评分。引用数仅采纳 DOI 精确匹配，或标题 token 重叠 ≥0.5 且年份差 ≤2 的检索结果；无来源引用按 0 计并在详情页标注「未知」。
- **OpenAlex 已商业化（2026-08 实测）**：每日免费额度极少，429 含 `Retry-After`，用尽自动熔断本轮、次日续跑；有 DOI 的论文走 CrossRef 免费引用计数，不受影响。
- **富化预算**：单篇 20s 总预算，超时跳过、下轮自动补；OpenAlex 8 并发、Semantic Scholar 限速 `EI_S2_MIN_INTERVAL`（默认 3.2s）。
- **CI 行为**：schedule 触发用 `--if-stale`（默认 5h）防重复；push / workflow_dispatch 用 `--force`。DB 备份提交必须带 `[skip ci]` 防 workflow 循环。GitHub cron 实际有 5-30 分钟延迟属正常。

## 评分机制（改公式前必读）

`机构权威(32/20/8) + 引用(log1p，100 引用打满) + 时效(连续指数衰减) + 论文类型(期刊 12/工作论文 4)`，总分 1 位小数；🔥/⭐ 阈值 80/60 固定；权重经 `EI_W_*` 可调。README「重要性评分透明性」一节是唯一权威说明，改代码必须同步改 README（check_docs 校验两者一致）。
