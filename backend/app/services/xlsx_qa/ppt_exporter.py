"""
XLSX 表格智能问答 · 会话导出 PPT (v3)

每个 Q&A 的幻灯片结构：
  1. 摘要页       — 左栏：核心结论 + 关键发现（自动缩放字号，不截断）
                    右栏：主图（原生 PPT 图表：柱/折/饼）
  2. 辅图页       — 每个次要图表独占一页（原生 PPT 图表，全屏）
  3. 数据明细页   — 每个子问题的 SQL 结果表（原生 PPT 表格，含全量行列）
"""
from __future__ import annotations

import io
import logging
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.chart import (
    XL_CHART_TYPE,
    XL_DATA_LABEL_POSITION,
    XL_LEGEND_POSITION,
    XL_TICK_LABEL_POSITION,
)
from pptx.enum.shapes import MSO_SHAPE
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

logger = logging.getLogger(__name__)

# ── 画布尺寸 (16:9) ──────────────────────────────────────────────────────────
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

# ── 配色 ──────────────────────────────────────────────────────────────────────
C_GREEN      = RGBColor(0x05, 0x96, 0x69)
C_GREEN_DARK = RGBColor(0x03, 0x6B, 0x4A)
C_TEXT       = RGBColor(0x1F, 0x2D, 0x3D)
C_MUTED      = RGBColor(0x8A, 0x8A, 0x8A)
C_BG_SOFT    = RGBColor(0xF0, 0xFB, 0xF6)
C_WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
C_TH         = RGBColor(0x05, 0x96, 0x69)   # 表头背景
C_ROW_ALT    = RGBColor(0xF4, 0xFD, 0xF8)
C_RED        = RGBColor(0xC0, 0x39, 0x2B)
C_GRAY_BG    = RGBColor(0xF1, 0xF5, 0xF9)
C_GRAY_GREEN = RGBColor(0x3B, 0x4A, 0x8E)

# ── 图表数据限制 ──────────────────────────────────────────────────────────────
MAX_PIE_CATS  = 10   # 饼图最多展示类目数
MAX_BAR_CATS  = 25   # 柱/折线图最多展示类目数
MAX_TBL_ROWS  = 16   # 数据表每页最多行数
MAX_TBL_COLS  = 8    # 数据表每页最多列数

# ── 摘要页内容限制 ────────────────────────────────────────────────────────────
CONCL_MAX_CHARS  = 180   # 核心结论最大字符数
FINDING_MAX_CHARS = 65   # 每条关键发现最大字符数
FINDING_MAX_COUNT = 4    # 关键发现最多显示条数
# 深度洞察维度总览页底栏（齿轮装饰卡内）结论：模板区高度有限，与 LLM 约 1/3 字数对齐
INSIGHT_SUMMARY_CONCL_MAX_CHARS = 100

# 原生 PPT 图表类型映射
_XL_MAP = {
    "bar":  XL_CHART_TYPE.COLUMN_CLUSTERED,
    "line": XL_CHART_TYPE.LINE,
    "pie":  XL_CHART_TYPE.PIE,
}


# ─────────────────────────────────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PptMessage:
    role: str
    content: str
    extras: Optional[dict] = None
    created_at: Optional[str] = None


@dataclass
class PptExportOptions:
    include_subquestions: bool = True
    include_sql: bool = True
    include_chart: bool = True
    template_id: str = "executive"


@dataclass(frozen=True)
class PptTheme:
    id: str
    name: str
    layout: str  # sidebar | header | minimal | dark_full | diagonal | corner | right_panel | dark_header
    accent: RGBColor
    accent_dark: RGBColor
    accent_soft: RGBColor
    bg: RGBColor
    panel: RGBColor
    text: RGBColor
    muted: RGBColor
    table_header: RGBColor
    table_alt: RGBColor
    palette: Tuple[RGBColor, ...]
    layout_config: Dict[str, Any] = field(default_factory=dict)


THEMES = {
    "executive": PptTheme(
        id="executive",
        name="Executive Brief",
        layout="sidebar",
        accent=RGBColor(0x16, 0xA3, 0x4A),
        accent_dark=RGBColor(0x08, 0x5F, 0x37),
        accent_soft=RGBColor(0xE8, 0xF8, 0xEE),
        bg=RGBColor(0xF7, 0xFA, 0xFC),
        panel=RGBColor(0xFF, 0xFF, 0xFF),
        text=RGBColor(0x17, 0x24, 0x1F),
        muted=RGBColor(0x64, 0x74, 0x8B),
        table_header=RGBColor(0x0F, 0x7A, 0x4B),
        table_alt=RGBColor(0xF1, 0xFA, 0xF5),
        palette=(
            RGBColor(0x16, 0xA3, 0x4A), RGBColor(0x25, 0x63, 0xEB),
            RGBColor(0xF5, 0x9E, 0x0B), RGBColor(0xDC, 0x26, 0x26),
            RGBColor(0x7C, 0x3A, 0xED), RGBColor(0x0E, 0x74, 0x80),
        ),
    ),
    "insight": PptTheme(
        id="insight",
        name="Insight Analysis",
        layout="header",
        accent=RGBColor(0x25, 0x63, 0xEB),
        accent_dark=RGBColor(0x1E, 0x3A, 0x8A),
        accent_soft=RGBColor(0xE8, 0xF0, 0xFF),
        bg=RGBColor(0xF8, 0xFA, 0xFC),
        panel=RGBColor(0xFF, 0xFF, 0xFF),
        text=RGBColor(0x0F, 0x17, 0x2A),
        muted=RGBColor(0x64, 0x74, 0x8B),
        table_header=RGBColor(0x1D, 0x4E, 0x89),
        table_alt=RGBColor(0xF1, 0xF5, 0xFF),
        palette=(
            RGBColor(0x25, 0x63, 0xEB), RGBColor(0x10, 0xB9, 0x81),
            RGBColor(0xF9, 0x73, 0x16), RGBColor(0x8B, 0x5C, 0xF6),
            RGBColor(0x06, 0xB6, 0xD4), RGBColor(0xE1, 0x1D, 0x48),
        ),
    ),
    "clean": PptTheme(
        id="clean",
        name="Clean Data",
        layout="minimal",
        accent=RGBColor(0x33, 0x41, 0x55),
        accent_dark=RGBColor(0x0F, 0x17, 0x2A),
        accent_soft=RGBColor(0xF1, 0xF5, 0xF9),
        bg=RGBColor(0xFF, 0xFF, 0xFF),
        panel=RGBColor(0xFF, 0xFF, 0xFF),
        text=RGBColor(0x11, 0x18, 0x27),
        muted=RGBColor(0x6B, 0x72, 0x80),
        table_header=RGBColor(0x33, 0x41, 0x55),
        table_alt=RGBColor(0xF8, 0xFA, 0xFC),
        palette=(
            RGBColor(0x33, 0x41, 0x55), RGBColor(0x0E, 0x74, 0x80),
            RGBColor(0x65, 0xA3, 0x0D), RGBColor(0xCA, 0x8A, 0x04),
            RGBColor(0x7C, 0x2D, 0x12), RGBColor(0x7E, 0x22, 0xCE),
        ),
    ),
    "midnight": PptTheme(
        id="midnight",
        name="Midnight Blue",
        layout="dark_full",
        accent=RGBColor(0xFF, 0xB2, 0x24),
        accent_dark=RGBColor(0x0D, 0x1B, 0x2A),
        accent_soft=RGBColor(0x1B, 0x2D, 0x44),
        bg=RGBColor(0x0D, 0x1B, 0x2A),
        panel=RGBColor(0x15, 0x26, 0x3B),
        text=RGBColor(0xE8, 0xEC, 0xF1),
        muted=RGBColor(0x8B, 0x9D, 0xB3),
        table_header=RGBColor(0x1B, 0x3A, 0x5C),
        table_alt=RGBColor(0x12, 0x22, 0x36),
        palette=(
            RGBColor(0xFF, 0xB2, 0x24), RGBColor(0x38, 0xBD, 0xF8),
            RGBColor(0xA7, 0x8B, 0xFA), RGBColor(0x34, 0xD3, 0x99),
            RGBColor(0xFB, 0x71, 0x85), RGBColor(0x60, 0xA5, 0xFA),
        ),
    ),
    "coral": PptTheme(
        id="coral",
        name="Coral Energy",
        layout="diagonal",
        accent=RGBColor(0xF9, 0x61, 0x67),
        accent_dark=RGBColor(0xC0, 0x39, 0x2B),
        accent_soft=RGBColor(0xFF, 0xF1, 0xF0),
        bg=RGBColor(0xFF, 0xFA, 0xF7),
        panel=RGBColor(0xFF, 0xFF, 0xFF),
        text=RGBColor(0x2D, 0x1B, 0x1B),
        muted=RGBColor(0x9C, 0x7A, 0x7A),
        table_header=RGBColor(0xE8, 0x4D, 0x4D),
        table_alt=RGBColor(0xFF, 0xF5, 0xF4),
        palette=(
            RGBColor(0xF9, 0x61, 0x67), RGBColor(0xF9, 0x73, 0x16),
            RGBColor(0xFB, 0xBF, 0x24), RGBColor(0x2D, 0xC6, 0x53),
            RGBColor(0x38, 0xBD, 0xF8), RGBColor(0xA7, 0x8B, 0xFA),
        ),
    ),
    "teal": PptTheme(
        id="teal",
        name="Teal Trust",
        layout="corner",
        accent=RGBColor(0x0D, 0x94, 0x88),
        accent_dark=RGBColor(0x11, 0x5E, 0x59),
        accent_soft=RGBColor(0xEC, 0xFD, 0xF5),
        bg=RGBColor(0xF0, 0xFD, 0xFA),
        panel=RGBColor(0xFF, 0xFF, 0xFF),
        text=RGBColor(0x13, 0x2B, 0x2B),
        muted=RGBColor(0x6B, 0x8A, 0x87),
        table_header=RGBColor(0x0F, 0x76, 0x6E),
        table_alt=RGBColor(0xF0, 0xFD, 0xFA),
        palette=(
            RGBColor(0x0D, 0x94, 0x88), RGBColor(0x06, 0xB6, 0xD4),
            RGBColor(0x8B, 0x5C, 0xF6), RGBColor(0xF5, 0x9E, 0x0B),
            RGBColor(0xEF, 0x44, 0x44), RGBColor(0x22, 0xC5, 0x5E),
        ),
    ),
    "berry": PptTheme(
        id="berry",
        name="Berry & Cream",
        layout="right_panel",
        accent=RGBColor(0x9D, 0x17, 0x4D),
        accent_dark=RGBColor(0x70, 0x12, 0x38),
        accent_soft=RGBColor(0xFD, 0xF2, 0xF8),
        bg=RGBColor(0xFF, 0xFA, 0xFC),
        panel=RGBColor(0xFF, 0xFF, 0xFF),
        text=RGBColor(0x2A, 0x15, 0x22),
        muted=RGBColor(0x9C, 0x7A, 0x8C),
        table_header=RGBColor(0x83, 0x18, 0x43),
        table_alt=RGBColor(0xFD, 0xF2, 0xF8),
        palette=(
            RGBColor(0x9D, 0x17, 0x4D), RGBColor(0xA2, 0x67, 0x69),
            RGBColor(0xBE, 0x18, 0x5D), RGBColor(0xD9, 0x77, 0x06),
            RGBColor(0x6D, 0x28, 0xD9), RGBColor(0x08, 0x91, 0xB2),
        ),
    ),
    "charcoal": PptTheme(
        id="charcoal",
        name="Charcoal Dark",
        layout="dark_header",
        accent=RGBColor(0xF5, 0x9E, 0x0B),
        accent_dark=RGBColor(0x1E, 0x1E, 0x1E),
        accent_soft=RGBColor(0x2A, 0x2A, 0x2A),
        bg=RGBColor(0x1E, 0x1E, 0x1E),
        panel=RGBColor(0x2A, 0x2A, 0x2A),
        text=RGBColor(0xE5, 0xE5, 0xE5),
        muted=RGBColor(0x8A, 0x8A, 0x8A),
        table_header=RGBColor(0x3A, 0x3A, 0x3A),
        table_alt=RGBColor(0x24, 0x24, 0x24),
        palette=(
            RGBColor(0xF5, 0x9E, 0x0B), RGBColor(0x38, 0xBD, 0xF8),
            RGBColor(0xA3, 0xE6, 0x35), RGBColor(0xF4, 0x72, 0xB6),
            RGBColor(0xC0, 0x84, 0xFC), RGBColor(0xFB, 0x92, 0x3C),
        ),
    ),
}


# ── 各布局默认可调参数 ──────────────────────────────────────────────────────

DEFAULT_LAYOUT_CONFIGS: Dict[str, Dict[str, Any]] = {
    "sidebar": {
        "accent_bar_width": 0.25,
    },
    "header": {
        "cover_header_height": 1.6,
        "qslide_header_height": 1.2,
    },
    "minimal": {
        "margin": 0.6,
    },
    "dark_full": {
        "content_margin": 1.0,
    },
    "diagonal": {
        "accent_bar_width": 0.4,
        "panel_width": 5.5,
    },
    "corner": {
        "corner_block_width": 5.5,
        "corner_block_height": 3.5,
        "corner_block_top": 4.0,
        "corner_qslide_block_top": 6.2,
        "corner_qslide_block_height": 1.3,
    },
    "right_panel": {
        "panel_left": 7.5,
        "panel_width": 5.833,
        "qslide_panel_left": 10.0,
        "qslide_panel_width": 3.333,
    },
    "dark_header": {
        "cover_header_height": 2.4,
        "qslide_header_height": 1.4,
    },
}


def _cfg(theme: PptTheme, key: str, default_inches: float) -> Inches:
    """从 theme.layout_config 读取配置值，不存在则用默认。返回 Inches。"""
    cfg = theme.layout_config or {}
    val = cfg.get(key, default_inches)
    return Inches(float(val))


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

def _hex_to_rgb(hex_str: str) -> RGBColor:
    """'#16A34A' → RGBColor(0x16, 0xA3, 0x4A)"""
    h = hex_str.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _db_row_to_ppt_theme(row) -> PptTheme:
    """数据库行 → PptTheme（row.colors 为 dict，值为 hex 字符串）。"""
    c = row.colors
    db_cfg = row.layout_config or {} if hasattr(row, "layout_config") else {}
    # DB 配置覆盖默认值
    layout_defaults = DEFAULT_LAYOUT_CONFIGS.get(row.layout, {})
    merged_cfg = {**layout_defaults, **db_cfg}
    return PptTheme(
        id=row.id,
        name=row.name,
        layout=row.layout,
        accent=_hex_to_rgb(c["accent"]),
        accent_dark=_hex_to_rgb(c["accent_dark"]),
        accent_soft=_hex_to_rgb(c["accent_soft"]),
        bg=_hex_to_rgb(c["bg"]),
        panel=_hex_to_rgb(c["panel"]),
        text=_hex_to_rgb(c["text"]),
        muted=_hex_to_rgb(c["muted"]),
        table_header=_hex_to_rgb(c["table_header"]),
        table_alt=_hex_to_rgb(c["table_alt"]),
        palette=tuple(_hex_to_rgb(h) for h in c["palette"]),
        layout_config=merged_cfg,
    )


def resolve_theme_from_db(db, template_id: str) -> PptTheme:
    """优先从 DB 加载模板，回退到内置 THEMES 字典。"""
    from ...repositories.xlsx_qa.repository import XlsxQaRepository
    tpl = XlsxQaRepository.get_ppt_template(db, template_id)
    if tpl:
        return _db_row_to_ppt_theme(tpl)
    return _resolve_theme(template_id)


def build_pptx(
    *,
    module_name: str,
    conversation_title: str,
    file_name: Optional[str],
    author: Optional[str] = None,
    messages: List[PptMessage],
    options: PptExportOptions,
    db=None,
) -> bytes:
    prs = Presentation()
    prs.slide_width  = SLIDE_W
    prs.slide_height = SLIDE_H
    if db is not None:
        theme = resolve_theme_from_db(db, options.template_id)
    else:
        theme = _resolve_theme(options.template_id)

    pairs = _pair_messages(messages)
    _add_cover(prs, module_name=module_name, conversation_title=conversation_title,
               file_name=file_name, author=author, n_questions=len(pairs), theme=theme)

    for idx, (user_msg, ast_msg) in enumerate(pairs, start=1):
        ex          = (ast_msg.extras or {}) if ast_msg else {}
        all_charts  = _parse_charts(ex)
        primary     = _get_primary(ex, all_charts)
        summary_md = ex.get("summary_markdown") or (ast_msg.content if ast_msg else "") or ""
        sections = _get_insight_sections(ex, all_charts, summary_md)

        _add_question_slide(
            prs, idx=idx, total=len(pairs), user_msg=user_msg, ast_msg=ast_msg,
            module_name=module_name, theme=theme,
        )

        for sec_idx, section in enumerate(sections, start=1):
            chart = _section_chart(section, all_charts, primary)
            _add_insight_slide(
                prs,
                q_idx=idx,
                q_total=len(pairs),
                sec_idx=sec_idx,
                sec_total=len(sections),
                section=section,
                chart=chart,
                theme=theme,
                include_chart=options.include_chart,
            )

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 封面页
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_theme(template_id: str) -> PptTheme:
    return THEMES.get((template_id or "").strip().lower(), THEMES["executive"])


def _add_cover(prs, *, module_name, conversation_title, file_name, author, n_questions, theme: PptTheme):
    slide = _blank(prs)
    _rect(slide, 0, 0, SLIDE_W, SLIDE_H, theme.bg)

    layout = theme.layout
    if layout == "sidebar":
        _cover_sidebar(slide, theme, module_name, conversation_title, file_name, author, n_questions)
    elif layout == "header":
        _cover_header(slide, theme, module_name, conversation_title, file_name, author, n_questions)
    elif layout == "minimal":
        _cover_minimal(slide, theme, module_name, conversation_title, file_name, author, n_questions)
    elif layout == "dark_full":
        _cover_dark_full(slide, theme, module_name, conversation_title, file_name, author, n_questions)
    elif layout == "diagonal":
        _cover_diagonal(slide, theme, module_name, conversation_title, file_name, author, n_questions)
    elif layout == "corner":
        _cover_corner(slide, theme, module_name, conversation_title, file_name, author, n_questions)
    elif layout == "right_panel":
        _cover_right_panel(slide, theme, module_name, conversation_title, file_name, author, n_questions)
    elif layout == "dark_header":
        _cover_dark_header(slide, theme, module_name, conversation_title, file_name, author, n_questions)
    else:
        _cover_sidebar(slide, theme, module_name, conversation_title, file_name, author, n_questions)


def _cover_meta_block(slide, theme, left, top, author, n_questions, module_name):
    """Shared metadata block: author + time + bottom line."""
    for i, (lbl, val) in enumerate([
        ("作者", author or "—"),
        ("时间", datetime.now().strftime("%Y-%m-%d %H:%M")),
    ]):
        y = Emu(top + Inches(i * 0.56))
        _text(slide, lbl, left, y, Inches(0.86), Inches(0.22),
              font_size=9, bold=True, color=theme.accent)
        _text(slide, _shrink(str(val), 70),
              Emu(left + Inches(0.92)), Emu(y - Inches(0.02)), Inches(5.5), Inches(0.3),
              font_size=12, color=theme.text)
    _text(slide, f"共 {n_questions} 个问题  ·  {module_name or '数据洞察'}  ·  {datetime.now().strftime('%Y-%m-%d')}",
          Inches(0.5), Inches(6.94), Inches(12.0), Inches(0.36),
          font_size=9, color=theme.muted, align=PP_ALIGN.CENTER)


def _cover_sidebar(slide, theme, module_name, conversation_title, file_name, author, n_questions):
    """executive — 左侧宽色块 + 数字"""
    _circle(slide, Inches(10.8), Inches(-0.6), Inches(2.2), theme.accent_soft)
    _circle(slide, Inches(11.5), Inches(0.3), Inches(1.1), theme.accent, opacity=0.15)
    _circle(slide, Inches(-0.4), Inches(5.8), Inches(1.8), theme.accent_soft)

    bar_w = _cfg(theme, "accent_bar_width", 0.25)
    _rect(slide, 0, 0, bar_w, SLIDE_H, theme.accent)
    _rect(slide, bar_w, 0, Inches(0.06), SLIDE_H, theme.accent_soft)
    _rect(slide, 0, Inches(6.85), SLIDE_W, Inches(0.65), theme.accent_soft)
    _rect(slide, 0, Inches(6.85), SLIDE_W, Inches(0.04), theme.accent)

    _rect(slide, Inches(0.72), Inches(0.72), Inches(3.6), Inches(5.8), theme.panel)
    _rect(slide, Inches(0.72), Inches(0.72), Inches(3.6), Inches(0.06), theme.accent)

    _round_rect(slide, Inches(1.02), Inches(1.12), Inches(1.8), Inches(0.34), theme.accent)
    _text(slide, theme.name.upper(),
          Inches(1.02), Inches(1.12), Inches(1.8), Inches(0.34),
          font_size=9, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)

    _text(slide, f"{n_questions}",
          Inches(1.02), Inches(2.0), Inches(3.0), Inches(0.9),
          font_size=52, bold=True, color=theme.accent)
    _text(slide, "个分析问题",
          Inches(1.08), Inches(2.92), Inches(2.8), Inches(0.3),
          font_size=13, color=theme.muted)

    for i, (lbl, val) in enumerate([
        ("模块", module_name or "—"),
        ("数据源", file_name or "—"),
    ]):
        y = Inches(3.72 + i * 0.66)
        _text(slide, lbl, Inches(1.08), y, Inches(0.86), Inches(0.22),
              font_size=9, bold=True, color=theme.accent)
        _text(slide, _shrink(str(val), 28),
              Inches(1.08), Emu(y + Inches(0.24)), Inches(3.0), Inches(0.28),
              font_size=11, color=theme.text)

    _text(slide, "数据洞察报告",
          Inches(5.0), Inches(1.4), Inches(7.4), Inches(0.9),
          font_size=38, bold=True, color=theme.accent_dark)
    _text(slide, conversation_title or "XLSX 表格智能问答",
          Inches(5.04), Inches(2.4), Inches(7.2), Inches(0.42),
          font_size=15, color=theme.muted)

    _rect(slide, Inches(5.0), Inches(3.2), Inches(7.0), Inches(0.02), theme.accent_soft)
    _cover_meta_block(slide, theme, Inches(5.04), Inches(3.5), author, n_questions, module_name)

    _rect(slide, Inches(5.0), Inches(4.9), Inches(0.4), Inches(0.4), theme.accent_soft)
    _rect(slide, Inches(5.0), Inches(4.9), Inches(0.06), Inches(0.4), theme.accent)
    _text(slide, "AI 自动生成报告，建议结合原始数据复核关键业务决策。",
          Inches(5.56), Inches(4.94), Inches(6.6), Inches(0.32),
          font_size=10, color=theme.muted)


def _cover_header(slide, theme, module_name, conversation_title, file_name, author, n_questions):
    """insight — 顶部宽色带 + 居中标题"""
    hdr_h = _cfg(theme, "cover_header_height", 1.6)
    _rect(slide, 0, 0, SLIDE_W, hdr_h, theme.accent)
    _rect(slide, 0, hdr_h, SLIDE_W, Inches(0.06), theme.accent_dark)

    _circle(slide, Inches(11.0), Inches(-0.4), Inches(2.0), theme.accent_soft, opacity=0.3)
    _circle(slide, Inches(-0.5), Inches(5.5), Inches(2.2), theme.accent_soft)

    _round_rect(slide, Inches(5.4), Inches(0.28), Inches(2.5), Inches(0.34), C_WHITE)
    _text(slide, theme.name.upper(),
          Inches(5.4), Inches(0.28), Inches(2.5), Inches(0.34),
          font_size=9, bold=True, color=theme.accent, align=PP_ALIGN.CENTER)

    _text(slide, "数据洞察报告",
          Inches(1.0), Inches(0.7), Inches(11.3), Inches(0.7),
          font_size=36, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)

    _text(slide, conversation_title or "XLSX 表格智能问答",
          Inches(2.0), Inches(2.1), Inches(9.3), Inches(0.42),
          font_size=16, color=theme.text, align=PP_ALIGN.CENTER)

    card_y = Inches(2.9)
    card_w = Inches(3.2)
    for i, (lbl, val) in enumerate([
        ("问题数", str(n_questions)),
        ("模块", _shrink(module_name or "—", 16)),
        ("数据源", _shrink(file_name or "—", 16)),
    ]):
        left = Inches(1.6 + i * 3.5)
        _rect(slide, left, card_y, card_w, Inches(1.3), theme.panel)
        _rect(slide, left, card_y, card_w, Inches(0.06), theme.palette[i % len(theme.palette)])
        _text(slide, lbl, Emu(left + Inches(0.2)), Emu(card_y + Inches(0.2)), Emu(card_w - Inches(0.4)), Inches(0.2),
              font_size=9, bold=True, color=theme.muted)
        _text(slide, val, Emu(left + Inches(0.2)), Emu(card_y + Inches(0.5)), Emu(card_w - Inches(0.4)), Inches(0.5),
              font_size=22, bold=True, color=theme.accent)

    _rect(slide, Inches(1.0), Inches(4.8), Inches(11.3), Inches(0.02), theme.accent_soft)

    _cover_meta_block(slide, theme, Inches(1.6), Inches(5.1), author, n_questions, module_name)

    _text(slide, "AI 自动生成报告，建议结合原始数据复核关键业务决策。",
          Inches(2.0), Inches(6.4), Inches(9.3), Inches(0.32),
          font_size=10, color=theme.muted, align=PP_ALIGN.CENTER)


def _cover_minimal(slide, theme, module_name, conversation_title, file_name, author, n_questions):
    """clean — 细边框 + 大留白"""
    m = _cfg(theme, "margin", 0.6)
    _rect(slide, m, m, Emu(SLIDE_W - m * 2), Emu(SLIDE_H - Inches(1.2)), theme.panel)
    _rect(slide, m, m, Emu(SLIDE_W - m * 2), Inches(0.03), theme.accent)

    _2m = Emu(m * 2)
    _circle(slide, Inches(11.2), Inches(5.4), Inches(1.6), theme.accent_soft)

    _text(slide, theme.name.upper(),
          _2m, _2m, Inches(2.0), Inches(0.28),
          font_size=9, bold=True, color=theme.accent)

    _text(slide, "数据洞察报告",
          _2m, Inches(2.0), Inches(10.5), Inches(0.9),
          font_size=40, bold=True, color=theme.text)
    _text(slide, conversation_title or "XLSX 表格智能问答",
          Emu(_2m + Inches(0.04)), Inches(3.0), Inches(10.0), Inches(0.42),
          font_size=14, color=theme.muted)

    _rect(slide, _2m, Inches(3.7), Inches(1.6), Inches(0.02), theme.accent)

    for i, (lbl, val) in enumerate([
        ("问题数", str(n_questions)),
        ("模块", _shrink(module_name or "—", 20)),
        ("数据源", _shrink(file_name or "—", 20)),
    ]):
        x = Emu(_2m + Inches(i * 3.6))
        _text(slide, lbl, x, Inches(4.1), Inches(1.0), Inches(0.2),
              font_size=9, bold=True, color=theme.muted)
        _text(slide, val, x, Inches(4.38), Inches(3.0), Inches(0.32),
              font_size=14, color=theme.text)

    _rect(slide, m, Emu(SLIDE_H - Inches(1.1)), Emu(SLIDE_W - m * 2), Inches(0.03), theme.accent)

    _text(slide, f"{module_name or '数据洞察'}  ·  {datetime.now().strftime('%Y-%m-%d')}",
          Inches(1.2), Inches(5.6), Inches(10.0), Inches(0.28),
          font_size=9, color=theme.muted)
    _text(slide, f"作者：{author or '—'}  ·  共 {n_questions} 个分析问题",
          Inches(1.2), Inches(5.9), Inches(10.0), Inches(0.28),
          font_size=9, color=theme.muted)


def _cover_dark_full(slide, theme, module_name, conversation_title, file_name, author, n_questions):
    """midnight — 全深色 + 金色大标题"""
    _rect(slide, 0, 0, SLIDE_W, SLIDE_H, theme.bg)

    _circle(slide, Inches(10.0), Inches(-1.0), Inches(3.5), theme.accent_soft, opacity=0.3)
    _circle(slide, Inches(-1.0), Inches(5.0), Inches(2.8), theme.accent_soft, opacity=0.2)
    _circle(slide, Inches(11.5), Inches(5.5), Inches(1.2), theme.accent_soft, opacity=0.25)

    _rect(slide, 0, 0, SLIDE_W, Inches(0.06), theme.accent)
    _rect(slide, 0, Inches(7.44), SLIDE_W, Inches(0.06), theme.accent)

    _round_rect(slide, Inches(5.2), Inches(0.6), Inches(2.9), Inches(0.36), theme.accent)
    _text(slide, theme.name.upper(),
          Inches(5.2), Inches(0.6), Inches(2.9), Inches(0.36),
          font_size=10, bold=True, color=theme.bg, align=PP_ALIGN.CENTER)

    _text(slide, "数据洞察报告",
          Inches(1.0), Inches(1.5), Inches(11.3), Inches(1.0),
          font_size=44, bold=True, color=theme.accent, align=PP_ALIGN.CENTER)
    _text(slide, conversation_title or "XLSX 表格智能问答",
          Inches(2.0), Inches(2.6), Inches(9.3), Inches(0.42),
          font_size=15, color=theme.muted, align=PP_ALIGN.CENTER)

    _rect(slide, Inches(4.0), Inches(3.3), Inches(5.3), Inches(0.02), theme.accent_soft)

    for i, (lbl, val) in enumerate([
        ("问题数", str(n_questions)),
        ("模块", _shrink(module_name or "—", 18)),
        ("数据源", _shrink(file_name or "—", 18)),
    ]):
        x = Inches(2.0 + i * 3.2)
        _rect(slide, x, Inches(3.7), Inches(2.8), Inches(1.1), theme.panel)
        _rect(slide, x, Inches(3.7), Inches(2.8), Inches(0.05), theme.accent)
        _text(slide, lbl, Emu(x + Inches(0.16)), Inches(3.86), Inches(2.5), Inches(0.2),
              font_size=9, bold=True, color=theme.muted)
        _text(slide, val, Emu(x + Inches(0.16)), Inches(4.14), Inches(2.5), Inches(0.42),
              font_size=20, bold=True, color=theme.accent)

    _text(slide, "AI 自动生成报告，建议结合原始数据复核关键业务决策。",
          Inches(2.0), Inches(5.4), Inches(9.3), Inches(0.32),
          font_size=10, color=theme.muted, align=PP_ALIGN.CENTER)

    _text(slide, f"共 {n_questions} 个问题  ·  {module_name or '数据洞察'}  ·  {datetime.now().strftime('%Y-%m-%d')}",
          Inches(0.5), Inches(6.5), Inches(12.0), Inches(0.36),
          font_size=9, color=theme.muted, align=PP_ALIGN.CENTER)


