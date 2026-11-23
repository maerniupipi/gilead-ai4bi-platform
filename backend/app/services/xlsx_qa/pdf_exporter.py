"""
XLSX 表格智能问答 · PDF 导出。

生成可交付汇报型 PDF：封面、目录、按问题/维度分页、表格与正文。
设计风格：医药行业专业报告 — 深蓝主调、青绿点缀、几何分子装饰。
"""
from __future__ import annotations

import datetime as _dt
import io
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .ppt_exporter import PptMessage

PAGE_W, PAGE_H = A4
MARGIN_X = 20 * mm
MARGIN_Y = 22 * mm

# ── 医药行业专业配色 ──
NAVY       = colors.HexColor("#0F2B46")
NAVY_DARK  = colors.HexColor("#091E33")
TEAL       = colors.HexColor("#0097A7")
TEAL_LIGHT = colors.HexColor("#E0F4F5")
TEAL_MID   = colors.HexColor("#B2E0E4")
INK        = colors.HexColor("#1A1A2E")
BODY_TEXT   = colors.HexColor("#2D3142")
MUTED      = colors.HexColor("#6B7280")
LIGHT_BG   = colors.HexColor("#F7FAFA")
CARD_BG    = colors.HexColor("#FFFFFF")
CARD_BORDER = colors.HexColor("#D6E4E8")
TABLE_HEAD  = colors.HexColor("#0F2B46")
TABLE_HEAD_TEXT = colors.white
TABLE_ROW_ALT = colors.HexColor("#F0F7F8")
TABLE_GRID = colors.HexColor("#D1DEE2")
PAGE_BG    = colors.white
DIVIDER    = colors.HexColor("#C5D5DA")
ACCENT_BAR = colors.HexColor("#0097A7")


@dataclass
class PdfOptions:
    title: str = "数据洞察报告"
    author: str = "AutoBI"
    generated_at: Optional[_dt.datetime] = None


def _register_fonts() -> tuple[str, str]:
    candidates = [
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if not Path(path).exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont("XlsxQaCJK", path))
            pdfmetrics.registerFont(TTFont("XlsxQaCJKBold", path))
            return "XlsxQaCJK", "XlsxQaCJKBold"
        except Exception:
            continue
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_BOLD = _register_fonts()


# ── 装饰绘图组件 ──

def _draw_hexagon(canvas, cx, cy, r, *, fill_color=None, stroke_color=None, line_width=0.6):
    """绘制单个正六边形（分子结构元素）。"""
    pts = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    p = canvas.beginPath()
    p.moveTo(*pts[0])
    for pt in pts[1:]:
        p.lineTo(*pt)
    p.close()
    canvas.saveState()
    if fill_color:
        canvas.setFillColor(fill_color)
    if stroke_color:
        canvas.setStrokeColor(stroke_color)
    canvas.setLineWidth(line_width)
    canvas.drawPath(p, fill=1 if fill_color else 0, stroke=1 if stroke_color else 0)
    canvas.restoreState()


def _draw_molecular_pattern(canvas, x0, y0, *, cols=5, rows=4, size=12, alpha_fill=None, alpha_stroke=None):
    """在指定区域绘制六边形分子网格装饰。"""
    dx = size * 1.75
    dy = size * 1.52
    for r in range(rows):
        for c in range(cols):
            offset_x = (size * 0.875) if r % 2 else 0
            cx = x0 + c * dx + offset_x
            cy = y0 + r * dy
            _draw_hexagon(canvas, cx, cy, size,
                          fill_color=alpha_fill,
                          stroke_color=alpha_stroke,
                          line_width=0.4)


