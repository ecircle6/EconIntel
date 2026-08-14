# EconIntel · 经济学前沿论文聚合与洞察平台

一个**网址**，每天北京时间 08:00 云端自动更新。任何人打开链接即可浏览最新经济学论文——**零安装、零环境依赖、手机电脑都能用**。

- 🌐 **8 大核心数据源**：NBER、CEPR、美联储 FEDS、世界银行、IMF、arXiv（econ/q-fin）、RePEc/NEP 领域文摘、TOP 经济学期刊（AER/QJE/JPE/Econometrica/REStud/JF/JFE，经 CrossRef）
- 🧠 **智能分析**：0-100 重要性评分（🔥热点 / ⭐重要 / 📄普通）、AI 精简标题、核心贡献一句话、关键词、JEL 分类、研究领域自动标注
- 🔗 **父子版本追踪**（全生态空白点）：同一研究的工作论文版 ↔ 期刊版自动关联，详情页展示版本历史
- 🧩 **学者画像 + 个性化订阅**：高频作者聚合页；关注作者/领域/来源，本地自动汇总匹配论文
- ⚡ **秒开体验**：滚动 30 天分片 + 按需加载，首屏 ~1-2 秒可交互；搜索/筛选全量覆盖、永不漏数据
- 📱 **响应式中文界面**：卡片/列表双视图、时间/领域/来源/重要性/类型/关键词多维筛选

---

## 一、给浏览者：零安装使用

把下面这个链接发给任何人即可（手机、电脑、iPad 都能开）：

```
https://<你的GitHub用户名>.github.io/EconIntel/
```

数据每天自动更新，页面打开期间检测到新数据会自动提示刷新。也可以把生成的 `site/EconIntel-离线版.html` 单文件发给别人——**双击即用，完全离线**。

## 二、给维护者：首次部署 5 步走（一次性，之后全自动）

> 前提：有一个 GitHub 账号（免费）。全流程约 5 分钟。

**第 1 步：创建公开仓库**
GitHub 首页 → `New repository` → 仓库名填 **`EconIntel`**（必须与 Pages 网址一致）→ Public → 创建。

**第 2 步（最容易漏的一步）：开启 Pages 部署权限**
进入仓库 → `Settings` → 左侧 `Pages` → **Build and deployment → Source 选择 `GitHub Actions`** → `Save`。
> ⚠️ 不做这一步，第一次部署会失败（workflow 报 `pages: Permission` 类错误）。

**第 3 步：推送代码**
```bash
git remote add origin https://github.com/<你的用户名>/EconIntel.git
git branch -M main
git push -u origin main
```

**第 4 步：等首次构建完成**
仓库 `Actions` 页会看到 `econintel-daily` 工作流正在运行（可手动点 `workflow_dispatch` 立即触发一次）。约 10-20 分钟后首次构建完成。

**第 5 步：验证**
打开 `https://<你的用户名>.github.io/EconIntel/`，看到论文列表即成功。工作流末尾有**部署自检**：URL 非 200 会自动失败并发邮件告警。

之后：**每天北京时间 08:00 自动更新**（cron 实际可能有 5-30 分钟延迟，页面显示真实更新时间）；**每天 12:00 兜底任务**检查今日是否已生成，未生成自动补跑；数据库随每次更新提交回仓库，兼作**异地备份**。

### （可选）开启 AI 精简标题 / 贡献摘要

仓库 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`，添加：

| Secret 名 | 值 | 说明 |
|---|---|---|
| `EI_LLM_API_KEY` | `sk-xxx` | 任意 OpenAI 兼容 Key（DeepSeek / OpenAI / 本地 Ollama 均可） |
| `EI_LLM_BASE_URL` | `https://api.deepseek.com/v1` | 默认即可，按服务商填写 |
| `EI_LLM_MODEL` | `deepseek-chat` | 模型名 |

**不配置也完全可用**：自动降级为规则算法（关键词抽取 + 标题截断 + 领域近似 JEL），评分/分类/标签等功能不受影响。

## 三、本地运行（可选，日常不需要）

不依赖 GitHub 也能本地跑：

```bat
双击 generator\scripts\更新.bat   :: 首次自动建 venv 装依赖；之后一键更新并打开网站
```

或命令行：`python generator/scripts/daily.py --full`（首跑全量）/ `python generator/scripts/daily.py`（增量）。

## 四、常见问题排查

| 症状 | 原因 | 解决 |
|---|---|---|
| 工作流 `deploy-pages` 失败，报 permission | 仓库 Pages 权限未开 | Settings → Pages → Source 选 **GitHub Actions** → Save |
| Actions 页看不到工作流 | 代码尚未推送 | 完成第 3 步 push |
| 构建成功但网址 404 | 仓库名与网址不一致 | Pages 网址 = `用户名.github.io/仓库名`，仓库名应为 `EconIntel` |
| 构建失败，`pip install` 报错 | 网络波动 | 在 Actions 页 `Re-run all jobs` 重跑即可 |
| 大陆访问 github.io 偶尔慢 | CDN 特性 | 属正常现象；也可改用 Cloudflare Pages（见「扩展路线」） |
| 某个数据源状态页显示「异常」 | 上游网站临时不可用 | 无需处理：单源失败不影响整体，连续失败会体现在状态页，下次运行自动恢复 |
| 想手动立即更新 | — | 仓库 Actions → `econintel-daily` → `Run workflow` |