def _cover_diagonal(slide, theme, module_name, conversation_title, file_name, author, n_questions):
    """coral — 斜切色块 + 暖色"""
    pnl_w = _cfg(theme, "panel_width", 5.5)
    # 斜切背景色块（用三角形近似：两个矩形拼接）
    _rect(slide, 0, 0, pnl_w, SLIDE_H, theme.accent_soft)
    _rect(slide, Emu(pnl_w - Inches(0.5)), 0, Inches(0.06), SLIDE_H, theme.accent, opacity=0.3)

    _circle(slide, Inches(3.8), Inches(-0.5), Inches(2.0), theme.accent, opacity=0.12)
    _circle(slide, Inches(-0.5), Inches(5.5), Inches(2.0), theme.accent, opacity=0.1)
    _circle(slide, Inches(11.0), Inches(5.8), Inches(1.5), theme.accent_soft)

    _rect(slide, Inches(0.7), Inches(0.7), Inches(4.2), Inches(5.8), theme.panel)
    _rect(slide, Inches(0.7), Inches(0.7), Inches(4.2), Inches(0.06), theme.accent)

    _round_rect(slide, Inches(1.0), Inches(1.1), Inches(1.8), Inches(0.34), theme.accent)
    _text(slide, theme.name.upper(),
          Inches(1.0), Inches(1.1), Inches(1.8), Inches(0.34),
          font_size=9, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)

    _text(slide, f"{n_questions}",
          Inches(1.0), Inches(1.9), Inches(3.5), Inches(0.9),
          font_size=52, bold=True, color=theme.accent)
    _text(slide, "个分析问题",
          Inches(1.06), Inches(2.82), Inches(3.0), Inches(0.3),
          font_size=13, color=theme.muted)

    for i, (lbl, val) in enumerate([
        ("模块", module_name or "—"),
        ("数据源", file_name or "—"),
    ]):
        y = Inches(3.5 + i * 0.66)
        _text(slide, lbl, Inches(1.06), y, Inches(0.86), Inches(0.22),
              font_size=9, bold=True, color=theme.accent)
        _text(slide, _shrink(str(val), 24),
              Inches(1.06), Emu(y + Inches(0.24)), Inches(3.2), Inches(0.28),
              font_size=11, color=theme.text)

    _text(slide, "数据洞察报告",
          Inches(6.0), Inches(1.8), Inches(6.5), Inches(0.9),
          font_size=36, bold=True, color=theme.accent_dark)
    _text(slide, conversation_title or "XLSX 表格智能问答",
          Inches(6.04), Inches(2.8), Inches(6.3), Inches(0.42),
          font_size=14, color=theme.muted)

    _rect(slide, Inches(6.0), Inches(3.5), Inches(6.0), Inches(0.02), theme.accent_soft)
    _cover_meta_block(slide, theme, Inches(6.04), Inches(3.8), author, n_questions, module_name)

    _rect(slide, Inches(6.0), Inches(5.2), Inches(0.4), Inches(0.4), theme.accent_soft)
    _rect(slide, Inches(6.0), Inches(5.2), Inches(0.06), Inches(0.4), theme.accent)
    _text(slide, "AI 自动生成报告，建议结合原始数据复核关键业务决策。",
          Inches(6.56), Inches(5.24), Inches(5.5), Inches(0.32),
          font_size=10, color=theme.muted)


def _cover_corner(slide, theme, module_name, conversation_title, file_name, author, n_questions):
    """teal — 左下角大色块"""
    cb_top = _cfg(theme, "corner_block_top", 4.0)
    cb_w = _cfg(theme, "corner_block_width", 5.5)
    cb_h = _cfg(theme, "corner_block_height", 3.5)
    _rect(slide, 0, cb_top, cb_w, cb_h, theme.accent)
    _circle(slide, Inches(-0.8), Inches(4.5), Inches(2.5), theme.accent_dark, opacity=0.3)

    _circle(slide, Inches(10.5), Inches(-0.5), Inches(2.0), theme.accent_soft)
    _circle(slide, Inches(11.5), Inches(0.5), Inches(0.8), theme.accent, opacity=0.15)

    _rect(slide, Inches(0.7), Inches(0.7), Inches(11.9), Inches(0.06), theme.accent)

    _round_rect(slide, Inches(1.0), Inches(1.2), Inches(1.8), Inches(0.34), theme.accent)
    _text(slide, theme.name.upper(),
          Inches(1.0), Inches(1.2), Inches(1.8), Inches(0.34),
          font_size=9, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)

    _text(slide, "数据洞察报告",
          Inches(1.0), Inches(2.0), Inches(11.0), Inches(0.9),
          font_size=38, bold=True, color=theme.accent_dark)
    _text(slide, conversation_title or "XLSX 表格智能问答",
          Inches(1.04), Inches(3.0), Inches(10.5), Inches(0.42),
          font_size=15, color=theme.muted)

    for i, (lbl, val) in enumerate([
        ("问题数", str(n_questions)),
        ("模块", _shrink(module_name or "—", 18)),
        ("数据源", _shrink(file_name or "—", 18)),
    ]):
        x = Inches(1.0 + i * 3.8)
        _rect(slide, x, Inches(3.7), Inches(3.3), Inches(0.9), theme.panel)
        _rect(slide, x, Inches(3.7), Inches(3.3), Inches(0.04), theme.palette[i % len(theme.palette)])
        _text(slide, lbl, Emu(x + Inches(0.14)), Inches(3.84), Inches(3.0), Inches(0.2),
              font_size=9, bold=True, color=theme.muted)
        _text(slide, val, Emu(x + Inches(0.14)), Inches(4.08), Inches(3.0), Inches(0.38),
              font_size=18, bold=True, color=theme.accent)

    _text(slide, f"共 {n_questions} 个问题",
          Inches(0.8), Inches(5.3), Inches(4.0), Inches(0.36),
          font_size=14, bold=True, color=C_WHITE)
    _text(slide, f"{module_name or '数据洞察'}  ·  {datetime.now().strftime('%Y-%m-%d')}",
          Inches(0.8), Inches(5.7), Inches(4.0), Inches(0.28),
          font_size=10, color=theme.accent_soft)
    _text(slide, f"作者：{author or '—'}",
          Inches(0.8), Inches(6.1), Inches(4.0), Inches(0.28),
          font_size=10, color=theme.accent_soft)

    _text(slide, "AI 自动生成报告，建议结合原始数据复核关键业务决策。",
          Inches(6.0), Inches(6.5), Inches(6.5), Inches(0.32),
          font_size=10, color=theme.muted, align=PP_ALIGN.RIGHT)