def _draw_cover_decoration(canvas, page_w, page_h):
    """封面页装饰：顶部深蓝色带 + 右上角分子结构图案。"""
    canvas.saveState()

    # 顶部深蓝色横条
    canvas.setFillColor(NAVY)
    canvas.rect(0, page_h - 8 * mm, page_w, 8 * mm, fill=1, stroke=0)

    # 左侧青绿色竖条
    canvas.setFillColor(TEAL)
    canvas.rect(0, 0, 5 * mm, page_h - 8 * mm, fill=1, stroke=0)

    # 右上角分子结构装饰区域
    _draw_molecular_pattern(
        canvas,
        page_w - 85 * mm, page_h - 95 * mm,
        cols=6, rows=5, size=10 * mm,
        alpha_fill=colors.HexColor("#E8F5F7"),
        alpha_stroke=colors.HexColor("#B8DDE3"),
    )

    # 底部青绿色细线
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(1.5)
    canvas.line(5 * mm, 18 * mm, page_w, 18 * mm)

    canvas.restoreState()


def _draw_toc_decoration(canvas, page_w, page_h):
    """目录页装饰：顶部条 + 左侧竖条。"""
    canvas.saveState()

    canvas.setFillColor(NAVY)
    canvas.rect(0, page_h - 6 * mm, page_w, 6 * mm, fill=1, stroke=0)

    canvas.setFillColor(TEAL)
    canvas.rect(0, 0, 3 * mm, page_h - 6 * mm, fill=1, stroke=0)

    canvas.restoreState()


# ── Flowable 组件 ──

class SoftCardFlowable(Flowable):
    """圆角卡片容器。"""

    def __init__(self, inner: Flowable, *, bg, border, padding: float = 8, radius: float = 6):
        super().__init__()
        self.inner = inner
        self.bg = bg
        self.border = border
        self.padding = padding
        self.radius = radius
        self._w = 0
        self._h = 0

    def wrap(self, availWidth, availHeight):
        iw, ih = self.inner.wrap(availWidth - self.padding * 2, availHeight)
        self._w = availWidth
        self._h = ih + self.padding * 2
        return self._w, self._h

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(self.bg)
        c.setStrokeColor(self.border)
        c.setLineWidth(0.5)
        c.roundRect(0, 0, self._w, self._h, self.radius, fill=1, stroke=1)
        c.restoreState()
        self.inner.drawOn(c, self.padding, self.padding)


class AccentBarFlowable(Flowable):
    """左侧带青绿色竖条的段落容器，用于引用和要点。"""

    def __init__(self, inner: Flowable, *, bar_color=TEAL, bar_width=3, bg=TEAL_LIGHT, padding=10):
        super().__init__()
        self.inner = inner
        self.bar_color = bar_color
        self.bar_width = bar_width
        self.bg = bg
        self.padding = padding
        self._w = 0
        self._h = 0

    def wrap(self, availWidth, availHeight):
        iw, ih = self.inner.wrap(availWidth - self.bar_width - self.padding * 2, availHeight)
        self._w = availWidth
        self._h = ih + self.padding * 2
        return self._w, self._h

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(self.bg)
        c.roundRect(0, 0, self._w, self._h, 4, fill=1, stroke=0)
        c.setFillColor(self.bar_color)
        c.rect(0, 0, self.bar_width, self._h, fill=1, stroke=0)
        c.restoreState()
        self.inner.drawOn(c, self.bar_width + self.padding, self.padding)


class HorizontalRuleFlowable(Flowable):
    """水平分割线。"""

    def __init__(self, width=None, color=DIVIDER, thickness=0.6):
        super().__init__()
        self._rule_width = width
        self.color = color
        self.thickness = thickness

    def wrap(self, availWidth, availHeight):
        self._rule_width = self._rule_width or availWidth
        return self._rule_width, 1

    def draw(self):
        self.canv.saveState()
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 0, self._rule_width, 0)
        self.canv.restoreState()


