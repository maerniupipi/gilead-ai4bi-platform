"""
XLSX 表格智能问答工具 · ORM

5 张控制表：
  - xlsx_qa_module        模块（= 多份 xlsx 文件的上下文 + 多会话）
  - xlsx_qa_document      xlsx 文件元信息 + 解析状态
  - xlsx_qa_sheet         每个 Sheet 的元信息 + 动态数据表名 + 独立表理解
  - xlsx_qa_conversation  会话
  - xlsx_qa_message       消息（user / assistant；assistant 的下钻过程存 extras_json）

说明：
  * 每上传一份文件会在 MySQL 中动态建物理数据表 `xlsx_qa_data_m{mid}_d{did}_s{idx}`，
    结构按 xlsx 表头 / 推断类型构造；该表不是 ORM 模型，纯 DDL 管理（见 services/xlsx_qa/xlsx_parser.py）。
"""
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    TIMESTAMP,
    func,
)
from sqlalchemy.orm import relationship

from ..core.database import Base


class XlsxQaModule(Base):
    """XLSX 问答模块（支持多文件多 Sheet）。"""

    __tablename__ = "xlsx_qa_module"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    name = Column(String(128), nullable=False)
    description = Column(String(500), nullable=True)
    owner_display_name = Column(String(128), nullable=True)
    # 默认使用的 LLM；为空时由 service 层回退到系统默认
    llm_provider_id = Column(Integer, nullable=True)
    llm_model = Column(String(128), nullable=True)
    # 预留：前端展示用的图标 / 颜色 / 其它模块级配置
    extra_config_json = Column(JSON, nullable=True)
    # 外链分享：随机 opaque token；仅用于 /api/xlsx-qa/share/{token}/... 免登录访问该模块
    share_token = Column(String(64), nullable=True, unique=True, index=True)
    # 跨 Sheet 汇总理解（LLM 在上传完所有 Sheet 后生成）；Stage 0 Module Planning 的输入
    module_understanding_md = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
    is_deleted = Column(Boolean, default=False, nullable=False)

    documents = relationship(
        "XlsxQaDocument",
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="XlsxQaDocument.id",
    )
    conversations = relationship(
        "XlsxQaConversation",
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="XlsxQaConversation.id.desc()",
    )
    insight_report = relationship(
        "XlsxQaInsightReport",
        back_populates="module",
        cascade="all, delete-orphan",
        uselist=False,
    )