def _cover_right_panel(slide, theme, module_name, conversation_title, file_name, author, n_questions):
    """berry — 右侧宽色块 + 左侧标题"""
    pnl_left = _cfg(theme, "panel_left", 7.5)
    pnl_w = _cfg(theme, "panel_width", 5.833)
    _rect(slide, pnl_left, 0, pnl_w, SLIDE_H, theme.accent)

    _circle(slide, Emu(pnl_left - Inches(0.7)), Inches(-0.5), Inches(1.8), theme.accent, opacity=0.15)
    _circle(slide, Inches(11.0), Inches(5.5), Inches(2.0), theme.accent_dark, opacity=0.25)
    _circle(slide, Inches(-0.4), Inches(6.0), Inches(1.5), theme.accent_soft)

    _rect(slide, pnl_left, 0, Inches(0.06), SLIDE_H, theme.accent_dark, opacity=0.3)

    _text(slide, theme.name.upper(),
          Inches(1.0), Inches(1.2), Inches(2.0), Inches(0.28),
          font_size=9, bold=True, color=theme.accent)

    _text(slide, "数据洞察报告",
          Inches(1.0), Inches(2.0), Inches(6.0), Inches(0.9),
          font_size=36, bold=True, color=theme.accent_dark)
    _text(slide, conversation_title or "XLSX 表格智能问答",
          Inches(1.04), Inches(3.0), Inches(5.8), Inches(0.42),
          font_size=14, color=theme.muted)

    _rect(slide, Inches(1.0), Inches(3.7), Inches(5.5), Inches(0.02), theme.accent_soft)

    for i, (lbl, val) in enumerate([
        ("问题数", str(n_questions)),
        ("模块", _shrink(module_name or "—", 18)),
        ("数据源", _shrink(file_name or "—", 18)),
    ]):
        y = Inches(4.0 + i * 0.56)
        _text(slide, lbl, Inches(1.0), y, Inches(0.86), Inches(0.2),
              font_size=9, bold=True, color=theme.accent)
        _text(slide, val, Inches(1.96), Emu(y - Inches(0.02)), Inches(5.0), Inches(0.28),
              font_size=12, color=theme.text)

    _text(slide, f"{n_questions}",
          Inches(8.2), Inches(1.5), Inches(4.0), Inches(1.2),
          font_size=64, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    _text(slide, "个分析问题",
          Inches(8.5), Inches(2.8), Inches(3.5), Inches(0.3),
          font_size=14, color=theme.accent_soft, align=PP_ALIGN.CENTER)

    _rect(slide, Inches(8.0), Inches(3.5), Inches(4.5), Inches(0.02), theme.accent_dark, opacity=0.3)

    _text(slide, f"作者：{author or '—'}",
          Inches(8.2), Inches(4.0), Inches(4.0), Inches(0.28),
          font_size=11, color=theme.accent_soft)
    _text(slide, f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
          Inches(8.2), Inches(4.4), Inches(4.0), Inches(0.28),
          font_size=11, color=theme.accent_soft)

    _text(slide, "AI 自动生成报告，建议结合原始数据复核关键业务决策。",
          Inches(1.0), Inches(5.8), Inches(5.8), Inches(0.32),
          font_size=10, color=theme.muted)

    _text(slide, f"共 {n_questions} 个问题  ·  {module_name or '数据洞察'}  ·  {datetime.now().strftime('%Y-%m-%d')}",
          Inches(0.5), Inches(6.94), Inches(12.0), Inches(0.36),
          font_size=9, color=theme.muted, align=PP_ALIGN.CENTER)


def _cover_dark_header(slide, theme, module_name, conversation_title, file_name, author, n_questions):
    """charcoal — 深色头部 + 琥珀高亮"""
    hdr_h = _cfg(theme, "cover_header_height", 2.4)
    _rect(slide, 0, 0, SLIDE_W, hdr_h, theme.panel)
    _rect(slide, 0, hdr_h, SLIDE_W, Inches(0.06), theme.accent)

    _circle(slide, Inches(10.5), Inches(-0.3), Inches(2.5), theme.accent_soft, opacity=0.3)
    _circle(slide, Inches(-0.5), Inches(1.2), Inches(1.2), theme.accent_soft, opacity=0.2)

    _round_rect(slide, Inches(5.0), Inches(0.3), Inches(3.3), Inches(0.36), theme.accent)
    _text(slide, theme.name.upper(),
          Inches(5.0), Inches(0.3), Inches(3.3), Inches(0.36),
          font_size=10, bold=True, color=theme.bg, align=PP_ALIGN.CENTER)

    _text(slide, "数据洞察报告",
          Inches(1.0), Inches(0.85), Inches(11.3), Inches(0.8),
          font_size=38, bold=True, color=theme.accent, align=PP_ALIGN.CENTER)
    _text(slide, conversation_title or "XLSX 表格智能问答",
          Inches(2.0), Inches(1.7), Inches(9.3), Inches(0.42),
          font_size=14, color=theme.muted, align=PP_ALIGN.CENTER)

    for i, (lbl, val) in enumerate([
        ("问题数", str(n_questions)),
        ("模块", _shrink(module_name or "—", 20)),
        ("数据源", _shrink(file_name or "—", 20)),
    ]):
        x = Inches(1.2 + i * 3.8)
        _rect(slide, x, Inches(3.0), Inches(3.3), Inches(1.2), theme.panel)
        _rect(slide, x, Inches(3.0), Inches(3.3), Inches(0.05), theme.accent)
        _text(slide, lbl, Emu(x + Inches(0.16)), Inches(3.18), Inches(3.0), Inches(0.2),
              font_size=9, bold=True, color=theme.muted)
        _text(slide, val, Emu(x + Inches(0.16)), Inches(3.46), Inches(3.0), Inches(0.48),
              font_size=22, bold=True, color=theme.accent)

    _rect(slide, Inches(1.0), Inches(4.6), Inches(11.3), Inches(0.02), theme.accent_soft)

    _cover_meta_block(slide, theme, Inches(1.6), Inches(4.9), author, n_questions, module_name)

    _rect(slide, Inches(1.0), Inches(6.3), Inches(0.4), Inches(0.4), theme.accent_soft)
    _rect(slide, Inches(1.0), Inches(6.3), Inches(0.06), Inches(0.4), theme.accent)
    _text(slide, "AI 自动生成报告，建议结合原始数据复核关键业务决策。",
          Inches(1.56), Inches(6.34), Inches(10.0), Inches(0.32),
          font_size=10, color=theme.muted)


# ─────────────────────────────────────────────────────────────────────────────
# 摘要页（左文 + 右原生图表）
# ─────────────────────────────────────────────────────────────────────────────

def _add_question_slide(prs, *, idx, total, user_msg, ast_msg, module_name: str, theme: PptTheme):
    slide = _blank(prs)
    _rect(slide, 0, 0, SLIDE_W, SLIDE_H, theme.bg)

    question = (user_msg.content or "").strip() if user_msg else "（无问题）"
    ex = (ast_msg.extras or {}) if ast_msg else {}
    charts = _parse_charts(ex)
    subqs = [s for s in (ex.get("subquestions") or []) if s.get("rows")]
    meta = [
        ("洞察页", f"{len(_get_insight_sections(ex, charts, ex.get('summary_markdown') or ''))} 页"),
        ("图表", f"{len(charts)} 个"),
        ("数据表", f"{len(subqs)} 个"),
    ]

    layout = theme.layout
    if layout == "header":
        _qslide_header(slide, theme, idx, total, question, meta, module_name)
    elif layout == "minimal":
        _qslide_minimal(slide, theme, idx, total, question, meta, module_name)
    elif layout == "dark_full":
        _qslide_dark_full(slide, theme, idx, total, question, meta, module_name)
    elif layout == "diagonal":
        _qslide_diagonal(slide, theme, idx, total, question, meta, module_name)
    elif layout == "corner":
        _qslide_corner(slide, theme, idx, total, question, meta, module_name)
    elif layout == "right_panel":
        _qslide_right_panel(slide, theme, idx, total, question, meta, module_name)
    elif layout == "dark_header":
        _qslide_dark_header(slide, theme, idx, total, question, meta, module_name)
    else:
        _qslide_sidebar(slide, theme, idx, total, question, meta, module_name)


def _qslide_meta_cards(slide, theme, meta, left, top, card_w, card_gap):
    """Shared metric cards for question slides."""
    for i, (label, value) in enumerate(meta):
        x = Emu(left + int(i * (card_w + card_gap)))
        _rect(slide, x, top, card_w, Inches(1.0), theme.panel)
        _rect(slide, x, top, card_w, Inches(0.05), theme.palette[i % len(theme.palette)])
        _text(slide, label, Emu(x + Inches(0.16)), Emu(top + Inches(0.18)), card_w - Inches(0.3), Inches(0.2),
              font_size=9, bold=True, color=theme.muted)
        _text(slide, value, Emu(x + Inches(0.16)), Emu(top + Inches(0.44)), card_w - Inches(0.3), Inches(0.38),
              font_size=20, bold=True, color=theme.accent)


def _qslide_footer(slide, theme, top):
    """Shared footer note for question slides."""
    _rect(slide, Inches(0.7), top, Inches(11.6), Inches(1.4), theme.panel)
    _rect(slide, Inches(0.7), top, Inches(0.06), Inches(1.4), theme.accent)
    _text(slide, "后续页面说明",
          Inches(1.0), Emu(top + Inches(0.14)), Inches(3.0), Inches(0.28),
          font_size=10, bold=True, color=theme.accent)
    _text(slide, "后续页面将按照洞察模块展开：上方展示图表或指标卡，下方给出可直接阅读的结论拆解与关键发现。",
          Inches(1.0), Emu(top + Inches(0.48)), Inches(11.0), Inches(0.6),
          font_size=11, color=theme.muted)


def _qslide_sidebar(slide, theme, idx, total, question, meta, module_name):
    """executive — 左侧边栏 + 圆形装饰"""
    _circle(slide, Inches(11.2), Inches(5.2), Inches(2.0), theme.accent_soft)
    _circle(slide, Inches(11.8), Inches(5.8), Inches(0.8), theme.accent, opacity=0.12)

    bar_w = _cfg(theme, "accent_bar_width", 0.25)
    _rect(slide, 0, 0, bar_w, SLIDE_H, theme.accent)
    _rect(slide, bar_w, Inches(0.6), Inches(0.04), Inches(6.2), theme.accent_soft)

    _round_rect(slide, Inches(0.7), Inches(0.5), Inches(1.6), Inches(0.34), theme.accent)
    _text(slide, f"问题 {idx}/{total}",
          Inches(0.7), Inches(0.5), Inches(1.6), Inches(0.34),
          font_size=10, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    _text(slide, module_name or "数据洞察",
          Inches(9.6), Inches(0.56), Inches(3.2), Inches(0.28),
          font_size=9, color=theme.muted, align=PP_ALIGN.RIGHT)

    _text(slide, "Q",
          Inches(0.7), Inches(1.3), Inches(0.6), Inches(0.7),
          font_size=44, bold=True, color=theme.accent)
    _text(slide, _shrink(question, 200),
          Inches(1.4), Inches(1.38), Inches(11.0), Inches(1.6),
          font_size=24, bold=True, color=theme.text, auto_fit=True)

    _rect(slide, Inches(0.7), Inches(3.2), Inches(11.6), Inches(0.02), theme.accent_soft)
    _qslide_meta_cards(slide, theme, meta, Inches(0.7), Inches(3.6), Inches(2.32), Inches(0.24))
    _qslide_footer(slide, theme, Inches(5.2))


def _qslide_header(slide, theme, idx, total, question, meta, module_name):
    """insight — 顶部色带 + 卡片网格"""
    hdr_h = _cfg(theme, "qslide_header_height", 1.2)
    _rect(slide, 0, 0, SLIDE_W, hdr_h, theme.accent)
    _rect(slide, 0, hdr_h, SLIDE_W, Inches(0.04), theme.accent_dark)

    _round_rect(slide, Inches(0.7), Inches(0.3), Inches(1.6), Inches(0.34), C_WHITE)
    _text(slide, f"问题 {idx}/{total}",
          Inches(0.7), Inches(0.3), Inches(1.6), Inches(0.34),
          font_size=10, bold=True, color=theme.accent, align=PP_ALIGN.CENTER)
    _text(slide, module_name or "数据洞察",
          Inches(10.0), Inches(0.36), Inches(2.8), Inches(0.28),
          font_size=9, color=theme.accent_soft, align=PP_ALIGN.RIGHT)

    _text(slide, _shrink(question, 200),
          Inches(0.7), Inches(1.6), Inches(11.6), Inches(1.4),
          font_size=26, bold=True, color=theme.text, auto_fit=True)

    _rect(slide, Inches(0.7), Inches(3.2), Inches(11.6), Inches(0.02), theme.accent_soft)
    _qslide_meta_cards(slide, theme, meta, Inches(0.7), Inches(3.6), Inches(2.32), Inches(0.24))
    _qslide_footer(slide, theme, Inches(5.2))


def _qslide_minimal(slide, theme, idx, total, question, meta, module_name):
    """clean — 极细线条 + 纯净背景"""
    _rect(slide, Inches(0.6), Inches(0.5), Inches(12.1), Inches(0.03), theme.accent)

    _text(slide, f"问题 {idx}/{total}",
          Inches(0.8), Inches(0.8), Inches(1.6), Inches(0.28),
          font_size=10, bold=True, color=theme.accent)
    _text(slide, module_name or "数据洞察",
          Inches(10.0), Inches(0.8), Inches(2.8), Inches(0.28),
          font_size=9, color=theme.muted, align=PP_ALIGN.RIGHT)

    _text(slide, _shrink(question, 200),
          Inches(0.8), Inches(1.5), Inches(11.5), Inches(1.6),
          font_size=28, bold=True, color=theme.text, auto_fit=True)

    _rect(slide, Inches(0.8), Inches(3.3), Inches(2.0), Inches(0.02), theme.accent)

    card_w = Inches(3.4)
    for i, (label, value) in enumerate(meta):
        x = Inches(0.8 + i * 3.7)
        _text(slide, label, x, Inches(3.7), Inches(1.0), Inches(0.2),
              font_size=9, bold=True, color=theme.muted)
        _text(slide, value, x, Inches(3.98), card_w, Inches(0.38),
              font_size=22, bold=True, color=theme.accent)
        if i < len(meta) - 1:
            _rect(slide, Emu(x + card_w + Inches(0.1)), Inches(3.7), Inches(0.02), Inches(0.7), theme.accent_soft)

    _qslide_footer(slide, theme, Inches(5.2))

    _rect(slide, Inches(0.6), Inches(7.0), Inches(12.1), Inches(0.03), theme.accent)


def _qslide_dark_full(slide, theme, idx, total, question, meta, module_name):
    """midnight — 深色面板 + 发光强调"""
    _circle(slide, Inches(10.0), Inches(-0.5), Inches(2.5), theme.accent_soft, opacity=0.25)
    _circle(slide, Inches(-0.5), Inches(5.5), Inches(1.8), theme.accent_soft, opacity=0.2)

    _rect(slide, 0, 0, SLIDE_W, Inches(0.06), theme.accent)

    _round_rect(slide, Inches(5.5), Inches(0.4), Inches(2.3), Inches(0.36), theme.accent)
    _text(slide, f"问题 {idx}/{total}",
          Inches(5.5), Inches(0.4), Inches(2.3), Inches(0.36),
          font_size=10, bold=True, color=theme.bg, align=PP_ALIGN.CENTER)
    _text(slide, module_name or "数据洞察",
          Inches(0.7), Inches(0.46), Inches(3.2), Inches(0.28),
          font_size=9, color=theme.muted)

    _text(slide, "Q",
          Inches(0.7), Inches(1.2), Inches(0.7), Inches(0.8),
          font_size=48, bold=True, color=theme.accent)
    _text(slide, _shrink(question, 200),
          Inches(1.5), Inches(1.28), Inches(11.0), Inches(1.6),
          font_size=24, bold=True, color=theme.text, auto_fit=True)

    _rect(slide, Inches(0.7), Inches(3.1), Inches(11.6), Inches(0.02), theme.accent_soft)

    card_w = Inches(3.3)
    for i, (label, value) in enumerate(meta):
        x = Inches(1.0 + i * 3.6)
        _rect(slide, x, Inches(3.5), card_w, Inches(1.1), theme.panel)
        _rect(slide, x, Inches(3.5), card_w, Inches(0.05), theme.accent)
        _text(slide, label, Emu(x + Inches(0.16)), Inches(3.7), card_w - Inches(0.3), Inches(0.2),
              font_size=9, bold=True, color=theme.muted)
        _text(slide, value, Emu(x + Inches(0.16)), Inches(3.98), card_w - Inches(0.3), Inches(0.38),
              font_size=22, bold=True, color=theme.accent)

    _rect(slide, Inches(0.7), Inches(5.2), Inches(11.6), Inches(1.4), theme.panel)
    _rect(slide, Inches(0.7), Inches(5.2), Inches(0.06), Inches(1.4), theme.accent)
    _text(slide, "后续页面说明",
          Inches(1.0), Inches(5.34), Inches(3.0), Inches(0.28),
          font_size=10, bold=True, color=theme.accent)
    _text(slide, "后续页面将按照洞察模块展开：上方展示图表或指标卡，下方给出可直接阅读的结论拆解与关键发现。",
          Inches(1.0), Inches(5.68), Inches(11.0), Inches(0.6),
          font_size=11, color=theme.muted)


def _qslide_diagonal(slide, theme, idx, total, question, meta, module_name):
    """coral — 斜线装饰 + 暖色卡片"""
    bar_w = _cfg(theme, "accent_bar_width", 0.4)
    _rect(slide, 0, 0, bar_w, SLIDE_H, theme.accent_soft)
    _rect(slide, bar_w, 0, Inches(0.06), SLIDE_H, theme.accent, opacity=0.2)

    _circle(slide, Inches(11.0), Inches(5.5), Inches(1.8), theme.accent_soft)

    _round_rect(slide, Inches(0.8), Inches(0.5), Inches(1.6), Inches(0.34), theme.accent)
    _text(slide, f"问题 {idx}/{total}",
          Inches(0.8), Inches(0.5), Inches(1.6), Inches(0.34),
          font_size=10, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    _text(slide, module_name or "数据洞察",
          Inches(9.6), Inches(0.56), Inches(3.2), Inches(0.28),
          font_size=9, color=theme.muted, align=PP_ALIGN.RIGHT)

    _text(slide, "Q",
          Inches(0.8), Inches(1.3), Inches(0.6), Inches(0.7),
          font_size=44, bold=True, color=theme.accent)
    _text(slide, _shrink(question, 200),
          Inches(1.5), Inches(1.38), Inches(11.0), Inches(1.6),
          font_size=24, bold=True, color=theme.text, auto_fit=True)

    _rect(slide, Inches(0.8), Inches(3.2), Inches(11.6), Inches(0.02), theme.accent_soft)
    _qslide_meta_cards(slide, theme, meta, Inches(0.8), Inches(3.6), Inches(2.32), Inches(0.24))
    _qslide_footer(slide, theme, Inches(5.2))


def _qslide_corner(slide, theme, idx, total, question, meta, module_name):
    """teal — 角落装饰 + 网格布局"""
    cb_top = _cfg(theme, "corner_qslide_block_top", 6.2)
    cb_h = _cfg(theme, "corner_qslide_block_height", 1.3)
    _rect(slide, 0, cb_top, Inches(3.5), cb_h, theme.accent)
    _circle(slide, Inches(-0.4), Inches(6.0), Inches(1.5), theme.accent_dark, opacity=0.3)

    _circle(slide, Inches(11.5), Inches(-0.3), Inches(1.5), theme.accent_soft)

    _rect(slide, Inches(0.5), Inches(0.4), Inches(12.3), Inches(0.04), theme.accent)

    _round_rect(slide, Inches(0.7), Inches(0.7), Inches(1.6), Inches(0.34), theme.accent)
    _text(slide, f"问题 {idx}/{total}",
          Inches(0.7), Inches(0.7), Inches(1.6), Inches(0.34),
          font_size=10, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    _text(slide, module_name or "数据洞察",
          Inches(9.6), Inches(0.76), Inches(3.2), Inches(0.28),
          font_size=9, color=theme.muted, align=PP_ALIGN.RIGHT)

    _text(slide, _shrink(question, 200),
          Inches(0.7), Inches(1.4), Inches(11.6), Inches(1.6),
          font_size=26, bold=True, color=theme.text, auto_fit=True)

    _rect(slide, Inches(0.7), Inches(3.2), Inches(11.6), Inches(0.02), theme.accent_soft)
    _qslide_meta_cards(slide, theme, meta, Inches(0.7), Inches(3.6), Inches(2.32), Inches(0.24))

    _rect(slide, Inches(0.7), Inches(5.2), Inches(11.6), Inches(1.4), theme.panel)
    _rect(slide, Inches(0.7), Inches(5.2), Inches(0.06), Inches(1.4), theme.accent)
    _text(slide, "后续页面说明",
          Inches(1.0), Inches(5.34), Inches(3.0), Inches(0.28),
          font_size=10, bold=True, color=theme.accent)
    _text(slide, "后续页面将按照洞察模块展开：上方展示图表或指标卡，下方给出可直接阅读的结论拆解与关键发现。",
          Inches(1.0), Inches(5.68), Inches(11.0), Inches(0.6),
          font_size=11, color=theme.muted)


def _qslide_right_panel(slide, theme, idx, total, question, meta, module_name):
    """berry — 右侧面板 + 左侧内容"""
    pnl_left = _cfg(theme, "qslide_panel_left", 10.0)
    pnl_w = _cfg(theme, "qslide_panel_width", 3.333)
    _rect(slide, pnl_left, 0, pnl_w, SLIDE_H, theme.accent_soft)
    _rect(slide, pnl_left, 0, Inches(0.06), SLIDE_H, theme.accent, opacity=0.2)

    _circle(slide, Inches(11.5), Inches(5.0), Inches(2.0), theme.accent, opacity=0.12)

    _round_rect(slide, Inches(0.7), Inches(0.5), Inches(1.6), Inches(0.34), theme.accent)
    _text(slide, f"问题 {idx}/{total}",
          Inches(0.7), Inches(0.5), Inches(1.6), Inches(0.34),
          font_size=10, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    _text(slide, module_name or "数据洞察",
          Inches(7.0), Inches(0.56), Inches(2.8), Inches(0.28),
          font_size=9, color=theme.muted, align=PP_ALIGN.RIGHT)

    _text(slide, "Q",
          Inches(0.7), Inches(1.3), Inches(0.6), Inches(0.7),
          font_size=44, bold=True, color=theme.accent)
    _text(slide, _shrink(question, 200),
          Inches(1.4), Inches(1.38), Inches(8.0), Inches(1.6),
          font_size=24, bold=True, color=theme.text, auto_fit=True)

    _rect(slide, Inches(0.7), Inches(3.2), Inches(8.8), Inches(0.02), theme.accent_soft)

    card_w = Inches(2.32)
    for i, (label, value) in enumerate(meta):
        x = Inches(0.7 + i * 2.56)
        _rect(slide, x, Inches(3.6), card_w, Inches(1.0), theme.panel)
        _rect(slide, x, Inches(3.6), card_w, Inches(0.05), theme.palette[i % len(theme.palette)])
        _text(slide, label, Emu(x + Inches(0.16)), Inches(3.78), card_w - Inches(0.3), Inches(0.2),
              font_size=9, bold=True, color=theme.muted)
        _text(slide, value, Emu(x + Inches(0.16)), Inches(4.04), card_w - Inches(0.3), Inches(0.38),
              font_size=20, bold=True, color=theme.accent)

    _text(slide, f"{idx}",
          Inches(10.6), Inches(2.0), Inches(2.0), Inches(1.2),
          font_size=52, bold=True, color=theme.accent, align=PP_ALIGN.CENTER)
    _text(slide, f"/ {total}",
          Inches(10.6), Inches(3.2), Inches(2.0), Inches(0.3),
          font_size=14, color=theme.muted, align=PP_ALIGN.CENTER)

    _rect(slide, Inches(0.7), Inches(5.2), Inches(8.8), Inches(1.4), theme.panel)
    _rect(slide, Inches(0.7), Inches(5.2), Inches(0.06), Inches(1.4), theme.accent)
    _text(slide, "后续页面说明",
          Inches(1.0), Inches(5.34), Inches(3.0), Inches(0.28),
          font_size=10, bold=True, color=theme.accent)
    _text(slide, "后续页面将按照洞察模块展开：上方展示图表或指标卡，下方给出可直接阅读的结论拆解与关键发现。",
          Inches(1.0), Inches(5.68), Inches(8.2), Inches(0.6),
          font_size=11, color=theme.muted)


def _qslide_dark_header(slide, theme, idx, total, question, meta, module_name):
    """charcoal — 深色标题栏 + 浅色内容"""
    hdr_h = _cfg(theme, "qslide_header_height", 1.4)
    _rect(slide, 0, 0, SLIDE_W, hdr_h, theme.panel)
    _rect(slide, 0, hdr_h, SLIDE_W, Inches(0.06), theme.accent)

    _circle(slide, Inches(11.0), Inches(-0.2), Inches(1.8), theme.accent_soft, opacity=0.3)

    _round_rect(slide, Inches(0.7), Inches(0.35), Inches(1.6), Inches(0.34), theme.accent)
    _text(slide, f"问题 {idx}/{total}",
          Inches(0.7), Inches(0.35), Inches(1.6), Inches(0.34),
          font_size=10, bold=True, color=theme.bg, align=PP_ALIGN.CENTER)
    _text(slide, module_name or "数据洞察",
          Inches(9.6), Inches(0.42), Inches(3.2), Inches(0.28),
          font_size=9, color=theme.muted, align=PP_ALIGN.RIGHT)

    _text(slide, _shrink(question, 200),
          Inches(0.7), Inches(0.78), Inches(11.6), Inches(0.5),
          font_size=20, bold=True, color=theme.accent)

    card_w = Inches(3.3)
    for i, (label, value) in enumerate(meta):
        x = Inches(0.7 + i * 3.6)
        _rect(slide, x, Inches(1.8), card_w, Inches(1.0), theme.panel)
        _rect(slide, x, Inches(1.8), card_w, Inches(0.05), theme.accent)
        _text(slide, label, Emu(x + Inches(0.16)), Inches(1.98), card_w - Inches(0.3), Inches(0.2),
              font_size=9, bold=True, color=theme.muted)
        _text(slide, value, Emu(x + Inches(0.16)), Inches(2.24), card_w - Inches(0.3), Inches(0.38),
              font_size=20, bold=True, color=theme.accent)

    _qslide_footer(slide, theme, Inches(3.4))


def _add_insight_slide(
    prs, *, q_idx, q_total, sec_idx, sec_total, section: dict,
    chart: Optional[dict], theme: PptTheme, include_chart: bool,
):
    slide = _blank(prs)
    _rect(slide, 0, 0, SLIDE_W, SLIDE_H, theme.bg)

    layout = theme.layout
    if layout == "header":
        _islide_header(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart)
    elif layout == "minimal":
        _islide_minimal(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart)
    elif layout == "dark_full":
        _islide_dark_full(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart)
    elif layout == "diagonal":
        _islide_diagonal(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart)
    elif layout == "corner":
        _islide_corner(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart)
    elif layout == "right_panel":
        _islide_right_panel(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart)
    elif layout == "dark_header":
        _islide_dark_header(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart)
    else:
        _islide_sidebar(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart)


def _islide_render_chart(slide, section, chart, include_chart, left, top, width, height, theme):
    """Shared chart rendering logic for insight slides."""
    visual_type = str(section.get("visual_type") or (chart or {}).get("chart_type") or "none").lower()
    if include_chart and chart:
        _rect(slide, left, Emu(top - Inches(0.08)), width, Emu(height + Inches(0.16)), theme.panel)
        _rect(slide, left, Emu(top - Inches(0.08)), width, Inches(0.04), theme.accent)
        if _should_render_cards(chart, visual_type):
            ctype = str((chart or {}).get("chart_type") or "").lower()
            if ctype == "table" and len((chart or {}).get("rows") or []) > 1:
                _draw_few_row_table_cards(
                    slide, chart, Emu(left + Inches(0.15)), top, Emu(width - Inches(0.3)), height, theme,
                )
            else:
                _draw_value_cards(slide, chart, Emu(left + Inches(0.15)), top, Emu(width - Inches(0.3)), height, theme)
        elif visual_type == "table" or chart.get("chart_type") == "table":
            _draw_mini_table(slide, chart, Emu(left + Inches(0.15)), top, Emu(width - Inches(0.3)), height, theme)
        elif chart.get("chart_type") in _XL_MAP:
            ok = _add_native_chart(
                slide, chart_spec=_chart_with_axis_note(chart, section),
                left=Emu(left + Inches(0.15)), top=top,
                width=Emu(width - Inches(0.3)), height=height,
                theme=theme,
            )
            if not ok:
                _draw_chart_info_card(slide, chart, [], Emu(left + Inches(0.15)), top, Emu(width - Inches(0.3)), height, theme)
        else:
            _draw_chart_info_card(slide, chart, [], Emu(left + Inches(0.15)), top, Emu(width - Inches(0.3)), height, theme)
    else:
        _rect(slide, left, Emu(top - Inches(0.08)), width, Emu(height + Inches(0.16)), theme.panel)
        _circle(slide, Emu(left + width // 2 - Inches(0.6)), Emu(top + Inches(0.6)), Inches(1.2), theme.accent_soft)
        _text(slide, "本页无可视化数据",
              Emu(left + Inches(0.15)), Emu(top + Inches(1.32)), Emu(width - Inches(0.3)), Inches(0.38),
              font_size=14, bold=True, color=theme.muted, align=PP_ALIGN.CENTER)


def _islide_render_conclusion(slide, section, theme, left, top, width):
    """Shared conclusion rendering for insight slides."""
    concl_h = Inches(1.72)
    _rect(slide, left, top, width, concl_h, theme.panel)
    _rect(slide, left, top, Inches(0.06), concl_h, theme.accent)
    _rect(slide, left, top, width, Inches(0.04), theme.accent_soft)

    _round_rect(slide, Emu(left + Inches(0.23)), Emu(top + Inches(0.12)), Inches(0.9), Inches(0.26), theme.accent)
    _text(slide, "结论",
          Emu(left + Inches(0.23)), Emu(top + Inches(0.12)), Inches(0.9), Inches(0.26),
          font_size=8, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    _text(slide, _shrink(str(section.get("conclusion") or ""), 160),
          Emu(left + Inches(1.29)), Emu(top + Inches(0.12)), Emu(width - Inches(1.5)), Inches(0.36),
          font_size=12, bold=True, color=theme.text)
    bullets = [str(x) for x in (section.get("bullets") or []) if str(x).strip()][:4]
    if bullets:
        _bullets(slide, bullets=[_shrink(b, 72) for b in bullets],
                 left=Emu(left + Inches(0.27)), top=Emu(top + Inches(0.58)),
                 width=Emu(width - Inches(0.5)), height=Inches(0.96),
                 font_size=10.5, color=theme.text, accent=theme.accent)


def _islide_sidebar(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart):
    """executive — 左侧边栏 + 圆形装饰"""
    _circle(slide, Inches(11.6), Inches(-0.4), Inches(1.4), theme.accent_soft)
    _circle(slide, Inches(-0.3), Inches(6.2), Inches(1.0), theme.accent_soft)
    _rect(slide, 0, 0, _cfg(theme, "accent_bar_width", 0.25), SLIDE_H, theme.accent)

    _rect(slide, Inches(0.55), Inches(0.35), Inches(12.2), Inches(0.8), theme.panel)
    _rect(slide, Inches(0.55), Inches(0.35), Inches(0.06), Inches(0.8), theme.accent)
    _round_rect(slide, Inches(0.78), Inches(0.46), Inches(1.2), Inches(0.28), theme.accent)
    _text(slide, f"Q{q_idx}/{q_total} · {sec_idx}/{sec_total}",
          Inches(0.78), Inches(0.46), Inches(1.2), Inches(0.28),
          font_size=8, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    _text(slide, _shrink(str(section.get("title") or "关键洞察"), 50),
          Inches(2.16), Inches(0.44), Inches(10.2), Inches(0.46),
          font_size=18, bold=True, color=theme.text)

    _islide_render_chart(slide, section, chart, include_chart,
                         Inches(0.55), Inches(1.35), Inches(12.2), Inches(3.2), theme)

    note = section.get("axis_note") or (chart or {}).get("explain") or ""
    if note:
        _text(slide, _shrink(str(note), 110),
              Inches(0.78), Inches(4.62), Inches(11.8), Inches(0.24),
              font_size=8.5, color=theme.muted, italic=True)

    _islide_render_conclusion(slide, section, theme, Inches(0.55), Inches(4.98), Inches(12.2))


def _islide_header(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart):
    """insight — 顶部色带 + 卡片网格"""
    _rect(slide, 0, 0, SLIDE_W, Inches(1.0), theme.accent)
    _rect(slide, 0, Inches(1.0), SLIDE_W, Inches(0.04), theme.accent_dark)

    _round_rect(slide, Inches(0.7), Inches(0.24), Inches(1.4), Inches(0.28), C_WHITE)
    _text(slide, f"Q{q_idx}/{q_total} · {sec_idx}/{sec_total}",
          Inches(0.7), Inches(0.24), Inches(1.4), Inches(0.28),
          font_size=8, bold=True, color=theme.accent, align=PP_ALIGN.CENTER)
    _text(slide, _shrink(str(section.get("title") or "关键洞察"), 50),
          Inches(2.3), Inches(0.22), Inches(10.2), Inches(0.46),
          font_size=18, bold=True, color=C_WHITE)

    _islide_render_chart(slide, section, chart, include_chart,
                         Inches(0.55), Inches(1.24), Inches(12.2), Inches(3.2), theme)

    note = section.get("axis_note") or (chart or {}).get("explain") or ""
    if note:
        _text(slide, _shrink(str(note), 110),
              Inches(0.78), Inches(4.5), Inches(11.8), Inches(0.24),
              font_size=8.5, color=theme.muted, italic=True)

    _islide_render_conclusion(slide, section, theme, Inches(0.55), Inches(4.86), Inches(12.2))


def _islide_minimal(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart):
    """clean — 极细线条 + 纯净背景"""
    _rect(slide, Inches(0.6), Inches(0.4), Inches(12.1), Inches(0.03), theme.accent)

    _text(slide, f"Q{q_idx}/{q_total} · {sec_idx}/{sec_total}",
          Inches(0.8), Inches(0.6), Inches(1.4), Inches(0.28),
          font_size=9, bold=True, color=theme.accent)
    _text(slide, _shrink(str(section.get("title") or "关键洞察"), 50),
          Inches(2.4), Inches(0.58), Inches(9.8), Inches(0.46),
          font_size=18, bold=True, color=theme.text)

    _islide_render_chart(slide, section, chart, include_chart,
                         Inches(0.6), Inches(1.2), Inches(12.1), Inches(3.2), theme)

    note = section.get("axis_note") or (chart or {}).get("explain") or ""
    if note:
        _text(slide, _shrink(str(note), 110),
              Inches(0.8), Inches(4.48), Inches(11.5), Inches(0.24),
              font_size=8.5, color=theme.muted, italic=True)

    _islide_render_conclusion(slide, section, theme, Inches(0.6), Inches(4.8), Inches(12.1))

    _rect(slide, Inches(0.6), Inches(7.0), Inches(12.1), Inches(0.03), theme.accent)


def _islide_dark_full(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart):
    """midnight — 深色面板 + 发光强调"""
    _circle(slide, Inches(11.0), Inches(-0.3), Inches(1.8), theme.accent_soft, opacity=0.25)
    _circle(slide, Inches(-0.3), Inches(6.0), Inches(1.2), theme.accent_soft, opacity=0.2)
    _rect(slide, 0, 0, SLIDE_W, Inches(0.04), theme.accent)

    _round_rect(slide, Inches(5.5), Inches(0.3), Inches(2.3), Inches(0.32), theme.accent)
    _text(slide, f"Q{q_idx}/{q_total} · {sec_idx}/{sec_total}",
          Inches(5.5), Inches(0.3), Inches(2.3), Inches(0.32),
          font_size=9, bold=True, color=theme.bg, align=PP_ALIGN.CENTER)
    _text(slide, _shrink(str(section.get("title") or "关键洞察"), 50),
          Inches(0.7), Inches(0.8), Inches(11.6), Inches(0.46),
          font_size=20, bold=True, color=theme.accent)

    _islide_render_chart(slide, section, chart, include_chart,
                         Inches(0.55), Inches(1.45), Inches(12.2), Inches(3.0), theme)

    note = section.get("axis_note") or (chart or {}).get("explain") or ""
    if note:
        _text(slide, _shrink(str(note), 110),
              Inches(0.78), Inches(4.52), Inches(11.8), Inches(0.24),
              font_size=8.5, color=theme.muted, italic=True)

    concl_top = Inches(4.86)
    concl_h = Inches(1.72)
    _rect(slide, Inches(0.55), concl_top, Inches(12.2), concl_h, theme.panel)
    _rect(slide, Inches(0.55), concl_top, Inches(0.06), concl_h, theme.accent)
    _round_rect(slide, Inches(0.78), concl_top + Inches(0.12), Inches(0.9), Inches(0.26), theme.accent)
    _text(slide, "结论",
          Inches(0.78), concl_top + Inches(0.12), Inches(0.9), Inches(0.26),
          font_size=8, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    _text(slide, _shrink(str(section.get("conclusion") or ""), 160),
          Inches(1.84), concl_top + Inches(0.12), Inches(10.6), Inches(0.36),
          font_size=12, bold=True, color=theme.text)
    bullets = [str(x) for x in (section.get("bullets") or []) if str(x).strip()][:4]
    if bullets:
        _bullets(slide, bullets=[_shrink(b, 72) for b in bullets],
                 left=Inches(0.82), top=concl_top + Inches(0.58), width=Inches(11.6), height=Inches(0.96),
                 font_size=10.5, color=theme.text, accent=theme.accent)


def _islide_diagonal(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart):
    """coral — 斜线装饰 + 暖色卡片"""
    _rect(slide, 0, 0, _cfg(theme, "accent_bar_width", 0.4), SLIDE_H, theme.accent_soft)
    _rect(slide, _cfg(theme, "accent_bar_width", 0.4), 0, Inches(0.06), SLIDE_H, theme.accent, opacity=0.2)
    _circle(slide, Inches(11.2), Inches(5.5), Inches(1.5), theme.accent_soft)

    _rect(slide, Inches(0.7), Inches(0.35), Inches(12.0), Inches(0.8), theme.panel)
    _rect(slide, Inches(0.7), Inches(0.35), Inches(0.06), Inches(0.8), theme.accent)
    _round_rect(slide, Inches(0.93), Inches(0.46), Inches(1.2), Inches(0.28), theme.accent)
    _text(slide, f"Q{q_idx}/{q_total} · {sec_idx}/{sec_total}",
          Inches(0.93), Inches(0.46), Inches(1.2), Inches(0.28),
          font_size=8, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    _text(slide, _shrink(str(section.get("title") or "关键洞察"), 50),
          Inches(2.3), Inches(0.44), Inches(10.0), Inches(0.46),
          font_size=18, bold=True, color=theme.text)

    _islide_render_chart(slide, section, chart, include_chart,
                         Inches(0.7), Inches(1.35), Inches(12.0), Inches(3.2), theme)

    note = section.get("axis_note") or (chart or {}).get("explain") or ""
    if note:
        _text(slide, _shrink(str(note), 110),
              Inches(0.93), Inches(4.62), Inches(11.6), Inches(0.24),
              font_size=8.5, color=theme.muted, italic=True)

    _islide_render_conclusion(slide, section, theme, Inches(0.7), Inches(4.98), Inches(12.0))


def _islide_corner(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart):
    """teal — 角落装饰 + 网格布局"""
    _rect(slide, 0, _cfg(theme, "corner_qslide_block_top", 6.2), Inches(3.0), _cfg(theme, "corner_qslide_block_height", 1.3), theme.accent)
    _circle(slide, Inches(-0.3), Inches(6.0), Inches(1.2), theme.accent_dark, opacity=0.3)
    _circle(slide, Inches(11.5), Inches(-0.3), Inches(1.3), theme.accent_soft)

    _rect(slide, Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.04), theme.accent)

    _round_rect(slide, Inches(0.7), Inches(0.55), Inches(1.2), Inches(0.28), theme.accent)
    _text(slide, f"Q{q_idx}/{q_total} · {sec_idx}/{sec_total}",
          Inches(0.7), Inches(0.55), Inches(1.2), Inches(0.28),
          font_size=8, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    _text(slide, _shrink(str(section.get("title") or "关键洞察"), 50),
          Inches(2.1), Inches(0.52), Inches(10.2), Inches(0.46),
          font_size=18, bold=True, color=theme.text)

    _islide_render_chart(slide, section, chart, include_chart,
                         Inches(0.55), Inches(1.2), Inches(12.2), Inches(3.2), theme)

    note = section.get("axis_note") or (chart or {}).get("explain") or ""
    if note:
        _text(slide, _shrink(str(note), 110),
              Inches(0.78), Inches(4.48), Inches(11.8), Inches(0.24),
              font_size=8.5, color=theme.muted, italic=True)

    _islide_render_conclusion(slide, section, theme, Inches(0.55), Inches(4.8), Inches(12.2))


def _islide_right_panel(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart):
    """berry — 右侧面板 + 左侧内容"""
    _rect(slide, _cfg(theme, "qslide_panel_left", 10.0), 0, _cfg(theme, "qslide_panel_width", 3.333), SLIDE_H, theme.accent_soft)
    _rect(slide, _cfg(theme, "qslide_panel_left", 10.0), 0, Inches(0.06), SLIDE_H, theme.accent, opacity=0.2)
    _circle(slide, Inches(11.2), Inches(5.5), Inches(1.5), theme.accent, opacity=0.12)

    _round_rect(slide, Inches(0.7), Inches(0.35), Inches(1.2), Inches(0.28), theme.accent)
    _text(slide, f"Q{q_idx}/{q_total} · {sec_idx}/{sec_total}",
          Inches(0.7), Inches(0.35), Inches(1.2), Inches(0.28),
          font_size=8, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    _text(slide, _shrink(str(section.get("title") or "关键洞察"), 50),
          Inches(2.1), Inches(0.32), Inches(7.5), Inches(0.46),
          font_size=18, bold=True, color=theme.text)

    _islide_render_chart(slide, section, chart, include_chart,
                         Inches(0.55), Inches(1.0), Inches(9.0), Inches(3.2), theme)

    note = section.get("axis_note") or (chart or {}).get("explain") or ""
    if note:
        _text(slide, _shrink(str(note), 110),
              Inches(0.78), Inches(4.28), Inches(8.8), Inches(0.24),
              font_size=8.5, color=theme.muted, italic=True)

    concl_top = Inches(4.6)
    concl_h = Inches(1.72)
    _rect(slide, Inches(0.55), concl_top, Inches(9.0), concl_h, theme.panel)
    _rect(slide, Inches(0.55), concl_top, Inches(0.06), concl_h, theme.accent)
    _rect(slide, Inches(0.55), concl_top, Inches(9.0), Inches(0.04), theme.accent_soft)

    _round_rect(slide, Inches(0.78), concl_top + Inches(0.12), Inches(0.9), Inches(0.26), theme.accent)
    _text(slide, "结论",
          Inches(0.78), concl_top + Inches(0.12), Inches(0.9), Inches(0.26),
          font_size=8, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    _text(slide, _shrink(str(section.get("conclusion") or ""), 160),
          Inches(1.84), concl_top + Inches(0.12), Inches(7.4), Inches(0.36),
          font_size=12, bold=True, color=theme.text)
    bullets = [str(x) for x in (section.get("bullets") or []) if str(x).strip()][:4]
    if bullets:
        _bullets(slide, bullets=[_shrink(b, 72) for b in bullets],
                 left=Inches(0.82), top=concl_top + Inches(0.58), width=Inches(8.4), height=Inches(0.96),
                 font_size=10.5, color=theme.text, accent=theme.accent)

    _text(slide, f"{sec_idx}",
          Inches(10.6), Inches(1.5), Inches(2.0), Inches(0.8),
          font_size=44, bold=True, color=theme.accent, align=PP_ALIGN.CENTER)
    _text(slide, f"/ {sec_total}",
          Inches(10.6), Inches(2.3), Inches(2.0), Inches(0.3),
          font_size=14, color=theme.muted, align=PP_ALIGN.CENTER)


def _islide_dark_header(slide, theme, q_idx, q_total, sec_idx, sec_total, section, chart, include_chart):
    """charcoal — 深色标题栏 + 浅色内容"""
    _rect(slide, 0, 0, SLIDE_W, Inches(1.0), theme.panel)
    _rect(slide, 0, Inches(1.0), SLIDE_W, Inches(0.06), theme.accent)
    _circle(slide, Inches(11.0), Inches(-0.2), Inches(1.5), theme.accent_soft, opacity=0.3)

    _round_rect(slide, Inches(0.7), Inches(0.24), Inches(1.4), Inches(0.28), theme.accent)
    _text(slide, f"Q{q_idx}/{q_total} · {sec_idx}/{sec_total}",
          Inches(0.7), Inches(0.24), Inches(1.4), Inches(0.28),
          font_size=9, bold=True, color=theme.bg, align=PP_ALIGN.CENTER)
    _text(slide, _shrink(str(section.get("title") or "关键洞察"), 50),
          Inches(2.3), Inches(0.2), Inches(10.2), Inches(0.46),
          font_size=18, bold=True, color=theme.accent)

    _islide_render_chart(slide, section, chart, include_chart,
                         Inches(0.55), Inches(1.26), Inches(12.2), Inches(3.0), theme)

    note = section.get("axis_note") or (chart or {}).get("explain") or ""
    if note:
        _text(slide, _shrink(str(note), 110),
              Inches(0.78), Inches(4.32), Inches(11.8), Inches(0.24),
              font_size=8.5, color=theme.muted, italic=True)

    _islide_render_conclusion(slide, section, theme, Inches(0.55), Inches(4.66), Inches(12.2))


def _get_insight_sections(ex: dict, charts: List[dict], summary_md: str) -> List[dict]:
    raw = ex.get("__ppt_insights") or ex.get("ppt_insights")
    sections = raw.get("sections") if isinstance(raw, dict) else raw
    if isinstance(sections, list):
        cleaned = [_clean_section(s) for s in sections if isinstance(s, dict)]
        cleaned = [s for s in cleaned if s.get("title") or s.get("conclusion")]
        if cleaned:
            return cleaned[:5]
    return _fallback_sections(summary_md, charts)


def _clean_section(s: dict) -> dict:
    bullets = s.get("bullets") or []
    if not isinstance(bullets, list):
        bullets = []
    return {
        "title": _shrink(str(s.get("title") or "关键洞察"), 40),
        "visual_type": str(s.get("visual_type") or "none").lower(),
        "chart_id": s.get("chart_id"),
        "axis_note": _shrink(str(s.get("axis_note") or ""), 120),
        "conclusion": _shrink(str(s.get("conclusion") or ""), 180),
        "bullets": [_shrink(str(b), 90) for b in bullets[:4] if str(b).strip()],
    }


def _fallback_sections(summary_md: str, charts: List[dict]) -> List[dict]:
    conclusion, findings = _extract_conclusion_findings(summary_md)
    if not findings:
        findings = [_strip_md(x.strip()) for x in summary_md.splitlines() if x.strip()][:4]
    base = []
    chunks = findings[:5] or [conclusion or "当前回答已生成可用于汇报的业务结论。"]
    for i, finding in enumerate(chunks[:5], start=1):
        chart = charts[(i - 1) % len(charts)] if charts else None
        base.append({
            "title": f"洞察 {i}",
            "visual_type": (chart or {}).get("chart_type") or "none",
            "chart_id": (chart or {}).get("subquestion_id"),
            "axis_note": (chart or {}).get("explain") or "",
            "conclusion": finding or conclusion,
            "bullets": [conclusion] if conclusion and conclusion != finding else [],
        })
    while len(base) < 3:
        chart = charts[(len(base)) % len(charts)] if charts else None
        base.append({
            "title": f"补充洞察 {len(base) + 1}",
            "visual_type": (chart or {}).get("chart_type") or "none",
            "chart_id": (chart or {}).get("subquestion_id"),
            "axis_note": (chart or {}).get("explain") or "",
            "conclusion": conclusion or "请结合图表查看当前问题的主要数据表现。",
            "bullets": [],
        })
    return base[:5]


def _section_chart(section: dict, charts: List[dict], primary: Optional[dict]) -> Optional[dict]:
    cid = str(section.get("chart_id") or "").strip()
    if cid:
        found = next((c for c in charts if str(c.get("subquestion_id") or "") == cid), None)
        if found:
            return found
    if primary:
        return primary
    return charts[0] if charts else None


def _chart_with_axis_note(chart: dict, section: dict) -> dict:
    cloned = dict(chart)
    note = (section.get("axis_note") or "").strip()
    if note and not cloned.get("explain"):
        cloned["explain"] = note
    return cloned


def _should_render_cards(chart: dict, visual_type: str) -> bool:
    rows = chart.get("rows") or []
    ctype = str(chart.get("chart_type") or "").lower()
    if ctype == "table":
        return len(rows) < 3
    return len(rows) == 1 or (visual_type == "cards" and len(rows) <= 1)


def _draw_few_row_table_cards(slide, chart_spec: dict, left, top, width, height, theme: PptTheme):
    """表格行数 <3 时：按行拆分指标卡片区（每行一套列指标）。"""
    cols = chart_spec.get("columns") or []
    rows = (chart_spec.get("rows") or [])[:2]
    if not cols or not rows:
        _draw_chart_info_card(slide, chart_spec, [], left, top, width, height, theme)
        return
    n = len(rows)
    gap_band = Inches(0.12) if n > 1 else Inches(0)
    band_h = (height - gap_band * (n - 1)) // n if n else height
    for ri, row in enumerate(rows):
        band_top = top + ri * (band_h + gap_band)
        cards = []
        for j, col in enumerate(cols[:8]):
            value = row[j] if j < len(row) else None
            cards.append((_shrink(str(col), 20), _fmt_metric_value(value), ""))
        cols_per_row = 4 if len(cards) > 3 else max(len(cards), 1)
        card_gap = Inches(0.14)
        card_w = (width - card_gap * (cols_per_row - 1)) // cols_per_row
        card_h = min(Inches(1.12), band_h - Inches(0.2))
        start_top = band_top + max(Inches(0.08), (band_h - card_h) // 2)
        for i, metric in enumerate(cards):
            r = i // cols_per_row
            c = i % cols_per_row
            _metric_card(
                slide, metric,
                left + c * (card_w + card_gap),
                start_top + r * (card_h + Inches(0.16)),
                card_w, card_h, theme, i,
            )


def _draw_value_cards(slide, chart_spec: dict, left, top, width, height, theme: PptTheme):
    cols = chart_spec.get("columns") or []
    rows = chart_spec.get("rows") or []
    if not cols or not rows:
        _draw_chart_info_card(slide, chart_spec, [], left, top, width, height, theme)
        return
    row = rows[0]
    cards = []
    for j, col in enumerate(cols[:8]):
        value = row[j] if j < len(row) else None
        cards.append((_shrink(str(col), 20), _fmt_metric_value(value), ""))
    cols_per_row = 4 if len(cards) > 3 else max(len(cards), 1)
    gap = Inches(0.14)
    card_w = (width - gap * (cols_per_row - 1)) // cols_per_row
    card_h = Inches(1.12)
    start_top = top + Inches(0.36 if len(cards) <= 4 else 0.16)
    for i, metric in enumerate(cards):
        r = i // cols_per_row
        c = i % cols_per_row
        _metric_card(
            slide, metric,
            left + c * (card_w + gap),
            start_top + r * (card_h + Inches(0.18)),
            card_w, card_h, theme, i,
        )


def _add_summary_slide(prs, *, idx, total, user_msg, ast_msg, primary_chart, options, theme: PptTheme):
    slide = _blank(prs)

    _rect(slide, 0, 0, SLIDE_W, SLIDE_H, theme.bg)
    _rect(slide, 0, 0, SLIDE_W, Inches(0.62), theme.accent_dark)
    _rect(slide, 0, Inches(0.62), SLIDE_W, Inches(0.04), theme.accent)
    _text(slide, f"问题 {idx} / {total}",
          Inches(0.4), Inches(0.12), Inches(6), Inches(0.42),
          font_size=18, bold=True, color=C_WHITE)
    if ast_msg and ast_msg.created_at:
        _text(slide, (ast_msg.created_at or "")[:16],
              Inches(9.8), Inches(0.17), Inches(3.1), Inches(0.32),
              font_size=10, color=RGBColor(0xD8, 0xE8, 0xFF), align=PP_ALIGN.RIGHT)

    # ── 解析 extras ──
    ex = (ast_msg.extras or {}) if ast_msg else {}
    summary_md = ex.get("summary_markdown") or (ast_msg.content if ast_msg else "") or ""

    # ── 决定布局（有/无右栏图表）──
    ctype        = (primary_chart or {}).get("chart_type", "")
    has_xl_chart = options.include_chart and bool(primary_chart) and ctype in _XL_MAP
    has_tbl_card = options.include_chart and bool(primary_chart) and ctype == "table"
    has_chart    = has_xl_chart or has_tbl_card

    TXT_L = Inches(0.45)
    if has_chart:
        TXT_W   = Inches(6.9)
        CHART_L = Inches(7.55)
        CHART_W = Inches(5.45)
        CHART_T = Inches(0.78)
        CHART_H = Inches(6.4)
    else:
        TXT_W   = Inches(12.5)
        CHART_L = CHART_W = CHART_T = CHART_H = None

    # ── 用户问题（跨全宽，1 行） ──
    q_text = _shrink((user_msg.content or "").strip() if user_msg else "（无问题）", 80)
    _text(slide, f"Q：{q_text}",
          TXT_L, Inches(0.78), Inches(12.5), Inches(0.46),
          font_size=13, bold=True, color=theme.text)
    # 分隔线
    _rect(slide, TXT_L, Inches(1.30), TXT_W, Inches(0.02), theme.accent)

    # ── 解析内容（有严格上限）──
    conclusion, findings = _extract_conclusion_findings(summary_md)
    # 硬截断：结论最多 CONCL_MAX_CHARS 字，发现最多 FINDING_MAX_COUNT 条且每条 ≤ FINDING_MAX_CHARS
    conclusion = _shrink(conclusion or "（模型未生成核心结论）", CONCL_MAX_CHARS)
    findings   = [_shrink(f, FINDING_MAX_CHARS) for f in (findings or ["（无要点）"])[:FINDING_MAX_COUNT]]

    # ── 核心结论区（固定 1.2" 高，约 3 行） ──
    _text(slide, "核心结论",
          TXT_L, Inches(1.38), Inches(2.2), Inches(0.30),
          font_size=11, bold=True, color=theme.accent)
    _rect(slide, TXT_L, Inches(1.72), TXT_W, Inches(1.40), theme.panel)
    _rect(slide, TXT_L, Inches(1.72), Inches(0.05), Inches(1.40), theme.accent)
    _text(slide, conclusion,
          TXT_L + Inches(0.16), Inches(1.80), TXT_W - Inches(0.28), Inches(1.02),
          font_size=12, color=theme.text, auto_fit=False)

    # ── 分隔线 ──
    _rect(slide, TXT_L, Inches(3.03), TXT_W, Inches(0.015), C_GRAY_BG)

    metrics = _extract_metric_cards(primary_chart, max_count=3)
    if metrics:
        card_w = (TXT_W - Inches(0.16)) // 3
        for i, metric in enumerate(metrics):
            left = TXT_L + i * (card_w + Inches(0.08))
            _metric_card(slide, metric, left, Inches(3.18), card_w, Inches(0.76), theme, i)
        findings_top = Inches(4.14)
        findings_h = Inches(2.55)
    else:
        findings_top = Inches(3.46)
        findings_h = Inches(3.2)

    # ── 关键发现区（固定 3.2" 高，最多 4 条） ──
    _text(slide, "关键发现",
          TXT_L, findings_top - Inches(0.32), Inches(2.2), Inches(0.30),
          font_size=11, bold=True, color=theme.accent)
    _bullets(slide, bullets=findings,
             left=TXT_L, top=findings_top, width=TXT_W, height=findings_h,
             font_size=12, color=theme.text, auto_fit=False, accent=theme.accent)

    # ── 右栏：原生 PPT 图表 ──
    if has_xl_chart:
        ok = _add_native_chart(slide, chart_spec=primary_chart,
                               left=CHART_L, top=CHART_T, width=CHART_W, height=CHART_H,
                               theme=theme)
        if not ok:
            _draw_chart_info_card(slide, primary_chart, [], CHART_L, CHART_T, CHART_W, CHART_H, theme)
    elif has_tbl_card:
        _draw_mini_table(slide, primary_chart, CHART_L, CHART_T, CHART_W, CHART_H, theme)


def _extract_metric_cards(chart_spec: Optional[dict], *, max_count: int = 3) -> List[Tuple[str, str, str]]:
    """从主图或表格里提取可直接放到摘要页的指标卡。"""
    if not chart_spec:
        return []
    cols = chart_spec.get("columns") or []
    rows = chart_spec.get("rows") or []
    metrics = chart_spec.get("metric_fields") or []
    dim = chart_spec.get("dimension_field")
    if not cols or not rows:
        return []

    cards: List[Tuple[str, str, str]] = []
    if dim and metrics:
        dim_idx = _col_idx(cols, dim)
        metric_idx = _col_idx(cols, metrics[0])
        if dim_idx >= 0 and metric_idx >= 0:
            ranked = sorted(
                rows,
                key=lambda r: _to_num(r[metric_idx] if metric_idx < len(r) else None),
                reverse=True,
            )
            for r in ranked[:max_count]:
                label = str(r[dim_idx]) if dim_idx < len(r) and r[dim_idx] is not None else "Top"
                value = _fmt_metric_value(r[metric_idx] if metric_idx < len(r) else None)
                cards.append((_shrink(label, 18), value, _shrink(metrics[0], 18)))
    else:
        first = rows[0] if rows else []
        for j, col in enumerate(cols[:max_count]):
            value = first[j] if j < len(first) else None
            cards.append((_shrink(str(col), 18), _fmt_metric_value(value), "结果"))
    return cards[:max_count]


def _metric_card(slide, metric: Tuple[str, str, str], left, top, width, height, theme: PptTheme, idx: int):
    label, value, hint = metric
    pal = theme.palette[idx % len(theme.palette)]
    # 卡片背景
    _rect(slide, left, top, width, height, theme.panel)
    # 顶部色条
    _rect(slide, left, top, width, Inches(0.05), pal)
    # 左侧色条
    _rect(slide, left, top, Inches(0.04), height, pal)
    # 标签
    _text(slide, label, left + Inches(0.14), top + Inches(0.12), width - Inches(0.26), Inches(0.18),
          font_size=8, bold=True, color=theme.muted)
    # 数值（大号）
    _text(slide, value, left + Inches(0.14), top + Inches(0.32), width - Inches(0.26), Inches(0.32),
          font_size=16, bold=True, color=pal)
    # 提示
    if hint:
        _text(slide, hint, left + Inches(0.14), top + Inches(0.66), width - Inches(0.26), Inches(0.15),
              font_size=7, color=theme.muted)


def _fmt_metric_value(v: Any) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, (date, datetime)):
        return v.strftime("%Y-%m-%d")
    try:
        n = float(v)
    except (TypeError, ValueError):
        return _shrink(str(v), 18)
    if abs(n) >= 1000:
        return f"{n:,.0f}" if n == int(n) else f"{n:,.1f}"
    if abs(n) >= 10:
        return f"{n:.0f}" if n == int(n) else f"{n:.1f}"
    return f"{n:.2f}".rstrip("0").rstrip(".")


# ─────────────────────────────────────────────────────────────────────────────
# 辅图页（次要图表，全屏原生图表）
# ─────────────────────────────────────────────────────────────────────────────

def _add_chart_slide(prs, *, chart: dict, q_idx: int, total: int, theme: PptTheme):
    slide = _blank(prs)
    _rect(slide, 0, 0, SLIDE_W, SLIDE_H, theme.bg)

    ctype    = chart.get("chart_type", "")
    ctype_cn = {"bar": "柱状图", "line": "折线图", "pie": "饼图"}.get(ctype, "图表")
    title    = chart.get("title") or ""
    title_text = f"{ctype_cn}{' · ' + title if title else ''}"
    layout = theme.layout

    if layout in ("dark_full", "dark_header"):
        # Dark layouts: header-style title bar
        _rect(slide, 0, 0, SLIDE_W, Inches(0.9), theme.panel if layout == "dark_header" else theme.panel)
        _rect(slide, 0, Inches(0.9), SLIDE_W, Inches(0.04), theme.accent)
        _round_rect(slide, Inches(0.7), Inches(0.2), Inches(0.7), Inches(0.28), theme.accent)
        _text(slide, f"Q{q_idx}",
              Inches(0.7), Inches(0.2), Inches(0.7), Inches(0.28),
              font_size=9, bold=True, color=C_WHITE if layout == "dark_header" else theme.bg, align=PP_ALIGN.CENTER)
        _text(slide, title_text,
              Inches(1.6), Inches(0.18), Inches(10.6), Inches(0.38),
              font_size=16, bold=True, color=theme.accent if layout == "dark_full" else theme.accent)
    elif layout == "header":
        _rect(slide, 0, 0, SLIDE_W, Inches(0.9), theme.accent)
        _rect(slide, 0, Inches(0.9), SLIDE_W, Inches(0.04), theme.accent_dark)
        _round_rect(slide, Inches(0.7), Inches(0.2), Inches(0.7), Inches(0.28), C_WHITE)
        _text(slide, f"Q{q_idx}",
              Inches(0.7), Inches(0.2), Inches(0.7), Inches(0.28),
              font_size=9, bold=True, color=theme.accent, align=PP_ALIGN.CENTER)
        _text(slide, title_text,
              Inches(1.6), Inches(0.18), Inches(10.6), Inches(0.38),
              font_size=16, bold=True, color=C_WHITE)
    elif layout == "right_panel":
        _rect(slide, _cfg(theme, "qslide_panel_left", 10.0), 0, _cfg(theme, "qslide_panel_width", 3.333), SLIDE_H, theme.accent_soft)
        _round_rect(slide, Inches(0.7), Inches(0.3), Inches(0.7), Inches(0.28), theme.accent)
        _text(slide, f"Q{q_idx}",
              Inches(0.7), Inches(0.3), Inches(0.7), Inches(0.28),
              font_size=9, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
        _text(slide, title_text,
              Inches(1.6), Inches(0.28), Inches(8.0), Inches(0.38),
              font_size=16, bold=True, color=theme.text)
    elif layout == "minimal":
        _rect(slide, Inches(0.6), Inches(0.3), Inches(12.1), Inches(0.03), theme.accent)
        _text(slide, f"Q{q_idx}",
              Inches(0.8), Inches(0.5), Inches(0.7), Inches(0.28),
              font_size=9, bold=True, color=theme.accent)
        _text(slide, title_text,
              Inches(1.7), Inches(0.48), Inches(10.0), Inches(0.38),
              font_size=16, bold=True, color=theme.text)
    elif layout == "corner":
        _rect(slide, 0, _cfg(theme, "corner_qslide_block_top", 6.2), Inches(3.0), _cfg(theme, "corner_qslide_block_height", 1.3), theme.accent)
        _rect(slide, Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.04), theme.accent)
        _round_rect(slide, Inches(0.7), Inches(0.55), Inches(0.7), Inches(0.28), theme.accent)
        _text(slide, f"Q{q_idx}",
              Inches(0.7), Inches(0.55), Inches(0.7), Inches(0.28),
              font_size=9, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
        _text(slide, title_text,
              Inches(1.6), Inches(0.52), Inches(10.6), Inches(0.38),
              font_size=16, bold=True, color=theme.text)
    elif layout == "diagonal":
        _rect(slide, 0, 0, _cfg(theme, "accent_bar_width", 0.4), SLIDE_H, theme.accent_soft)
        _rect(slide, _cfg(theme, "accent_bar_width", 0.4), 0, Inches(0.06), SLIDE_H, theme.accent, opacity=0.2)
        _round_rect(slide, Inches(0.7), Inches(0.3), Inches(0.7), Inches(0.28), theme.accent)
        _text(slide, f"Q{q_idx}",
              Inches(0.7), Inches(0.3), Inches(0.7), Inches(0.28),
              font_size=9, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
        _text(slide, title_text,
              Inches(1.6), Inches(0.28), Inches(10.6), Inches(0.38),
              font_size=16, bold=True, color=theme.text)
    else:
        # sidebar (default)
        _circle(slide, Inches(11.4), Inches(5.8), Inches(1.6), theme.accent_soft)
        _circle(slide, Inches(-0.3), Inches(-0.3), Inches(1.2), theme.accent_soft)
        _rect(slide, 0, 0, _cfg(theme, "accent_bar_width", 0.25), SLIDE_H, theme.accent)
        _rect(slide, Inches(0.55), Inches(0.35), Inches(12.2), Inches(0.65), theme.panel)
        _rect(slide, Inches(0.55), Inches(0.35), Inches(0.06), Inches(0.65), theme.accent)
        _round_rect(slide, Inches(0.78), Inches(0.46), Inches(0.7), Inches(0.28), theme.accent)
        _text(slide, f"Q{q_idx}",
              Inches(0.78), Inches(0.46), Inches(0.7), Inches(0.28),
              font_size=9, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
        _text(slide, title_text,
              Inches(1.66), Inches(0.44), Inches(10.6), Inches(0.38),
              font_size=16, bold=True, color=theme.text)

    # ── 图表主体 ──
    chart_left = Inches(0.55) if layout != "right_panel" else Inches(0.55)
    chart_width = Inches(12.2) if layout != "right_panel" else Inches(9.0)
    chart_top = Inches(1.2) if layout not in ("header", "dark_header") else Inches(1.14)
    if layout in ("dark_full",):
        chart_top = Inches(1.14)
    if layout == "corner":
        chart_top = Inches(1.1)
    CAPTION_H = Inches(0.4) if chart.get("explain") else Inches(0)
    chart_h = Inches(5.6) - CAPTION_H - (Inches(0.2) if layout in ("header", "dark_header") else 0)

    _rect(slide, chart_left, Emu(chart_top - Inches(0.08)), chart_width, Emu(chart_h + Inches(0.16)), theme.panel)
    _rect(slide, chart_left, Emu(chart_top - Inches(0.08)), chart_width, Inches(0.04), theme.accent)

    ok = _add_native_chart(slide, chart_spec=chart,
                           left=Emu(chart_left + Inches(0.15)), top=chart_top,
                           width=Emu(chart_width - Inches(0.3)), height=chart_h,
                           theme=theme)

    if not ok:
        _circle(slide, Emu(chart_left + chart_width // 2 - Inches(0.7)), Emu(chart_top + Inches(1.4)), Inches(1.4), theme.accent_soft)
        _text(slide, "图表数据不足",
              Emu(chart_left + Inches(0.15)), Emu(chart_top + Inches(2.0)), Emu(chart_width - Inches(0.3)), Inches(0.5),
              font_size=14, bold=True, color=theme.muted, align=PP_ALIGN.CENTER)

    # ── 说明文字 ──
    if chart.get("explain"):
        explain_left = Inches(0.78) if layout != "right_panel" else Inches(0.78)
        explain_width = Inches(11.6) if layout != "right_panel" else Inches(8.6)
        _text(slide, chart["explain"],
              explain_left, Inches(6.88), explain_width, Inches(0.42),
              font_size=10, color=theme.muted, italic=True)


# ─────────────────────────────────────────────────────────────────────────────
# 数据明细页（原生 PPT 表格）
# ─────────────────────────────────────────────────────────────────────────────

def _add_subq_table_slide(prs, *, sq_idx, total_sq, sq, options, theme: PptTheme):
    slide = _blank(prs)
    _rect(slide, 0, 0, SLIDE_W, SLIDE_H, theme.bg)

    layout = theme.layout

    # ── Layout-specific header ──
    if layout in ("dark_full", "dark_header"):
        _rect(slide, 0, 0, SLIDE_W, Inches(0.9), theme.panel)
        _rect(slide, 0, Inches(0.9), SLIDE_W, Inches(0.04), theme.accent)
        _round_rect(slide, Inches(0.7), Inches(0.2), Inches(1.1), Inches(0.28), theme.accent)
        _text(slide, f"数据 {sq_idx}/{total_sq}",
              Inches(0.7), Inches(0.2), Inches(1.1), Inches(0.28),
              font_size=8, bold=True, color=C_WHITE if layout == "dark_header" else theme.bg, align=PP_ALIGN.CENTER)
    elif layout == "header":
        _rect(slide, 0, 0, SLIDE_W, Inches(0.9), theme.accent)
        _rect(slide, 0, Inches(0.9), SLIDE_W, Inches(0.04), theme.accent_dark)
        _round_rect(slide, Inches(0.7), Inches(0.2), Inches(1.1), Inches(0.28), C_WHITE)
        _text(slide, f"数据 {sq_idx}/{total_sq}",
              Inches(0.7), Inches(0.2), Inches(1.1), Inches(0.28),
              font_size=8, bold=True, color=theme.accent, align=PP_ALIGN.CENTER)
    elif layout == "right_panel":
        _rect(slide, _cfg(theme, "qslide_panel_left", 10.0), 0, _cfg(theme, "qslide_panel_width", 3.333), SLIDE_H, theme.accent_soft)
        _round_rect(slide, Inches(0.7), Inches(0.3), Inches(1.1), Inches(0.28), theme.accent)
        _text(slide, f"数据 {sq_idx}/{total_sq}",
              Inches(0.7), Inches(0.3), Inches(1.1), Inches(0.28),
              font_size=8, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    elif layout == "minimal":
        _rect(slide, Inches(0.6), Inches(0.3), Inches(12.1), Inches(0.03), theme.accent)
        _text(slide, f"数据 {sq_idx}/{total_sq}",
              Inches(0.8), Inches(0.5), Inches(1.1), Inches(0.28),
              font_size=8, bold=True, color=theme.accent)
    elif layout == "corner":
        _rect(slide, 0, _cfg(theme, "corner_qslide_block_top", 6.2), Inches(3.0), _cfg(theme, "corner_qslide_block_height", 1.3), theme.accent)
        _rect(slide, Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.04), theme.accent)
        _round_rect(slide, Inches(0.7), Inches(0.55), Inches(1.1), Inches(0.28), theme.accent)
        _text(slide, f"数据 {sq_idx}/{total_sq}",
              Inches(0.7), Inches(0.55), Inches(1.1), Inches(0.28),
              font_size=8, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    elif layout == "diagonal":
        _rect(slide, 0, 0, _cfg(theme, "accent_bar_width", 0.4), SLIDE_H, theme.accent_soft)
        _rect(slide, _cfg(theme, "accent_bar_width", 0.4), 0, Inches(0.06), SLIDE_H, theme.accent, opacity=0.2)
        _round_rect(slide, Inches(0.7), Inches(0.3), Inches(1.1), Inches(0.28), theme.accent)
        _text(slide, f"数据 {sq_idx}/{total_sq}",
              Inches(0.7), Inches(0.3), Inches(1.1), Inches(0.28),
              font_size=8, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    else:
        # sidebar
        _circle(slide, Inches(11.8), Inches(5.6), Inches(1.4), theme.accent_soft)
        _rect(slide, 0, 0, Inches(0.25), SLIDE_H, theme.accent)
        _rect(slide, Inches(0.55), Inches(0.35), Inches(12.2), Inches(0.65), theme.panel)
        _rect(slide, Inches(0.55), Inches(0.35), Inches(0.06), Inches(0.65), theme.accent)
        _round_rect(slide, Inches(0.78), Inches(0.46), Inches(1.1), Inches(0.28), theme.accent)
        _text(slide, f"数据 {sq_idx}/{total_sq}",
              Inches(0.78), Inches(0.46), Inches(1.1), Inches(0.28),
              font_size=8, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)

    # ── Status badge + question text (layout-aware positions) ──
    status    = sq.get("sql_status") or "ok"
    status_cn = {"ok": "查询成功", "error": "查询失败", "pending": "未执行"}.get(status, status)
    status_color = C_RED if status == "error" else theme.accent

    if layout in ("dark_full", "dark_header"):
        sy = Inches(0.2)
        qy = Inches(0.18)
        q_left = Inches(2.0)
        q_width = Inches(7.8)
    elif layout == "header":
        sy = Inches(0.2)
        qy = Inches(0.18)
        q_left = Inches(2.0)
        q_width = Inches(7.8)
    elif layout in ("right_panel", "minimal", "diagonal"):
        sy = Inches(0.3)
        qy = Inches(0.28)
        q_left = Inches(2.0)
        q_width = Inches(7.2) if layout == "right_panel" else Inches(8.2)
    elif layout == "corner":
        sy = Inches(0.55)
        qy = Inches(0.52)
        q_left = Inches(2.0)
        q_width = Inches(8.2)
    else:
        sy = Inches(0.46)
        qy = Inches(0.44)
        q_left = Inches(2.1)
        q_width = Inches(8.2)

    _round_rect(slide, Inches(10.6), sy, Inches(1.0), Inches(0.28), status_color)
    _text(slide, status_cn,
          Inches(10.6), sy, Inches(1.0), Inches(0.28),
          font_size=8, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)

    q_text = _shrink(sq.get("question") or f"子问题 {sq_idx}", 110)
    _text(slide, q_text,
          q_left, qy, q_width, Inches(0.38),
          font_size=14, bold=True, color=theme.text)

    body_top = Inches(1.25) if layout not in ("header", "dark_header") else Inches(1.14)
    if layout == "corner":
        body_top = Inches(1.1)
    body_width = Inches(12.2) if layout != "right_panel" else Inches(9.0)
    body_left = Inches(0.55)

    # SQL（可选，卡片式）
    if options.include_sql and sq.get("sql"):
        sql_text = _shrink(sq["sql"].strip().replace("\n", " "), 250)
        _rect(slide, body_left, body_top, body_width, Inches(0.44), theme.accent_soft)
        _rect(slide, body_left, body_top, Inches(0.04), Inches(0.44), theme.accent)
        _text(slide, f"SQL：{sql_text}",
              Emu(body_left + Inches(0.21)), Emu(body_top + Inches(0.05)), Emu(body_width - Inches(0.4)), Inches(0.36),
              font_size=9, color=theme.muted, italic=True)
        body_top = Emu(body_top + Inches(0.54))

    # 错误
    if sq.get("error"):
        _rect(slide, body_left, body_top, body_width, Inches(0.8), RGBColor(0xFF, 0xF0, 0xF0))
        _rect(slide, body_left, body_top, Inches(0.04), Inches(0.8), C_RED)
        _text(slide, f"错误：{_shrink(sq['error'], 300)}",
              Emu(body_left + Inches(0.23)), Emu(body_top + Inches(0.1)), Emu(body_width - Inches(0.4)), Inches(0.6),
              font_size=11, color=C_RED)
        return

    cols       = sq.get("columns") or []
    rows       = sq.get("rows") or []
    total_rows = sq.get("total_rows") or len(rows)

    if not cols or not rows:
        _rect(slide, body_left, body_top, body_width, Inches(0.6), theme.accent_soft)
        _text(slide, "该子问题无返回数据",
              Emu(body_left + Inches(0.23)), Emu(body_top + Inches(0.1)), Emu(body_width - Inches(0.4)), Inches(0.4),
              font_size=12, color=theme.muted, align=PP_ALIGN.CENTER)
        return

    show_cols  = cols[:MAX_TBL_COLS]
    show_rows  = rows[:MAX_TBL_ROWS]
    trunc_cols = len(cols) > MAX_TBL_COLS
    trunc_rows = len(rows) > MAX_TBL_ROWS

    FOOTER_H = Inches(0.3)
    T_H      = SLIDE_H - body_top - FOOTER_H - Inches(0.1)
    _add_ppt_table(slide, columns=show_cols, rows=show_rows,
                   left=body_left, top=body_top, width=body_width, height=T_H,
                   theme=theme)

    parts: List[str] = []
    parts.append(f"{'仅展示前 ' + str(MAX_TBL_ROWS) + ' 行 / ' if trunc_rows else ''}共 {total_rows} 行")
    if trunc_cols:
        parts.append(f"仅展示前 {MAX_TBL_COLS} 列 / 共 {len(cols)} 列")
    _text(slide, "  ·  ".join(parts),
          body_left, Emu(SLIDE_H - FOOTER_H - Inches(0.05)), body_width, FOOTER_H,
          font_size=9, color=theme.muted, italic=True)


# ─────────────────────────────────────────────────────────────────────────────
# 原生 PPT 图表核心
# ─────────────────────────────────────────────────────────────────────────────

def _add_native_chart(slide, *, chart_spec: dict, left, top, width, height, theme: PptTheme) -> bool:
    """
    根据 chart_spec 生成原生 PPT 图表（柱/折/饼）。
    成功返回 True，数据不足时返回 False。
    """
    ctype   = chart_spec.get("chart_type", "")
    xl_type = _XL_MAP.get(ctype)
    if not xl_type:
        return False

    cd = _build_chart_data(chart_spec)
    if cd is None:
        return False

    try:
        shape = slide.shapes.add_chart(xl_type, left, top, width, height, cd)
    except Exception:
        return False

    chart = shape.chart
    _style_native_chart(chart, ctype=ctype, theme=theme)

    # 标题
    title_text = chart_spec.get("title") or ""
    if title_text:
        chart.has_title = True
        try:
            chart.chart_title.text_frame.text = title_text
            for para in chart.chart_title.text_frame.paragraphs:
                for r in para.runs:
                    r.font.name = PPT_FONT
        except Exception:
            pass
    else:
        chart.has_title = False

    # 图例
    metrics = chart_spec.get("metric_fields") or []
    chart.has_legend = (len(metrics) > 1) or (ctype == "pie")
    if chart.has_legend:
        try:
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
            chart.legend.include_in_layout = False
        except Exception:
            pass

    return True


def _style_native_chart(chart, *, ctype: str, theme: PptTheme):
    try:
        chart.chart_style = 2
    except Exception:
        pass
    try:
        chart.font.size = Pt(9)
        chart.font.color.rgb = theme.muted
        chart.font.name = PPT_FONT
    except Exception:
        pass
    try:
        plot = chart.plots[0]
        # 通用：间隙宽度（柱状图）
        if ctype == "bar":
            try:
                plot.gap_width = 80
            except Exception:
                pass
        for idx, series in enumerate(plot.series):
            color = theme.palette[idx % len(theme.palette)]
            if ctype == "bar":
                series.format.fill.solid()
                series.format.fill.fore_color.rgb = color
                series.format.line.fill.background()
                # 顶部圆角效果：添加浅色边框
                try:
                    series.format.line.color.rgb = color
                    series.format.line.width = Pt(0.5)
                except Exception:
                    pass
            elif ctype == "line":
                series.format.line.color.rgb = color
                series.format.line.width = Pt(2.8)
                series.format.line.dash_style = None  # 实线
                series.format.fill.background()
                # 数据点标记
                try:
                    series.marker.style = 8  # 圆形
                    series.marker.size = Pt(6)
                    series.marker.format.fill.solid()
                    series.marker.format.fill.fore_color.rgb = color
                    series.marker.format.line.fill.background()
                except Exception:
                    pass
            elif ctype == "pie":
                pt = series.points[0] if len(series.points) > 0 else None
                for p_idx, point in enumerate(series.points):
                    pcolor = theme.palette[p_idx % len(theme.palette)]
                    point.format.fill.solid()
                    point.format.fill.fore_color.rgb = pcolor
                    point.format.line.color.rgb = C_WHITE
                    point.format.line.width = Pt(1.5)
    except Exception:
        pass
    try:
        if ctype in {"bar", "line"}:
            chart.value_axis.has_major_gridlines = True
            try:
                chart.value_axis.major_gridlines.format.line.color.rgb = RGBColor(0xE8, 0xE8, 0xE8)
                chart.value_axis.major_gridlines.format.line.width = Pt(0.5)
            except Exception:
                pass
            chart.value_axis.tick_labels.font.size = Pt(9)
            chart.value_axis.tick_labels.font.color.rgb = theme.muted
            chart.value_axis.tick_labels.number_format = "#,##0.##"
            chart.value_axis.tick_labels.number_format_is_linked = False
            try:
                chart.value_axis.tick_labels.font.name = PPT_FONT
            except Exception:
                pass
            try:
                chart.value_axis.format.line.color.rgb = RGBColor(0xD0, 0xD0, 0xD0)
            except Exception:
                pass
            chart.category_axis.tick_labels.font.size = Pt(9)
            chart.category_axis.tick_labels.font.color.rgb = theme.muted
            try:
                chart.category_axis.tick_labels.font.name = PPT_FONT
            except Exception:
                pass
            chart.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
            try:
                chart.category_axis.format.line.color.rgb = RGBColor(0xD0, 0xD0, 0xD0)
            except Exception:
                pass
    except Exception:
        pass
    try:
        if chart.has_legend:
            chart.legend.font.size = Pt(9)
            chart.legend.font.color.rgb = theme.muted
            try:
                chart.legend.font.name = PPT_FONT
            except Exception:
                pass
            chart.legend.include_in_layout = False
    except Exception:
        pass
    # 饼图数据标签
    if ctype == "pie":
        try:
            plot = chart.plots[0]
            plot.has_data_labels = True
            dl = plot.data_labels
            dl.font.size = Pt(9)
            dl.font.color.rgb = theme.text
            try:
                dl.font.name = PPT_FONT
            except Exception:
                pass
            dl.show_percentage = True
            dl.show_category_name = True
            dl.show_value = True
            dl.number_format = "#,##0.##"
            dl.number_format_is_linked = False
            dl.label_position = XL_DATA_LABEL_POSITION.BEST_FIT
        except Exception:
            pass
    # 柱状图/折线图始终显示数值标签。
    if ctype in {"bar", "line"}:
        try:
            plot = chart.plots[0]
            plot.has_data_labels = True
            dl = plot.data_labels
            dl.font.size = Pt(8)
            dl.font.color.rgb = theme.text
            try:
                dl.font.name = PPT_FONT
            except Exception:
                pass
            dl.show_value = True
            dl.number_format = "#,##0.##"
            dl.number_format_is_linked = False
            dl.label_position = (
                XL_DATA_LABEL_POSITION.OUTSIDE_END
                if ctype == "bar"
                else XL_DATA_LABEL_POSITION.ABOVE
            )
        except Exception:
            pass


def _build_chart_data(chart_spec: dict) -> Optional[CategoryChartData]:
    """把 chart_spec 转换为 CategoryChartData，失败返回 None。"""
    cols    = chart_spec.get("columns") or []
    rows    = chart_spec.get("rows") or []
    dim     = chart_spec.get("dimension_field")
    metrics = chart_spec.get("metric_fields") or []
    ctype   = chart_spec.get("chart_type", "")

    if not cols or not rows or not dim or not metrics:
        return None

    dim_idx = _col_idx(cols, dim)
    if dim_idx < 0:
        return None

    # 限制类目数
    max_cats = MAX_PIE_CATS if ctype == "pie" else MAX_BAR_CATS
    use_rows = rows[:max_cats]

    # 对饼图：按值降序排列（展示 top-N）
    if ctype == "pie" and metrics:
        m0_idx = _col_idx(cols, metrics[0])
        if m0_idx >= 0:
            try:
                use_rows = sorted(use_rows,
                                  key=lambda r: _to_num(r[m0_idx] if m0_idx < len(r) else None),
                                  reverse=True)[:max_cats]
            except Exception:
                pass

    categories = [
        str(r[dim_idx]) if dim_idx < len(r) and r[dim_idx] is not None else ""
        for r in use_rows
    ]

    cd = CategoryChartData()
    cd.categories = categories

    added = 0
    for m in (metrics[:1] if ctype == "pie" else metrics):  # 饼图只取第一个指标
        m_idx = _col_idx(cols, m)
        if m_idx < 0:
            continue
        values = [_to_num(r[m_idx] if m_idx < len(r) else None) for r in use_rows]
        cd.add_series(m, values)
        added += 1

    return cd if added > 0 else None


def _to_num(v) -> float:
    if v is None or v == "":
        return 0.0
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _col_idx(cols: List[str], name: Optional[str]) -> int:
    """大小写不敏感地查找列名索引。"""
    if not name:
        return -1
    try:
        return cols.index(name)
    except ValueError:
        nl = name.lower()
        for i, c in enumerate(cols):
            if c.lower() == nl:
                return i
        return -1


# ─────────────────────────────────────────────────────────────────────────────
# 迷你表格卡片（table 类型图表 / 右栏 fallback）
# ─────────────────────────────────────────────────────────────────────────────

def _draw_mini_table(slide, chart_spec: dict, left, top, width, height, theme: PptTheme):
    """在摘要页右栏展示 table 类型图表的数据预览。"""
    cols = chart_spec.get("columns") or []
    rows = chart_spec.get("rows") or []
    if not cols or not rows:
        _draw_chart_info_card(slide, chart_spec, [], left, top, width, height, theme)
        return

    # 标题区
    title = chart_spec.get("title") or "数据表格"
    _rect(slide, left, top, width, Inches(0.42), theme.accent_soft)
    _rect(slide, left, top, Inches(0.04), Inches(0.42), theme.accent)
    _text(slide, title, left + Inches(0.16), top + Inches(0.06), width - Inches(0.3), Inches(0.3),
          font_size=11, bold=True, color=theme.accent)

    # 展示迷你表格（最多 5 行 × 4 列）
    show_cols = cols[:4]
    show_rows = rows[:5]
    tbl_top  = Emu(top + Inches(0.5))
    tbl_h    = height - Inches(0.55)
    _add_ppt_table(slide, columns=show_cols, rows=show_rows,
                   left=left + Inches(0.05), top=tbl_top,
                   width=width - Inches(0.1), height=tbl_h, theme=theme)


def _draw_chart_info_card(slide, primary_chart, secondary_charts, left, top, width, height, theme: PptTheme):
    """无法渲染图表时的纯文字信息卡片（兜底）。"""
    _rect(slide, left, top, width, height, theme.panel)
    _rect(slide, left, top, width, Inches(0.04), theme.accent)
    _rect(slide, left, top, Inches(0.04), height, theme.accent)
    # 装饰圆
    _circle(slide, left + width - Inches(1.0), top + height - Inches(1.0), Inches(0.8), theme.accent_soft)
    ctype_cn = {"bar": "柱状图", "line": "折线图", "pie": "饼图", "table": "数据表格"}.get(
        (primary_chart or {}).get("chart_type", ""), "图表")
    CX = left + Inches(0.2)
    CW = width - Inches(0.4)
    _round_rect(slide, CX, top + Inches(0.16), Inches(1.2), Inches(0.3), theme.accent)
    _text(slide, f"📊 {ctype_cn}",
          CX, top + Inches(0.16), Inches(1.2), Inches(0.3),
          font_size=9, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    if primary_chart and primary_chart.get("title"):
        _text(slide, primary_chart["title"],
              CX, top + Inches(0.6), CW, Inches(0.35),
              font_size=12, bold=True, color=theme.text)
    if primary_chart and primary_chart.get("explain"):
        _text(slide, primary_chart["explain"],
              CX, top + Inches(1.0), CW, Inches(0.6),
              font_size=10, color=theme.muted, italic=True)


# ─────────────────────────────────────────────────────────────────────────────
# 原生 PPT 表格
# ─────────────────────────────────────────────────────────────────────────────

def _add_ppt_table(slide, *, columns: List[str], rows: List[list], left, top, width, height, theme: PptTheme):
    n_cols  = len(columns)
    n_data  = len(rows)
    n_total = n_data + 1

    shape = slide.shapes.add_table(n_total, n_cols, left, top, width, height)
    tbl   = shape.table

    # 列宽（等分）
    col_w = width // n_cols
    for j in range(n_cols):
        tbl.columns[j].width = col_w if j < n_cols - 1 else (width - col_w * (n_cols - 1))

    # 行高
    hdr_h    = Inches(0.42)
    data_h   = max(Inches(0.28), (height - hdr_h) // max(n_data, 1))
    tbl.rows[0].height = hdr_h
    for i in range(1, n_total):
        tbl.rows[i].height = (
            data_h if i < n_total - 1
            else max(Inches(0.28), height - hdr_h - data_h * (n_data - 1))
        )

    # 表头（加粗，居中，大字号）
    for j, col in enumerate(columns):
        _cell(tbl.cell(0, j), _shrink(str(col), 24),
              font_size=11, bold=True, fg=C_WHITE, bg=theme.table_header, align=PP_ALIGN.CENTER)

    # 数据行（交替色 + 更好的间距）
    for i, row in enumerate(rows, start=1):
        bg = theme.table_alt if i % 2 == 0 else C_WHITE
        for j in range(n_cols):
            v = row[j] if j < len(row) else None
            _cell(tbl.cell(i, j), _fmt_val(v), font_size=10, bold=False,
                  fg=theme.text, bg=bg, align=PP_ALIGN.LEFT)


def _cell(cell, text: str, *, font_size, bold, fg, bg, align=PP_ALIGN.LEFT):
    cell.fill.solid()
    cell.fill.fore_color.rgb = bg
    tf = cell.text_frame
    tf.word_wrap = False
    p  = tf.paragraphs[0]
    p.alignment = align
    for e in list(p._p.findall(qn("a:r"))):
        p._p.remove(e)
    if text:
        run = p.add_run()
        run.text           = text
        run.font.size      = Pt(font_size)
        run.font.bold      = bold
        run.font.name      = PPT_FONT
        run.font.color.rgb = fg


# ─────────────────────────────────────────────────────────────────────────────
# 低层绘图工具
# ─────────────────────────────────────────────────────────────────────────────

def _blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _rect(slide, left, top, width, height, color: RGBColor, *, opacity: float = 1.0):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    s.fill.solid()
    s.fill.fore_color.rgb = color
    if opacity < 1.0:
        _set_shape_opacity(s, opacity)
    s.line.fill.background()
    return s


def _circle(slide, left, top, size, color: RGBColor, *, opacity: float = 1.0):
    s = slide.shapes.add_shape(MSO_SHAPE.OVAL, left, top, size, size)
    s.fill.solid()
    s.fill.fore_color.rgb = color
    if opacity < 1.0:
        _set_shape_opacity(s, opacity)
    s.line.fill.background()
    return s


def _round_rect(slide, left, top, width, height, color: RGBColor, *, line_color: Optional[RGBColor] = None):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    s.fill.solid()
    s.fill.fore_color.rgb = color
    if line_color:
        s.line.color.rgb = line_color
        s.line.width = Pt(0.8)
    else:
        s.line.fill.background()
    return s


def _set_shape_opacity(shape, alpha: float):
    """设置形状填充透明度 (0.0 ~ 1.0)。"""
    try:
        fill = shape.fill._fill
        solid = fill.find(qn("a:solidFill"))
        if solid is not None:
            srgb = solid.find(qn("a:srgbClr"))
            if srgb is not None:
                a_elem = srgb.find(qn("a:alpha"))
                if a_elem is None:
                    from lxml import etree
                    a_elem = etree.SubElement(srgb, qn("a:alpha"))
                a_elem.set("val", str(int(alpha * 100000)))
    except Exception:
        pass


def _text(
    slide, text: str, left, top, width, height,
    *, font_size=12, bold=False, italic=False,
    color: RGBColor = None, align=PP_ALIGN.LEFT, auto_fit=False,
    line_spacing: Optional[float] = None,
    word_wrap: bool = True,
):
    color = color or C_TEXT
    tb    = slide.shapes.add_textbox(left, top, width, height)
    tf    = tb.text_frame
    tf.word_wrap = word_wrap
    if auto_fit:
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    p = tf.paragraphs[0]
    p.alignment = align
    if line_spacing:
        p.line_spacing = Pt(float(font_size) * float(line_spacing))
    run = p.add_run()
    run.text           = text
    run.font.size      = Pt(font_size)
    run.font.bold      = bold
    run.font.italic    = italic
    run.font.name      = PPT_FONT
    run.font.color.rgb = color
    return tb


def _bullets(
    slide, *, bullets: List[str], left, top, width, height,
    font_size=12, color: RGBColor = None, auto_fit=False,
    accent: RGBColor = None,
):
    color = color or C_TEXT
    accent = accent or color
    tb    = slide.shapes.add_textbox(left, top, width, height)
    tf    = tb.text_frame
    tf.word_wrap = True
    if auto_fit:
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    for i, line in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(4)
        # 彩色标记符号
        marker = p.add_run()
        marker.text = "▸ "
        marker.font.size = Pt(font_size)
        marker.font.bold = True
        marker.font.name = PPT_FONT
        marker.font.color.rgb = accent
        # 内容文字
        run = p.add_run()
        run.text = line
        run.font.size = Pt(font_size)
        run.font.name = PPT_FONT
        run.font.color.rgb = color
    return tb


# ─────────────────────────────────────────────────────────────────────────────
# 消息配对 & 图表解析
# ─────────────────────────────────────────────────────────────────────────────

def _parse_charts(ex: dict) -> List[dict]:
    raw = ex.get("charts")
    if isinstance(raw, list) and raw:
        return raw
    single = ex.get("chart")
    return [single] if single else []


def _get_primary(ex: dict, all_charts: List[dict]) -> Optional[dict]:
    if not all_charts:
        return None
    pid = ex.get("primary_chart_id")
    return next((c for c in all_charts if c.get("subquestion_id") == pid), all_charts[0])


def _pair_messages(messages: List[PptMessage]):
    pairs, pending = [], None
    for m in messages:
        if m.role == "user":
            if pending is not None:
                pairs.append((pending, None))
            pending = m
        elif m.role == "assistant":
            pairs.append((pending, m))
            pending = None
    if pending is not None:
        pairs.append((pending, None))
    return pairs


# ─────────────────────────────────────────────────────────────────────────────
# Markdown 解析 & 格式化
# ─────────────────────────────────────────────────────────────────────────────

_HEADING_RE   = re.compile(r"^\s*#{1,6}\s+.*$")
_BULLET_RE    = re.compile(r"^\s*[-*•]\s+(.+)$")
_MD_INLINE_RE = re.compile(r"\*\*(.+?)\*\*|`([^`]+)`|\*(.+?)\*")
# 匹配 LLM 输出的顶层节标题（一/二/三/四 或单数字+点，不含 2.1 等子标题）
# 例：**一、核心结论** / **1. 核心结论** / ## 核心结论
# 不匹配：**2.1 xxx**、**3.2 xxx** 等子标题
_SECTION_RE   = re.compile(
    r"^\*{0,2}\s*(?:[一二三四五六][\、．]|[1-6]\.\s)(?!\d).+\*{0,2}$"
    r"|^\s*#{1,4}\s+.+$"
)


def _extract_conclusion_findings(md: str) -> Tuple[str, List[str]]:
    """
    从 LLM 生成的 summary_markdown 中提取核心结论和关键发现。

    LLM 按固定骨架输出四段：
      **一、核心结论**  → 自然段文字（非 bullet）
      **二、详细统计数据** → 各种 bullet
      **三、关键发现**  → bullet 列表（这里才是我们要的发现）
      **四、建议动作**  → bullet

    策略：
    - 把文本按节标题切分，收集各节内容
    - 节 0（第一节）的非 bullet 文字作为核心结论
    - 节 2（第三节，关键发现）的 bullet 作为关键发现
    - 若第三节为空则回退到第一节的 bullet
    """
    if not md:
        return "", []

    lines = [ln.rstrip() for ln in md.splitlines()]

    # 切分到各 section（section_idx → lines）
    sections: List[List[str]] = []
    cur: List[str] = []

    for ln in lines:
        if _SECTION_RE.match(ln.strip()):
            sections.append(cur)
            cur = []
        else:
            cur.append(ln)
    sections.append(cur)

    # sections[0] 是第一个节标题之前的内容（通常为空）
    # sections[1] = 一、核心结论内容, sections[3] = 三、关键发现内容, etc.
    def _para(sec_lines: List[str]) -> str:
        """提取段落文字（非 bullet，非空行）。"""
        parts = []
        for ln in sec_lines:
            s = ln.strip()
            if not s:
                continue
            if _BULLET_RE.match(s):
                continue
            parts.append(_strip_md(s))
        return " ".join(parts)

    def _bullets_from(sec_lines: List[str]) -> List[str]:
        """提取 bullet 列表文字。"""
        result = []
        for ln in sec_lines:
            m = _BULLET_RE.match(ln.strip())
            if m:
                t = _strip_md(m.group(1)).strip()
                if t:
                    result.append(t)
        return result

    # 核心结论：取第 1 节（索引 1）的非 bullet 文字
    conclusion = _para(sections[1]) if len(sections) > 1 else ""

    # 关键发现：取第 3 节（索引 3）的 bullet；不足则取第 1 节的 bullet
    findings: List[str] = []
    if len(sections) > 3:
        findings = _bullets_from(sections[3])
    if not findings and len(sections) > 1:
        findings = _bullets_from(sections[1])
    # 最终兜底：取所有节的 bullet
    if not findings:
        for sec in sections:
            findings.extend(_bullets_from(sec))

    return conclusion, findings


def _strip_md(s: str) -> str:
    return _MD_INLINE_RE.sub(lambda m: m.group(1) or m.group(2) or m.group(3) or "", s)


def _shrink(s: str, max_len: int) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= max_len else s[:max_len - 1] + "…"


def _fmt_val(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, bool):
        return str(v)
    raw = str(v).strip()
    numeric = raw.replace(",", "")
    percent = numeric.endswith("%")
    if percent:
        numeric = numeric[:-1].strip()
    try:
        n = float(numeric)
        if n == int(n) and abs(n) < 1e15:
            text = f"{int(n):,}"
        else:
            text = f"{n:,.2f}".rstrip("0").rstrip(".")
        return f"{text}%" if percent else text
    except (TypeError, ValueError):
        pass
    s = str(v)
    return (s[:27] + "…") if len(s) > 27 else s


# ─────────────────────────────────────────────────────────────────────────────
# 专属定制版：销售业绩汇报模板节奏
# ─────────────────────────────────────────────────────────────────────────────

CUST_W = Inches(20)
CUST_H = Inches(11.25)
CUST_GREEN = RGBColor(0x08, 0x5B, 0x4A)
CUST_GREEN_2 = RGBColor(0x0D, 0x70, 0x5D)
CUST_MINT = RGBColor(0xE8, 0xF5, 0xF1)
CUST_MINT_2 = RGBColor(0xD6, 0xEC, 0xE6)
CUST_COVER_BG = RGBColor(0xE9, 0xF7, 0xF7)
CUST_COVER_GREEN = RGBColor(0x2F, 0x7F, 0x2F)
CUST_TEXT = RGBColor(0x1D, 0x2E, 0x2A)
# 封面主标题色（RGB 59, 74, 142）
C_TITLE_NAVY = RGBColor(0x3B, 0x4A, 0x8E)
CUST_MUTED = RGBColor(0x6E, 0x83, 0x7D)
PPT_FONT = "Microsoft YaHei"
TABLE_CHART_SUBTITLE_CN = "数据图表洞察"
TABLE_CHART_SUBTITLE_EN = "Data chart insights"
CUST_LINE = RGBColor(0xB9, 0xD8, 0xCF)
CUST_CHART_PALETTE = (
    RGBColor(0x10, 0x8A, 0xA8),
    RGBColor(0x0F, 0x6E, 0x9E),
    RGBColor(0x63, 0xB7, 0xC9),
    RGBColor(0x93, 0xD1, 0xDD),
    RGBColor(0x0B, 0x5E, 0x75),
    RGBColor(0x9A, 0xC8, 0xD4),
)
PPT_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "pptTemplate"
CUSTOM_COVER_BG_PATH = PPT_TEMPLATE_DIR / "cover_bg.png"
CUSTOM_END_BG_PATH = PPT_TEMPLATE_DIR / "end_bg.png"


def _intro_ph_full_question_for_custom_sales(
    *, conversation_title: str, question: str, summary_desc: str
) -> Tuple[str, Optional[int]]:
    """深度洞察会话：PH_FULL_QUESTION 与 PH_SUMMARY_DESC 同源（summary_desc），取首句（至第一个。）；无。则全文；不再做 max_len 截断。"""
    if "深度洞察" not in (conversation_title or ""):
        return question, 70
    raw = (summary_desc or "").strip()
    if not raw:
        return question, 70
    i = raw.find("。")
    snippet = raw[: i + 1].strip() if i >= 0 else raw
    return snippet, None


def _insight_intro_ph_full_question_from_desc(desc: str, *, fallback_claim: str) -> Tuple[str, Optional[int]]:
    """模块深度洞察：第三页 PH_FULL_QUESTION 与第四页 PH_SUMMARY_DESC（desc）同源。
    优先取 desc 的第一段（按空行分段）；无空行则取至第一个「。」（含句号）；无句号则整段 desc。无 desc 时回退 claim 并 max_len。"""
    raw = (desc or "").strip()
    if not raw:
        fb = (fallback_claim or "").strip()
        return (fb if fb else "—", 70)
    for sep in ("\n\n", "\r\n\r\n"):
        if sep in raw:
            first = raw.split(sep, 1)[0].strip()
            if first:
                return first, None
    i = raw.find("。")
    snippet = raw[: i + 1].strip() if i >= 0 else raw
    return snippet, None


def build_custom_sales_pptx(
    *,
    module_name: str,
    conversation_title: str,
    file_name: Optional[str],
    author: Optional[str],
    generated_at: Optional[datetime],
    messages: List[PptMessage],
    options: PptExportOptions,
    logo_bytes: Optional[bytes] = None,
) -> bytes:
    template = _load_custom_template()
    prs = Presentation()
    prs.slide_width = template.slide_width
    prs.slide_height = template.slide_height
    theme = _custom_chart_theme()
    pairs = _pair_messages(messages)[:5]
    now = generated_at or datetime.now()

    _custom_reference_cover(prs, author=author, generated_at=now, logo_bytes=logo_bytes)

    toc = _clone_template_slide(prs, template.slides[1])
    _retint_custom_slide(toc, theme)
    for i in range(5):
        digest = _custom_digest_for_pair(pairs[i]) if i < len(pairs) else {}
        label = digest.get("question_short") or _custom_question_short((pairs[i][0].content if i < len(pairs) and pairs[i][0] else "") or "")
        _replace_template_text(toc, f"PH_TOC_NO_{i + 1}", f"{i + 1:02d}" if i < len(pairs) else "")
        _replace_template_text(toc, f"PH_TOC_Q_{i + 1}", _clean_custom_heading(label) if i < len(pairs) else "", font_size=17)

    for idx, (user_msg, ast_msg) in enumerate(pairs, start=1):
        question = (user_msg.content or "").strip() if user_msg else "（无问题）"
        ex = (ast_msg.extras or {}) if ast_msg else {}
        charts = _parse_charts(ex)
        primary = _get_primary(ex, charts)
        summary_md = ex.get("summary_markdown") or (ast_msg.content if ast_msg else "") or ""
        sections = _get_insight_sections(ex, charts, summary_md)
        digest = _custom_digest_for_pair((user_msg, ast_msg))
        question_short = _clean_custom_heading(digest.get("question_short") or _custom_question_short(question))
        summary_content = _custom_summary_content_from_digest(digest, summary_md, sections)
        intro_full_q, intro_full_q_max = _intro_ph_full_question_for_custom_sales(
            conversation_title=conversation_title,
            question=question,
            summary_desc=summary_content[1],
        )

        intro = _clone_template_slide(prs, template.slides[2])
        _retint_custom_slide(intro, theme)
        _replace_template_text(intro, "PH_SECTION_SHORT", question_short, font_size=40)
        _replace_template_text(intro, "PH_SECTION_NO", f"{idx:02d}")
        if intro_full_q_max is not None:
            _replace_template_text(intro, "PH_FULL_QUESTION", intro_full_q, max_len=intro_full_q_max, font_size=20)
        else:
            _replace_template_text(intro, "PH_FULL_QUESTION", intro_full_q, font_size=20)
        _replace_template_text(intro, "PH_PART_NO", f"PART {idx:02d}")
        _replace_template_logos(intro, logo_bytes)

        summary = _clone_template_slide(prs, template.slides[3])
        _replace_template_text(summary, "PH_SUMMARY_QUESTION", _clean_custom_heading(question_short), font_size=30)
        _replace_template_text(summary, "PH_SUMMARY_SUBTITLE", "Overview of the data insight")
        _replace_template_text(summary, "PH_SUMMARY_TITLE", _clean_custom_heading(summary_content[0]), font_size=18, word_wrap=False)
        _replace_template_text(summary, "PH_SUMMARY_DESC", summary_content[1], max_len=320, font_size=14, line_spacing=1.40)
        _replace_template_text(summary, "PH_SUMMARY_POINT_1", "", max_len=320, font_size=14, line_spacing=1.40)
        _replace_template_text(summary, "PH_SUMMARY_POINT_2", "", max_len=320, font_size=14, line_spacing=1.40)
        _replace_template_text(summary, "PH_SUMMARY_CONCLUSION", summary_content[3], max_len=300, font_size=14, line_spacing=1.40)
        _replace_custom_summary_image(summary, idx)
        _finalize_template_summary_four_points(
            summary, summary_content[2], summary_content[1], summary_content[3], theme,
            layout="sales",
        )
        _replace_template_logos(summary, logo_bytes)
        _retint_custom_slide(summary, theme)

        table_charts = _custom_table_charts_from_subquestions(ex.get("subquestions") or [])
        chart_items = charts or table_charts or ([primary] if primary else [])
        seen = set()
        unique_charts = []
        for c in chart_items:
            if not c:
                continue
            key = c.get("subquestion_id") or c.get("title") or id(c)
            if key in seen:
                continue
            seen.add(key)
            unique_charts.append(c)
        if not unique_charts:
            unique_charts = [None]

        for c_idx, chart in enumerate(unique_charts, start=1):
            section = _custom_section_for_chart(chart, sections, c_idx)
            chart_slide = _clone_template_slide(prs, _custom_chart_template_slide(template, chart))
            _fill_custom_chart_slide(
                chart_slide,
                q_idx=idx,
                chart_idx=c_idx,
                summary_title=summary_content[0],
                question_short=question_short,
                chart=chart,
                section=section,
                digest=digest,
                include_chart=options.include_chart,
                theme=theme,
                logo_bytes=logo_bytes,
            )

    end = _custom_end_with_background(prs, logo_bytes=logo_bytes)
    _replace_template_logos(end, logo_bytes)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def build_insight_custom_pptx(
    *,
    module_name: str,
    author: Optional[str],
    generated_at: Optional[datetime],
    report: Dict[str, Any],
    logo_bytes: Optional[bytes] = None,
    digests: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Build module-level deep insight PPT with the same custom template grammar.

    When *digests* (from _attach_insight_ppt_digests_sync) is provided, dimension
    summary / chart_summaries / actions are sourced from the model for slides.
    evidence / dim_texts / dim_digests 的 dict key 会规范为 str，与 DB JSON 反序列化一致。
    """
    template = _load_custom_template()
    prs = Presentation()
    prs.slide_width = template.slide_width
    prs.slide_height = template.slide_height
    theme = _custom_chart_theme()
    now = generated_at or datetime.now()

    dimensions = report.get("dimensions") or []
    evidence = _insight_str_key_dict(report.get("evidence") or {})
    dim_texts = _insight_str_key_dict(report.get("dim_texts") or {})
    final_md = str(report.get("final_md") or "").strip()
    dimension_items = _insight_dimension_items(dimensions, evidence, dim_texts)[:4]

    _dd_raw = (digests or {}).get("dim_digests") or {}
    dim_digests = {str(k): v for k, v in _dd_raw.items() if isinstance(v, dict)}
    final_digest = (digests or {}).get("final_digest")

    cover = _custom_reference_cover(prs, author=author, generated_at=now, logo_bytes=logo_bytes)
    _replace_cover_text(cover, "数据洞察报告", "深度洞察报告", color=C_TITLE_NAVY)
    _replace_cover_text(cover, "Data Insight Report", "Data Deep Insight Report")

    toc = _clone_template_slide(prs, template.slides[1])
    _retint_custom_slide(toc, theme)
    # 目录 01–04：与报告页一致（display_title || title || id），不用 item["title"] 的二次截断
    dim_labels: List[str] = []
    for item in dimension_items[:4]:
        raw = str(item.get("toc_label") or item.get("title") or "").strip()
        dim_labels.append(_shrink(raw, 22) if len(raw) > 22 else raw)
    for i, label in enumerate(dim_labels + ["洞察总结"], start=1):
        _replace_template_text(toc, f"PH_TOC_NO_{i}", f"{i:02d}")
        _replace_template_text(toc, f"PH_TOC_Q_{i}", label, font_size=17)

    if not dimension_items:
        dimension_items = [{
            "idx": 1, "id": "", "title": "维度洞察", "toc_label": "维度洞察",
            "claim": "当前报告暂无可展开的维度，请确认深度洞察报告已完整生成后重试导出。",
            "markdown": final_md, "charts": [], "tables": [],
        }]

    for item in dimension_items:
        dim_digest = dim_digests.get(item["id"])

        if dim_digest and dim_digest.get("summary"):
            summary = {
                "title": str(dim_digest["summary"].get("title") or _clean_custom_heading(_shrink_cn(item.get("title") or "维度洞察", 8))),
                "desc": str(dim_digest["summary"].get("desc") or ""),
                "points": [str(x) for x in (dim_digest["summary"].get("points") or [])[:4]],
                "conclusion": _shrink(str(dim_digest["summary"].get("conclusion") or ""), INSIGHT_SUMMARY_CONCL_MAX_CHARS),
            }
        else:
            summary = _insight_dimension_summary(item)
        summary_title = summary["title"]

        intro_full_q, intro_full_q_max = _insight_intro_ph_full_question_from_desc(
            summary["desc"], fallback_claim=str(item.get("claim") or ""),
        )

        # --- intro slide（PH_FULL_QUESTION 与下一页 PH_SUMMARY_DESC 同源首段）---
        intro = _clone_template_slide(prs, template.slides[2])
        _retint_custom_slide(intro, theme)
        _replace_template_text(intro, "PH_SECTION_SHORT", _clean_custom_heading(_shrink(item.get("toc_label") or item["title"], 18)), font_size=40)
        _replace_template_text(intro, "PH_SECTION_NO", f"{item['idx']:02d}")
        if intro_full_q_max is not None:
            _replace_template_text(intro, "PH_FULL_QUESTION", intro_full_q, max_len=intro_full_q_max, font_size=20)
        else:
            _replace_template_text(intro, "PH_FULL_QUESTION", intro_full_q, font_size=20)
        _replace_template_text(intro, "PH_PART_NO", f"PART {item['idx']:02d}")
        _replace_template_logos(intro, logo_bytes)

        # --- dimension summary slide (model or regex fallback) ---
        _add_insight_template_summary(
            prs, template, theme,
            question=item.get("toc_label") or item["title"],
            subtitle="Overview of the data insight",
            title=summary_title,
            desc=summary["desc"],
            points=summary["points"],
            conclusion=summary["conclusion"],
            logo_bytes=logo_bytes,
            image_idx=item["idx"],
        )

        # --- chart / evidence slides：顺序与 LLM digest 的 evidence 列表一致，避免解析文案错位 ---
        all_evidence = _insight_ordered_evidence_visuals(item.get("evidence") or [])
        if all_evidence:
            for c_idx, ev in enumerate(all_evidence, start=1):
                chart_slide = _clone_template_slide(prs, _custom_chart_template_slide(template, ev))
                section = {
                    "title": ev.get("title") or item["title"],
                    "conclusion": ev.get("explain") or item["claim"],
                    "bullets": summary["points"],
                }
                chart_digest = _insight_digest_for_chart_slide(dim_digest, ev, item, summary, chart_seq_index=c_idx - 1)
                _fill_custom_chart_slide(
                    chart_slide, q_idx=item["idx"], chart_idx=c_idx,
                    summary_title=summary_title,
                    question_short=item.get("toc_label") or item["title"],
                    chart=ev, section=section,
                    digest=chart_digest,
                    include_chart=True, theme=theme, logo_bytes=logo_bytes,
                    chart_summary_index=c_idx - 1,
                )
        else:
            chart_slide = _clone_template_slide(prs, template.slides[5])
            _fill_custom_chart_slide(
                chart_slide, q_idx=item["idx"], chart_idx=1,
                summary_title=summary_title,
                question_short=item.get("toc_label") or item["title"],
                chart=None,
                section={"title": item["title"], "conclusion": item["claim"], "bullets": summary["points"]},
                digest={}, include_chart=True, theme=theme, logo_bytes=logo_bytes,
            )

        # --- per-dimension action slide ---
        if dim_digest and dim_digest.get("actions"):
            _add_insight_action_slide(
                prs, template, theme,
                logo_bytes=logo_bytes,
                actions=list(dim_digest["actions"])[:3],
            )
        else:
            # Fallback: extract chunks from dimension markdown
            dim_chunks_ar = _insight_text_chunks(item.get("markdown") or "", limit=12)
            pool_ar = [x for x in dim_chunks_ar if x] or [item.get("claim", "")]
            fallback_actions = [
                {"title": _shrink(t, 12), "body": _shrink(t, 140), "owner": "业务负责人", "metric": "关键指标", "deadline": "2周内"}
                for t in _insight_pick_items(pool_ar, 0)
            ]
            _add_insight_action_slide(
                prs, template, theme,
                logo_bytes=logo_bytes,
                actions=fallback_actions,
            )

    # Final summary 4 pages: model-generated when available
    if final_digest:
        _add_insight_summary_pages_from_digest(prs, theme, module_name, final_digest, logo_bytes=logo_bytes)
    else:
        _add_insight_summary_pages(prs, theme, module_name, final_md, dimension_items, logo_bytes=logo_bytes)

    end = _custom_end_with_background(prs, logo_bytes=logo_bytes)
    _replace_template_logos(end, logo_bytes)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _load_custom_template() -> Presentation:
    path = Path(__file__).resolve().parents[3] / "tem.pptx"
    if not path.exists():
        raise FileNotFoundError(f"Custom PPT template not found: {path}")
    return Presentation(str(path))


def _custom_chart_theme() -> PptTheme:
    return PptTheme(
        id="custom_med_chart",
        name="Custom Med Chart",
        layout="custom",
        accent=RGBColor(0x10, 0x8A, 0xA8),
        accent_dark=RGBColor(0x0B, 0x5E, 0x75),
        accent_soft=RGBColor(0xE4, 0xF6, 0xF8),
        bg=C_WHITE,
        panel=C_WHITE,
        text=CUST_TEXT,
        muted=CUST_MUTED,
        table_header=RGBColor(0x0F, 0x6E, 0x9E),
        table_alt=RGBColor(0xF0, 0xFA, 0xFC),
        palette=CUST_CHART_PALETTE,
    )


def _custom_reference_cover(prs: Presentation, *, author: Optional[str], generated_at: datetime, logo_bytes: Optional[bytes]):
    slide = _blank(prs)
    _add_full_slide_image(slide, CUSTOM_COVER_BG_PATH, prs.slide_width, prs.slide_height, fallback_color=CUST_COVER_BG)
    _custom_logo(slide, logo_bytes, Inches(16.25), Inches(0.78), Inches(2.25), Inches(0.42))

    _text(slide, "数据洞察报告", Inches(1.58), Inches(2.74), Inches(7.2), Inches(0.95),
          font_size=72, bold=True, color=C_TITLE_NAVY)
    _text(slide, "Data Insight Report", Inches(1.62), Inches(4.92), Inches(3.6), Inches(0.28),
          font_size=30, color=CUST_TEXT)
    _rect(slide, Inches(1.58), Inches(5.45), Inches(4.75), Inches(0.035), RGBColor(0xA4, 0xC8, 0xA6))
    _round_rect(slide, Inches(1.58), Inches(6.32), Inches(7.2), Inches(0.68), RGBColor(0x0A, 0x7D, 0xAA))
    _round_rect(slide, Inches(4.7), Inches(6.32), Inches(4.08), Inches(0.68), RGBColor(0x0B, 0x72, 0x9D))
    _text(slide, f"汇报人：{author or '—'}", Inches(1.95), Inches(6.52), Inches(2.6), Inches(0.22),
          font_size=18, bold=True, color=C_WHITE)
    _text(slide, f"汇报时间：{generated_at.strftime('%Y-%m-%d')}", Inches(4.98), Inches(6.52), Inches(3.3), Inches(0.22),
          font_size=18, bold=True, color=C_WHITE)

    return slide


def _add_full_slide_image(slide, path: Path, width, height, *, fallback_color: RGBColor):
    if path.exists():
        try:
            slide.shapes.add_picture(str(path), 0, 0, width=width, height=height)
            return
        except Exception:
            pass
    _rect(slide, 0, 0, width, height, fallback_color)


def _custom_end_with_background(prs: Presentation, *, logo_bytes: Optional[bytes]):
    slide = _blank(prs)
    _add_full_slide_image(slide, CUSTOM_END_BG_PATH, prs.slide_width, prs.slide_height, fallback_color=CUST_COVER_BG)
    _custom_logo(slide, logo_bytes, Inches(16.35), Inches(0.72), Inches(2.25), Inches(0.42))
    _text(slide, "谢谢观看", Inches(0.62), Inches(2.94), Inches(5.3), Inches(0.92),
          font_size=72, bold=True, color=C_WHITE)
    _text(slide, "THANK  YOU  FOR  WATCHING", Inches(0.68), Inches(4.22), Inches(8.2), Inches(0.52),
          font_size=42, color=C_WHITE)
    return slide


def _draw_cover_illustration(slide):
    _circle(slide, Inches(11.6), Inches(2.0), Inches(5.7), RGBColor(0xB7, 0xE1, 0xF4), opacity=0.55)
    _circle(slide, Inches(12.0), Inches(2.55), Inches(4.55), RGBColor(0xC9, 0xED, 0xF5), opacity=0.45)
    for i, (x, h, color) in enumerate([
        (13.0, 4.6, RGBColor(0x0E, 0x83, 0xCC)),
        (13.8, 3.8, RGBColor(0x14, 0xD0, 0xB6)),
        (14.6, 3.0, RGBColor(0x0E, 0xA5, 0xE9)),
        (15.4, 2.45, RGBColor(0x16, 0xD1, 0xC4)),
        (16.2, 2.0, RGBColor(0x0B, 0x8D, 0xCD)),
        (17.0, 1.65, RGBColor(0x14, 0xD0, 0xB6)),
    ]):
        _round_rect(slide, Inches(x), Inches(7.7 - h), Inches(0.62), Inches(h), color)
        _circle(slide, Inches(x), Inches(7.7 - h - 0.03), Inches(0.62), color)
    _rect(slide, Inches(13.05), Inches(2.24), Inches(0.42), Inches(0.34), RGBColor(0xF2, 0xC8, 0x3D))
    _circle(slide, Inches(12.92), Inches(2.28), Inches(0.22), RGBColor(0xF2, 0xC8, 0x3D))
    _circle(slide, Inches(13.38), Inches(2.28), Inches(0.22), RGBColor(0xF2, 0xC8, 0x3D))
    _rect(slide, Inches(13.22), Inches(2.58), Inches(0.08), Inches(0.34), RGBColor(0xD9, 0x9D, 0x20))
    _rect(slide, Inches(13.08), Inches(2.9), Inches(0.36), Inches(0.08), RGBColor(0xD9, 0x9D, 0x20))
    _rect(slide, Inches(12.35), Inches(3.1), Inches(0.04), Inches(3.5), RGBColor(0x7E, 0xCF, 0xE6), opacity=0.7)
    _text(slide, "↗", Inches(12.2), Inches(3.45), Inches(2.0), Inches(1.4), font_size=36, color=RGBColor(0x7E, 0xCF, 0xE6), align=PP_ALIGN.CENTER)
    _draw_person(slide, Inches(12.45), Inches(7.15), RGBColor(0x2E, 0x5D, 0x8B))
    _draw_person(slide, Inches(16.35), Inches(7.18), RGBColor(0xB8, 0x66, 0xA9))
    _draw_person(slide, Inches(17.75), Inches(6.35), RGBColor(0x38, 0xB9, 0x73))


def _draw_person(slide, left, top, color):
    _circle(slide, left + Inches(0.2), top - Inches(0.48), Inches(0.22), RGBColor(0xF0, 0xB8, 0xA8))
    _rect(slide, left + Inches(0.18), top - Inches(0.25), Inches(0.22), Inches(0.65), color)
    _rect(slide, left + Inches(0.0), top + Inches(0.34), Inches(0.16), Inches(0.75), RGBColor(0x24, 0x3B, 0x5A))
    _rect(slide, left + Inches(0.36), top + Inches(0.34), Inches(0.16), Inches(0.75), RGBColor(0x24, 0x3B, 0x5A))


def _clone_template_slide(prs: Presentation, src_slide):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    sp_tree = slide.shapes._spTree
    for shape in list(slide.shapes):
        sp_tree.remove(shape.element)

    relmap: Dict[str, str] = {}
    for rel in src_slide.part.rels.values():
        if rel.reltype == RT.SLIDE_LAYOUT or "notesSlide" in rel.reltype:
            continue
        target = rel.target_ref if rel.is_external else rel.target_part
        relmap[rel.rId] = slide.part.rels._add_relationship(rel.reltype, target, rel.is_external)

    for shape in src_slide.shapes:
        element = deepcopy(shape.element)
        for node in element.iter():
            for attr, val in list(node.attrib.items()):
                if val in relmap:
                    node.set(attr, relmap[val])
        sp_tree.insert_element_before(element, "p:extLst")
    return slide


def _iter_template_shapes(shapes):
    for shape in shapes:
        yield shape
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_template_shapes(shape.shapes)


def _shape_by_name(slide, name: str):
    return next((s for s in _iter_template_shapes(slide.shapes) if getattr(s, "name", "") == name), None)


def _shapes_by_name(slide, name: str) -> List[Any]:
    return [s for s in _iter_template_shapes(slide.shapes) if getattr(s, "name", "") == name]


def _replace_template_text(
    slide,
    name: str,
    text: str,
    *,
    max_len: Optional[int] = None,
    font_size: Optional[float] = None,
    word_wrap: bool = True,
    line_spacing: Optional[float] = None,
    auto_size: Optional[int] = None,
):
    shape = _shape_by_name(slide, name)
    if shape is None or not hasattr(shape, "text_frame"):
        return
    if max_len is not None:
        text = _shrink_cn(str(text or ""), max_len) if max_len <= 12 else _shrink(str(text or ""), max_len)
    _set_shape_text(shape, text, font_size=font_size, word_wrap=word_wrap, line_spacing=line_spacing, auto_size=auto_size)


def _set_shape_text(
    shape,
    text: str,
    *,
    font_size: Optional[float] = None,
    word_wrap: bool = True,
    line_spacing: Optional[float] = None,
    color: Optional[RGBColor] = None,
    auto_size: Optional[int] = None,
):
    tf = shape.text_frame
    tf.word_wrap = word_wrap
    tf.auto_size = auto_size if auto_size is not None else MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    tf.margin_left = Inches(0.05)
    tf.margin_right = Inches(0.05)
    tf.margin_top = Inches(0.03)
    tf.margin_bottom = Inches(0.03)
    p = tf.paragraphs[0]
    if line_spacing and font_size:
        p.line_spacing = Pt(float(font_size) * float(line_spacing))
    if p.runs:
        p.runs[0].text = str(text or "")
        for run in p.runs[1:]:
            run.text = ""
    else:
        run = p.add_run()
        run.text = str(text or "")
    for para in tf.paragraphs:
        for run in para.runs:
            run.font.name = PPT_FONT
            if font_size:
                run.font.size = Pt(font_size)
            if color is not None:
                run.font.color.rgb = color


def _replace_template_logos(slide, logo_bytes: Optional[bytes]):
    for shape in _shapes_by_name(slide, "PH_LOGO"):
        if hasattr(shape, "text_frame"):
            _set_shape_text(shape, "")
        if not logo_bytes:
            try:
                shape.fill.background()
            except Exception:
                pass
            try:
                shape.line.fill.background()
            except Exception:
                pass
            continue
        try:
            slide.shapes.add_picture(
                io.BytesIO(logo_bytes),
                shape.left,
                shape.top,
                width=shape.width,
                height=shape.height,
            )
        except Exception:
            pass


def _add_cover_logo_if_needed(slide, logo_bytes: Optional[bytes]):
    if not logo_bytes:
        return
    try:
        slide.shapes.add_picture(
            io.BytesIO(logo_bytes),
            Inches(16.95),
            Inches(0.78),
            width=Inches(2.25),
            height=Inches(0.42),
        )
    except Exception:
        pass


def _shrink_cn(text: str, max_len: int) -> str:
    s = re.sub(r"\s+", "", str(text or "").strip())
    s = s.replace("。", "").replace("，", "，")
    return s if len(s) <= max_len else s[:max_len]


def _clean_custom_heading(text: str) -> str:
    s = re.sub(r"\s+", "", str(text or "").strip())
    return s.replace("……", "").replace("...", "").replace("…", "")


def _humanize_custom_field(field: str) -> str:
    raw = str(field or "").strip()
    lower = raw.lower()
    mapping = [
        ("supplier", "供应商"),
        ("project", "项目"),
        ("purchase", "采购"),
        ("spend", "支出"),
        ("expense", "支出"),
        ("amount", "金额"),
        ("count", "数量"),
        ("new", "新增"),
        ("large", "大型"),
        ("market", "市场"),
        ("month", "月份"),
        ("sales", "销售"),
        ("revenue", "收入"),
        ("cost", "成本"),
        ("profit", "利润"),
    ]
    words = [w for w in re.split(r"[_\s/\\-]+", lower) if w]
    translated = []
    for w in words:
        hit = next((cn for key, cn in mapping if key == w or key in w), "")
        if hit and hit not in translated:
            translated.append(hit)
    if translated:
        label = "".join(translated)
        if label.endswith("数量数量"):
            label = label[:-2]
        return _shrink(label, 14)
    return _shrink(raw.replace("_", " "), 18)


def _custom_digest_for_pair(pair) -> dict:
    if not pair:
        return {}
    ast_msg = pair[1] if len(pair) > 1 else None
    ex = (ast_msg.extras or {}) if ast_msg else {}
    digest = ex.get("__custom_digest") or ex.get("custom_ppt_digest") or {}
    return digest if isinstance(digest, dict) else {}


def _custom_summary_content_from_digest(digest: dict, summary_md: str, sections: List[dict]) -> Tuple[str, str, List[str], str]:
    summary = digest.get("summary") if isinstance(digest, dict) else {}
    if isinstance(summary, dict):
        title = str(summary.get("title") or "").strip()
        desc = str(summary.get("description") or "").strip()
        points = [str(x) for x in (summary.get("points") or []) if str(x).strip()]
        conclusion = str(summary.get("conclusion") or "").strip()
        if title and desc and conclusion:
            while len(points) < 4:
                points.append(desc)
            return (
                _clean_custom_heading(_shrink_cn(title, 10)),
                _shrink(desc, 320),
                [_shrink(p, 320) for p in points[:4]],
                _shrink(conclusion, 320),
            )
    title, desc, points, final = _custom_summary_content(summary_md, sections)
    return _clean_custom_heading(_shrink_cn(title, 10)), _shrink(desc, 320), [_shrink(p, 320) for p in points[:4]], _shrink(final, 320)


def _custom_chart_template_slide(template: Presentation, chart: Optional[dict]):
    ctype = str((chart or {}).get("chart_type") or "table").lower()
    if ctype == "pie":
        return template.slides[4]
    if ctype == "table":
        return template.slides[6]
    return template.slides[5]


def _custom_table_charts_from_subquestions(subquestions: List[Any]) -> List[dict]:
    result: List[dict] = []
    for idx, subq in enumerate(subquestions[:5], start=1):
        if not isinstance(subq, dict):
            continue
        cols = subq.get("columns") or []
        rows = subq.get("rows") or []
        if not cols or not rows:
            continue
        sid = str(subq.get("id") or f"table_{idx}")
        result.append({
            "subquestion_id": f"table_{sid}",
            "chart_type": "table",
            "title": subq.get("question") or f"数据表 {idx}",
            "explain": subq.get("purpose") or f"{TABLE_CHART_SUBTITLE_CN} · {TABLE_CHART_SUBTITLE_EN}",
            "columns": cols,
            "rows": rows,
            "dimension_field": cols[0] if cols else None,
            "metric_fields": cols[1:3],
        })
    return result


def _fill_custom_chart_slide(
    slide, *, q_idx: int, chart_idx: int, summary_title: str, question_short: str, chart: Optional[dict],
    section: dict, digest: dict, include_chart: bool, theme: PptTheme, logo_bytes: Optional[bytes],
    chart_summary_index: Optional[int] = None,
):
    ctype = str((chart or {}).get("chart_type") or section.get("visual_type") or "table").lower()
    chart_summary = list(_custom_chart_summary(digest, chart, section, summary_index=chart_summary_index))
    if ctype == "table":
        chart_summary[1] = _bilingual_table_chart_subtitle(chart_summary[1])
    chart_summary = tuple(chart_summary)
    logger.info(
        "xlsx_qa.fill_custom_chart_slide q=%d c=%d cid=%s title=%s subtitle=%s analysis_preview=%s cards_count=%d cards=%s",
        q_idx, chart_idx,
        str((chart or {}).get("subquestion_id") or ""),
        str(chart_summary[0])[:40],
        str(chart_summary[1])[:60],
        str(chart_summary[2])[:120],
        len(chart_summary[3]) if isinstance(chart_summary[3], list) else 0,
        [(str(c.get("title",""))[:8], str(c.get("body",""))[:60]) for c in (chart_summary[3] or [])[:3] if isinstance(c, dict)],
    )
    _rewrite_template_static_labels(slide)
    _replace_template_text(slide, "PH_CHART_TITLE", _clean_custom_heading(question_short or summary_title), font_size=30, word_wrap=False)
    _replace_template_text(slide, "PH_CHART_SUBTITLE", chart_summary[1], max_len=150, font_size=8.5)
    _replace_template_logos(slide, logo_bytes)
    _retint_custom_slide(slide, theme)

    if ctype == "pie":
        chart_left, chart_top, chart_w, chart_h = Inches(1.0), Inches(2.2), Inches(8.9), Inches(5.75)
        text_left, text_top, text_w = Inches(10.7), Inches(2.45), Inches(7.55)
    else:
        chart_left, chart_top, chart_w, chart_h = Inches(1.0), Inches(1.95), Inches(17.9), Inches(5.65)
        text_left, text_top, text_w = Inches(1.2), Inches(8.15), Inches(17.2)

    if include_chart and chart:
        if ctype == "table":
            cols = (chart.get("columns") or [])[:MAX_TBL_COLS]
            rows = (chart.get("rows") or [])[:MAX_TBL_ROWS]
            if cols and rows:
                if len(rows) < 3:
                    _draw_custom_compact_table_cards(
                        slide, columns=cols, rows=rows, left=chart_left, top=chart_top,
                        width=chart_w, height=chart_h, theme=theme, max_rows=2,
                    )
                else:
                    _add_ppt_table(slide, columns=cols, rows=rows, left=chart_left, top=chart_top, width=chart_w, height=chart_h, theme=theme)
            else:
                _draw_chart_info_card(slide, chart, [], chart_left, chart_top, chart_w, chart_h, theme)
        elif ctype in _XL_MAP:
            ok = _add_native_chart(slide, chart_spec=chart, left=chart_left, top=chart_top, width=chart_w, height=chart_h, theme=theme)
            if not ok:
                _draw_chart_info_card(slide, chart, [], chart_left, chart_top, chart_w, chart_h, theme)
        else:
            _draw_chart_info_card(slide, chart, [], chart_left, chart_top, chart_w, chart_h, theme)
    else:
        _rect(slide, chart_left, chart_top, chart_w, chart_h, CUST_MINT)
        _text(slide, "本页无可视化数据", chart_left, Emu(chart_top + chart_h // 2 - Inches(0.2)), chart_w, Inches(0.4), font_size=18, bold=True, color=CUST_MUTED, align=PP_ALIGN.CENTER)

    is_few_row_table = ctype == "table" and chart and len(chart.get("rows") or []) < 3
    if is_few_row_table:
        _text(slide, _shrink(chart_summary[2], 480), text_left, Inches(7.9), text_w, Inches(1.28),
              font_size=13.2, bold=False, color=CUST_TEXT, auto_fit=True)
    else:
        _draw_custom_analysis_cards(
            slide,
            cards=chart_summary[3],
            fallback_text=chart_summary[2],
            left=text_left,
            top=text_top,
            width=text_w,
            theme=theme,
        )
    _text(slide, f"Q{q_idx:02d} · Chart {chart_idx:02d}", Inches(17.1), Inches(10.36), Inches(1.8), Inches(0.28), font_size=10, color=CUST_MUTED, align=PP_ALIGN.RIGHT)


def _relayout_custom_summary_text(slide):
    layout = {
        "PH_SUMMARY_DESC": (Inches(9.89), Inches(3.48), Inches(8.66), Inches(1.42)),
        "PH_SUMMARY_POINT_1": (Inches(9.89), Inches(4.94), Inches(8.66), Inches(1.42)),
        "PH_SUMMARY_POINT_2": (Inches(9.89), Inches(6.36), Inches(8.66), Inches(1.42)),
        "PH_SUMMARY_CONCLUSION": (Inches(10.95), Inches(8.02), Inches(7.72), Inches(0.86)),
    }
    for name, (left, top, width, height) in layout.items():
        shape = _shape_by_name(slide, name)
        if shape is not None:
            shape.left, shape.top, shape.width, shape.height = left, top, width, height


def _offslide_named_placeholder(slide, name: str) -> None:
    shape = _shape_by_name(slide, name)
    if shape is None:
        return
    try:
        _set_shape_text(shape, "")
        shape.left = Inches(-30)
    except Exception:
        pass


def _relayout_sales_summary_four(slide) -> None:
    """普通问答专属模板总览页：保持原模板占位尺寸（与 _relayout_custom_summary_text 一致）。"""
    desc = _shape_by_name(slide, "PH_SUMMARY_DESC")
    if desc is not None:
        desc.left, desc.top, desc.width, desc.height = (
            Inches(9.89), Inches(3.48), Inches(8.66), Inches(1.42),
        )
    concl = _shape_by_name(slide, "PH_SUMMARY_CONCLUSION")
    if concl is not None:
        concl.left, concl.top, concl.width, concl.height = (
            Inches(10.95), Inches(8.02), Inches(7.72), Inches(0.86),
        )


def _relayout_insight_summary_four(slide) -> None:
    desc = _shape_by_name(slide, "PH_SUMMARY_DESC")
    if desc is not None:
        desc.left, desc.top, desc.width, desc.height = (
            Inches(9.89), Inches(3.42), Inches(8.66), Inches(1.18),
        )
    concl = _shape_by_name(slide, "PH_SUMMARY_CONCLUSION")
    if concl is not None:
        # 与 tem.pptx 中 PH_SUMMARY_CONCLUSION 一致：左缘避开齿轮方块，文字落在右侧灰条卡内（勿与 9.89 正文列左对齐）
        concl.left, concl.top, concl.width, concl.height = (
            Inches(11.14), Inches(8.05), Inches(7.20), Inches(0.78),
        )


def _draw_insight_summary_point_grid(slide, points: List[str], theme: PptTheme) -> None:
    pts = [_shrink(str(p or ""), 300) for p in (list(points) + [""] * 4)][:4]
    x0 = Inches(9.89)
    w = Inches(4.12)
    h = Inches(1.16)
    gap_x = Inches(0.40)
    gap_y = Inches(0.18)
    y0 = Inches(4.68)
    for i, pt in enumerate(pts):
        r, c = divmod(i, 2)
        x = x0 + c * (w + gap_x)
        y = y0 + r * (h + gap_y)
        _round_rect(slide, x, y, w, h, RGBColor(0xF5, 0xFC, 0xFD))
        bar = theme.palette[i % len(theme.palette)]
        _rect(slide, x, y, Inches(0.075), h, bar)
        _text(
            slide, pt, x + Inches(0.22), y + Inches(0.12), w - Inches(0.36), h - Inches(0.22),
            font_size=12.5, color=CUST_TEXT, auto_fit=True, line_spacing=1.38,
        )


def _finalize_template_summary_four_points(
    slide,
    points: List[str],
    desc: str,
    conclusion: str,
    theme: PptTheme,
    *,
    layout: str = "sales",
) -> None:
    pts = [str(x) for x in points if str(x).strip()]
    while len(pts) < 4:
        pts.append(_shrink(desc or conclusion, 300))
    pts = pts[:4]
    _offslide_named_placeholder(slide, "PH_SUMMARY_POINT_1")
    _offslide_named_placeholder(slide, "PH_SUMMARY_POINT_2")
    if layout == "insight":
        _relayout_insight_summary_four(slide)
    else:
        _relayout_sales_summary_four(slide)
    _draw_insight_summary_point_grid(slide, pts, theme)


def _replace_custom_summary_image(slide, q_idx: int):
    placeholder = _shape_by_name(slide, "PH_SUMMARY_IMAGE")
    image_path = PPT_TEMPLATE_DIR / f"Q{q_idx}.png"
    if placeholder is None:
        return
    left, top, width, height = placeholder.left, placeholder.top, placeholder.width, placeholder.height
    try:
        placeholder.fill.background()
    except Exception:
        pass
    try:
        placeholder.line.fill.background()
    except Exception:
        pass
    if not image_path.exists():
        return
    try:
        slide.shapes.add_picture(str(image_path), left, top, width=width, height=height)
    except Exception:
        pass


def _retint_custom_slide(slide, theme: PptTheme):
    for shape in _iter_template_shapes(slide.shapes):
        _retint_shape_xml(shape, theme)
        _retint_shape_fill(shape, theme)
        _retint_shape_line(shape, theme)
        _strip_custom_template_line(shape)


def _strip_custom_template_line(shape):
    if getattr(shape, "has_chart", False):
        return
    try:
        shape.line.fill.background()
    except Exception:
        pass


def _retint_shape_xml(shape, theme: PptTheme):
    """Convert template scheme accent colors to fixed custom teal colors.

    The source PPT uses theme scheme colors for the red bars, icon block and
    footer decorations. python-pptx does not expose those as RGB, so we rewrite
    the underlying color nodes directly.
    """
    accent_hex = _rgb_hex(theme.accent)
    soft_hex = _rgb_hex(theme.accent_soft)
    footer_hex = "9ED7DF"
    footer_soft_hex = "D6F2F5"
    for node in shape.element.iter():
        if node.tag == qn("a:schemeClr") and node.get("val") in {"accent1", "accent2"}:
            val = node.get("val")
            if getattr(shape, "top", 0) >= Inches(8.0):
                replacement = footer_hex if val == "accent1" else footer_soft_hex
            else:
                replacement = accent_hex if val == "accent1" else soft_hex
            node.tag = qn("a:srgbClr")
            node.set("val", replacement)
        elif node.tag == qn("a:srgbClr"):
            rgb = node.get("val")
            if rgb and _is_reddish_rgb(rgb):
                node.set("val", footer_hex if getattr(shape, "top", 0) >= Inches(8.0) else accent_hex)


def _rgb_hex(color: RGBColor) -> str:
    return f"{int(color[0]):02X}{int(color[1]):02X}{int(color[2]):02X}"


def _retint_shape_fill(shape, theme: PptTheme):
    try:
        rgb = shape.fill.fore_color.rgb
    except Exception:
        return
    if not rgb:
        return
    if _is_reddish_rgb(rgb):
        try:
            shape.fill.fore_color.rgb = theme.accent if shape.top < Inches(2.0) else theme.accent_soft
        except Exception:
            pass


def _retint_shape_line(shape, theme: PptTheme):
    try:
        rgb = shape.line.color.rgb
    except Exception:
        return
    if not rgb:
        return
    if _is_reddish_rgb(rgb):
        try:
            shape.line.color.rgb = theme.accent
        except Exception:
            pass


def _is_reddish_rgb(rgb) -> bool:
    try:
        r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    except Exception:
        s = str(rgb)
        if len(s) != 6:
            return False
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    return r > 130 and g < 150 and b < 150 and r > g + 25


def _draw_custom_single_row_cards(
    slide, *, columns: List[str], row: List[Any], left, top, width, height, theme: PptTheme
):
    items = []
    for idx, col in enumerate(columns[:6]):
        value = row[idx] if idx < len(row) else None
        items.append((_humanize_custom_field(str(col)), _fmt_metric_value(value)))
    if not items:
        return

    cols_per_row = 2 if len(items) <= 2 else min(3, len(items))
    gap = Inches(0.26)
    card_w = (width - gap * (cols_per_row - 1)) // cols_per_row
    card_h = Inches(1.34)
    total_rows = (len(items) + cols_per_row - 1) // cols_per_row
    grid_h = total_rows * card_h + max(total_rows - 1, 0) * Inches(0.28)
    start_top = top + max(Inches(0.18), (height - grid_h) // 2)

    for idx, (label, value) in enumerate(items):
        r = idx // cols_per_row
        c = idx % cols_per_row
        x = left + c * (card_w + gap)
        y = start_top + r * (card_h + Inches(0.28))
        _custom_metric_card(slide, label=label, value=value, left=x, top=y, width=card_w, height=card_h, theme=theme)


def _draw_custom_compact_table_cards(
    slide,
    *,
    columns: List[str],
    rows: List[list],
    left,
    top,
    width,
    height,
    theme: PptTheme,
    max_rows: int = 2,
):
    use_rows = rows[:max_rows]
    if not use_rows:
        return
    n = len(use_rows)
    gap = Inches(0.14) if n > 1 else Inches(0)
    band_h = (height - gap * (n - 1)) // n
    for ri, row in enumerate(use_rows):
        band_top = top + ri * (band_h + gap)
        _draw_custom_single_row_cards(
            slide, columns=columns, row=row, left=left, top=band_top, width=width, height=band_h, theme=theme,
        )


def _bilingual_table_chart_subtitle(existing: str) -> str:
    s = (existing or "").strip()
    if not s or "明细" in s or "证据" in s:
        return f"{TABLE_CHART_SUBTITLE_CN} · {TABLE_CHART_SUBTITLE_EN}"
    return s


def _custom_metric_card(slide, *, label: str, value: str, left, top, width, height, theme: PptTheme):
    _round_rect(slide, left, top, width, height, RGBColor(0xF5, 0xFC, 0xFD))
    _rect(slide, left, top, width, Inches(0.055), theme.accent)
    _circle(slide, Emu(left + width - Inches(0.46)), top + Inches(0.12), Inches(0.28), RGBColor(0xCF, 0xF1, 0xF5), opacity=0.95)
    _text(slide, label, left + Inches(0.32), top + Inches(0.19), width - Inches(0.7), Inches(0.28),
          font_size=12.6, bold=True, color=theme.accent_dark, align=PP_ALIGN.CENTER, auto_fit=True)
    _text(slide, value, left + Inches(0.32), top + Inches(0.60), width - Inches(0.64), Inches(0.56),
          font_size=28, bold=True, color=theme.accent_dark, align=PP_ALIGN.CENTER, auto_fit=True)


def _draw_custom_analysis_cards(slide, *, cards: List[dict], fallback_text: str, left, top, width, theme: PptTheme):
    normalized = [c for c in cards if isinstance(c, dict) and (c.get("title") or c.get("body"))][:3]
    if len(normalized) < 3:
        chunks = _split_analysis_text(fallback_text)
        labels = ["趋势", "对比", "结论"]
        for idx in range(len(normalized), 3):
            normalized.append({"title": labels[idx], "body": chunks[idx] if idx < len(chunks) else fallback_text})

    narrow = width < Inches(10)
    gap = Inches(0.16 if not narrow else 0.12)
    card_w = width if narrow else (width - gap * 2) // 3
    card_h = Inches(1.92 if not narrow else 1.36)
    fills = [RGBColor(0xF1, 0xFB, 0xFC), theme.accent, RGBColor(0xF1, 0xFB, 0xFC)]
    title_colors = [theme.accent_dark, C_WHITE, theme.accent_dark]
    body_colors = [CUST_TEXT, C_WHITE, CUST_TEXT]
    for idx, card in enumerate(normalized[:3]):
        x = left if narrow else left + idx * (card_w + gap)
        y = top + idx * (card_h + gap) if narrow else top
        _round_rect(slide, x, y, card_w, card_h, fills[idx])
        if idx != 1:
            _rect(slide, x, y, Inches(0.055), card_h, theme.accent, opacity=0.8)
        _text(slide, str(card.get("title") or f"分析{idx + 1}")[:8],
              x + Inches(0.26), y + Inches(0.16), card_w - Inches(0.52), Inches(0.28),
              font_size=13.4, bold=True, color=title_colors[idx], align=PP_ALIGN.CENTER, auto_fit=True)
        _text(slide, str(card.get("body") or ""),
              x + Inches(0.32), y + Inches(0.58), card_w - Inches(0.64), card_h - Inches(0.70),
              font_size=15, color=body_colors[idx], align=PP_ALIGN.LEFT, auto_fit=True, line_spacing=1.4)


def _split_analysis_text(text: str) -> List[str]:
    s = str(text or "").strip()
    parts = [p.strip() for p in re.split(r"[。；;]\s*", s) if p.strip()]
    if len(parts) >= 3:
        return parts[:3]
    if not s:
        return ["请结合图表查看趋势变化", "关注主要类别的差异", "用于辅助业务判断"]
    chunk = max(1, len(s) // 3)
    return [s[i:i + chunk] for i in range(0, len(s), chunk)][:3]


def _tuple_from_chart_summary_item(item_cs: dict, chart: Optional[dict], section: dict) -> Tuple[str, str, str, List[dict]]:
    cid = str(chart.get("subquestion_id") or "") if chart else ""
    title = str(item_cs.get("title") or (chart or {}).get("title") or section.get("title") or "数据洞察")
    subtitle = str(item_cs.get("description") or (chart or {}).get("explain") or "")
    analysis = str(item_cs.get("analysis") or item_cs.get("conclusion") or section.get("conclusion") or subtitle).strip()
    blurb = _insight_chart_data_blurb(chart or {})
    if blurb and blurb not in analysis:
        analysis = _shrink(f"{analysis} {blurb}", 480).strip() if analysis else blurb
    elif not analysis:
        analysis = _shrink(blurb or section.get("conclusion") or subtitle, 480)
    cards = item_cs.get("cards") if isinstance(item_cs.get("cards"), list) else []
    if not cards:
        points = [str(x) for x in (item_cs.get("points") or []) if str(x).strip()]
        if not points:
            points = [str(x) for x in (section.get("bullets") or []) if str(x).strip()]
        cards = [{"title": f"要点{i + 1}", "body": p} for i, p in enumerate(points[:3])]
    else:
        bodies = [str((c or {}).get("body") or "").strip() for c in cards[:3] if isinstance(c, dict)]
        if len(bodies) >= 2 and bodies and len(set(bodies)) == 1:
            logger.warning(
                "xlsx_qa.tuple_from_chart_summary DUPLICATE_CARDS chart=%s bodies_count=%d unique=%d",
                cid, len(bodies), len(set(bodies)),
            )
            parts = _split_analysis_text(analysis or bodies[0])
            cards = [{"title": f"要点{i + 1}", "body": _shrink(parts[i], 200)} for i in range(min(3, len(parts)))]
            while len(cards) < 3:
                cards.append({"title": f"要点{len(cards) + 1}", "body": _shrink(analysis, 200)})
    if chart:
        llm_analysis = str(item_cs.get("analysis") or "").strip()
        llm_cards = item_cs.get("cards") if isinstance(item_cs.get("cards"), list) else []
        has_llm_analysis = len(llm_analysis) > 60  # meaningful business insight, not just placeholder
        has_llm_cards = len(llm_cards) >= 2
        if not has_llm_analysis:
            analysis = _chart_specific_analysis_text(chart, analysis)
        if not has_llm_cards:
            cards = _chart_specific_analysis_cards(chart)

        # Detailed per-chart debug log
        card_previews = [
            f"{str(c.get('title',''))[:6]}:{str(c.get('body',''))[:60]}"
            for c in cards[:3] if isinstance(c, dict)
        ]
        logger.info(
            "xlsx_qa.tuple_from_chart_summary chart=%s has_llm_analysis=%s (len=%d) has_llm_cards=%s (count=%d) "
            "final_analysis_preview=%s cards=%s section_conclusion=%s",
            cid, has_llm_analysis, len(llm_analysis), has_llm_cards, len(llm_cards),
            analysis[:100], card_previews, str(section.get("conclusion") or "")[:80],
        )
    return _clean_custom_heading(_shrink_cn(title, 12)), _shrink(subtitle, 150), _shrink(analysis, 480), cards[:3]


def _custom_chart_summary(
    digest: dict,
    chart: Optional[dict],
    section: dict,
    *,
    summary_index: Optional[int] = None,
) -> Tuple[str, str, str, List[dict]]:
    """Chat 路径和 Insight 路径共用入口，但匹配逻辑不同：
    - Chat 路径：digest 含完整 chart_summaries，summary_index=None，按 chart_id 匹配。
    - Insight 路径：digest 由 _insight_digest_for_chart_slide 预选好单条（列表长度≤1），直接取用。
    """
    cid = str((chart or {}).get("subquestion_id") or "").strip()
    items = digest.get("chart_summaries") if isinstance(digest, dict) else []
    if isinstance(items, list) and items:
        # A) Insight 路径：列表已预选为 1 条，直接取
        if len(items) == 1 and isinstance(items[0], dict):
            return _tuple_from_chart_summary_item(items[0], chart, section)

        # B) Chat 路径：按 chart_id 精确匹配
        if cid:
            for cs in items:
                if isinstance(cs, dict) and str(cs.get("chart_id") or "").strip() == cid:
                    return _tuple_from_chart_summary_item(cs, chart, section)

        # C) 按 summary_index 兜底
        if summary_index is not None and 0 <= summary_index < len(items):
            cand = items[summary_index]
            if isinstance(cand, dict):
                return _tuple_from_chart_summary_item(cand, chart, section)

    # D) 完全无模型数据：用图表自身字段生成独立内容（不用 section["bullets"] 避免维度级雷同）
    title = str((chart or {}).get("title") or section.get("title") or "数据洞察")
    subtitle = str((chart or {}).get("explain") or section.get("axis_note") or "")
    blurb = _insight_chart_data_blurb(chart or {})
    conclusion = subtitle or blurb or str(section.get("conclusion") or "请结合图表查看当前问题的主要数据表现。")
    if blurb and blurb not in conclusion:
        conclusion = _shrink(f"{conclusion} {blurb}", 480)
    chart_analysis = _chart_specific_analysis_text(chart or {}, conclusion)
    cards = _chart_specific_analysis_cards(chart or {})
    return _clean_custom_heading(_shrink_cn(title, 12)), _shrink(subtitle, 150), _shrink(chart_analysis, 480), cards


def _custom_slide(prs, *, logo_bytes: Optional[bytes] = None):
    slide = _blank(prs)
    _rect(slide, 0, 0, CUST_W, CUST_H, C_WHITE)
    return slide


def _custom_logo(slide, logo_bytes: Optional[bytes], left, top, width, height):
    if logo_bytes:
        try:
            slide.shapes.add_picture(io.BytesIO(logo_bytes), left, top, width=width, height=height)
            return
        except Exception:
            pass


def _custom_header(slide, title: str, subtitle: str = "", *, logo_bytes: Optional[bytes] = None):
    _custom_logo(slide, logo_bytes, CUST_W - Inches(3.15), Inches(0.78), Inches(2.25), Inches(0.42))
    _rect(slide, Inches(0.7), Inches(0.86), Inches(0.13), Inches(0.55), CUST_GREEN)
    _rect(slide, Inches(0.92), Inches(0.86), Inches(0.08), Inches(0.55), CUST_MINT_2)
    _text(slide, title[:34], Inches(1.14), Inches(0.68), Inches(7.6), Inches(0.55), font_size=24, bold=True, color=CUST_TEXT, auto_fit=True)
    if subtitle:
        _text(slide, subtitle[:70], Inches(1.14), Inches(1.38), Inches(7.2), Inches(0.28), font_size=10.5, color=CUST_MUTED, auto_fit=True)


def _custom_cover(prs, *, author: Optional[str], generated_at: datetime, logo_bytes: Optional[bytes]):
    slide = _custom_slide(prs, logo_bytes=logo_bytes)
    _rect(slide, 0, 0, CUST_W, CUST_H, CUST_GREEN)
    _rect(slide, 0, Inches(8.1), CUST_W, Inches(3.15), CUST_MINT)
    _rect(slide, Inches(1.65), Inches(3.48), Inches(8.9), Inches(0.32), CUST_GREEN_2)
    _text(slide, "数据洞察报告", Inches(1.65), Inches(3.02), Inches(9.0), Inches(1.0), font_size=60, bold=True, color=C_TITLE_NAVY)
    _text(slide, "Data Insight Report", Inches(1.72), Inches(4.28), Inches(8.5), Inches(0.35), font_size=32, color=C_WHITE)
    _rect(slide, Inches(1.65), Inches(6.7), Inches(4.0), Inches(0.03), C_WHITE, opacity=0.7)
    _text(slide, f"汇报人：{author or '—'}", Inches(1.65), Inches(7.1), Inches(4.8), Inches(0.38), font_size=24, color=C_WHITE)
    _text(slide, f"汇报时间：{generated_at.strftime('%Y-%m-%d %H:%M')}", Inches(1.65), Inches(7.65), Inches(5.6), Inches(0.38), font_size=24, color=C_WHITE)
    _custom_logo(slide, logo_bytes, Inches(1.0), Inches(0.78), Inches(2.25), Inches(0.42))


def _custom_toc(prs, *, pairs, logo_bytes: Optional[bytes]):
    slide = _custom_slide(prs, logo_bytes=logo_bytes)
    _custom_logo(slide, logo_bytes, CUST_W - Inches(3.15), Inches(0.78), Inches(2.25), Inches(0.42))
    _rect(slide, 0, Inches(3.25), Inches(13.9), Inches(4.8), CUST_MINT)
    _rect(slide, Inches(10.4), Inches(3.25), Inches(9.6), Inches(4.8), CUST_GREEN)
    _text(slide, "Content 目录", Inches(1.1), Inches(1.25), Inches(5.3), Inches(0.9), font_size=34, bold=True, color=CUST_TEXT)
    for i in range(5):
        y = Inches(3.96 + i * 0.9)
        label = _custom_question_short((pairs[i][0].content if i < len(pairs) and pairs[i][0] else "") or "其他")
        color = C_WHITE if i < len(pairs) else RGBColor(0xB7, 0xCD, 0xC7)
        _text(slide, f"{i + 1:02d}", Inches(13.1), y, Inches(0.8), Inches(0.36), font_size=20, bold=True, color=color, align=PP_ALIGN.CENTER)
        _text(slide, label if i < len(pairs) else "其他", Inches(14.1), Emu(y - Inches(0.02)), Inches(5.1), Inches(0.38), font_size=21, color=color)


def _custom_question_intro(prs, *, idx: int, question: str, summary_md: str, sections: List[dict], logo_bytes: Optional[bytes]):
    slide = _custom_slide(prs, logo_bytes=logo_bytes)
    _, desc, _, _ = _custom_summary_content(summary_md, sections)
    _rect(slide, 0, Inches(7.78), CUST_W, Inches(3.47), CUST_GREEN)
    _text(slide, f"{idx:02d}", Inches(8.95), Inches(1.8), Inches(2.1), Inches(1.55), font_size=56, bold=True, color=CUST_GREEN, align=PP_ALIGN.CENTER)
    _text(slide, _custom_question_short(question), Inches(3.8), Inches(3.75), Inches(12.4), Inches(0.75), font_size=32, bold=True, color=CUST_TEXT, align=PP_ALIGN.CENTER)
    _rect(slide, Inches(4.18), Inches(5.28), Inches(11.65), Inches(0.82), CUST_MINT)
    _text(slide, desc, Inches(4.35), Inches(5.44), Inches(11.3), Inches(0.38), font_size=14, color=CUST_MUTED, auto_fit=True, align=PP_ALIGN.CENTER)
    _round_rect(slide, Inches(7.8), Inches(8.18), Inches(4.4), Inches(0.72), CUST_MINT)
    _text(slide, f"PART1 {idx:02d}", Inches(8.42), Inches(8.32), Inches(3.2), Inches(0.34), font_size=18, bold=True, color=CUST_GREEN, align=PP_ALIGN.CENTER)
    _custom_logo(slide, logo_bytes, Inches(1.0), Inches(0.78), Inches(2.25), Inches(0.42))


def _custom_summary(prs, *, idx: int, question: str, summary_md: str, sections: List[dict], logo_bytes: Optional[bytes]):
    slide = _custom_slide(prs, logo_bytes=logo_bytes)
    _custom_header(slide, _custom_question_short(question), "Overview of the data insight", logo_bytes=logo_bytes)
    _rect(slide, Inches(1.14), Inches(2.28), Inches(8.25), Inches(6.5), CUST_MINT)
    _circle(slide, Inches(4.45), Inches(4.1), Inches(1.75), CUST_GREEN, opacity=0.18)
    _text(slide, "SUMMARY", Inches(2.8), Inches(5.02), Inches(5.1), Inches(0.45), font_size=19, bold=True, color=CUST_GREEN, align=PP_ALIGN.CENTER)

    title, desc, points, conclusion = _custom_summary_content(summary_md, sections)
    _text(slide, title, Inches(9.9), Inches(2.72), Inches(7.1), Inches(0.48), font_size=22, bold=True, color=CUST_TEXT)
    _text(slide, desc, Inches(9.9), Inches(3.45), Inches(8.2), Inches(0.82), font_size=14, color=CUST_MUTED, auto_fit=True)
    for i, point in enumerate(points[:4], start=1):
        r, c = divmod(i - 1, 2)
        x = Inches(9.9) + c * Inches(4.35)
        y = Inches(4.42) + r * Inches(1.38)
        _round_rect(slide, x, y, Inches(0.5), Inches(0.5), CUST_GREEN)
        _text(slide, str(i), x, Emu(y + Inches(0.06)), Inches(0.5), Inches(0.22), font_size=11, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
        _text(slide, _shrink(point, 52), x + Inches(0.56), Emu(y - Inches(0.02)), Inches(3.65), Inches(0.82), font_size=13, color=CUST_TEXT, auto_fit=True)
    _text(slide, _shrink(conclusion, 72), Inches(11.9), Inches(7.72), Inches(8.1), Inches(0.55), font_size=14, color=CUST_TEXT, auto_fit=True)
    _rect(slide, 0, Inches(10.84), CUST_W, Inches(0.41), CUST_GREEN)


def _custom_chart_page(
    prs, *, q_idx: int, chart_idx: int, question: str, chart: Optional[dict],
    section: dict, include_chart: bool, theme: PptTheme, logo_bytes: Optional[bytes],
):
    slide = _custom_slide(prs, logo_bytes=logo_bytes)
    chart_type = str((chart or {}).get("chart_type") or section.get("visual_type") or "table").lower()
    ctype_cn = {
        "pie": "结构占比",
        "bar": "柱状对比",
        "line": "趋势变化",
        "table": f"{TABLE_CHART_SUBTITLE_CN} · {TABLE_CHART_SUBTITLE_EN}",
    }.get(chart_type, "数据洞察")
    title = chart.get("title") if chart else ""
    _custom_header(slide, _shrink(title or section.get("title") or _custom_question_short(question), 34), ctype_cn, logo_bytes=logo_bytes)

    if chart_type == "pie":
        chart_left, chart_top, chart_w, chart_h = Inches(1.15), Inches(2.05), Inches(8.6), Inches(6.4)
        text_left, text_top, text_w = Inches(10.55), Inches(2.55), Inches(7.6)
    else:
        chart_left, chart_top, chart_w, chart_h = Inches(1.15), Inches(1.95), Inches(17.7), Inches(5.55)
        text_left, text_top, text_w = Inches(1.35), Inches(7.88), Inches(17.1)

    _rect(slide, chart_left, chart_top, chart_w, chart_h, C_WHITE)
    if include_chart and chart:
        if chart_type == "table":
            cols = (chart.get("columns") or [])[:MAX_TBL_COLS]
            rows = (chart.get("rows") or [])[:MAX_TBL_ROWS]
            if cols and rows:
                if len(rows) < 3:
                    _draw_custom_compact_table_cards(
                        slide, columns=cols, rows=rows,
                        left=Emu(chart_left + Inches(0.1)), top=Emu(chart_top + Inches(0.1)),
                        width=Emu(chart_w - Inches(0.2)), height=Emu(chart_h - Inches(0.2)),
                        theme=theme, max_rows=2,
                    )
                else:
                    _add_ppt_table(
                        slide, columns=cols, rows=rows,
                        left=Emu(chart_left + Inches(0.1)), top=Emu(chart_top + Inches(0.1)),
                        width=Emu(chart_w - Inches(0.2)), height=Emu(chart_h - Inches(0.2)),
                        theme=theme,
                    )
            else:
                _draw_chart_info_card(slide, chart, [], chart_left, chart_top, chart_w, chart_h, theme)
        elif chart_type in _XL_MAP:
            ok = _add_native_chart(slide, chart_spec=chart, left=Emu(chart_left + Inches(0.12)), top=Emu(chart_top + Inches(0.12)), width=Emu(chart_w - Inches(0.24)), height=Emu(chart_h - Inches(0.24)), theme=theme)
            if not ok:
                _draw_chart_info_card(slide, chart, [], chart_left, chart_top, chart_w, chart_h, theme)
        else:
            _draw_chart_info_card(slide, chart, [], chart_left, chart_top, chart_w, chart_h, theme)
    else:
        _rect(slide, chart_left, chart_top, chart_w, chart_h, CUST_MINT)
        _text(slide, "本页无可视化数据", chart_left, Emu(chart_top + chart_h // 2 - Inches(0.2)), chart_w, Inches(0.4), font_size=18, bold=True, color=CUST_MUTED, align=PP_ALIGN.CENTER)

    _rect(slide, text_left, text_top, Inches(0.12), Inches(1.85), CUST_GREEN)
    _text(slide, _shrink(section.get("conclusion") or "请结合图表查看当前问题的主要数据表现。", 92), Emu(text_left + Inches(0.35)), text_top, text_w, Inches(0.46), font_size=17, bold=True, color=CUST_TEXT, auto_fit=True)
    bullets = [str(x) for x in (section.get("bullets") or []) if str(x).strip()][:2]
    if not bullets and chart and chart.get("explain"):
        bullets = [str(chart.get("explain"))]
    _bullets(slide, bullets=[_shrink(b, 72) for b in bullets[:2]], left=Emu(text_left + Inches(0.35)), top=Emu(text_top + Inches(0.72)), width=text_w, height=Inches(0.9), font_size=13.5, color=CUST_TEXT, accent=CUST_GREEN)
    _text(slide, f"Q{q_idx:02d} · Chart {chart_idx:02d}", Inches(17.1), Inches(10.36), Inches(1.8), Inches(0.28), font_size=10, color=CUST_MUTED, align=PP_ALIGN.RIGHT)
    _rect(slide, 0, Inches(10.84), CUST_W, Inches(0.41), CUST_GREEN)


def _custom_end(prs, *, logo_bytes: Optional[bytes]):
    slide = _custom_slide(prs, logo_bytes=logo_bytes)
    _rect(slide, 0, 0, CUST_W, CUST_H, CUST_GREEN)
    _text(slide, "谢谢观看", Inches(0.9), Inches(3.5), Inches(8.3), Inches(1.2), font_size=48, bold=True, color=C_WHITE)
    _text(slide, "THANK YOU FOR WATCHING", Inches(1.0), Inches(5.12), Inches(10.6), Inches(0.62), font_size=19, color=C_WHITE)
    _custom_logo(slide, logo_bytes, Inches(1.0), Inches(0.78), Inches(2.25), Inches(0.42))
    _rect(slide, Inches(10.4), Inches(9.15), Inches(9.6), Inches(1.65), CUST_MINT)


def _custom_question_short(question: str) -> str:
    s = _strip_md(str(question or "")).strip()
    s = re.sub(r"[？?。！!，,、：:；;（）()【】\\[\\]\"'“”‘’]", "", s)
    s = re.sub(r"\s+", "", s)
    for prefix in ("请问", "帮我看一下", "帮我看看", "分析一下", "统计一下"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return (s[:10] or "数据洞察")


def _custom_summary_content(summary_md: str, sections: List[dict]) -> Tuple[str, str, List[str], str]:
    first = sections[0] if sections else {}
    conclusion, findings = _extract_conclusion_findings(summary_md)
    title = _shrink(str(first.get("title") or _custom_question_short(conclusion) or "核心结论"), 10)
    desc = _shrink(str(first.get("conclusion") or conclusion or "当前问题已生成可用于汇报的业务结论。"), 78)
    points = [str(x) for x in (first.get("bullets") or []) if str(x).strip()]
    if len(points) < 4:
        for f in findings:
            if f not in points:
                points.append(f)
            if len(points) >= 4:
                break
    while len(points) < 4:
        points.append(desc)
    final = _shrink(conclusion or desc, 82)
    return title, desc, points[:4], final


def _custom_section_for_chart(chart: Optional[dict], sections: List[dict], idx: int) -> dict:
    if chart:
        cid = str(chart.get("subquestion_id") or "")
        for sec in sections:
            if cid and str(sec.get("chart_id") or "") == cid:
                return sec
    if sections:
        return sections[min(idx - 1, len(sections) - 1)]
    return {
        "title": (chart or {}).get("title") or "关键洞察",
        "visual_type": (chart or {}).get("chart_type") or "table",
        "conclusion": (chart or {}).get("explain") or "请结合图表查看当前问题的主要数据表现。",
        "bullets": [],
    }


def _replace_cover_text(slide, old: str, new: str, *, color: Optional[RGBColor] = None) -> None:
    for shape in _iter_template_shapes(slide.shapes):
        if not getattr(shape, "has_text_frame", False):
            continue
        text = "".join(p.text for p in shape.text_frame.paragraphs).strip()
        if text == old:
            _set_shape_text(shape, new, color=color)


def _rewrite_template_static_labels(slide) -> None:
    """将模板中写死的「证据/证明明细」等副标题统一为数据图表洞察双语文案。"""
    repl = {
        "证明明细": f"{TABLE_CHART_SUBTITLE_CN} · {TABLE_CHART_SUBTITLE_EN}",
        "证据明细": f"{TABLE_CHART_SUBTITLE_CN} · {TABLE_CHART_SUBTITLE_EN}",
    }
    for shape in _iter_template_shapes(slide.shapes):
        if not getattr(shape, "has_text_frame", False):
            continue
        full = "".join(p.text for p in shape.text_frame.paragraphs)
        new_full = full
        for a, b in repl.items():
            if a in new_full:
                new_full = new_full.replace(a, b)
        if new_full != full:
            _set_shape_text(shape, new_full)


def _insight_str_key_dict(raw: Any) -> Dict[str, Any]:
    """JSON 反序列化后 dict 的 key 可能是 int/str，统一为 str，避免 evidence / dim_texts / digest 对不上。"""
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items()}


def _insight_dimension_items(dimensions: List[Any], evidence: Dict[str, Any], dim_texts: Dict[str, Any]) -> List[dict]:
    evidence = _insight_str_key_dict(evidence)
    dim_texts = _insight_str_key_dict(dim_texts)
    items: List[dict] = []
    for idx, dim in enumerate(dimensions or [], start=1):
        if not isinstance(dim, dict):
            continue
        did = str(dim.get("id") or "")
        title = str(dim.get("display_title") or dim.get("title") or f"维度 {idx}").strip()
        toc_label = title
        markdown = str(dim_texts.get(did) or "")
        evs = evidence.get(did) or []
        charts = _insight_charts_from_evidence(evs)
        tables = _insight_tables_from_evidence(evs)
        conclusion, findings = _extract_conclusion_findings(markdown)
        claim = conclusion or str(dim.get("why_selected") or dim.get("title") or title)
        items.append({
            "idx": idx,
            "id": did,
            "title": _shrink(title, 24),
            "toc_label": toc_label,
            "claim": _shrink(_strip_md(claim), 90),
            "markdown": markdown,
            "findings": findings,
            "charts": charts,
            "tables": tables,
            "evidence": evs,
        })
    return items


def _insight_charts_from_evidence(evs: List[Any]) -> List[dict]:
    out: List[dict] = []
    seen = set()
    for ev in evs or []:
        if not isinstance(ev, dict) or not ev.get("supported"):
            continue
        chart = ev.get("chart")
        if not isinstance(chart, dict):
            continue
        chart = dict(chart)
        if not chart.get("rows") or not chart.get("columns"):
            cols = ev.get("columns") or []
            rows = ev.get("rows") or []
            if cols and rows:
                chart.setdefault("columns", cols)
                chart.setdefault("rows", rows)
                chart.setdefault("dimension_field", cols[0])
                chart.setdefault("metric_fields", cols[1:3])
        if not chart.get("rows") or not chart.get("columns"):
            continue
        chart.setdefault("subquestion_id", ev.get("question_id") or ev.get("business_question") or f"ev_{len(out) + 1}")
        chart.setdefault("title", ev.get("business_question") or "关键证据")
        chart.setdefault("explain", ev.get("purpose") or ev.get("business_question") or "")
        key = str(chart.get("subquestion_id") or chart.get("title"))
        if key in seen:
            continue
        seen.add(key)
        out.append(chart)
    return out[:5]


def _insight_tables_from_evidence(evs: List[Any]) -> List[dict]:
    out: List[dict] = []
    for idx, ev in enumerate(evs or [], start=1):
        if not isinstance(ev, dict) or not ev.get("supported"):
            continue
        cols = ev.get("columns") or []
        rows = ev.get("rows") or []
        if not cols or not rows:
            continue
        out.append({
            "subquestion_id": ev.get("question_id") or f"table_{idx}",
            "chart_type": "table",
            "title": ev.get("business_question") or f"关键证据 {idx}",
            "explain": ev.get("purpose") or f"{TABLE_CHART_SUBTITLE_CN} · {TABLE_CHART_SUBTITLE_EN}",
            "columns": cols,
            "rows": rows,
            "dimension_field": cols[0],
            "metric_fields": cols[1:3],
        })
    return out[:5]


def _insight_ordered_evidence_visuals(evs: List[Any]) -> List[dict]:
    """与 service._compact_insight_evidence 同源：仅前 5 条 evidence、且只包含有图/表可出页者，顺序与 PPT 逐页一致。"""
    out: List[dict] = []
    for ei, ev in enumerate((evs or [])[:5]):
        if not isinstance(ev, dict) or not ev.get("supported"):
            continue
        qid = str(ev.get("question_id") or "").strip()
        chart = ev.get("chart")
        if isinstance(chart, dict):
            ch = dict(chart)
            if not ch.get("rows") or not ch.get("columns"):
                cols = ev.get("columns") or []
                rows = ev.get("rows") or []
                if cols and rows:
                    ch.setdefault("columns", cols)
                    ch.setdefault("rows", rows)
                    ch.setdefault("dimension_field", cols[0])
                    ch.setdefault("metric_fields", cols[1:3])
            if ch.get("rows") and ch.get("columns"):
                slot = len(out) + 1
                stable = (
                    str(ch.get("subquestion_id") or "").strip()
                    or qid
                    or str(ev.get("business_question") or "").strip()
                    or f"ev_{ei + 1}"
                )
                ch["subquestion_id"] = stable
                ch.setdefault("title", ev.get("business_question") or "关键证据")
                ch.setdefault("explain", ev.get("purpose") or ev.get("business_question") or "")
                ch.setdefault("evidence_explain", ev.get("explain") or "")
                out.append(ch)
                continue
        cols = ev.get("columns") or []
        rows = ev.get("rows") or []
        if cols and rows:
            slot = len(out) + 1
            stable = qid or f"table_{ei + 1}"
            out.append({
                "subquestion_id": stable,
                "chart_type": "table",
                "title": ev.get("business_question") or f"关键证据 {slot}",
                "explain": ev.get("purpose") or f"{TABLE_CHART_SUBTITLE_CN} · {TABLE_CHART_SUBTITLE_EN}",
                "evidence_explain": ev.get("explain") or "",
                "columns": cols,
                "rows": rows,
                "dimension_field": cols[0],
                "metric_fields": cols[1:3],
            })
    return out[:5]


def _insight_text_chunks(md: str, *, limit: int = 8) -> List[str]:
    text = _strip_md(md)
    parts = [p.strip() for p in re.split(r"[。；;\n]+", text) if p.strip()]
    cleaned = []
    for part in parts:
        if len(part) < 6:
            continue
        if part not in cleaned:
            cleaned.append(part)
    return cleaned[:limit]


def _insight_overall_content(final_md: str, dimension_items: List[dict]) -> dict:
    chunks = _insight_text_chunks(final_md, limit=24)
    if not chunks:
        chunks = [item.get("claim", "") for item in dimension_items if item.get("claim")]
    title = "核心结论"
    desc = _shrink(chunks[0] if chunks else "当前深度洞察报告已生成，可结合维度页面查看主要结论、证据和后续动作。", 130)
    tail_pool = chunks[1:] or [item.get("claim", "") for item in dimension_items if item.get("claim")]
    points = [_shrink(x, 70) for x in tail_pool if x][:4]
    while len(points) < 4:
        points.append(desc)
    if len(chunks) > 5:
        conclusion = _shrink(chunks[5], 70)
    elif len(chunks) > 1:
        conclusion = _shrink(chunks[-1], 70)
    else:
        conclusion = _shrink(points[0], 70)
    return {"title": title, "desc": desc, "points": points[:4], "conclusion": conclusion}


def _insight_dimension_summary(item: dict) -> dict:
    conclusion, findings = _extract_conclusion_findings(item.get("markdown") or "")
    chunks = findings or _insight_text_chunks(item.get("markdown") or "")
    desc = conclusion or item.get("claim") or "请结合本维度图表和证据查看业务表现。"
    points = chunks[:4]
    while len(points) < 4:
        points.append(desc)
    return {
        "title": _clean_custom_heading((item.get("title") or "维度洞察")[:8]),
        "desc": desc,
        "points": points[:4],
        "conclusion": _shrink(points[0] if points else desc, INSIGHT_SUMMARY_CONCL_MAX_CHARS),
    }


def _insight_chart_data_blurb(chart: dict) -> str:
    """从当前表/图抽取一两句与数据绑定的短说明，避免多表 fallback 文案完全相同。"""
    ctype = str((chart or {}).get("chart_type") or "table").lower()
    cols = list((chart or {}).get("columns") or [])
    rows = list((chart or {}).get("rows") or [])
    n = len(rows)
    if ctype == "table" and cols and rows and n:
        r0 = rows[0]
        parts = []
        for i in range(min(4, len(cols), len(r0))):
            v = r0[i]
            if v is None or v == "":
                continue
            parts.append(f"{cols[i]}={_fmt_metric_value(v)}")
        head = "、".join(parts[:3]) if parts else ""
        if head:
            return _shrink(f"本表{n}行；首行：{head}", 220)
        return _shrink(f"本表共{n}行，列为「{'、'.join(str(c) for c in cols[:6])}」", 220)
    if rows and cols:
        return _shrink(f"数据{n}行×{len(cols)}列", 120)
    return ""


def _as_float_for_chart(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip().replace(",", "")
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _chart_numeric_profiles(chart: dict) -> List[dict]:
    cols = list((chart or {}).get("columns") or [])
    rows = list((chart or {}).get("rows") or [])
    profiles: List[dict] = []
    for col_idx, col in enumerate(cols[:12]):
        vals: List[float] = []
        zeros = 0
        for row in rows:
            if not isinstance(row, (list, tuple)) or col_idx >= len(row):
                continue
            num = _as_float_for_chart(row[col_idx])
            if num is None:
                continue
            vals.append(num)
            if abs(num) < 0.0000001:
                zeros += 1
        if vals:
            profiles.append({
                "column": str(col),
                "count": len(vals),
                "zero_count": zeros,
                "min": min(vals),
                "max": max(vals),
                "avg": sum(vals) / len(vals),
                "sum": sum(vals),
            })
        if len(profiles) >= 4:
            break
    return profiles


def _chart_category_profiles(chart: dict) -> List[dict]:
    cols = list((chart or {}).get("columns") or [])
    rows = list((chart or {}).get("rows") or [])
    profiles: List[dict] = []
    for col_idx, col in enumerate(cols[:10]):
        col_name = str(col).lower()
        if col_name.endswith("_id") or col_name == "id" or "id" == col_name[-2:]:
            continue
        if col_name.endswith("_name") or col_name == "name":
            continue
        values = []
        numeric_seen = 0
        for row in rows:
            if not isinstance(row, (list, tuple)) or col_idx >= len(row):
                continue
            val = row[col_idx]
            if val is None or val == "":
                continue
            if _as_float_for_chart(val) is not None:
                numeric_seen += 1
            values.append(str(val))
        if not values or numeric_seen >= max(1, len(values) // 2):
            continue
        counts: Dict[str, int] = {}
        for val in values:
            counts[val] = counts.get(val, 0) + 1
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        profiles.append({
            "column": str(col),
            "distinct": len(counts),
            "top": top,
        })
        if len(profiles) >= 4:
            break
    return profiles


def _chart_scope_sentence(chart: dict) -> str:
    cols = list((chart or {}).get("columns") or [])
    rows = list((chart or {}).get("rows") or [])
    scope = f"本页数据为{len(rows)}行×{len(cols)}列"
    if cols:
        scope += f"，字段包括{'、'.join(str(c) for c in cols[:5])}"
    return scope + "，应按这张表单独解读。"


def _chart_metric_sentence(chart: dict) -> str:
    numeric = _chart_numeric_profiles(chart)
    if not numeric:
        return "本页没有稳定数值列，分析重点应放在医院、地区、专科、类型等分类字段的结构差异。"
    parts = []
    for n in numeric[:2]:
        zero_note = f"，其中0值{n['zero_count']}条" if n.get("zero_count") else ""
        parts.append(
            f"{n['column']}均值{_fmt_metric_value(n['avg'])}，范围{_fmt_metric_value(n['min'])}至{_fmt_metric_value(n['max'])}{zero_note}"
        )
    return "；".join(parts) + "，请结合维度报告判断这些指标反映的业务趋势与异常，而非仅描述数值本身。"


def _chart_structure_sentence(chart: dict) -> str:
    cats = _chart_category_profiles(chart)
    if not cats:
        return "当前字段以数值指标为主，可优先比较高低差距、集中度和异常值。"
    parts = []
    for c in cats[:2]:
        top = "、".join(f"{k}{v}条" for k, v in c.get("top", [])[:2])
        if top:
            parts.append(f"{c['column']}有{c['distinct']}类，主要为{top}")
    if parts:
        return "；".join(parts) + "。"
    return "分类字段分布较分散，需要结合业务口径逐项查看。"


def _chart_sample_sentence(chart: dict) -> str:
    cols = list((chart or {}).get("columns") or [])
    rows = list((chart or {}).get("rows") or [])
    if not rows or not cols or not isinstance(rows[0], (list, tuple)):
        return "当前图表没有足够样本行可展开细节，应以字段结构和业务问题为主进行谨慎判断。"
    pairs = []
    for idx, col in enumerate(cols[:4]):
        if idx < len(rows[0]) and rows[0][idx] not in (None, ""):
            pairs.append(f"{col}={_fmt_metric_value(rows[0][idx])}")
    if not pairs:
        return "样本首行缺少可展示值，需要回到表格字段逐项核对。"
    return f"首行样本为{'、'.join(pairs)}，可作为本页解读的具体锚点。"


def _chart_specific_analysis_text(chart: dict, llm_text: str = "") -> str:
    title = str((chart or {}).get("title") or "当前图表").strip()
    explain = _strip_md(str((chart or {}).get("explain") or "")).strip()
    pieces = [
        f"本页对应「{title}」。",
        _chart_scope_sentence(chart),
        _chart_metric_sentence(chart),
        _chart_structure_sentence(chart),
    ]
    if explain:
        pieces.append(f"业务问题是：{_shrink(explain, 160)}")
    return _shrink("".join(pieces), 480)


def _chart_specific_analysis_cards(chart: dict) -> List[dict]:
    if not ((chart or {}).get("columns") or (chart or {}).get("rows")):
        return [
            {"title": "数据范围", "body": "当前图表缺少可展示数据，需要回到原始证据核对。"},
            {"title": "数值特征", "body": "暂无稳定数值列可计算。"},
            {"title": "结构线索", "body": "暂无分类字段可归纳。"},
        ]
    scope = _chart_scope_sentence(chart)
    metric_body = _chart_metric_sentence(chart)
    structure = _chart_structure_sentence(chart)
    sample = _chart_sample_sentence(chart)
    third = structure if structure else sample
    if len(third) < 30 and sample:
        third = f"{third}{sample}"
    cards = [
        {"title": "数据范围", "body": _shrink(scope, 160)},
        {"title": "数值特征", "body": _shrink(metric_body, 160)},
        {"title": "结构线索", "body": _shrink(third, 160)},
    ]
    if not _chart_numeric_profiles(chart):
        cards[1] = {"title": "样本线索", "body": _shrink(sample, 160)}
    else:
        cards[2] = {"title": "样本线索", "body": _shrink(sample, 160)}
    return cards


def _insight_chart_digest(chart: dict, item: dict, summary: dict) -> dict:
    cid = str(chart.get("subquestion_id") or "")
    explain = _strip_md(str(chart.get("explain") or "")).strip()
    title = str(chart.get("title") or item.get("title") or "关键图表").strip()
    blurb = _insight_chart_data_blurb(chart)
    if explain and blurb and blurb not in explain:
        analysis = _shrink(f"{explain} {blurb}", 480)
    elif explain:
        analysis = _shrink(explain, 480)
    elif blurb:
        analysis = blurb
    else:
        analysis = _shrink(item.get("claim") or summary.get("desc") or title, 480)
    logger.info(
        "xlsx_qa.insight_chart_digest FALLBACK chart=%s explain_len=%d blurb_len=%d analysis_preview=%s",
        cid, len(explain), len(blurb), analysis[:100],
    )
    # Use chart-specific cards instead of dimension-level summary points
    cards = _chart_specific_analysis_cards(chart)
    return {
        "chart_summaries": [{
            "chart_id": cid,
            "title": chart.get("title") or item.get("title") or "关键图表",
            "description": chart.get("explain") or title,
            "analysis": analysis,
            "cards": cards,
        }]
    }


def _add_insight_template_summary(
    prs: Presentation,
    template: Presentation,
    theme: PptTheme,
    *,
    question: str,
    subtitle: str,
    title: str,
    desc: str,
    points: List[str],
    conclusion: str,
    logo_bytes: Optional[bytes],
    image_idx: int = 1,
):
    slide = _clone_template_slide(prs, template.slides[3])
    _replace_template_text(slide, "PH_SUMMARY_QUESTION", _clean_custom_heading(question[:24]), font_size=30)
    _replace_template_text(slide, "PH_SUMMARY_SUBTITLE", subtitle)
    _replace_template_text(slide, "PH_SUMMARY_TITLE", _clean_custom_heading(title[:10]), font_size=18, word_wrap=False)
    _replace_template_text(slide, "PH_SUMMARY_DESC", desc, font_size=14, line_spacing=1.40)
    _replace_template_text(slide, "PH_SUMMARY_POINT_1", "", font_size=14, line_spacing=1.40)
    _replace_template_text(slide, "PH_SUMMARY_POINT_2", "", font_size=14, line_spacing=1.40)
    _replace_template_text(slide, "PH_SUMMARY_CONCLUSION", conclusion, font_size=14, line_spacing=1.40,
                           max_len=INSIGHT_SUMMARY_CONCL_MAX_CHARS, auto_size=MSO_AUTO_SIZE.NONE)
    _replace_custom_summary_image(slide, image_idx)
    _finalize_template_summary_four_points(slide, points, desc, conclusion, theme, layout="insight")
    _replace_template_logos(slide, logo_bytes)
    _retint_custom_slide(slide, theme)
    return slide


def _insight_digest_for_chart_slide(
    dim_digest: Optional[dict],
    chart: dict,
    item: dict,
    summary: dict,
    *,
    chart_seq_index: int = 0,
) -> dict:
    """为单张图/表精确匹配一条 chart_summary；找不到时用图表自身数据生成，保证每页内容独立。"""
    cid = str((chart or {}).get("subquestion_id") or "").strip()
    if dim_digest and isinstance(dim_digest.get("chart_summaries"), list):
        summaries = dim_digest["chart_summaries"]
        available_ids = [str((cs or {}).get("chart_id") or "").strip() for cs in summaries]

        # 1) chart_id 精确匹配 — 当多结果共享同一 chart_id 时，按页序号取第 N 个匹配项
        if cid:
            matched_indices = [
                i for i, cs in enumerate(summaries)
                if isinstance(cs, dict) and str(cs.get("chart_id") or "").strip() == cid
            ]
            if matched_indices:
                # 优先用页序号定位；超出范围时退回到第一个匹配项
                pick_idx = matched_indices[chart_seq_index] if chart_seq_index < len(matched_indices) else matched_indices[0]
                logger.info(
                    "xlsx_qa.insight_digest_for_chart MATCHED dim=%s chart=%s seq=%d pick=%d/%d available_ids=%s",
                    item.get("id"), cid, chart_seq_index, pick_idx, len(matched_indices), available_ids,
                )
                return {"chart_summaries": [summaries[pick_idx]]}

        # 2) 只有当前图表没有稳定 chart_id 时，才允许按页序号兜底。
        # 有 chart_id 却匹配不到时直接走当前图表 fallback，避免拿到同维度其他图表的文案。
        if not cid and 0 <= chart_seq_index < len(summaries):
            cs = summaries[chart_seq_index]
            if isinstance(cs, dict):
                logger.info(
                    "xlsx_qa.insight_digest_for_chart FALLBACK_INDEX dim=%s seq=%d available_ids=%s",
                    item.get("id"), chart_seq_index, available_ids,
                )
                return {"chart_summaries": [cs]}

        logger.warning(
            "xlsx_qa.insight_digest_for_chart NO_MATCH dim=%s chart=%s available_ids=%s seq=%d n_summaries=%d",
            item.get("id"), cid, available_ids, chart_seq_index, len(summaries),
        )
    else:
        logger.warning(
            "xlsx_qa.insight_digest_for_chart NO_LLM_DIGEST dim=%s chart=%s dim_digest_type=%s",
            item.get("id"), cid, type(dim_digest).__name__ if dim_digest else "None",
        )

    # 3) 用图表自身数据生成独立 fallback
    fallback = _insight_chart_digest(chart, item, summary)
    logger.info(
        "xlsx_qa.insight_digest_for_chart FALLBACK_DATA dim=%s chart=%s analysis_preview=%s",
        item.get("id"), cid, str(fallback.get("chart_summaries", [{}])[0].get("analysis", ""))[:120] if fallback.get("chart_summaries") else "none",
    )
    return fallback


def _add_insight_action_slide(
    prs: Presentation,
    template: Presentation,
    theme: PptTheme,
    *,
    logo_bytes: Optional[bytes],
    actions: List[dict],
):
    """每维度行动建议：三栏通栏布局（无底部重复卡片），序号与标题同一文本框避免换行断开。"""
    slide = _clone_template_slide(prs, template.slides[5])
    _replace_template_text(slide, "PH_CHART_TITLE", "行动建议", font_size=30, word_wrap=False)
    _replace_template_text(slide, "PH_CHART_SUBTITLE", "Recommended actions", max_len=150, font_size=8.5 )
    _replace_template_logos(slide, logo_bytes)
    _retint_custom_slide(slide, theme)

    fallback_body = (
        "结合本维度证据与结论，明确责任人与交付物：先复核指标口径与数据来源，再对 Top 风险对象制定一周内的触达与补数计划，"
        "并将结果纳入例会复盘；同步设定可量化监控指标与截止时间，避免策略与执行脱节。"
    )
    while len(actions) < 3:
        actions.append({
            "title": f"建议动作 {len(actions) + 1}",
            "body": fallback_body,
            "owner": "业务负责人",
            "metric": "关键指标",
            "deadline": "2周内",
        })

    left, top, width, height = Inches(1.0), Inches(1.95), Inches(17.9), Inches(5.65)
    _rect(slide, left, top, width, height, RGBColor(0xF6, 0xFA, 0xFB))
    sep = Inches(0.06)
    col_w = (width - sep * 2) // 3
    bar_colors = [theme.accent, RGBColor(0xF3, 0x8A, 0x3D), RGBColor(0x2B, 0x74, 0xB8)]

    for idx in range(3):
        action = actions[idx]
        color = bar_colors[idx]
        x = left + idx * (col_w + sep)
        _rect(slide, x, top, col_w, Inches(0.07), color)
        headline = f"{idx + 1:02d}  {str(action.get('title') or '').strip()}"
        _text(
            slide, headline, x + Inches(0.22), top + Inches(0.16), col_w - Inches(0.40), Inches(0.52),
            font_size=17, bold=True, color=CUST_TEXT, word_wrap=False, auto_fit=True,
        )
        _text(
            slide, str(action.get("body", "")),
            x + Inches(0.26), top + Inches(0.82), col_w - Inches(0.48), Inches(3.85),
            font_size=16.5, color=CUST_TEXT, auto_fit=True, line_spacing=1.4,
        )
        meta_lines = []
        owner = str(action.get("owner", "")).strip()
        metric = str(action.get("metric", "")).strip()
        deadline = str(action.get("deadline", "")).strip()
        if owner:
            meta_lines.append(f"负责人: {owner}")
        if metric:
            meta_lines.append(f"指标: {metric}")
        if deadline:
            meta_lines.append(f"时间: {deadline}")
        meta_text = "  |  ".join(meta_lines) if meta_lines else ""
        _text(
            slide, meta_text, x + Inches(0.26), top + Inches(4.92), col_w - Inches(0.48), Inches(0.42),
            font_size=11.5, color=CUST_MUTED, align=PP_ALIGN.LEFT, auto_fit=True,
        )

    _text(slide, "Insight Report · Actions", Inches(16.45), Inches(10.36), Inches(2.45), Inches(0.28),
          font_size=10, color=CUST_MUTED, align=PP_ALIGN.RIGHT)


def _insight_pick_items(pool: List[str], offset: int) -> List[str]:
    fallback = ["复核关键指标口径，优先处理影响最大的业务对象。", "关注异常波动来源，补齐缺失数据后再固化判断。", "建立监控节奏，将结论转成可执行跟进动作。"]
    items = []
    for i in range(3):
        src = pool[(offset + i) % len(pool)] if pool else fallback[i]
        items.append(_shrink(src, 42))
    return items


def _add_insight_summary_pages(
    prs: Presentation,
    theme: PptTheme,
    module_name: str,
    final_md: str,
    dimension_items: List[dict],
    *,
    logo_bytes: Optional[bytes],
) -> None:
    chunks = _insight_text_chunks(final_md, limit=16)
    claims = [item.get("claim", "") for item in dimension_items if item.get("claim")]
    pool = [x for x in chunks + claims if x] or ["当前报告已形成可用于复盘和决策的洞察总结。"]
    _add_insight_summary_dashboard(prs, theme, pool, logo_bytes=logo_bytes)
    _add_insight_priority_map(prs, theme, pool, logo_bytes=logo_bytes)
    _add_insight_roadmap(prs, theme, pool, logo_bytes=logo_bytes)
    _add_insight_readout(prs, theme, module_name, pool, logo_bytes=logo_bytes)


def _insight_summary_slide(prs: Presentation, title: str, subtitle: str, marker: str, logo_bytes: Optional[bytes]):
    """Unified summary slide header — matches dimension overall text slide style."""
    slide = _custom_slide(prs, logo_bytes=logo_bytes)
    # Top accent bar (matching dimension slide format)
    _rect(slide, Inches(1.0), Inches(0.58), Inches(17.95), Inches(0.06), _custom_chart_theme().accent)
    # Title
    _text(slide, title[:34], Inches(1.05), Inches(0.82), Inches(12.2), Inches(0.65),
          font_size=34, bold=True, color=CUST_TEXT, auto_fit=True)
    # English subtitle
    _text(slide, subtitle[:70], Inches(1.08), Inches(1.55), Inches(11.7), Inches(0.32),
          font_size=12, color=CUST_MUTED, auto_fit=True)
    # Logo
    _custom_logo(slide, logo_bytes, CUST_W - Inches(3.15), Inches(0.78), Inches(2.25), Inches(0.42))
    # Page marker
    _text(slide, marker, Inches(17.0), Inches(10.36), Inches(1.9), Inches(0.28),
          font_size=10, color=CUST_MUTED, align=PP_ALIGN.RIGHT)
    # Bottom green bar
    _rect(slide, 0, Inches(10.84), CUST_W, Inches(0.41), CUST_GREEN)
    return slide


def _summary_box(slide, x, y, w, h, *, accent: RGBColor, title: str, body: str, title_w=1.6):
    _round_rect(slide, Inches(x), Inches(y), Inches(w), Inches(h), C_WHITE)
    _rect(slide, Inches(x), Inches(y), Inches(0.07), Inches(h), accent)
    _text(slide, title, Inches(x + 0.28), Inches(y + 0.18), Inches(title_w), Inches(0.25),
          font_size=13, bold=True, color=accent, align=PP_ALIGN.CENTER, auto_fit=True)
    _text(slide, body, Inches(x + title_w + 0.55), Inches(y + 0.18),
          Inches(w - title_w - 0.85), Inches(h - 0.32), font_size=13.5, color=CUST_TEXT, auto_fit=True)


def _add_insight_summary_dashboard(prs, theme, pool, *, logo_bytes):
    slide = _insight_summary_slide(prs, "洞察总结", "Executive conclusion dashboard", "05 · 01", logo_bytes)
    _rect(slide, Inches(1.0), Inches(2.0), Inches(17.95), Inches(0.04), theme.accent)
    _text(slide, _shrink(pool[0], 34), Inches(1.05), Inches(2.22), Inches(12.2), Inches(0.55),
          font_size=28, bold=True, color=CUST_TEXT, auto_fit=True)
    _text(slide, _shrink(pool[1] if len(pool) > 1 else pool[0], 70), Inches(1.08), Inches(2.93),
          Inches(11.7), Inches(0.42), font_size=15, color=CUST_MUTED, auto_fit=True)
    for idx, title in enumerate(["增长判断", "结构判断", "效率判断", "风险判断"]):
        x = 1.05 + (idx % 2) * 8.95
        y = 4.15 + (idx // 2) * 2.1
        _summary_box(slide, x, y, 8.25, 1.58, accent=theme.palette[idx % len(theme.palette)],
                     title=title, body=pool[idx % len(pool)])
    _text(slide, _shrink(pool[-1], 60), Inches(2.2), Inches(8.9), Inches(15.2), Inches(0.38),
          font_size=18, bold=True, color=theme.accent_dark, align=PP_ALIGN.CENTER, auto_fit=True)


def _add_insight_priority_map(prs, theme, pool, *, logo_bytes):
    slide = _insight_summary_slide(prs, "洞察总结 · 机会风险地图", "Priority map for follow-up decisions", "05 · 02", logo_bytes)
    _round_rect(slide, Inches(1.05), Inches(2.0), Inches(8.4), Inches(6.8), CUST_MINT)
    _rect(slide, Inches(5.25), Inches(2.68), Inches(0.04), Inches(5.3), CUST_MUTED)
    _rect(slide, Inches(1.75), Inches(5.35), Inches(6.9), Inches(0.04), CUST_MUTED)
    _text(slide, "影响高", Inches(1.55), Inches(2.28), Inches(1.0), Inches(0.18), font_size=10, color=CUST_MUTED)
    _text(slide, "确定性高", Inches(7.0), Inches(8.08), Inches(1.25), Inches(0.18), font_size=10, color=CUST_MUTED)
    for idx, (x, y, label, color) in enumerate([
        (5.9, 3.35, "立即投入", theme.accent),
        (2.35, 3.5, "补证验证", RGBColor(0xF3, 0x8A, 0x3D)),
        (5.9, 6.45, "规模复制", RGBColor(0x2B, 0x74, 0xB8)),
        (2.35, 6.45, "低频跟踪", CUST_MUTED),
    ]):
        _round_rect(slide, Inches(x), Inches(y), Inches(1.65), Inches(0.55), color)
        _text(slide, label, Inches(x + 0.1), Inches(y + 0.14), Inches(1.45), Inches(0.18),
              font_size=10, bold=True, color=C_WHITE if idx < 3 else CUST_TEXT, align=PP_ALIGN.CENTER)
    for idx, (title, color) in enumerate([("机会清单", theme.accent), ("异常清单", RGBColor(0xF3, 0x8A, 0x3D)), ("风险清单", RGBColor(0xD9, 0x4A, 0x4A))]):
        x, y = 10.25, 2.0 + idx * 2.25
        _round_rect(slide, Inches(x), Inches(y), Inches(8.15), Inches(1.72), C_WHITE)
        _rect(slide, Inches(x), Inches(y), Inches(0.07), Inches(1.72), color)
        _text(slide, title, Inches(x + 0.3), Inches(y + 0.18), Inches(1.6), Inches(0.25), font_size=14, bold=True, color=color, align=PP_ALIGN.CENTER)
        for row in range(3):
            _text(slide, _shrink(pool[(idx * 3 + row) % len(pool)], 42), Inches(x + 2.05), Inches(y + 0.2 + row * 0.42),
                  Inches(5.9), Inches(0.28), font_size=12.5, color=CUST_TEXT, auto_fit=True)
    _text(slide, _shrink(pool[-1], 55), Inches(10.25), Inches(8.95), Inches(8.1), Inches(0.32),
          font_size=15, bold=True, color=theme.accent_dark, align=PP_ALIGN.CENTER, auto_fit=True)


def _add_insight_roadmap(prs, theme, pool, *, logo_bytes):
    slide = _insight_summary_slide(prs, "洞察总结 · 行动路线", "Recommended actions and sequencing", "05 · 03", logo_bytes)
    _rect(slide, Inches(1.25), Inches(5.2), Inches(17.1), Inches(0.05), theme.accent)
    stages = [("短期校准", theme.accent), ("中期优化", RGBColor(0x2B, 0x74, 0xB8)), ("长期机制", RGBColor(0x7A, 0x5C, 0xC8))]
    for idx, (stage, color) in enumerate(stages):
        x = 1.35 + idx * 5.85
        _round_rect(slide, Inches(x), Inches(4.75), Inches(0.86), Inches(0.86), color)
        _text(slide, str(idx + 1), Inches(x + 0.21), Inches(4.98), Inches(0.44), Inches(0.18),
              font_size=14, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
        _text(slide, stage, Inches(x - 0.35), Inches(3.55), Inches(2.5), Inches(0.35),
              font_size=19, bold=True, color=color, align=PP_ALIGN.CENTER)
        _round_rect(slide, Inches(x - 0.7), Inches(5.95), Inches(4.35), Inches(2.18), C_WHITE)
        _rect(slide, Inches(x - 0.7), Inches(5.95), Inches(0.07), Inches(2.18), color)
        _text(slide, _shrink(pool[idx % len(pool)], 42), Inches(x - 0.38), Inches(6.22), Inches(3.65), Inches(0.28), font_size=13, color=CUST_TEXT, auto_fit=True)
        _text(slide, _shrink(pool[(idx + 3) % len(pool)], 42), Inches(x - 0.38), Inches(6.78), Inches(3.65), Inches(0.28), font_size=13, color=CUST_TEXT, auto_fit=True)
    _round_rect(slide, Inches(1.25), Inches(8.75), Inches(17.1), Inches(0.62), CUST_MINT)
    _text(slide, _shrink(pool[-1], 65), Inches(1.65), Inches(8.93), Inches(16.3), Inches(0.24),
          font_size=15, bold=True, color=theme.accent_dark, align=PP_ALIGN.CENTER, auto_fit=True)


def _add_insight_readout(prs, theme, module_name, pool, *, logo_bytes):
    slide = _insight_summary_slide(prs, "洞察总结 · 管理层读数", "Final readout and monitoring plan", "05 · 04", logo_bytes)
    for idx, (title, color) in enumerate([("一句话结论", theme.accent), ("必须复核", RGBColor(0xF3, 0x8A, 0x3D)), ("持续监控", RGBColor(0x2B, 0x74, 0xB8))]):
        x = 1.1 + idx * 6.05
        _round_rect(slide, Inches(x), Inches(2.15), Inches(5.45), Inches(2.2), C_WHITE)
        _rect(slide, Inches(x), Inches(2.15), Inches(0.07), Inches(2.2), color)
        _text(slide, title, Inches(x + 0.35), Inches(2.45), Inches(1.55), Inches(0.28), font_size=15, bold=True, color=color, align=PP_ALIGN.CENTER)
        _text(slide, _shrink(pool[idx % len(pool)], 105), Inches(x + 0.45), Inches(3.0), Inches(4.5), Inches(0.78), font_size=15, color=CUST_TEXT, auto_fit=True)
    for idx, (label, color) in enumerate([("指标口径", theme.accent), ("数据缺口", RGBColor(0xF3, 0x8A, 0x3D)), ("责任动作", RGBColor(0x2B, 0x74, 0xB8)), ("下次复盘", RGBColor(0x7A, 0x5C, 0xC8))]):
        x = 1.1 + (idx % 2) * 9.0
        y = 5.25 + (idx // 2) * 1.55
        _round_rect(slide, Inches(x), Inches(y), Inches(8.0), Inches(1.1), RGBColor(0xF5, 0xFC, 0xFD))
        _rect(slide, Inches(x), Inches(y), Inches(0.07), Inches(1.1), color)
        _text(slide, label, Inches(x + 0.3), Inches(y + 0.22), Inches(1.45), Inches(0.22), font_size=12, bold=True, color=color, align=PP_ALIGN.CENTER)
        _text(slide, _shrink(pool[(idx + 3) % len(pool)], 55), Inches(x + 1.95), Inches(y + 0.22), Inches(5.75), Inches(0.36), font_size=13, color=CUST_TEXT, auto_fit=True)
    _round_rect(slide, Inches(3.15), Inches(8.8), Inches(13.7), Inches(0.68), theme.accent_dark)
    _text(slide, _shrink(f"{pool[0]}", 55), Inches(3.55), Inches(9.0), Inches(12.9), Inches(0.24),
          font_size=16, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER, auto_fit=True)


def _add_insight_summary_pages_from_digest(
    prs: Presentation,
    theme: PptTheme,
    module_name: str,
    final_digest: dict,
    *,
    logo_bytes: Optional[bytes],
) -> None:
    """Build the 4 final summary slides from model-generated final_digest."""
    dashboard = final_digest.get("dashboard") if isinstance(final_digest.get("dashboard"), dict) else {}
    priority_map = final_digest.get("priority_map") if isinstance(final_digest.get("priority_map"), dict) else {}
    roadmap = final_digest.get("roadmap") if isinstance(final_digest.get("roadmap"), dict) else {}
    readout = final_digest.get("readout") if isinstance(final_digest.get("readout"), dict) else {}

    # Page 1: Dashboard
    slide = _insight_summary_slide(prs, "洞察总结", "Executive conclusion dashboard", "05 · 01", logo_bytes)
    _rect(slide, Inches(1.0), Inches(2.0), Inches(17.95), Inches(0.04), theme.accent)
    dash_title = str(dashboard.get("title") or "洞察总结")
    dash_desc = str(dashboard.get("desc") or "")
    _text(slide, dash_title, Inches(1.05), Inches(2.22), Inches(12.2), Inches(0.55),
          font_size=28, bold=True, color=CUST_TEXT, auto_fit=True)
    _text(slide, dash_desc, Inches(1.08), Inches(2.93),
          Inches(11.7), Inches(0.42), font_size=15, color=CUST_MUTED, auto_fit=True)
    # kpis = dashboard.get("kpis") or []
    # for idx, kpi in enumerate(kpis[:4]):
    #     if not isinstance(kpi, dict):
    #         continue
    #     x = 13.35 + (idx % 2) * 2.78
    #     y = 2.18 + (idx // 2) * 1.2
    #     color = theme.palette[idx % len(theme.palette)]
    #     _round_rect(slide, Inches(x), Inches(y), Inches(2.45), Inches(0.88), RGBColor(0xF5, 0xFC, 0xFD))
    #     _rect(slide, Inches(x), Inches(y), Inches(0.07), Inches(0.88), color)
    #     _text(slide, str(kpi.get("label", "")), Inches(x + 0.24), Inches(y + 0.12), Inches(1.95), Inches(0.18),
    #           font_size=9.5, color=CUST_MUTED, align=PP_ALIGN.CENTER)
    #     _text(slide, str(kpi.get("value", "")), Inches(x + 0.22), Inches(y + 0.42), Inches(1.98), Inches(0.28),
    #           font_size=15, bold=True, color=color, align=PP_ALIGN.CENTER)
    judgments = dashboard.get("judgments") or []
    for idx, j in enumerate(judgments[:4]):
        if not isinstance(j, dict):
            continue
        x = 1.05 + (idx % 2) * 8.95
        y = 4.15 + (idx // 2) * 2.1
        _summary_box(slide, x, y, 8.25, 1.58, accent=theme.palette[idx % len(theme.palette)],
                     title=str(j.get("title", "")), body=str(j.get("body", "")))
    _text(slide, dash_desc, Inches(2.2), Inches(8.9), Inches(15.2), Inches(0.38),
          font_size=18, bold=True, color=theme.accent_dark, align=PP_ALIGN.CENTER, auto_fit=True)

    # Page 2: Priority map
    opportunities = priority_map.get("opportunities") or []
    anomalies_in = priority_map.get("anomalies") or []
    risks_in = priority_map.get("risks") or []
    pool_priority = opportunities + anomalies_in + risks_in
    if not pool_priority:
        pool_priority = ["数据不足以形成明确的优先级判断。"]
    slide = _insight_summary_slide(prs, "洞察总结 · 机会风险地图", "Priority map for follow-up decisions", "05 · 02", logo_bytes)
    _round_rect(slide, Inches(1.05), Inches(2.0), Inches(8.4), Inches(6.8), CUST_MINT)
    _rect(slide, Inches(5.25), Inches(2.68), Inches(0.04), Inches(5.3), CUST_MUTED)
    _rect(slide, Inches(1.75), Inches(5.35), Inches(6.9), Inches(0.04), CUST_MUTED)
    _text(slide, "影响高", Inches(1.55), Inches(2.28), Inches(1.0), Inches(0.18), font_size=10, color=CUST_MUTED)
    _text(slide, "确定性高", Inches(7.0), Inches(8.08), Inches(1.25), Inches(0.18), font_size=10, color=CUST_MUTED)
    for idx, (x, y, label, color) in enumerate([
        (5.9, 3.35, "立即投入", theme.accent),
        (2.35, 3.5, "补证验证", RGBColor(0xF3, 0x8A, 0x3D)),
        (5.9, 6.45, "规模复制", RGBColor(0x2B, 0x74, 0xB8)),
        (2.35, 6.45, "低频跟踪", CUST_MUTED),
    ]):
        _round_rect(slide, Inches(x), Inches(y), Inches(1.65), Inches(0.55), color)
        _text(slide, label, Inches(x + 0.1), Inches(y + 0.14), Inches(1.45), Inches(0.18),
              font_size=10, bold=True, color=C_WHITE if idx < 3 else CUST_TEXT, align=PP_ALIGN.CENTER)
    for idx, (title, color, items) in enumerate([
        ("机会清单", theme.accent, opportunities),
        ("异常清单", RGBColor(0xF3, 0x8A, 0x3D), anomalies_in),
        ("风险清单", RGBColor(0xD9, 0x4A, 0x4A), risks_in),
    ]):
        x, y = 10.25, 2.0 + idx * 2.25
        _round_rect(slide, Inches(x), Inches(y), Inches(8.15), Inches(1.72), C_WHITE)
        _rect(slide, Inches(x), Inches(y), Inches(0.07), Inches(1.72), color)
        _text(slide, title, Inches(x + 0.3), Inches(y + 0.18), Inches(1.6), Inches(0.25), font_size=14, bold=True, color=color, align=PP_ALIGN.CENTER)
        for row in range(3):
            item_text = items[row] if row < len(items) else ""
            _text(slide, item_text, Inches(x + 2.05), Inches(y + 0.2 + row * 0.42),
                  Inches(5.9), Inches(0.28), font_size=12.5, color=CUST_TEXT, auto_fit=True)
    _text(slide, pool_priority[-1] if pool_priority else "", Inches(10.25), Inches(8.95), Inches(8.1), Inches(0.32),
          font_size=15, bold=True, color=theme.accent_dark, align=PP_ALIGN.CENTER, auto_fit=True)

    # Page 3: Roadmap
    short_term = roadmap.get("short_term") or []
    mid_term = roadmap.get("mid_term") or []
    long_term = roadmap.get("long_term") or []
    pool_roadmap = short_term + mid_term + long_term
    if not pool_roadmap:
        pool_roadmap = ["根据洞察结论制定分阶段行动计划。"]
    slide = _insight_summary_slide(prs, "洞察总结 · 行动路线", "Recommended actions and sequencing", "05 · 03", logo_bytes)
    _rect(slide, Inches(1.25), Inches(5.2), Inches(17.1), Inches(0.05), theme.accent)
    stages = [
        ("短期校准", theme.accent, short_term),
        ("中期优化", RGBColor(0x2B, 0x74, 0xB8), mid_term),
        ("长期机制", RGBColor(0x7A, 0x5C, 0xC8), long_term),
    ]
    for idx, (stage, color, items) in enumerate(stages):
        x = 1.35 + idx * 5.85
        _round_rect(slide, Inches(x), Inches(4.75), Inches(0.86), Inches(0.86), color)
        _text(slide, str(idx + 1), Inches(x + 0.21), Inches(4.98), Inches(0.44), Inches(0.18),
              font_size=14, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
        _text(slide, stage, Inches(x - 0.35), Inches(3.55), Inches(2.5), Inches(0.35),
              font_size=19, bold=True, color=color, align=PP_ALIGN.CENTER)
        _round_rect(slide, Inches(x - 0.7), Inches(5.95), Inches(4.35), Inches(2.18), C_WHITE)
        _rect(slide, Inches(x - 0.7), Inches(5.95), Inches(0.07), Inches(2.18), color)
        _text(slide, items[0] if items else "", Inches(x - 0.38), Inches(6.22), Inches(3.65), Inches(0.28),
              font_size=13, color=CUST_TEXT, auto_fit=True)
        _text(slide, items[1] if len(items) > 1 else "", Inches(x - 0.38), Inches(6.78), Inches(3.65), Inches(0.28),
              font_size=13, color=CUST_TEXT, auto_fit=True)
        _text(slide, "", Inches(x - 0.38), Inches(7.45), Inches(3.65), Inches(0.24),
              font_size=11, color=CUST_MUTED, align=PP_ALIGN.CENTER)
    _round_rect(slide, Inches(1.25), Inches(8.75), Inches(17.1), Inches(0.62), CUST_MINT)
    _text(slide, pool_roadmap[-1] if pool_roadmap else "", Inches(1.65), Inches(8.93), Inches(16.3), Inches(0.24),
          font_size=15, bold=True, color=theme.accent_dark, align=PP_ALIGN.CENTER, auto_fit=True)

    # Page 4: Readout
    one_liner = str(readout.get("one_liner") or pool_roadmap[0] if pool_roadmap else "")
    must_verify = str(readout.get("must_verify") or "")
    keep_watching = str(readout.get("keep_watching") or "")
    pool_readout = [one_liner, must_verify, keep_watching] + (pool_roadmap or ["持续跟踪关键指标变化。"])
    slide = _insight_summary_slide(prs, "洞察总结 · 管理层读数", "Final readout and monitoring plan", "05 · 04", logo_bytes)
    for idx, (title, color) in enumerate([
        ("一句话结论", theme.accent),
        ("必须复核", RGBColor(0xF3, 0x8A, 0x3D)),
        ("持续监控", RGBColor(0x2B, 0x74, 0xB8)),
    ]):
        x = 1.1 + idx * 6.05
        _round_rect(slide, Inches(x), Inches(2.15), Inches(5.45), Inches(2.2), C_WHITE)
        _rect(slide, Inches(x), Inches(2.15), Inches(0.07), Inches(2.2), color)
        _text(slide, title, Inches(x + 0.35), Inches(2.45), Inches(1.55), Inches(0.28),
              font_size=15, bold=True, color=color, align=PP_ALIGN.CENTER)
        _text(slide, pool_readout[idx % len(pool_readout)], Inches(x + 0.45), Inches(3.0),
              Inches(4.5), Inches(0.78), font_size=15, color=CUST_TEXT, auto_fit=True)
    for idx, (label, color) in enumerate([
        ("指标口径", theme.accent),
        ("数据缺口", RGBColor(0xF3, 0x8A, 0x3D)),
        ("责任动作", RGBColor(0x2B, 0x74, 0xB8)),
        ("下次复盘", RGBColor(0x7A, 0x5C, 0xC8)),
    ]):
        x = 1.1 + (idx % 2) * 9.0
        y = 5.25 + (idx // 2) * 1.55
        _round_rect(slide, Inches(x), Inches(y), Inches(8.0), Inches(1.1), RGBColor(0xF5, 0xFC, 0xFD))
        _rect(slide, Inches(x), Inches(y), Inches(0.07), Inches(1.1), color)
        _text(slide, label, Inches(x + 0.3), Inches(y + 0.22), Inches(1.45), Inches(0.22),
              font_size=12, bold=True, color=color, align=PP_ALIGN.CENTER)
        _text(slide, pool_readout[(idx + 3) % len(pool_readout)], Inches(x + 1.95), Inches(y + 0.22),
              Inches(5.75), Inches(0.36), font_size=13, color=CUST_TEXT, auto_fit=True)
    _round_rect(slide, Inches(3.15), Inches(8.8), Inches(13.7), Inches(0.68), theme.accent_dark)
    _text(slide, f"{one_liner}", Inches(3.55), Inches(9.0), Inches(12.9), Inches(0.24),
          font_size=14, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER, auto_fit=True)


__all__ = ["PptMessage", "PptExportOptions", "build_pptx", "build_custom_sales_pptx", "build_insight_custom_pptx"]