class SectionNumberFlowable(Flowable):
    """章节编号圆圈（深蓝底白字）。"""

    def __init__(self, number: int, title: str, style: ParagraphStyle):
        super().__init__()
        self.number = number
        self.title = title
        self.style = style
        self._para = Paragraph(_esc(title), style)
        self._h = 0

    def wrap(self, availWidth, availHeight):
        circle_space = 14 * mm
        pw, ph = self._para.wrap(availWidth - circle_space, availHeight)
        self._h = max(ph, 10 * mm)
        return availWidth, self._h

    def draw(self):
        c = self.canv
        c.saveState()
        r = 4.5 * mm
        cx = r + 1 * mm
        cy = self._h / 2
        c.setFillColor(NAVY)
        c.circle(cx, cy, r, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(FONT_BOLD, 11)
        c.drawCentredString(cx, cy - 3.5, str(self.number))
        c.restoreState()
        self._para.drawOn(c, 14 * mm, (self._h - self._para.height) / 2)


class SimpleChartFlowable(Flowable):
    """轻量原生 PDF 图表。"""

    def __init__(self, chart: Dict[str, Any], width: float):
        super().__init__()
        self.chart = chart
        self.width = width
        self.height = 68 * mm

    def wrap(self, availWidth, availHeight):
        self.width = min(self.width, availWidth)
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(colors.white)
        c.setStrokeColor(CARD_BORDER)
        c.setLineWidth(0.5)
        c.roundRect(0, 0, self.width, self.height, 6, fill=1, stroke=1)

        # 顶部标题栏
        c.setFillColor(colors.HexColor("#F4F9FA"))
        c.roundRect(0, self.height - 22, self.width, 22, 6, fill=1, stroke=0)
        c.setFillColor(TEAL)
        c.rect(0, self.height - 22, 3, 22, fill=1, stroke=0)

        c.setFont(FONT_BOLD, 9.5)
        c.setFillColor(INK)
        c.drawString(10, self.height - 15, _clean_text(self.chart.get("title") or "图表")[:50])

        ctype = str(self.chart.get("chart_type") or "bar").lower()
        if ctype == "pie":
            self._draw_pie(c)
        elif ctype == "line":
            self._draw_line(c)
        else:
            self._draw_bar(c)
        c.restoreState()

    def _data(self):
        rows = (self.chart.get("rows") or [])[:8]
        cols = self.chart.get("columns") or []
        dim_name = self.chart.get("dimension_field")
        metric_names = self.chart.get("metric_fields") or []
        dim_i = _idx(cols, dim_name) if dim_name else 0
        met_i = _idx(cols, metric_names[0]) if metric_names else 1
        if dim_i is None:
            dim_i = 0
        if met_i is None:
            met_i = 1 if len(cols) > 1 else 0
        data = []
        for r in rows:
            if dim_i >= len(r) or met_i >= len(r):
                continue
            try:
                val = float(str(r[met_i]).replace(",", "").replace("%", "").strip())
            except (TypeError, ValueError):
                continue
            data.append((_clean_text(r[dim_i])[:10], val))
        return data

    def _draw_bar(self, c):
        data = self._data()
        if not data:
            return
        x0, y0 = 16, 18
        chart_w, chart_h = self.width - 32, self.height - 50
        max_v = max(abs(v) for _, v in data) or 1
        gap = 6
        bw = max(10, (chart_w - gap * (len(data) - 1)) / len(data))
        palette = [TEAL, NAVY, colors.HexColor("#5BB5BF"), colors.HexColor("#A3D5DB")]
        c.setFont(FONT, 7)
        for i, (label, val) in enumerate(data):
            h = chart_h * max(0, val) / max_v
            x = x0 + i * (bw + gap)
            c.setFillColor(palette[i % len(palette)])
            c.roundRect(x, y0 + 15, bw, h, 2, fill=1, stroke=0)
            c.setFillColor(MUTED)
            c.drawCentredString(x + bw / 2, y0 + 3, label[:8])

    def _draw_line(self, c):
        data = self._data()
        if len(data) < 2:
            self._draw_bar(c)
            return
        x0, y0 = 18, 24
        chart_w, chart_h = self.width - 36, self.height - 52
        max_v, min_v = max(v for _, v in data), min(v for _, v in data)
        span = max(max_v - min_v, 1)
        pts = []
        for i, (_label, val) in enumerate(data):
            x = x0 + chart_w * i / (len(data) - 1)
            y = y0 + chart_h * (val - min_v) / span
            pts.append((x, y))
        c.setStrokeColor(TEAL)
        c.setLineWidth(2)
        for a, b in zip(pts, pts[1:]):
            c.line(a[0], a[1], b[0], b[1])
        c.setFillColor(NAVY)
        for x, y in pts:
            c.circle(x, y, 2.5, fill=1, stroke=0)

    def _draw_pie(self, c):
        data = self._data()[:6]
        total = sum(max(0, v) for _, v in data)
        if total <= 0:
            return
        cx, cy, r = 50, 32, 20
        start = 90
        palette = [TEAL, NAVY, colors.HexColor("#5BB5BF"), colors.HexColor("#A3D5DB"),
                   colors.HexColor("#D4EEF0"), colors.HexColor("#7BCAD3")]
        for i, (label, val) in enumerate(data):
            extent = 360 * max(0, val) / total
            c.setFillColor(palette[i % len(palette)])
            c.wedge(cx - r, cy - r, cx + r, cy + r, start, extent, fill=1, stroke=0)
            start += extent
        c.setFont(FONT, 7.5)
        lx = 82
        ly = 50
        for i, (label, val) in enumerate(data[:5]):
            c.setFillColor(palette[i % len(palette)])
            c.roundRect(lx, ly - 2, 7, 7, 1.5, fill=1, stroke=0)
            c.setFillColor(BODY_TEXT)
            c.drawString(lx + 10, ly - 1, f"{label[:10]}  {val / total * 100:.1f}%")
            ly -= 11


# ── 样式表 ──

def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title", parent=base["Title"], fontName=FONT_BOLD, fontSize=30,
            leading=40, textColor=INK, alignment=TA_LEFT, spaceAfter=6,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle", parent=base["Normal"], fontName=FONT, fontSize=13,
            leading=20, textColor=TEAL,
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta", parent=base["Normal"], fontName=FONT, fontSize=10.5,
            leading=18, textColor=MUTED,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontName=FONT_BOLD, fontSize=17,
            leading=26, textColor=INK, spaceBefore=6, spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName=FONT_BOLD, fontSize=13,
            leading=20, textColor=NAVY, spaceBefore=10, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontName=FONT, fontSize=10.5,
            leading=18, textColor=BODY_TEXT, spaceAfter=5,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=base["BodyText"], fontName=FONT, fontSize=10.3,
            leading=18, leftIndent=12, firstLineIndent=-8, textColor=BODY_TEXT, spaceAfter=4,
        ),
        "toc_title": ParagraphStyle(
            "toc_title", parent=base["Heading1"], fontName=FONT_BOLD, fontSize=22,
            leading=30, textColor=INK, spaceAfter=14,
        ),
        "toc_item": ParagraphStyle(
            "toc_item", parent=base["BodyText"], fontName=FONT, fontSize=12,
            leading=22, textColor=BODY_TEXT, spaceAfter=2,
        ),
        "toc_num": ParagraphStyle(
            "toc_num", parent=base["BodyText"], fontName=FONT_BOLD, fontSize=13,
            leading=22, textColor=TEAL,
        ),
        "table_title": ParagraphStyle(
            "table_title", parent=base["BodyText"], fontName=FONT_BOLD, fontSize=11,
            leading=17, textColor=INK, spaceBefore=8, spaceAfter=5,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base["BodyText"], fontName=FONT, fontSize=8.5,
            leading=13, textColor=BODY_TEXT,
        ),
        "cell_head": ParagraphStyle(
            "cell_head", parent=base["BodyText"], fontName=FONT_BOLD, fontSize=8.8,
            leading=13, textColor=TABLE_HEAD_TEXT,
        ),
        "quote": ParagraphStyle(
            "quote", parent=base["BodyText"], fontName=FONT, fontSize=10.3,
            leading=18, textColor=BODY_TEXT,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"], fontName=FONT, fontSize=7.5,
            leading=10, textColor=MUTED,
        ),
    }


