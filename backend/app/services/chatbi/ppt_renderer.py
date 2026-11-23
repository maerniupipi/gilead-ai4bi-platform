"""Editable platform PPT exports using neutral templates."""
import logging
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

TITLE = "Chat BI Business Insight Summary"
TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates" / "ppt"
TEMPLATE_PATHS = {
    "FULL_SUMMARY": TEMPLATE_DIR / "ai4bi_export_template_full_summary.pptx",
    "AI_SUMMARY": TEMPLATE_DIR / "ai4bi_export_template_ai_summary.pptx",
}
TITLE_COLOR = (37, 99, 235)
TABLE_HEADER_FILL = (37, 99, 235)
TABLE_HEADER_TEXT = (255, 255, 255)
TABLE_DATA_ROW_FILLS = ((239, 246, 255), (219, 234, 254))
TABLE_BORDER_COLOR = (255, 255, 255)
TABLE_DATA_BORDER_COLOR = (255, 255, 255)
QUESTION_LEFT_PT = 78
QUESTION_TOP_PT = 66
QUESTION_WIDTH_PT = 820
QUESTION_HEIGHT_PT = 30
AI_SUMMARY_TITLE_LEFT_PT = 48
AI_SUMMARY_TITLE_TOP_PT = 66
AI_SUMMARY_TITLE_WIDTH_PT = 820
AI_SUMMARY_TITLE_HEIGHT_PT = 30
AI_SUMMARY_AGENDA_LEFT_PT = 100
AI_SUMMARY_AGENDA_TOP_PT = 150
AI_SUMMARY_AGENDA_WIDTH_PT = 750
AI_SUMMARY_AGENDA_HEIGHT_PT = 330
TABLE_LEFT_PT = 78.33
TABLE_TOP_PT = 123.26
TABLE_WIDTH_PT = 730
TABLE_HEIGHT_PT = 340.8
TABLE_HEADER_HEIGHT_PT = 24
TABLE_DATA_ROW_HEIGHT_PT = 24
TABLE_IMAGE_SCALE = 3
CHART_IMAGE_SCALE = 3
CHART_LEFT_PT = 90
CHART_TOP_PT = 150
CHART_WIDTH_PT = 780
CHART_HEIGHT_PT = 315
SUMMARY_CHART_TOP_PT = 190
SUMMARY_CHART_HEIGHT_PT = 285
TEXT_LEFT_PT = 78
TEXT_TOP_PT = 112
TEXT_WIDTH_PT = 800
TEXT_HEIGHT_PT = 405
CHART_HEADER_LEFT_PT = 130
CHART_HEADER_TOP_PT = 108
CHART_HEADER_WIDTH_PT = 700
CHART_HEADER_HEIGHT_PT = 24

# 默认导出为可编辑 PPT 表格；如需临时改回图片贴入，把该值改为 True 并重启后端。
PPT_TABLES_AS_IMAGES = False
# 默认导出为可编辑 PPT 图表；如需临时改回图片贴入，把该值改为 True 并重启后端。
PPT_CHARTS_AS_IMAGES = False

PRIMARY_COLOR = (37, 99, 235)
CHART_GRIDLINE_COLOR = (230, 230, 230)
PERCENTAGE_TOTAL = 100.0
PERCENTAGE_TOTAL_TOLERANCE = 0.05

# Non-black chart colors used for chart series and category points.
THEME_COLORS = [
    PRIMARY_COLOR,
    (165, 165, 165),
    (68, 114, 196),
    (112, 173, 71),
    (255, 192, 0),
    (91, 155, 213),
    (237, 125, 49),
    (112, 48, 160),
]

# Text pagination constants
ROW_LENGTH = 50      # 每行文字阈值
PAGE_SIZE = 18       # 每页行数阈值；给 14 号正文保留底部安全距离，避免贴近页脚
TABLE_PAGE_SIZE = 13 # 表格每页行数