class XlsxQaDocument(Base):
    """xlsx 文件元信息 + 解析状态。"""

    __tablename__ = "xlsx_qa_document"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    module_id = Column(
        Integer,
        ForeignKey("xlsx_qa_module.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_name = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False, default=0)
    oss_object_key = Column(String(512), nullable=False)
    sheet_name = Column(String(255), nullable=True)       # 保留用于向后兼容，新上传不再填充
    data_table_name = Column(String(128), nullable=True)  # 保留用于向后兼容，新上传不再填充
    total_rows = Column(Integer, nullable=False, default=0)     # 保留向后兼容
    total_columns = Column(Integer, nullable=False, default=0)  # 保留向后兼容
    columns_json = Column(JSON, nullable=True)            # 保留向后兼容
    understanding_md = Column(Text, nullable=True)        # 保留向后兼容
    suggested_questions_json = Column(JSON, nullable=True) # 保留向后兼容
    status = Column(String(32), nullable=False, default="pending")  # pending|parsing|ready|failed
    parse_error = Column(Text, nullable=True)
    # 多 Sheet：该文件内解析出的 Sheet 数量（1~5）
    sheet_count = Column(Integer, nullable=False, default=0)
    # 模块内"主文件"标记
    is_primary = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    module = relationship("XlsxQaModule", back_populates="documents")
    sheets = relationship(
        "XlsxQaSheet",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="XlsxQaSheet.sheet_index",
    )


class XlsxQaConversation(Base):
    """会话（同一模块下可以有多个会话）。"""

    __tablename__ = "xlsx_qa_conversation"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    module_id = Column(
        Integer,
        ForeignKey("xlsx_qa_module.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=False, default="新会话")
    # 本次会话关联的 Sheet ID 列表，默认 = 模块所有 Sheet 的 ID
    active_sheet_ids = Column(JSON, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    module = relationship("XlsxQaModule", back_populates="conversations")
    messages = relationship(
        "XlsxQaMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="XlsxQaMessage.id",
    )


class XlsxQaMessage(Base):
    """会话消息。assistant 的下钻过程 / SQL / 结果 / 总结全部放在 extras_json。"""

    __tablename__ = "xlsx_qa_message"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    conversation_id = Column(
        Integer,
        ForeignKey("xlsx_qa_conversation.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(16), nullable=False)  # user | assistant
    content = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="ok")  # ok | failed | partial
    # {plan_summary, subquestions:[{id,question,purpose,sql,sql_status,columns,rows,total_rows,error?}],
    #  summary_markdown, follow_up_questions:[...], stage_timings:{...}}
    extras_json = Column(JSON, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    conversation = relationship("XlsxQaConversation", back_populates="messages")


class XlsxQaSheet(Base):
    """每个 xlsx Sheet 的元信息 + 独立表理解。

    物理表名：xlsx_qa_data_m{module_id}_d{doc_id}_s{sheet_index}
    一个 Document 最多 5 条 Sheet 记录。
    """

    __tablename__ = "xlsx_qa_sheet"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_id = Column(
        Integer,
        ForeignKey("xlsx_qa_document.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sheet_index = Column(Integer, nullable=False, comment="Sheet 序号（0-based，最多 5 个）")
    sheet_name = Column(String(255), nullable=False)
    # 动态物理表名：xlsx_qa_data_m{module_id}_d{doc_id}_s{sheet_index}
    data_table_name = Column(String(128), nullable=False, unique=True)
    total_rows = Column(Integer, nullable=False, default=0)
    total_columns = Column(Integer, nullable=False, default=0)
    # [{raw_header, column_name, column_type, sample, distinct}]
    columns_json = Column(JSON, nullable=True)
    # LLM 生成的该 Sheet 的独立表理解（Markdown）
    understanding_md = Column(Text, nullable=True)
    # LLM 生成的推荐问题列表 List[str]
    suggested_questions_json = Column(JSON, nullable=True)
    status = Column(String(32), nullable=False, default="pending")  # pending|parsing|ready|failed
    parse_error = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    document = relationship("XlsxQaDocument", back_populates="sheets")


class XlsxQaInsightReport(Base):
    """模块级深度洞察报告（保存最新一次生成结果，支持刷新恢复）。"""

    __tablename__ = "xlsx_qa_insight_report"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    module_id = Column(
        Integer,
        ForeignKey("xlsx_qa_module.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status = Column(String(32), nullable=False, default="generating")  # generating | done | failed
    phase = Column(String(32), nullable=False, default="profile")
    role_cards_json = Column(JSON, nullable=True)
    dimensions_json = Column(JSON, nullable=True)
    evidence_json = Column(JSON, nullable=True)
    dim_texts_json = Column(JSON, nullable=True)
    final_md = Column(Text, nullable=True)
    elapsed_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    module = relationship("XlsxQaModule", back_populates="insight_report")


class XlsxQaPptTemplate(Base):
    """PPT 导出模板（内置 + 用户自定义）。"""

    __tablename__ = "xlsx_qa_ppt_template"

    id = Column(String(32), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(String(200), nullable=False, default="")
    layout = Column(String(32), nullable=False, comment="布局类型: sidebar/header/minimal/dark_full/diagonal/corner/right_panel/dark_header")
    colors = Column(JSON, nullable=False, comment="颜色配置 JSON")
    layout_config = Column(JSON, nullable=True, comment="布局参数覆盖 JSON")
    is_builtin = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class XlsxQaPptHistory(Base):
    """PPT 导出历史记录（异步生成，追踪状态）。"""

    __tablename__ = "xlsx_qa_ppt_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    module_id = Column(
        Integer,
        ForeignKey("xlsx_qa_module.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id = Column(
        Integer,
        ForeignKey("xlsx_qa_conversation.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_title = Column(String(255), nullable=False, default="")
    template_id = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="generating")  # generating | ready | failed
    status_message = Column(Text, nullable=True)  # Current progress message
    progress_messages_json = Column(JSON, nullable=True)  # Array of recent status messages for frontend scroll
    error_message = Column(Text, nullable=True)
    oss_object_key = Column(String(512), nullable=True)
    file_size = Column(BigInteger, nullable=True, default=0)
    options_json = Column(JSON, nullable=True)  # Export options snapshot
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