# ── 公开接口 ──

def build_qa_pdf(
    *,
    module_name: str,
    conversation_title: str,
    file_name: Optional[str],
    author: str,
    messages: List[PptMessage],
) -> bytes:
    pairs = _pair_messages(messages)
    sections = [
        {
            "title": _clean_text(user.content)[:60] or f"问题 {idx}",
            "question": _clean_text(user.content),
            "assistant": ast,
            "charts": _charts_from_assistant(ast),
            "tables": _tables_from_assistant(ast),
            "markdown": _assistant_markdown(ast),
        }
        for idx, (user, ast) in enumerate(pairs, start=1)
    ]
    opts = PdfOptions(title="数据问答报告", author=author)
    meta = {
        "模块": module_name,
        "会话": conversation_title,
        "数据文件": file_name or "未命名文件",
    }
    return _build_report_pdf(opts, meta, sections, toc_title="问题目录")


def build_insight_pdf(
    *,
    module_name: str,
    author: str,
    report: Dict[str, Any],
) -> bytes:
    dimensions = report.get("dimensions") or []
    evidence = report.get("evidence") or {}
    dim_texts = report.get("dim_texts") or {}
    sections: List[Dict[str, Any]] = []
    for i, dim in enumerate(dimensions, start=1):
        did = str(dim.get("id") or "")
        title = dim.get("display_title") or dim.get("title") or f"维度 {i}"
        sections.append(
            {
                "title": str(title),
                "question": str(dim.get("title") or title),
                "charts": _charts_from_evidence(evidence.get(did) or []),
                "tables": _tables_from_evidence(evidence.get(did) or []),
                "markdown": dim_texts.get(did) or "",
            }
        )

    final_md = str(report.get("final_md") or "").strip()
    summary_md = final_md if final_md else "（暂无洞察总结正文，请确认报告已完整生成后重试导出。）"
    sections.append(
        {
            "title": "洞察总结",
            "question": "",
            "charts": [],
            "tables": [],
            "markdown": summary_md,
        }
    )

    opts = PdfOptions(title="数据洞察报告", author=author)
    meta = {"模块": module_name}
    return _build_report_pdf(opts, meta, sections, toc_title="报告目录")