def _format_ppt_number(value: Any) -> str:
    """Format numeric table values with grouping while preserving decimals."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)

    raw = str(value).strip()
    numeric = raw.replace(",", "")
    is_percent = numeric.endswith("%")
    if is_percent:
        numeric = numeric[:-1].strip()
    try:
        number = Decimal(numeric)
    except (InvalidOperation, ValueError):
        return str(value)

    if not number.is_finite():
        return str(value)
    normalized = format(number, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    integer, dot, fraction = normalized.partition(".")
    sign = ""
    if integer.startswith(("-", "+")):
        sign, integer = integer[0], integer[1:]
    grouped = f"{int(integer or '0'):,}"
    result = f"{sign}{grouped}{dot}{fraction}" if dot else f"{sign}{grouped}"
    return f"{result}%" if is_percent else result


def _style_chart_number_labels(chart, chart_type, point_count: int, is_percentage: bool = False) -> None:
    """Show data labels only for compact charts, keeping labels small."""
    from pptx.enum.chart import XL_CHART_TYPE, XL_DATA_LABEL_POSITION
    from pptx.util import Pt

    is_pie = chart_type == XL_CHART_TYPE.PIE
    number_format = "0.00%" if is_pie else ('0.00"%"' if is_percentage else "#,##0.00")
    if not is_pie:
        try:
            chart.value_axis.tick_labels.number_format = number_format
            chart.value_axis.tick_labels.number_format_is_linked = False
        except Exception:
            pass

    try:
        plot = chart.plots[0]
        if point_count > 10 and not is_pie:
            plot.has_data_labels = False
            return
        plot.has_data_labels = True
        labels = plot.data_labels
        labels.show_value = not is_pie
        labels.number_format = number_format
        labels.number_format_is_linked = False
        labels.font.size = Pt(7)
        if is_pie:
            labels.show_category_name = True
            labels.show_percentage = True
            labels.label_position = XL_DATA_LABEL_POSITION.BEST_FIT
        elif chart_type == XL_CHART_TYPE.LINE:
            labels.label_position = XL_DATA_LABEL_POSITION.ABOVE
        else:
            labels.label_position = XL_DATA_LABEL_POSITION.OUTSIDE_END
    except Exception:
        logger.debug("Unable to apply PPT chart data labels", exc_info=True)


def _style_chart_gridlines(chart, chart_type) -> None:
    """Use light gridlines for editable bar and line charts."""
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE

    if chart_type == XL_CHART_TYPE.PIE:
        return
    try:
        line = chart.value_axis.major_gridlines.format.line
        line.color.rgb = RGBColor(*CHART_GRIDLINE_COLOR)
    except Exception:
        pass


def _style_chart_text(chart, chart_type, point_count: int, legend_size_pt: Optional[int] = None) -> None:
    """Keep editable PPT charts visually close to the raster/template chart style."""
    from pptx.util import Pt

    def apply_font(font, size_pt: int, bold: Optional[bool] = None) -> None:
        font.name = "Microsoft YaHei"
        font.size = Pt(size_pt)
        if bold is not None:
            font.bold = bold

    try:
        apply_font(chart.font, 8)
    except Exception:
        pass

    try:
        if chart.has_title:
            for paragraph in chart.chart_title.text_frame.paragraphs:
                apply_font(paragraph.font, 12, True)
    except Exception:
        pass

    try:
        if chart.has_legend and chart.legend:
            apply_font(chart.legend.font, legend_size_pt or (6 if point_count > 20 else 8))
    except Exception:
        pass

    try:
        tick_size = 6 if point_count > 20 else 8
        apply_font(chart.category_axis.tick_labels.font, tick_size)
        apply_font(chart.value_axis.tick_labels.font, 8)
    except Exception:
        pass

    try:
        for paragraph in chart.category_axis.axis_title.text_frame.paragraphs:
            apply_font(paragraph.font, 9, True)
        for paragraph in chart.value_axis.axis_title.text_frame.paragraphs:
            apply_font(paragraph.font, 9, True)
    except Exception:
        pass

def _apply_chart_theme_colors(chart, chart_type) -> None:
    """Apply palette colors and vary single-series column/bar categories."""
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE

    def rgb(index: int) -> RGBColor:
        return RGBColor(*THEME_COLORS[index % len(THEME_COLORS)])

    is_pie = chart_type == XL_CHART_TYPE.PIE
    is_bar = chart_type in {XL_CHART_TYPE.COLUMN_CLUSTERED, XL_CHART_TYPE.BAR_CLUSTERED}
    try:
        if is_bar:
            try:
                chart.plots[0].vary_by_categories = True
            except Exception:
                pass

        for series_index, series in enumerate(chart.series):
            if is_pie:
                for point_index, point in enumerate(series.points):
                    try:
                        fill = point.format.fill
                        fill.solid()
                        fill.fore_color.rgb = rgb(point_index)
                        point.format.line.color.rgb = RGBColor(255, 255, 255)
                    except Exception:
                        pass
                continue

            if is_bar and len(chart.series) == 1:
                for point_index, point in enumerate(series.points):
                    try:
                        fill = point.format.fill
                        fill.solid()
                        fill.fore_color.rgb = rgb(point_index)
                        point.format.line.color.rgb = RGBColor(255, 255, 255)
                    except Exception:
                        pass
                continue

            color = rgb(series_index)
            try:
                fill = series.format.fill
                fill.solid()
                fill.fore_color.rgb = color
            except Exception:
                pass
            try:
                series.format.line.color.rgb = color
            except Exception:
                pass
            try:
                series.marker.format.fill.solid()
                series.marker.format.fill.fore_color.rgb = color
                series.marker.format.line.color.rgb = color
            except Exception:
                pass
    except Exception:
        logger.debug("Unable to apply PPT chart theme colors", exc_info=True)


def _set_placeholder_text(slide, placeholder_type_names: set[str], text: str) -> bool:
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
    from pptx.util import Pt

    for shape in slide.placeholders:
        try:
            placeholder_name = str(shape.placeholder_format.type).split(" ")[0]
        except Exception:
            continue
        if placeholder_name not in placeholder_type_names:
            continue
        if not shape.has_text_frame:
            continue
        tf = shape.text_frame
        tf.word_wrap = False
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        try:
            shape.left = Pt(30)
            shape.top = Pt(20)
            shape.width = Pt(820)
            shape.height = Pt(42)
        except Exception:
            pass
        tf.clear()
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(32)
        p.font.name = "Microsoft YaHei"
        p.font.bold = False
        p.font.color.rgb = RGBColor(*TITLE_COLOR)
        p.alignment = PP_ALIGN.LEFT
        return True
    return False


def _clear_template_placeholders(slide) -> None:
    placeholder_texts = {
        "Subtitle goes here if required",
        "单击此处添加文本",
    }

    for shape in list(slide.shapes):
        if not shape.has_text_frame:
            continue
        text = shape.text_frame.text.strip()
        if text in placeholder_texts or any(text.startswith(value) for value in placeholder_texts):
            _delete_shape(shape)

    for shape in list(slide.placeholders):
        if not shape.has_text_frame:
            continue
        try:
            placeholder_name = str(shape.placeholder_format.type).split(" ")[0]
        except Exception:
            continue
        text = shape.text_frame.text.strip()
        if text == "Focus area":
            continue
        if placeholder_name in {"SUBTITLE", "BODY", "FOOTER", "OBJECT", "CHART", "TABLE"}:
            _delete_shape(shape)


def _delete_shape(shape) -> None:
    element = shape._element
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _remove_template_slides(prs) -> None:
    slide_id_list = prs.slides._sldIdLst
    for slide_id in list(slide_id_list):
        prs.part.drop_rel(slide_id.rId)
        slide_id_list.remove(slide_id)


def _resolve_template_path(summary_type: str = "FULL_SUMMARY") -> Path:
    """Return the template for the selected export mode for the selected mode."""
    normalized_type = (summary_type or "FULL_SUMMARY").upper()
    preferred_template = TEMPLATE_PATHS.get(normalized_type, TEMPLATE_PATHS["FULL_SUMMARY"])
    if preferred_template.exists():
        return preferred_template
    return preferred_template


def _create_presentation(summary_type: str = "FULL_SUMMARY"):
    from pptx import Presentation
    from pptx.util import Inches

    template_path = _resolve_template_path(summary_type)
    if template_path.exists():
        prs = Presentation(str(template_path))
        slide_layout = prs.slide_layouts[6]
        _remove_template_slides(prs)
        return prs, slide_layout

    logger.warning("PPT template not found, falling back to blank presentation: %s", template_path)
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    return prs, prs.slide_layouts[6]


def _add_content_slide(prs, slide_layout):
    slide = prs.slides.add_slide(slide_layout)
    _clear_template_placeholders(slide)
    return slide


def _handle_tags(text: str) -> str:
    """Remove HTML and Markdown tags from text.

    Matches Java handleTags().
    """
    if not text:
        return text
    # 去除所有 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 去除 Markdown 加粗符号
    text = text.replace("**", "")
    text = text.replace("*", "")
    return text


def _add_title_text(slide):
    """Add title text to slide.

    Matches Java addTitleText(). Java: Rectangle(100, 25, 750, 40)
    """
    from pptx.util import Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN

    if _set_placeholder_text(slide, {"TITLE", "CENTER_TITLE"}, TITLE):
        return

    txBox = slide.shapes.add_textbox(Pt(30), Pt(20), Pt(820), Pt(42))
    tf = txBox.text_frame
    tf.word_wrap = False
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    p = tf.paragraphs[0]
    p.text = TITLE
    p.font.size = Pt(32)
    p.font.name = "Microsoft YaHei"
    p.font.bold = False
    p.font.color.rgb = RGBColor(*TITLE_COLOR)
    p.alignment = PP_ALIGN.LEFT


def _add_question_text(slide, question: str, question_index: Optional[int] = None):
    """Add question text to slide.

    Write the question into the template's fixed white header banner.
    """
    from pptx.util import Pt
    from pptx.enum.text import PP_ALIGN

    txBox = slide.shapes.add_textbox(
        Pt(QUESTION_LEFT_PT),
        Pt(QUESTION_TOP_PT),
        Pt(QUESTION_WIDTH_PT),
        Pt(QUESTION_HEIGHT_PT),
    )
    tf = txBox.text_frame
    tf.margin_left = Pt(0)
    tf.margin_right = Pt(0)
    tf.margin_top = Pt(0)
    tf.margin_bottom = Pt(0)
    p = tf.paragraphs[0]
    suffix = f"{question_index:02d}" if question_index else ""
    p.text = f"【对话名称{suffix}】  {question}"
    p.font.size = Pt(18)
    p.font.name = "Microsoft YaHei"
    p.font.bold = True
    p.alignment = PP_ALIGN.LEFT


def _add_biz_date_text(slide, biz_date: str):
    """Add business date text to slide.

    Matches Java addBizDateText(). Java: Rectangle(800, 500, 70, 20)
    """
    if not biz_date:
        return
    if _resolve_template_path().exists():
        return
    from pptx.util import Pt
    from pptx.enum.text import PP_ALIGN

    txBox = slide.shapes.add_textbox(Pt(800), Pt(500), Pt(70), Pt(20))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = biz_date
    p.font.size = Pt(10)
    p.alignment = PP_ALIGN.RIGHT


def _add_answer_text(slide, answer: str):
    """Add answer text to slide.

    Matches Java addAnswerText(). Java: Rectangle(100, 100, 750, 100)
    """
    from pptx.util import Pt
    from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN

    txBox = slide.shapes.add_textbox(Pt(TEXT_LEFT_PT), Pt(TEXT_TOP_PT), Pt(TEXT_WIDTH_PT), Pt(TEXT_HEIGHT_PT))
    tf = txBox.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    tf.margin_left = Pt(0)
    tf.margin_right = Pt(0)
    tf.margin_top = Pt(0)
    tf.margin_bottom = Pt(0)
    tf.clear()

    lines = str(answer or "").split("\n")
    for idx, line in enumerate(lines):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.text = line
        p.font.name = "Microsoft YaHei"
        p.font.size = Pt(18 if _is_answer_heading(line) else 14)
        p.font.bold = _is_answer_heading(line)
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(2 if _is_answer_heading(line) else 4)
        p.line_spacing = 1.05


def _is_answer_heading(line: str) -> bool:
    text = str(line or "").strip()
    return bool(re.fullmatch(r"(?:【[^】]+】|\[[^\]]+\])", text))


def _add_text_slides(
    prs,
    slide_layout,
    answer: str,
    question: str,
    biz_date: str = None,
    question_index: Optional[int] = None,
):
    """Add text slides with pagination.

    Matches Java addText2PPT(). Splits long text into multiple slides:
    - 50 characters per line
    - 26 lines per page
    """
    answer = _handle_tags(answer)
    if not answer:
        return

    answer_lines = answer.split("\n")
    # Build list of (text, useRows) tuples
    line_info = []
    total_rows = 0
    for text in answer_lines:
        use_rows = max(1, (len(text) - 1) // ROW_LENGTH + 1)
        line_info.append({"text": text, "use_rows": use_rows})
        total_rows += use_rows

    # Paginate
    while total_rows > 0:
        already_use_rows = 0
        page_lines = []
        consumed = []
        for info in line_info:
            if info["use_rows"] + already_use_rows > PAGE_SIZE:
                break
            page_lines.append(info["text"])
            already_use_rows += info["use_rows"]
            consumed.append(info)

        # Remove consumed lines
        for c in consumed:
            line_info.remove(c)

        answer_fragment = "\n".join(page_lines)
        slide = _add_content_slide(prs, slide_layout)
        _add_title_text(slide)
        _add_question_text(slide, question, question_index)
        _add_biz_date_text(slide, biz_date)
        _add_answer_text(slide, answer_fragment)

        total_rows -= already_use_rows


def _get_slide_question(question: str, index: int, ppt_answer_model: dict) -> str:
    """Get the slide question text.

    Matches Java getSlideQuestion(). For the first answer, use the original question.
    For subsequent answers, try to get the query from sql_data.
    """
    if index == 0:
        return question
    sql_data = ppt_answer_model.get("sql_data", [])
    if not sql_data:
        return question
    if isinstance(sql_data, list) and len(sql_data) > 0:
        first = sql_data[0]
        if isinstance(first, dict):
            return first.get("query", question)
    return question


def _add_table_slides(
    prs,
    slide_layout,
    ppt_answer_model: dict,
    question: str,
    biz_date: str = None,
    question_index: Optional[int] = None,
):
    """Add table slides with pagination.

    Matches Java addTable2PPT() / createTable(). Splits large tables into multiple slides:
    - 13 rows per page
    """
    from pptx.util import Pt
    excel_data = ppt_answer_model.get("excel_data", [])
    if not excel_data:
        return

    for data_item in excel_data:
        if not isinstance(data_item, dict):
            continue
        data_list = data_item.get("data", [])

        if not data_list:
            continue

        # Paginate: 13 rows per page
        total_pages = (len(data_list) - 1) // TABLE_PAGE_SIZE + 1
        for page_no in range(1, total_pages + 1):
            offset = (page_no - 1) * TABLE_PAGE_SIZE
            to_index = min(offset + TABLE_PAGE_SIZE, len(data_list))
            page_data = data_list[offset:to_index]

            slide = _add_content_slide(prs, slide_layout)
            _add_title_text(slide)
            _add_question_text(slide, question, question_index)
            _add_biz_date_text(slide, biz_date)

            if not page_data:
                continue

            # Get columns from first row
            columns = list(page_data[0].keys())
            rows_count = len(page_data) + 1  # +1 for header
            cols_count = len(columns)

            if cols_count == 0:
                continue

            if PPT_TABLES_AS_IMAGES and _add_table_image(slide, columns, page_data):
                continue

            _add_editable_table(slide, columns, page_data, rows_count, cols_count)


def _add_editable_table(slide, columns: List[str], page_data: List[dict], rows_count: int, cols_count: int) -> None:
    """Add the original editable PPT table.

    This remains as the rollback path for the temporary image-table export.
    """
    from pptx.util import Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

    table_height = _table_render_height_pt(page_data)
    table_top = _table_render_top_pt(page_data)
    table_shape = slide.shapes.add_table(
        rows_count, cols_count,
        Pt(TABLE_LEFT_PT), Pt(table_top),
        Pt(TABLE_WIDTH_PT), Pt(table_height),
    )
    table = table_shape.table
    numeric_columns = _numeric_table_columns(columns, page_data)

    header_fill = RGBColor(*TABLE_HEADER_FILL)
    header_border = RGBColor(*TABLE_BORDER_COLOR)
    for i, col in enumerate(columns):
        cell = table.cell(0, i)
        cell.text = str(col)
        for paragraph in cell.text_frame.paragraphs:
            paragraph.font.name = "Microsoft YaHei"
            paragraph.font.size = Pt(18)
            paragraph.font.bold = True
            paragraph.font.color.rgb = RGBColor(*TABLE_HEADER_TEXT)
            paragraph.alignment = PP_ALIGN.CENTER
        cell.fill.solid()
        cell.fill.fore_color.rgb = header_fill
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        _set_cell_border(cell, header_border)

    table.rows[0].height = Pt(TABLE_HEADER_HEIGHT_PT)

    data_border = RGBColor(*TABLE_DATA_BORDER_COLOR)
    for row_idx, row_data in enumerate(page_data):
        row_fill = RGBColor(*TABLE_DATA_ROW_FILLS[row_idx % len(TABLE_DATA_ROW_FILLS)])
        for col_idx, col in enumerate(columns):
            cell = table.cell(row_idx + 1, col_idx)
            value = row_data.get(col)
            cell.text = _format_ppt_number(value)
            for paragraph in cell.text_frame.paragraphs:
                paragraph.font.name = "Microsoft YaHei"
                paragraph.font.size = Pt(14)
                paragraph.alignment = PP_ALIGN.RIGHT if col in numeric_columns else PP_ALIGN.CENTER
            cell.fill.solid()
            cell.fill.fore_color.rgb = row_fill
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            _set_cell_border(cell, data_border)
        table.rows[row_idx + 1].height = Pt(TABLE_DATA_ROW_HEIGHT_PT)

    col_width = TABLE_WIDTH_PT / cols_count
    for c in range(cols_count):
        table.columns[c].width = Pt(col_width)


def _add_table_image(slide, columns: List[str], page_data: List[dict]) -> bool:
    """Render the table as a PNG and place it at the original table position."""
    import os
    import tempfile
    from pptx.util import Pt

    image_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = tmp.name
        _render_table_png(columns, page_data, image_path)
        table_height = _table_render_height_pt(page_data)
        table_top = _table_render_top_pt(page_data)
        image_shape = slide.shapes.add_picture(
            image_path,
            Pt(TABLE_LEFT_PT),
            Pt(table_top),
            width=Pt(TABLE_WIDTH_PT),
            height=Pt(table_height),
        )
        image_shape.name = "Rendered Table Image"
        return True
    except Exception:
        logger.warning("Failed to render PPT table as image; falling back to editable table.", exc_info=True)
        return False
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)


def _render_table_png(columns: List[str], page_data: List[dict], image_path: str) -> None:
    """Render table cells to a transparent PNG matching the PPT table geometry."""
    from PIL import Image, ImageDraw

    scale = TABLE_IMAGE_SCALE
    width_px = int(TABLE_WIDTH_PT * scale)
    height_px = int(_table_render_height_pt(page_data) * scale)
    header_h = int(TABLE_HEADER_HEIGHT_PT * scale)
    row_h = int(TABLE_DATA_ROW_HEIGHT_PT * scale)
    line_w = max(1, int(scale))
    padding_x = int(5 * scale)

    image = Image.new("RGBA", (width_px, height_px), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)

    header_font = _load_table_font(int(18 * scale), bold=True)
    data_font = _load_table_font(int(14 * scale), bold=False)
    col_w = width_px / max(1, len(columns))
    numeric_columns = _numeric_table_columns(columns, page_data)

    for col_idx, col in enumerate(columns):
        x0 = int(round(col_idx * col_w))
        x1 = int(round((col_idx + 1) * col_w))
        _draw_table_cell(
            draw,
            text=str(col),
            xy=(x0, 0, x1, header_h),
            fill=TABLE_HEADER_FILL,
            outline=TABLE_BORDER_COLOR,
            font=header_font,
            text_fill=TABLE_HEADER_TEXT,
            padding_x=padding_x,
            line_w=line_w,
            alignment="center",
        )

    for row_idx, row_data in enumerate(page_data):
        y0 = header_h + row_idx * row_h
        y1 = y0 + row_h
        row_fill = TABLE_DATA_ROW_FILLS[row_idx % len(TABLE_DATA_ROW_FILLS)]
        for col_idx, col in enumerate(columns):
            x0 = int(round(col_idx * col_w))
            x1 = int(round((col_idx + 1) * col_w))
            _draw_table_cell(
                draw,
                text=_format_ppt_number(row_data.get(col)),
                xy=(x0, y0, x1, y1),
                fill=row_fill,
                outline=TABLE_DATA_BORDER_COLOR,
                font=data_font,
                text_fill=(0, 0, 0),
                padding_x=padding_x,
                line_w=line_w,
                alignment="right" if col in numeric_columns else "center",
            )

    image.save(image_path, "PNG")


def _load_table_font(size_px: int, bold: bool = False):
    """Load Microsoft YaHei for table images when available, with CJK fallbacks."""
    from PIL import ImageFont

    candidates = [
        "/Library/Fonts/Microsoft YaHei Bold.ttf" if bold else "/Library/Fonts/Microsoft YaHei.ttf",
        "/System/Library/Fonts/Microsoft YaHei Bold.ttf" if bold else "/System/Library/Fonts/Microsoft YaHei.ttf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for font_path in candidates:
        if Path(font_path).exists():
            try:
                return ImageFont.truetype(font_path, size_px)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_table_cell(
    draw,
    *,
    text: str,
    xy: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    outline: tuple[int, int, int],
    font,
    text_fill: tuple[int, int, int],
    padding_x: int,
    line_w: int,
    alignment: str = "center",
) -> None:
    x0, y0, x1, y1 = xy
    draw.rectangle([x0, y0, x1, y1], fill=fill + (255,), outline=outline + (255,), width=line_w)
    max_text_width = max(0, x1 - x0 - padding_x * 2)
    rendered_text = _fit_text_to_width(draw, text or "", font, max_text_width)
    if not rendered_text:
        return
    bbox = draw.textbbox((0, 0), rendered_text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    if alignment == "right":
        text_x = x1 - padding_x - text_w
    elif alignment == "left":
        text_x = x0 + padding_x
    else:
        text_x = x0 + max(0, (x1 - x0 - text_w) // 2)
    text_y = y0 + max(0, (y1 - y0 - text_h) // 2) - bbox[1]
    draw.text((text_x, text_y), rendered_text, fill=text_fill + (255,), font=font)


def _fit_text_to_width(draw, text: str, font, max_width: int) -> str:
    if not text or max_width <= 0:
        return ""
    if _text_width(draw, text, font) <= max_width:
        return text

    ellipsis = "..."
    if _text_width(draw, ellipsis, font) > max_width:
        return ""
    fitted = text
    while fitted and _text_width(draw, fitted + ellipsis, font) > max_width:
        fitted = fitted[:-1]
    return fitted + ellipsis if fitted else ""


def _text_width(draw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _numeric_table_columns(columns: List[str], page_data: List[dict]) -> set[str]:
    numeric_columns: set[str] = set()
    for col in columns:
        for row_data in page_data:
            if isinstance(row_data, dict) and _to_float(row_data.get(col)) is not None:
                numeric_columns.add(col)
                break
    return numeric_columns


def _table_render_height_pt(page_data: List[dict]) -> float:
    return min(TABLE_HEIGHT_PT, TABLE_HEADER_HEIGHT_PT + len(page_data) * TABLE_DATA_ROW_HEIGHT_PT)


def _table_render_top_pt(page_data: List[dict]) -> float:
    return TABLE_TOP_PT


def _set_cell_border(cell, color_rgb):
    """Set all four border colors on a table cell.

    Matches Java setBorderColor() on left, right, bottom, top.
    """
    from pptx.oxml.ns import qn
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    # Remove existing borders if any
    for edge_name in ['lnL', 'lnR', 'lnT', 'lnB']:
        existing = tcPr.findall(qn(f'a:{edge_name}'))
        for e in existing:
            tcPr.remove(e)
    # Add borders
    for edge_name in ['lnL', 'lnR', 'lnT', 'lnB']:
        ln = tcPr.makeelement(qn(f'a:{edge_name}'), {})
        ln.set('w', '12700')  # 1pt in EMU
        solidFill = ln.makeelement(qn('a:solidFill'), {})
        srgbClr = solidFill.makeelement(qn('a:srgbClr'), {'val': f'{color_rgb[0]:02X}{color_rgb[1]:02X}{color_rgb[2]:02X}'})
        solidFill.append(srgbClr)
        ln.append(solidFill)
        tcPr.append(ln)


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if not value:
                return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _series_values(data: List[dict], y_key: str) -> List[float]:
    values = []
    for row in data:
        if not isinstance(row, dict):
            continue
        value = _to_float(row.get(y_key))
        if value is not None:
            values.append(value)
    return values


def _values_sum_to_100(values: List[float]) -> bool:
    if not values:
        return False
    return abs(sum(values) - PERCENTAGE_TOTAL) <= PERCENTAGE_TOTAL_TOLERANCE


def _chart_values_sum_to_100(data: List[dict], y_keys: List[str]) -> bool:
    """Infer percentage distributions when each plotted series totals 100."""
    series_totals = []
    for y_key in y_keys:
        values = _series_values(data, y_key)
        if values:
            series_totals.append(_values_sum_to_100(values))
    return bool(series_totals) and all(series_totals)


def _chart_title_text(query: str, y_axis_name: str) -> str:
    return f"下图表示的是： {y_axis_name}"


def _add_chart_header(slide, query: str, y_axis_name: str):
    from pptx.util import Pt
    from pptx.enum.text import PP_ALIGN

    txBox = slide.shapes.add_textbox(
        Pt(CHART_HEADER_LEFT_PT),
        Pt(CHART_HEADER_TOP_PT),
        Pt(CHART_HEADER_WIDTH_PT),
        Pt(CHART_HEADER_HEIGHT_PT),
    )
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = _chart_title_text(query, y_axis_name)
    p.font.size = Pt(14)
    p.font.name = "Microsoft YaHei"
    p.font.bold = True
    p.alignment = PP_ALIGN.LEFT


def _make_category_chart_data(data: List[dict], x_key: str, y_keys: List[str], series_title: Optional[str] = None):
    from pptx.chart.data import CategoryChartData

    chart_data = CategoryChartData()
    chart_data.categories = [str(row.get(x_key, "")) for row in data if isinstance(row, dict)]
    for y_key in y_keys:
        values = []
        for row in data:
            if not isinstance(row, dict):
                continue
            values.append(_to_float(row.get(y_key)) or 0)
        chart_data.add_series(series_title or str(y_key), values)
    return chart_data


def _make_chart_image_payload(
    data: List[dict],
    x_key: str,
    y_keys: List[str],
    series_title: Optional[str] = None,
) -> tuple[List[str], List[dict]]:
    categories = [str(row.get(x_key, "")) for row in data if isinstance(row, dict)]
    series_list = []
    for y_key in y_keys:
        values = []
        for row in data:
            if not isinstance(row, dict):
                continue
            values.append(_to_float(row.get(y_key)) or 0)
        series_list.append({"name": series_title or str(y_key), "values": values})
    return categories, series_list


def _add_chart_image(
    slide,
    *,
    chart_type,
    data: List[dict],
    x_key: str,
    y_keys: List[str],
    x_axis_name: str,
    y_axis_name: str,
    left_pt: float,
    top_pt: float,
    width_pt: float,
    height_pt: float,
    series_title: Optional[str] = None,
    has_legend: bool = True,
    percentage_context_names: Optional[List[str]] = None,
) -> bool:
    """Render chart as PNG and place it at the chart position."""
    import os
    import tempfile
    from pptx.util import Pt

    image_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = tmp.name
        categories, series_list = _make_chart_image_payload(data, x_key, y_keys, series_title)
        _render_chart_png(
            chart_type,
            categories,
            series_list,
            x_axis_name,
            y_axis_name,
            image_path,
            int(width_pt * CHART_IMAGE_SCALE),
            int(height_pt * CHART_IMAGE_SCALE),
            _should_format_chart_as_percentage(
                data,
                y_keys,
                y_axis_name,
                series_title or "",
                *(percentage_context_names or []),
            ),
            has_legend,
        )
        image_shape = slide.shapes.add_picture(
            image_path,
            Pt(left_pt),
            Pt(top_pt),
            width=Pt(width_pt),
            height=Pt(height_pt),
        )
        image_shape.name = "Rendered Chart Image"
        return True
    except Exception:
        logger.warning("Failed to render PPT chart as image; falling back to editable chart.", exc_info=True)
        return False
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)


def _render_chart_png(
    chart_type,
    categories: List[str],
    series_list: List[dict],
    x_axis_name: str,
    y_axis_name: str,
    image_path: str,
    width_px: int,
    height_px: int,
    is_percentage: bool = False,
    has_legend: bool = True,
) -> None:
    from PIL import Image, ImageDraw
    from pptx.enum.chart import XL_CHART_TYPE

    image = Image.new("RGBA", (width_px, height_px), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    if not categories or not series_list:
        image.save(image_path, "PNG")
        return

    if chart_type == XL_CHART_TYPE.PIE:
        _draw_pie_chart(draw, categories, series_list[0], width_px, height_px, is_percentage)
    elif chart_type == XL_CHART_TYPE.LINE:
        _draw_line_chart(draw, categories, series_list, width_px, height_px, x_axis_name, y_axis_name, is_percentage, has_legend)
    else:
        _draw_bar_chart(draw, categories, series_list, width_px, height_px, x_axis_name, y_axis_name, is_percentage, has_legend)
    image.save(image_path, "PNG")


def _draw_bar_chart(draw, categories, series_list, width_px, height_px, x_axis_name, y_axis_name, is_percentage, has_legend):
    scale = CHART_IMAGE_SCALE
    axis_font = _load_table_font(int(9 * scale))
    label_font = _load_table_font(int((7 if len(categories) > 10 else 8) * scale))
    legend_font = _load_table_font(int(9 * scale))
    right = int(18 * scale)
    category_legend = len(series_list) == 1 and len(categories) > 10
    top = int((70 if category_legend else (26 if has_legend else 10)) * scale)
    bottom = int((82 if len(categories) > 10 else 58) * scale)
    values = [value for series in series_list for value in series["values"]]
    min_value, max_value = _chart_value_bounds(values)
    left = _chart_left_margin(draw, min_value, max_value, axis_font, is_percentage)
    plot_w = max(1, width_px - left - right)
    plot_h = max(1, height_px - top - bottom)

    _draw_chart_axes(draw, left, top, plot_w, plot_h, min_value, max_value, axis_font, is_percentage)
    if category_legend:
        _draw_category_legend(draw, categories, left, int(4 * scale), width_px - left - right, legend_font)
    if has_legend and len(series_list) > 1:
        _draw_chart_legend(draw, series_list, left, int(4 * scale), legend_font)

    group_gap = max(2 * scale, plot_w / max(1, len(categories)) * 0.25)
    group_w = max(1, (plot_w - group_gap * (len(categories) + 1)) / max(1, len(categories)))
    series_count = max(1, len(series_list))
    bar_gap = max(1, int(2 * scale))
    bar_w = max(1, int((group_w - bar_gap * (series_count - 1)) / series_count))
    baseline_y = _value_to_y(0 if min_value < 0 < max_value else min_value, min_value, max_value, top, plot_h)

    for category_index, category in enumerate(categories):
        group_x = left + group_gap + category_index * (group_w + group_gap)
        for series_index, series in enumerate(series_list):
            value = series["values"][category_index] if category_index < len(series["values"]) else 0
            bar_x0 = int(group_x + series_index * (bar_w + bar_gap))
            bar_x1 = int(bar_x0 + bar_w)
            value_y = _value_to_y(value, min_value, max_value, top, plot_h)
            y0, y1 = sorted((baseline_y, value_y))
            color = _chart_color(category_index) if len(series_list) == 1 else _chart_color(series_index)
            draw.rectangle([bar_x0, y0, bar_x1, y1], fill=color + (255,), outline=(255, 255, 255, 255), width=max(1, scale))
            if len(categories) <= 10:
                label = _format_chart_value(value, is_percentage)
                _draw_centered_text(draw, label, (bar_x0 + bar_x1) // 2, max(0, y0 - int(4 * scale)), label_font, (0, 0, 0), anchor_bottom=True)

        label_x = int(group_x + group_w / 2)
        if len(categories) > 10:
            _draw_vertical_label(draw, _shorten_label(category, 5), label_x, top + plot_h + int(6 * scale), label_font, (0, 0, 0))
        else:
            _draw_centered_text(draw, _shorten_label(category, 8), label_x, top + plot_h + int(8 * scale), label_font, (0, 0, 0))

    _draw_axis_titles(draw, x_axis_name, y_axis_name, left, top, plot_w, plot_h, axis_font)


def _draw_line_chart(draw, categories, series_list, width_px, height_px, x_axis_name, y_axis_name, is_percentage, has_legend):
    scale = CHART_IMAGE_SCALE
    axis_font = _load_table_font(int(9 * scale))
    label_font = _load_table_font(int(8 * scale))
    legend_font = _load_table_font(int(9 * scale))
    right = int(18 * scale)
    top = int((26 if has_legend else 10) * scale)
    bottom = int(58 * scale)
    values = [value for series in series_list for value in series["values"]]
    min_value, max_value = _chart_value_bounds(values)
    left = _chart_left_margin(draw, min_value, max_value, axis_font, is_percentage)
    plot_w = max(1, width_px - left - right)
    plot_h = max(1, height_px - top - bottom)

    _draw_chart_axes(draw, left, top, plot_w, plot_h, min_value, max_value, axis_font, is_percentage)
    if has_legend:
        _draw_chart_legend(draw, series_list, left, int(4 * scale), legend_font)

    denom = max(1, len(categories) - 1)
    for series_index, series in enumerate(series_list):
        color = PRIMARY_COLOR if len(series_list) == 1 else _chart_color(series_index)
        points = []
        for category_index, value in enumerate(series["values"]):
            x = int(left + (category_index / denom) * plot_w)
            y = _value_to_y(value, min_value, max_value, top, plot_h)
            points.append((x, y, value))
        if len(points) > 1:
            draw.line([(x, y) for x, y, _ in points], fill=color + (255,), width=max(2, int(2 * scale)))
        radius = max(3, int(3 * scale))
        for x, y, value in points:
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color + (255,), outline=(255, 255, 255, 255), width=max(1, scale))
            if len(categories) <= 10 and len(series_list) == 1:
                _draw_centered_text(draw, _format_chart_value(value, is_percentage), x, y - int(7 * scale), label_font, (0, 0, 0), anchor_bottom=True)

    label_step = max(1, len(categories) // 10)
    for category_index, category in enumerate(categories):
        if category_index % label_step != 0 and category_index != len(categories) - 1:
            continue
        x = int(left + (category_index / denom) * plot_w)
        _draw_centered_text(draw, _shorten_label(category, 8), x, top + plot_h + int(8 * scale), label_font, (0, 0, 0))

    _draw_axis_titles(draw, x_axis_name, y_axis_name, left, top, plot_w, plot_h, axis_font)


def _draw_pie_chart(draw, categories, series, width_px, height_px, is_percentage):
    import math

    scale = CHART_IMAGE_SCALE
    label_font = _load_table_font(int(9 * scale))
    values = [max(0, float(value or 0)) for value in series["values"]]
    total = sum(values)
    if total <= 0:
        return
    radius = int(min(width_px, height_px) * 0.34)
    center_x = int(width_px * 0.38)
    center_y = int(height_px * 0.5)
    bbox = [center_x - radius, center_y - radius, center_x + radius, center_y + radius]
    start = -90
    for index, value in enumerate(values):
        extent = value / total * 360
        color = _chart_color(index)
        draw.pieslice(bbox, start=start, end=start + extent, fill=color + (255,), outline=(255, 255, 255, 255), width=max(1, scale))
        if len(values) <= 10 and extent >= 10:
            mid = start + extent / 2
            x = center_x + int(radius * 0.62 * math.cos(math.radians(mid)))
            y = center_y + int(radius * 0.62 * math.sin(math.radians(mid)))
            label = f"{value / total * 100:.2f}%"
            _draw_centered_text(draw, label, x, y, label_font, (0, 0, 0))
        start += extent

    legend_x = int(width_px * 0.72)
    legend_y = int(height_px * 0.18)
    line_h = int(17 * scale)
    for index, category in enumerate(categories[:12]):
        y = legend_y + index * line_h
        color = _chart_color(index)
        draw.rectangle([legend_x, y, legend_x + int(10 * scale), y + int(10 * scale)], fill=color + (255,))
        percentage = (values[index] / total * 100) if index < len(values) else 0
        text = f"{_shorten_label(category, 14)} {_format_chart_value(percentage, True)}"
        draw.text((legend_x + int(15 * scale), y - int(2 * scale)), text, fill=(0, 0, 0, 255), font=label_font)


def _draw_chart_axes(draw, left, top, plot_w, plot_h, min_value, max_value, font, is_percentage):
    scale = CHART_IMAGE_SCALE
    axis_color = (80, 80, 80, 255)
    grid_color = CHART_GRIDLINE_COLOR + (255,)
    ticks = 5
    for idx in range(ticks + 1):
        value = min_value + (max_value - min_value) * idx / ticks
        y = _value_to_y(value, min_value, max_value, top, plot_h)
        draw.line([left, y, left + plot_w, y], fill=grid_color, width=max(1, scale // 2))
        label = _format_chart_value(value, is_percentage)
        bbox = draw.textbbox((0, 0), label, font=font)
        draw.text((left - (bbox[2] - bbox[0]) - int(6 * scale), y - (bbox[3] - bbox[1]) // 2), label, fill=(0, 0, 0, 255), font=font)
    draw.line([left, top, left, top + plot_h], fill=axis_color, width=max(1, scale))
    draw.line([left, top + plot_h, left + plot_w, top + plot_h], fill=axis_color, width=max(1, scale))


def _chart_left_margin(draw, min_value: float, max_value: float, font, is_percentage: bool) -> int:
    scale = CHART_IMAGE_SCALE
    labels = [
        _format_chart_value(min_value + (max_value - min_value) * idx / 5, is_percentage)
        for idx in range(6)
    ]
    max_width = max((_text_width(draw, label, font) for label in labels), default=0)
    return max(int(64 * scale), max_width + int(12 * scale))


def _draw_chart_legend(draw, series_list, left, top, font):
    scale = CHART_IMAGE_SCALE
    x = left
    for index, series in enumerate(series_list[:6]):
        color = _chart_color(index)
        draw.rectangle([x, top, x + int(10 * scale), top + int(10 * scale)], fill=color + (255,))
        label = str(series.get("name") or "")
        draw.text((x + int(14 * scale), top - int(2 * scale)), _shorten_label(label, 18), fill=(0, 0, 0, 255), font=font)
        text_w = _text_width(draw, _shorten_label(label, 18), font)
        x += int(28 * scale) + text_w


def _draw_category_legend(draw, categories: List[str], left: int, top: int, max_width: int, font) -> None:
    scale = CHART_IMAGE_SCALE
    x = left
    y = top
    row_h = int(15 * scale)
    square = int(8 * scale)
    for category in categories[:48]:
        label = _shorten_label(category, 5)
        item_w = square + int(5 * scale) + _text_width(draw, label, font) + int(12 * scale)
        if x > left and x + item_w > left + max_width:
            x = left
            y += row_h
        draw.rectangle([x, y + int(2 * scale), x + square, y + int(2 * scale) + square], fill=_chart_color(index) + (255,))
        draw.text((x + square + int(4 * scale), y), label, fill=(0, 0, 0, 255), font=font)
        x += item_w


def _draw_vertical_label(draw, text: str, center_x: int, top: int, font, fill: tuple[int, int, int]) -> None:
    y = top
    for char in str(text or ""):
        bbox = draw.textbbox((0, 0), char, font=font)
        char_w = bbox[2] - bbox[0]
        char_h = bbox[3] - bbox[1]
        draw.text((center_x - char_w // 2, y), char, fill=fill + (255,), font=font)
        y += max(char_h, int(7 * CHART_IMAGE_SCALE))


def _draw_axis_titles(draw, x_axis_name, y_axis_name, left, top, plot_w, plot_h, font):
    scale = CHART_IMAGE_SCALE
    _draw_centered_text(draw, x_axis_name, left + plot_w // 2, top + plot_h + int(35 * scale), font, (0, 0, 0))
    if y_axis_name:
        draw.text((left, max(0, top - int(20 * scale))), y_axis_name, fill=(0, 0, 0, 255), font=font)


def _draw_centered_text(draw, text, center_x, y, font, fill, anchor_bottom: bool = False):
    if not text:
        return
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_y = y - text_h if anchor_bottom else y
    draw.text((center_x - text_w // 2, text_y), text, fill=fill + (255,), font=font)


def _chart_value_bounds(values: List[float]) -> tuple[float, float]:
    clean_values = [float(value or 0) for value in values] or [0]
    min_value = min(0, min(clean_values))
    max_value = max(clean_values)
    if max_value == min_value:
        max_value = min_value + 1
    padding = (max_value - min_value) * 0.12
    return min_value, max_value + padding


def _value_to_y(value: float, min_value: float, max_value: float, top: int, plot_h: int) -> int:
    ratio = (float(value) - min_value) / (max_value - min_value)
    return int(top + plot_h - ratio * plot_h)


def _chart_color(index: int) -> tuple[int, int, int]:
    return THEME_COLORS[index % len(THEME_COLORS)]


def _format_chart_value(value: float, is_percentage: bool = False) -> str:
    value = float(value or 0)
    if is_percentage:
        return f"{value:.2f}%"
    if abs(value) >= 1000:
        return f"{value:,.2f}"
    return f"{value:.2f}"


def _shorten_label(text: str, max_chars: int) -> str:
    text = str(text or "")
    return text if len(text) <= max_chars else text[: max(1, max_chars - 3)] + "..."


def _add_native_chart_slide(
    prs,
    slide_layout,
    *,
    chart_type,
    chart_item: dict,
    data: List[dict],
    x_key: str,
    y_keys: List[str],
    x_axis_name: str,
    y_axis_name: str,
    question: str,
    biz_date: str = None,
    series_title: Optional[str] = None,
    question_index: Optional[int] = None,
):
    from pptx.util import Pt
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION

    if not data or not x_key or not y_keys:
        return

    slide = _add_content_slide(prs, slide_layout)
    _add_title_text(slide)
    _add_question_text(slide, question, question_index)
    _add_biz_date_text(slide, biz_date)
    _add_chart_header(slide, str(chart_item.get("query") or ""), y_axis_name)
    is_percentage_chart = _should_format_chart_as_percentage(
        data,
        y_keys,
        y_axis_name,
        series_title or "",
        chart_item.get("query") or "",
        question,
    )

    if PPT_CHARTS_AS_IMAGES and _add_chart_image(
        slide,
        chart_type=chart_type,
        data=data,
        x_key=x_key,
        y_keys=y_keys,
        x_axis_name=x_axis_name,
        y_axis_name=y_axis_name,
        left_pt=CHART_LEFT_PT,
        top_pt=CHART_TOP_PT,
        width_pt=CHART_WIDTH_PT,
        height_pt=CHART_HEIGHT_PT,
        series_title=series_title,
        has_legend=chart_type == XL_CHART_TYPE.PIE or len(y_keys) > 1,
        percentage_context_names=[chart_item.get("query") or "", question],
    ):
        return

    chart_data = _make_category_chart_data(data, x_key, y_keys, series_title)
    graphic_frame = slide.shapes.add_chart(
        chart_type,
        Pt(CHART_LEFT_PT),
        Pt(CHART_TOP_PT),
        Pt(CHART_WIDTH_PT),
        Pt(CHART_HEIGHT_PT),
        chart_data,
    )
    chart = graphic_frame.chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.TOP
    chart.legend.include_in_layout = False
    _apply_chart_theme_colors(chart, chart_type)
    _style_chart_gridlines(chart, chart_type)
    _style_chart_number_labels(chart, chart_type, len(data), is_percentage_chart)
    try:
        chart.category_axis.axis_title.text_frame.text = x_axis_name
    except Exception:
        pass
    try:
        chart.value_axis.axis_title.text_frame.text = y_axis_name
    except Exception:
        pass
    _style_chart_text(chart, chart_type, len(data), legend_size_pt=12)


def _pivot_two_x_axes(data: List[dict], x_key: str, convert_x_key: str, y_key: str) -> tuple[List[dict], List[str]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    series_keys: List[str] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        category = str(row.get(x_key, ""))
        series = str(row.get(convert_x_key, ""))
        if series not in series_keys:
            series_keys.append(series)
        grouped.setdefault(category, {x_key: category})[series] = row.get(y_key)
    return list(grouped.values()), series_keys


def _handle_single_x_axis_chart(
    prs,
    slide_layout,
    chart_item: dict,
    data: List[dict],
    x_key: str,
    y_keys: List[str],
    x_axis_name: str,
    y_axis_name: str,
    series_title: Optional[str],
    question: str,
    biz_date: str = None,
    question_index: Optional[int] = None,
):
    from pptx.enum.chart import XL_CHART_TYPE

    _add_native_chart_slide(
        prs,
        slide_layout,
        chart_type=XL_CHART_TYPE.COLUMN_CLUSTERED,
        chart_item=chart_item,
        data=data,
        x_key=x_key,
        y_keys=y_keys,
        x_axis_name=x_axis_name,
        y_axis_name=y_axis_name,
        question=question,
        biz_date=biz_date,
        series_title=series_title,
        question_index=question_index,
    )
    _add_native_chart_slide(
        prs,
        slide_layout,
        chart_type=XL_CHART_TYPE.LINE,
        chart_item=chart_item,
        data=data,
        x_key=x_key,
        y_keys=y_keys,
        x_axis_name=x_axis_name,
        y_axis_name=y_axis_name,
        question=question,
        biz_date=biz_date,
        series_title=series_title,
        question_index=question_index,
    )
    if len(y_keys) == 1:
        _add_native_chart_slide(
            prs,
            slide_layout,
            chart_type=XL_CHART_TYPE.PIE,
            chart_item=chart_item,
            data=data,
            x_key=x_key,
            y_keys=y_keys,
            x_axis_name=x_axis_name,
            y_axis_name=y_axis_name,
            question=question,
            biz_date=biz_date,
            series_title=series_title,
            question_index=question_index,
        )


def _add_chart_slides(
    prs,
    slide_layout,
    ppt_answer_model: dict,
    question: str,
    biz_date: str = None,
    question_index: Optional[int] = None,
):
    """Add real bar/line/pie chart slides, matching Java addCharts2PPT behavior."""

    chart_data = ppt_answer_model.get("chart_data", [])
    if not chart_data:
        return

    for chart_item in chart_data:
        if not isinstance(chart_item, dict):
            continue

        query = chart_item.get("query", "")
        chart_obj = chart_item.get("chart", {})
        if not isinstance(chart_obj, dict):
            continue

        columns = chart_obj.get("columns", [])
        data = chart_obj.get("data", [])

        x_axes = [c for c in columns if isinstance(c, dict) and c.get("target") == "xaxis" and c.get("key")]
        y_axes = [c for c in columns if isinstance(c, dict) and c.get("target") == "yaxis" and c.get("key")]
        if not x_axes or not y_axes or not isinstance(data, list) or not data:
            continue
        if len(x_axes) > 2:
            continue

        key_name = {str(col.get("key")): str(col.get("name") or col.get("key")) for col in columns if isinstance(col, dict) and col.get("key")}
        if len(x_axes) == 2:
            first_x = str(x_axes[0].get("key"))
            second_x = str(x_axes[1].get("key"))
            for y_axis in y_axes:
                y_key = str(y_axis.get("key"))
                pivoted, series_keys = _pivot_two_x_axes(data, first_x, second_x, y_key)
                _handle_single_x_axis_chart(
                    prs, slide_layout, chart_item, pivoted, first_x, series_keys,
                    key_name.get(first_x, first_x), key_name.get(y_key, y_key), None, question, biz_date, question_index
                )
                pivoted, series_keys = _pivot_two_x_axes(data, second_x, first_x, y_key)
                _handle_single_x_axis_chart(
                    prs, slide_layout, chart_item, pivoted, second_x, series_keys,
                    key_name.get(second_x, second_x), key_name.get(y_key, y_key), None, question, biz_date, question_index
                )
            continue

        x_key = str(x_axes[0].get("key"))
        for y_axis in y_axes:
            y_key = str(y_axis.get("key"))
            y_name = key_name.get(y_key, y_key)
            _handle_single_x_axis_chart(
                prs, slide_layout, chart_item, data, x_key, [y_key],
                key_name.get(x_key, x_key), y_name, y_name, question, biz_date, question_index
            )


def _is_percentage_metric(metric_name: str) -> bool:
    normalized_name = str(metric_name or "").lower()
    percentage_tokens = ("%", "占比", "百分比", "比例", "ratio", "percent", "percentage")
    return any(token in normalized_name for token in percentage_tokens)


def _should_format_chart_as_percentage(
    data: List[dict],
    y_keys: List[str],
    *context_names: str,
) -> bool:
    """Format chart values as percentages when explicitly named or totaling 100."""
    if any(_is_percentage_metric(name) for name in context_names):
        return True
    return _chart_values_sum_to_100(data, y_keys)


def _add_bullet_textbox(
    slide,
    lines: List[str],
    *,
    left,
    top,
    width,
    height,
    font_size=14,
    bold=False,
    space_after=6,
    line_spacing=None,
    alignment=None,
):
    from pptx.util import Pt
    from pptx.enum.text import PP_ALIGN

    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(0)
    tf.margin_right = Pt(0)
    tf.margin_top = Pt(0)
    tf.margin_bottom = Pt(0)
    tf.clear()
    for idx, line in enumerate(lines):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        # Preserve Markdown emphasis as editable PowerPoint runs.
        for segment in re.split(r'(\*\*.+?\*\*)', str(line or '')):
            if not segment:
                continue
            run = p.add_run()
            emphasized = segment.startswith('**') and segment.endswith('**')
            run.text = segment[2:-2] if emphasized else segment
            run.font.bold = bool(bold or emphasized)
        p.level = 0
        p.font.name = "Microsoft YaHei"
        p.font.size = Pt(font_size)
        p.font.bold = bold
        p.space_after = Pt(space_after)
        p.alignment = alignment or PP_ALIGN.LEFT
        if line_spacing is not None:
            p.line_spacing = line_spacing
    return txBox


def _strip_leading_index(text: str) -> str:
    return re.sub(r"^\s*\d+\s*[.、]\s*", "", str(text or "").strip())


def _format_ai_summary_slide_title(title: str, slide_number: Optional[int] = None) -> str:
    clean_title = _strip_leading_index(title)
    if slide_number:
        return f"{slide_number}. {clean_title}"
    return clean_title


def _add_ai_summary_page_title(slide, title: str):
    from pptx.util import Pt
    from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN

    txBox = slide.shapes.add_textbox(
        Pt(AI_SUMMARY_TITLE_LEFT_PT),
        Pt(AI_SUMMARY_TITLE_TOP_PT),
        Pt(AI_SUMMARY_TITLE_WIDTH_PT),
        Pt(AI_SUMMARY_TITLE_HEIGHT_PT),
    )
    tf = txBox.text_frame
    tf.word_wrap = False
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    tf.margin_left = Pt(0)
    tf.margin_right = Pt(0)
    tf.margin_top = Pt(0)
    tf.margin_bottom = Pt(0)
    p = tf.paragraphs[0]
    p.text = str(title or "")
    p.font.name = "Microsoft YaHei"
    p.font.size = Pt(18)
    p.font.bold = True
    p.alignment = PP_ALIGN.LEFT


def _add_ai_summary_agenda_slide(prs, slide_layout, agenda: List[str], footer_question: str):
    from pptx.util import Pt
    from pptx.enum.text import PP_ALIGN

    slide = _add_content_slide(prs, slide_layout)
    _add_title_text(slide)
    _add_ai_summary_page_title(slide, "目录")

    lines = [f"{idx}. {_strip_leading_index(title)}" for idx, title in enumerate(agenda[:5], start=1)]
    _add_bullet_textbox(
        slide,
        lines,
        left=Pt(AI_SUMMARY_AGENDA_LEFT_PT),
        top=Pt(AI_SUMMARY_AGENDA_TOP_PT),
        width=Pt(AI_SUMMARY_AGENDA_WIDTH_PT),
        height=Pt(AI_SUMMARY_AGENDA_HEIGHT_PT),
        font_size=18,
        bold=True,
        space_after=14,
        line_spacing=1.4,
        alignment=PP_ALIGN.LEFT,
    )


def _add_summary_chart(slide, visual: dict) -> bool:
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.util import Pt

    if not isinstance(visual, dict):
        return False
    chart_obj = visual.get("chart")
    if not isinstance(chart_obj, dict):
        return False
    columns = chart_obj.get("columns") or []
    data = chart_obj.get("data") or []
    if not isinstance(columns, list) or not isinstance(data, list) or not data:
        return False

    x_axes = [c for c in columns if isinstance(c, dict) and c.get("target") == "xaxis" and c.get("key")]
    y_axes = [c for c in columns if isinstance(c, dict) and c.get("target") == "yaxis" and c.get("key")]
    if not x_axes or not y_axes:
        return False
    x_key = str(x_axes[0].get("key"))
    y_key = str(y_axes[0].get("key"))
    key_name = {str(col.get("key")): str(col.get("name") or col.get("key")) for col in columns if isinstance(col, dict) and col.get("key")}
    x_axis_name = key_name.get(x_key, x_key)
    y_axis_name = key_name.get(y_key, y_key)
    is_percentage_chart = _should_format_chart_as_percentage(data[:30], [y_key], y_axis_name, y_key)

    if PPT_CHARTS_AS_IMAGES and _add_chart_image(
        slide,
        chart_type=XL_CHART_TYPE.COLUMN_CLUSTERED,
        data=data[:30],
        x_key=x_key,
        y_keys=[y_key],
        x_axis_name=x_axis_name,
        y_axis_name=y_axis_name,
        left_pt=CHART_LEFT_PT,
        top_pt=SUMMARY_CHART_TOP_PT,
        width_pt=CHART_WIDTH_PT,
        height_pt=SUMMARY_CHART_HEIGHT_PT,
        series_title=y_axis_name,
        has_legend=False,
        percentage_context_names=[y_key],
    ):
        return True

    chart_data = _make_category_chart_data(data[:30], x_key, [y_key], y_axis_name)
    graphic_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Pt(CHART_LEFT_PT),
        Pt(SUMMARY_CHART_TOP_PT),
        Pt(CHART_WIDTH_PT),
        Pt(SUMMARY_CHART_HEIGHT_PT),
        chart_data,
    )
    chart = graphic_frame.chart
    chart.has_legend = False
    _apply_chart_theme_colors(chart, XL_CHART_TYPE.COLUMN_CLUSTERED)
    _style_chart_gridlines(chart, XL_CHART_TYPE.COLUMN_CLUSTERED)
    _style_chart_number_labels(
        chart,
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        len(data[:30]),
        is_percentage_chart,
    )
    try:
        chart.category_axis.axis_title.text_frame.text = x_axis_name
        chart.value_axis.axis_title.text_frame.text = y_axis_name
    except Exception:
        pass
    _style_chart_text(chart, XL_CHART_TYPE.COLUMN_CLUSTERED, len(data[:30]))
    return True


def _add_ai_summary_slide(
    prs,
    slide_layout,
    slide_model: dict,
    footer_question: str,
    slide_number: Optional[int] = None,
    is_final_slide: bool = False,
):
    from pptx.util import Pt
    from pptx.enum.text import PP_ALIGN

    slide = _add_content_slide(prs, slide_layout)
    _add_title_text(slide)
    _add_ai_summary_page_title(
        slide,
        _format_ai_summary_slide_title(slide_model.get("title") or "", slide_number),
    )

    insights = [f"• {item}" for item in (slide_model.get("insights") or []) if str(item or "").strip()]
    has_chart = _add_summary_chart(slide, slide_model.get("visual"))
    max_items = 8 if is_final_slide else (2 if has_chart else 6)
    text_top = Pt(TEXT_TOP_PT)
    text_height = Pt((SUMMARY_CHART_TOP_PT - TEXT_TOP_PT - 8) if has_chart else TEXT_HEIGHT_PT)
    body_space_after = 8 if is_final_slide else 4
    body_line_spacing = 1.35 if is_final_slide else 1.2
    _add_bullet_textbox(
        slide,
        insights[:max_items],
        left=Pt(TEXT_LEFT_PT),
        top=text_top,
        width=Pt(TEXT_WIDTH_PT),
        height=text_height,
        font_size=14,
        space_after=body_space_after,
        line_spacing=body_line_spacing,
        alignment=PP_ALIGN.LEFT,
    )


def generate_ai_summary_ppt_to_bytes(summary: Dict[str, Any], footer_question: str) -> Optional[bytes]:
    """Generate AI Summary PPT bytes from structured summary JSON."""
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        prs, slide_layout = _create_presentation("AI_SUMMARY")
        agenda = summary.get("agenda") or []
        slides = summary.get("slides") or []
        if agenda:
            _add_ai_summary_agenda_slide(prs, slide_layout, agenda[:5], footer_question)
        render_slides = slides[:5]
        for idx, slide_model in enumerate(render_slides):
            if isinstance(slide_model, dict):
                _add_ai_summary_slide(
                    prs,
                    slide_layout,
                    slide_model,
                    footer_question,
                    slide_number=idx + 1,
                    is_final_slide=idx == len(render_slides) - 1,
                )
        prs.save(tmp_path)
        with open(tmp_path, 'rb') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Generate AI Summary PPT error: {e}", exc_info=True)
        return None
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _fill_content(prs, slide_layout, model: dict, question_index: int = 1):
    """Fill content for a single GeneratorPPTModel.

    Matches Java fillContent(). Creates slides for one question-answer pair.
    """
    question = model.get("question", "")
    biz_date = model.get("biz_date")
    ppt_answer_models = model.get("ppt_answer_models", [])

    if not ppt_answer_models:
        # No answers - just add a title slide
        slide = _add_content_slide(prs, slide_layout)
        _add_title_text(slide)
        _add_question_text(slide, question, question_index)
        _add_biz_date_text(slide, biz_date)
        return

    for i, answer_model in enumerate(ppt_answer_models):
        slide_question = _get_slide_question(question, i, answer_model)
        # 添加文本到PPT
        _add_text_slides(
            prs,
            slide_layout,
            answer_model.get("answer", ""),
            slide_question,
            biz_date,
            question_index,
        )
        # 添加表格到PPT
        _add_table_slides(prs, slide_layout, answer_model, slide_question, biz_date, question_index)
        # 添加图表到PPT
        _add_chart_slides(prs, slide_layout, answer_model, slide_question, biz_date, question_index)


def generate_ppt_from_models(
    file_path: str,
    models: List[Dict[str, Any]],
) -> bool:
    """Generate a PPT file from a list of GeneratorPPTModel dicts.

    Matches Java PPTGenerationUtil.generatePPT(File, List<GeneratorPPTModel>).

    Each model has:
        - question: str
        - title: str
        - biz_date: str
        - ppt_answer_models: list of dicts with:
            - answer: str
            - sql_data: list
            - excel_data: list (each item has "query" and "data" keys)
            - chart_data: list (each item has "query", "id", "chart" keys)

    Args:
        file_path: Output file path.
        models: List of GeneratorPPTModel dicts.

    Returns:
        True if successful, False otherwise.
    """
    try:
        from pptx import Presentation  # noqa: F401
    except ImportError:
        logger.error("python-pptx library not installed. Install with: pip install python-pptx")
        return False

    if not models:
        return False

    try:
        prs, slide_layout = _create_presentation("FULL_SUMMARY")

        for question_index, model in enumerate(models, start=1):
            try:
                _fill_content(prs, slide_layout, model, question_index)
            except Exception as e:
                logger.error(f"Error filling content for model: {e}", exc_info=True)

        prs.save(file_path)
        logger.info(f"PPT file generated: {file_path}")
        return True

    except Exception as e:
        logger.error(f"Generate PPT error: {e}", exc_info=True)
        return False


def generate_ppt_from_models_to_bytes(
    models: List[Dict[str, Any]],
) -> Optional[bytes]:
    """Generate a PPT from models and return as bytes.

    Args:
        models: List of GeneratorPPTModel dicts.

    Returns:
        PPT file content as bytes, or None if failed.
    """
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        success = generate_ppt_from_models(tmp_path, models)
        if not success:
            return None
        with open(tmp_path, 'rb') as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# Keep legacy functions for backward compatibility
def generate_ppt(
    file_path: str,
    question: str,
    answer: str = None,
    tables: List[Dict[str, Any]] = None,
    charts: List[Dict[str, Any]] = None,
    biz_date: str = None,
) -> bool:
    """Generate a PPT file from flat chat data (legacy interface).

    Args:
        file_path: Output file path.
        question: The user's question.
        answer: Text answer content.
        tables: List of table data dicts.
        charts: List of chart data dicts.
        biz_date: Business date string.

    Returns:
        True if successful, False otherwise.
    """
    model = {
        "question": question,
        "title": "",
        "biz_date": biz_date,
        "ppt_answer_models": [{
            "answer": answer or "",
            "sql_data": [],
            "excel_data": tables or [],
            "chart_data": charts or [],
        }],
    }
    return generate_ppt_from_models(file_path, [model])


def generate_ppt_to_bytes(
    question: str,
    answer: str = None,
    tables: List[Dict[str, Any]] = None,
    charts: List[Dict[str, Any]] = None,
    biz_date: str = None,
) -> Optional[bytes]:
    """Generate a PPT file and return as bytes (legacy interface).

    Args:
        question: The user's question.
        answer: Text answer content.
        tables: List of table data dicts.
        charts: List of chart data dicts.
        biz_date: Business date string.

    Returns:
        PPT file content as bytes.
    """
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        generate_ppt(tmp_path, question, answer, tables, charts, biz_date)
        with open(tmp_path, 'rb') as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
