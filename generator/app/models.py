"""数据模型：论文、版本分组、数据源、订阅、学者画像、元信息。"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String, Text

from .database import Base


class Paper(Base):
    """一篇论文（同一研究的不同版本共享 version_group）。"""

    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doi = Column(String(255), unique=True, nullable=True, index=True)
    title_original = Column(Text, nullable=False)
    title_short = Column(String(200), default="")           # AI/规则精简标题
    contribution = Column(Text, default="")                 # 1-2 句核心贡献
    keywords = Column(JSON, default=list)                   # 3-5 关键词
    jel = Column(JSON, default=list)                        # JEL 分类码
    abstract = Column(Text, default="")
    abstract_source = Column(String(24), default="")        # source/crossref/openalex/s2/version
    authors = Column(JSON, default=list)                    # 作者名列表
    source = Column(String(32), index=True, nullable=False)  # 数据源 key
    paper_type = Column(String(16), default="working")      # working / journal
    published_at = Column(DateTime, index=True, nullable=True)
    collected_at = Column(DateTime, default=datetime.utcnow)
    url_original = Column(Text, default="")
    citations = Column(Integer, nullable=True)              # 引用数（未知为 None）
    citation_source = Column(String(16), default="")        # 引用数来源：crossref/openalex/s2
    importance_score = Column(Float, default=0.0)           # 0-100（1 位小数）
    importance_label = Column(String(8), default="📄普通")
    field = Column(String(32), default="")                  # 研究领域（中文）
    credibility = Column(String(1), default="B")            # A 官方 / B 学术数据库 / C 预印本
    version_group = Column(String(40), index=True, nullable=False)
    version_role = Column(String(8), default="root")        # root=主展示版 / variant=其他版本
    enriched_at = Column(DateTime, nullable=True)           # 摘要/引用富化完成时间
    summarized_at = Column(DateTime, nullable=True)         # 精简/关键词生成完成时间
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Source(Base):
    """数据源健康状态（由 pipeline 每次抓取后更新）。"""

    __tablename__ = "sources"

    key = Column(String(32), primary_key=True)
    name = Column(String(64), default="")
    source_type = Column(String(16), default="")
    url = Column(Text, default="")
    credibility = Column(String(1), default="B")
    enabled = Column(Boolean, default=True)
    last_fetch_at = Column(DateTime, nullable=True)
    last_fetch_status = Column(String(16), default="")      # ok / error
    last_fetch_count = Column(Integer, default=0)
    last_error = Column(Text, default="")
    error_count = Column(Integer, default=0)                # 连续失败次数


class Subscription(Base):
    """个性化订阅（关注作者/机构/领域）。"""

    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(16), nullable=False)               # author / institution / field
    value = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Scholar(Base):
    """学者画像缓存（导出时聚合）。"""

    __tablename__ = "scholars"

    name = Column(String(128), primary_key=True)
    fields = Column(JSON, default=list)
    sources = Column(JSON, default=list)
    paper_count = Column(Integer, default=0)
    avg_score = Column(Float, default=0.0)
    top_papers = Column(JSON, default=list)                 # [paper_id, ...]
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MetaKV(Base):
    """键值元信息（last_run 等）。"""

    __tablename__ = "meta_kv"

    key = Column(String(64), primary_key=True)
    value = Column(Text, default="")