# ── 报告主构建 ──

def _build_report_pdf(opts: PdfOptions, meta: Dict[str, str], sections: List[Dict[str, Any]], *, toc_title: str) -> bytes:
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_Y,
        bottomMargin=MARGIN_Y,
        title=opts.title,
        author=opts.author,
    )

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    cover_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="cover")
    toc_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="toc")

    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], onPage=_draw_cover_page_bg),
        PageTemplate(id="toc", frames=[toc_frame], onPage=_draw_toc_page_bg),
        PageTemplate(id="content", frames=[frame], onPage=_draw_content_page_bg),
    ])

    st = _styles()
    story: List[Any] = []
    generated_at = opts.generated_at or _dt.datetime.now()

    story.extend(_cover_flowables(st, opts.title, opts.author, generated_at, meta))
    story.append(PageBreak())

    from reportlab.platypus.doctemplate import NextPageTemplate
    story.append(NextPageTemplate("toc"))
    story.extend(_toc_flowables(st, toc_title, sections))
    story.append(PageBreak())

    story.append(NextPageTemplate("content"))
    for idx, sec in enumerate(sections, start=1):
        if idx > 1:
            story.append(PageBreak())
        story.append(SectionNumberFlowable(idx, sec["title"], st["h1"]))
        story.append(Spacer(1, 3 * mm))
        if sec.get("question") and sec["question"] != sec["title"]:
            story.append(Paragraph(_esc(sec["question"]), st["body"]))
            story.append(Spacer(1, 4 * mm))
        story.append(HorizontalRuleFlowable(color=TEAL_MID, thickness=0.8))
        story.append(Spacer(1, 4 * mm))
        for chart in sec.get("charts") or []:
            story.extend(_chart_flowables(st, chart))
        for tbl in sec.get("tables") or []:
            story.extend(_table_flowables(st, tbl))
        story.extend(_markdown_flowables(st, sec.get("markdown") or ""))

    doc.build(story)
    return buf.getvalue()


