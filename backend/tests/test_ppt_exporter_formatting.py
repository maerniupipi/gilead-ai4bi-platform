from app.services.xlsx_qa.ppt_exporter import _fmt_val, _style_native_chart, THEMES
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches


def test_fmt_val_adds_thousands_separators():
    assert _fmt_val(1234567) == "1,234,567"
    assert _fmt_val(1234567.5) == "1,234,567.5"
    assert _fmt_val("1234567.50") == "1,234,567.5"
    assert _fmt_val("12.5%") == "12.5%"


def test_native_bar_chart_always_shows_formatted_value_labels():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    data = CategoryChartData()
    data.categories = [f"C{i}" for i in range(15)]
    data.add_series("销售额", [1000 + i for i in range(15)])
    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(1),
        Inches(1),
        Inches(8),
        Inches(4),
        data,
    ).chart

    _style_native_chart(chart, ctype="bar", theme=THEMES["executive"])

    assert chart.plots[0].has_data_labels is True
    assert chart.plots[0].data_labels.show_value is True
    assert chart.plots[0].data_labels.number_format == "#,##0.##"
    assert chart.value_axis.tick_labels.number_format == "#,##0.##"