## 五、架构说明

### 数据流水线（`generator/`，每日云端执行）

```
8 源采集（RSS/API/HTML，全部免维护）
  → DOI/URL/标题+作者 三维去重 + 父子版本分组
  → 摘要多级富化：源自带 → CrossRef → OpenAlex → Semantic Scholar（并发 + 超时预算 + 命中短路 + 增量缓存）
  → 引用数（CrossRef / OpenAlex）→ 领域分类（规则词典，标题加权）
  → 0-100 重要性评分（机构权威 25 + 引用 45 + 时效 24 + 论文类型 6，权重可配）
  → AI 精简（LLM 优先，规则降级）
  → 导出静态站点（滚动分片）
```

### 静态站点与分片（`site/`，即部署产物）

| 文件 | 内容 | 加载时机 |
|---|---|---|
| `meta.js` | 版本号、真实更新时间、窗口、源状态（含摘要覆盖率） | 首屏 |
| `index-bN.js` | 轻量索引（列表/筛选/搜索），每片 ~80KB gzip | 首屏载 b1（最近 30 天），后台自动补载其余 |
| `detail-bN.js` | 全字段详情（含版本历史） | 点开论文才加载，内存缓存 |
| `scholars.js` | 学者画像聚合 | 学者页 |
| `EconIntel-离线版.html` | 全部内联的单文件版 | 离线分发用 |

- 数据全部经 `<script>` 标签注入（无 fetch），`file://` 双击也能用
- 搜索/筛选作用在**全部已加载数据**；后台补载完成自动刷新结果，搜索永不漏
- 每 60 秒轮询 `meta.js` 检测新版本，发现即提示一键刷新

### 关键设计约束（对应工程决策）

- **滚动 30 天分片**：窗口永远精确 = `HISTORY_DAYS`（默认 90 天 = 3 片），文件名带版本参数防 CDN 缓存陈旧
- **富化并发与限速**：OpenAlex 8 并发（免费无 key）、Semantic Scholar 按 1.2s/请求限速；单篇 20s 总预算，超时跳过、下次自动补
- **OpenAlex 已商业化（2026-08 实测）**：每日免费额度极少，429 响应含 `Retry-After`，用尽后自动熔断本轮、次日额度重置自动续跑；有 DOI 的论文（NBER/期刊等）走 CrossRef 免费引用计数，不受影响
- **GitHub cron 是 best-effort**：可能有 5-30 分钟延迟——页面显示真实生成时间，另有 12:00 兜底任务
- **摘要缺失不编造**：展示「该来源未提供摘要」降级样式；状态页按源展示摘要覆盖率指标（实测 8 源总体 ≥97%）

## 五点五、测试

```bash
.venv/Scripts/python.exe -m unittest discover -s tests        # 核心逻辑冒烟测试（去重/评分/分类/分片边界）
.venv/Scripts/python.exe tests/gui_test.py                    # 前端 GUI 测试（Playwright 驱动系统 Edge，28 项断言）
```

GUI 测试覆盖：首页渲染、分片后台补载、跨片搜索、详情弹窗（含版本历史）、领域筛选、排序、列表/卡片视图、订阅中心、学者画像、数据源状态页、移动端响应式、离线单文件版。

## 六、扩展路线

| 方向 | 做法 | 工作量 |
|---|---|---|
| 扩展数据源 | `generator/app/collectors/registry.py` 加一行 + 复用采集基类（可参考 Roundup 的 21 源目录，MIT 许可） | 每个源约 30 分钟 |
| 调整导出窗口 | `EI_HISTORY_DAYS=180` → 自动 6 片 | 改一个配置 |
| 微信公众号周报 | 导出器顺带输出微信友好的 Markdown digest | 约半天 |
| Cloudflare Pages 迁移 | 仓库代码不变，仅换部署目标（大陆访问更稳） | 约 1 小时 |
| PostgreSQL 升级 | 改 `EI_DB_PATH` 为 PG 连接串（SQLAlchemy 已兼容） | 改配置 |
| 邮件订阅推送 | 前端订阅数据已就绪，接 SMTP 即可 | 约半天 |

## 七、借鉴与致谢

本项目为自研，MIT 许可发布。设计过程中参考了以下开源项目的思路（依许可合规使用）：

- **[Roundup](https://github.com/lorae/roundup)**（MIT）：多源经济学论文聚合的采集架构与 21 源目录启发——本项目的采集器基类模式与其思路一致，未复制其代码
- **[Academic Door](https://github.com/academic-door)**：中文友好与来源透明的理念启发
- **[Research Tracker](https://github.com/shenyichong/research-tracker)**：多 API 集成思路启发
- **[Econ-Paper-Search](https://github.com/Alalalalaki/Econ-Paper-Search)**：期刊集合与搜索体验启发
- 形态可行性参考 **[daily-paper-reader](https://github.com/ziwenhahaha/daily-paper-reader)**（GH Actions + Pages + AI 阅读的成熟模板）

数据来源：NBER、CEPR、美联储、世界银行、IMF、arXiv、RePEc/IDEAS/NEP、CrossRef、OpenAlex、Semantic Scholar——均为各机构官方公开数据接口。

## 八、技术栈

Python 3.10 · requests / feedparser / BeautifulSoup4 · SQLAlchemy + SQLite · GitHub Actions + GitHub Pages · 原生 HTML/CSS/JS（无构建工具）