# ── 页面背景绘制 ──

def _draw_cover_page_bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAGE_BG)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    _draw_cover_decoration(canvas, PAGE_W, PAGE_H)
    canvas.restoreState()


def _draw_toc_page_bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAGE_BG)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    _draw_toc_decoration(canvas, PAGE_W, PAGE_H)

    canvas.setFont(FONT, 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(PAGE_W - MARGIN_X, 10 * mm, f"{doc.page}")
    canvas.restoreState()


def _draw_content_page_bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAGE_BG)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # 顶部深蓝细条
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - 4 * mm, PAGE_W, 4 * mm, fill=1, stroke=0)

    # 顶部青绿色装饰点
    canvas.setFillColor(TEAL)
    canvas.circle(MARGIN_X + 2 * mm, PAGE_H - 2 * mm, 1.2 * mm, fill=1, stroke=0)

    # 底部页码和分割线
    canvas.setStrokeColor(DIVIDER)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN_X, 14 * mm, PAGE_W - MARGIN_X, 14 * mm)
    canvas.setFont(FONT, 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(PAGE_W - MARGIN_X, 9 * mm, f"— {doc.page} —")

    # 左下角品牌标记
    canvas.setFont(FONT, 6.5)
    canvas.setFillColor(colors.HexColor("#B0BEC5"))
    canvas.drawString(MARGIN_X, 9 * mm, "Pharma Data Intelligence")

    canvas.restoreState()


# ── 封面页 ──

def _cover_flowables(st, title, author, generated_at, meta):
    flow: List[Any] = []
    flow.append(Spacer(1, 55 * mm))

    # 青绿色副标题
    flow.append(Paragraph("PHARMA DATA INTELLIGENCE", st["cover_subtitle"]))
    flow.append(Spacer(1, 4 * mm))

    # 主标题（黑色）
    flow.append(Paragraph(_esc(title), st["cover_title"]))
    flow.append(Spacer(1, 3 * mm))

    # 青绿色横线
    flow.append(HorizontalRuleFlowable(color=TEAL, thickness=2.5))
    flow.append(Spacer(1, 20 * mm))

    # 元信息表格
    rows = []
    for k, v in meta.items():
        rows.append([
            Paragraph(f"<b>{_esc(k)}</b>", ParagraphStyle(
                "meta_k", fontName=FONT_BOLD, fontSize=9.5, leading=15, textColor=NAVY,
            )),
            Paragraph(_esc(v), ParagraphStyle(
                "meta_v", fontName=FONT, fontSize=9.5, leading=15, textColor=BODY_TEXT,
            )),
        ])
    rows.append([
        Paragraph("<b>制作人</b>", ParagraphStyle(
            "meta_k2", fontName=FONT_BOLD, fontSize=9.5, leading=15, textColor=NAVY,
        )),
        Paragraph(_esc(author), ParagraphStyle(
            "meta_v2", fontName=FONT, fontSize=9.5, leading=15, textColor=BODY_TEXT,
        )),
    ])
    rows.append([
        Paragraph("<b>生成时间</b>", ParagraphStyle(
            "meta_k3", fontName=FONT_BOLD, fontSize=9.5, leading=15, textColor=NAVY,
        )),
        Paragraph(generated_at.strftime("%Y-%m-%d %H:%M"), ParagraphStyle(
            "meta_v3", fontName=FONT, fontSize=9.5, leading=15, textColor=BODY_TEXT,
        )),
    ])

    t = Table(rows, colWidths=[30 * mm, 115 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0F7F8")),
        ("BACKGROUND", (1, 0), (1, -1), colors.white),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, DIVIDER),
        ("LINEBEFORE", (0, 0), (0, -1), 2, TEAL),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    flow.append(t)
    return flow


# ── 目录页 ──

def _toc_flowables(st, toc_title, sections):
    flow: List[Any] = []
    flow.append(Spacer(1, 12 * mm))

    # 目录标题
    flow.append(Paragraph(_esc(toc_title), st["toc_title"]))
    flow.append(HorizontalRuleFlowable(color=NAVY, thickness=1.5))
    flow.append(Spacer(1, 10 * mm))

    for i, sec in enumerate(sections, start=1):
        num_text = f'<font color="{TEAL.hexval()}">{i:02d}</font>'
        title_text = _esc(sec.get("title") or "")

        row = Table(
            [[
                Paragraph(num_text, st["toc_num"]),
                Paragraph(title_text, st["toc_item"]),
            ]],
            colWidths=[14 * mm, None],
            hAlign="LEFT",
        )
        row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (0, 0), 4),
            ("LEFTPADDING", (1, 0), (1, 0), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))

        flow.append(row)
        flow.append(HorizontalRuleFlowable(color=colors.HexColor("#E8EDEF"), thickness=0.4))
        flow.append(Spacer(1, 1 * mm))

    return flow


