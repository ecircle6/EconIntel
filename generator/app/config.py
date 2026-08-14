"""EconIntel 生成端配置：环境变量优先，附默认值；支持仓库根目录 .env 文件。"""
import os
from pathlib import Path

GENERATOR_DIR = Path(__file__).resolve().parent.parent   # generator/
PROJECT_ROOT = GENERATOR_DIR.parent                       # 仓库根


def _load_dotenv() -> None:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


_load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


class Config:
    """集中配置。所有字段在 __init__ 中从环境变量读取。"""

    def __init__(self) -> None:
        # ---- 路径 ----
        self.db_path = Path(_env("EI_DB_PATH", str(GENERATOR_DIR / "data" / "econintel.db")))
        self.site_dir = Path(_env("EI_SITE_DIR", str(PROJECT_ROOT / "site")))
        self.frontend_dir = Path(_env("EI_FRONTEND_DIR", str(PROJECT_ROOT / "frontend")))
        # ---- 时间窗口 ----
        self.history_days = _env_int("EI_HISTORY_DAYS", 90)          # 导出窗口（滚动分片）
        self.fetch_days_first = _env_int("EI_FETCH_DAYS_FIRST", 90)  # 首跑回填窗口
        self.fetch_days_incremental = _env_int("EI_FETCH_DAYS_INCREMENTAL", 3)  # 每日增量窗口
        # ---- 网络 ----
        self.request_timeout = _env_float("EI_REQUEST_TIMEOUT", 8.0)
        self.series_workers = _env_int("EI_SERIES_WORKERS", 6)       # RePEc 系列详情并发
        self.enrich_workers = _env_int("EI_ENRICH_WORKERS", 8)       # 富化总并发
        self.enrich_max_papers = _env_int("EI_ENRICH_MAX_PAPERS", 600)  # 每轮富化上限（新→旧，剩余下轮补）
        self.s2_min_interval = _env_float("EI_S2_MIN_INTERVAL", 3.2)  # Semantic Scholar 限速（秒，未认证 ≥3.2）
        self.openalex_min_interval = _env_float("EI_OPENALEX_MIN_INTERVAL", 0.25)  # OpenAlex 限速（秒/请求）
        self.openalex_mailto = _env("EI_OPENALEX_MAILTO")            # 填邮箱进 polite pool（10rps 专属）
        self.paper_budget = _env_float("EI_PAPER_BUDGET", 20.0)      # 单篇富化总预算
        # ---- LLM（OpenAI 兼容接口）----
        self.llm_api_key = _env("EI_LLM_API_KEY")
        self.llm_base_url = _env("EI_LLM_BASE_URL", "https://api.deepseek.com/v1")
        self.llm_model = _env("EI_LLM_MODEL", "deepseek-chat")
        self.llm_timeout = _env_float("EI_LLM_TIMEOUT", 60.0)
        # ---- 重要性评分权重（合计 100）----
        self.importance_weights = {
            "institution": _env_int("EI_W_INSTITUTION", 32),  # 机构权威（A/B/C 内再分级）
            "citations": _env_int("EI_W_CITATIONS", 30),      # 引用数（对数归一化）
            "recency": _env_int("EI_W_RECENCY", 26),          # 时效性（分段）
            "paper_type": _env_int("EI_W_TYPE", 12),          # 论文类型（期刊加分）
        }

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


config = Config()