# ── 表格 ──

def _table_flowables(st, tbl):
    cols = [str(c) for c in (tbl.get("columns") or [])][:7]
    rows = (tbl.get("rows") or [])[:18]
    if not cols or not rows:
        return []

    data = [[Paragraph(_esc(c), st["cell_head"]) for c in cols]]
    for r in rows:
        data.append([Paragraph(_esc(_fmt_cell(r[i] if i < len(r) else "")), st["cell"]) for i in range(len(cols))])

    table = Table(data, repeatRows=1, colWidths=_col_widths(len(cols)))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), TABLE_HEAD_TEXT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, TABLE_ROW_ALT]),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, TEAL),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, TABLE_GRID),
        ("LINEAFTER", (0, 0), (-2, -1), 0.2, TABLE_GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    title_para = Paragraph(
        f'<font color="{TEAL.hexval()}">■</font> {_esc(tbl.get("title") or "关键数据表")}',
        st["table_title"],
    )
    return [KeepTogether([title_para, Spacer(1, 2 * mm), table]), Spacer(1, 6 * mm)]


# ── 图表 ──

def _chart_flowables(st, chart):
    rows = chart.get("rows") or []
    cols = chart.get("columns") or []
    ctype = str(chart.get("chart_type") or "").lower()
    if ctype in {"none", "table"} or not rows or len(cols) < 2:
        return []
    title = chart.get("title") or "关键趋势图"
    return [
        Paragraph(
            f'<font color="{TEAL.hexval()}">■</font> {_esc(title)}',
            st["table_title"],
        ),
        SimpleChartFlowable(chart, PAGE_W - 2 * MARGIN_X),
        Spacer(1, 6 * mm),
    ]


# ── Markdown 渲染 ──

def _markdown_flowables(st, md):
    flow: List[Any] = []
    pending_table: List[str] = []
    for raw in (md or "").splitlines():
        line = raw.strip()
        if not line:
            if pending_table:
                flow.extend(_markdown_table_flowables(st, pending_table))
                pending_table = []
            flow.append(Spacer(1, 2 * mm))
            continue
        if "|" in line and line.startswith("|"):
            pending_table.append(line)
            continue
        if pending_table:
            flow.extend(_markdown_table_flowables(st, pending_table))
            pending_table = []
        if line.startswith("### "):
            flow.append(Paragraph(_esc(line[4:]), st["h2"]))
        elif line.startswith("## "):
            flow.append(Paragraph(_esc(line[3:]), st["h1"]))
        elif line.startswith("- "):
            flow.append(Paragraph(
                f'<font color="{TEAL.hexval()}">●</font> ' + _inline_md(line[2:]),
                st["bullet"],
            ))
        elif line.startswith(">"):
            inner = Paragraph(_inline_md(line.lstrip("> ").strip()), st["quote"])
            flow.append(AccentBarFlowable(inner))
            flow.append(Spacer(1, 2 * mm))
        else:
            flow.append(Paragraph(_inline_md(line), st["body"]))
    if pending_table:
        flow.extend(_markdown_table_flowables(st, pending_table))
    return flow


def _markdown_table_flowables(st, lines):
    parsed = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells):
            continue
        parsed.append(cells)
    if len(parsed) < 2:
        return []
    cols = parsed[0][:7]
    rows = [r[: len(cols)] for r in parsed[1:18]]
    return _table_flowables(st, {"title": "关键内容", "columns": cols, "rows": rows})


# ── 数据提取辅助 ──

def _tables_from_assistant(ast: PptMessage) -> List[Dict[str, Any]]:
    extras = ast.extras or {}
    out: List[Dict[str, Any]] = []
    for sq in extras.get("subquestions") or []:
        cols = sq.get("columns") or []
        rows = sq.get("rows") or []
        if cols and rows:
            out.append({"title": sq.get("question") or sq.get("id") or "数据明细", "columns": cols, "rows": rows})
    return out


def _charts_from_assistant(ast: PptMessage) -> List[Dict[str, Any]]:
    extras = ast.extras or {}
    raw = []
    if isinstance(extras.get("charts"), list):
        raw.extend(extras.get("charts") or [])
    if isinstance(extras.get("chart"), dict):
        raw.append(extras.get("chart"))
    out = []
    seen = set()
    for ch in raw:
        if not isinstance(ch, dict):
            continue
        key = (ch.get("title"), ch.get("subquestion_id"))
        if key in seen:
            continue
        seen.add(key)
        if ch.get("rows") and ch.get("columns"):
            out.append(ch)
    return out[:4]


def _tables_from_evidence(evs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ev in evs:
        if not ev.get("supported"):
            continue
        cols = ev.get("columns") or []
        rows = ev.get("rows") or []
        if cols and rows:
            out.append({"title": ev.get("business_question") or "关键证据", "columns": cols, "rows": rows})
    return out[:5]


def _charts_from_evidence(evs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for ev in evs:
        if not ev.get("supported"):
            continue
        ch = ev.get("chart")
        if isinstance(ch, dict) and ch.get("rows") and ch.get("columns"):
            out.append(ch)
    return out[:5]


def _assistant_markdown(ast: PptMessage) -> str:
    extras = ast.extras or {}
    return extras.get("summary_markdown") or ast.content or ""


def _pair_messages(messages: List[PptMessage]):
    pairs = []
    last_user: Optional[PptMessage] = None
    for m in messages:
        if m.role == "user":
            last_user = m
        elif m.role == "assistant" and last_user is not None:
            pairs.append((last_user, m))
            last_user = None
    return pairs


# ── 通用工具 ──

def _col_widths(n: int):
    total = PAGE_W - 2 * MARGIN_X
    return [total / max(1, n)] * max(1, n)


def _idx(cols: List[Any], name: Any) -> Optional[int]:
    if name is None:
        return None
    key = str(name).strip().lower()
    for i, c in enumerate(cols):
        if str(c).strip().lower() == key:
            return i
    return None


def _clean_text(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _fmt_cell(v: Any) -> str:
    if v is None:
        return ""
    return _clean_text(v)[:180]


def _esc(s: Any) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _inline_md(s: str) -> str:
    x = _esc(s)
    x = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", x)
    x = x.replace("`", "")
    return x


__all__ = ["build_qa_pdf", "build_insight_pdf"]
