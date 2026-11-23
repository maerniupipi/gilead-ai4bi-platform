"""Generate safe, editable spreadsheets from complete query results."""
from io import BytesIO


def generate_xlsx(columns, rows):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "完整数据"
    count = max(1, len(columns))
    for i, col in enumerate(columns, 1):
        cell = sheet.cell(1, i, str(col.get("name") or col["key"]))
        cell.data_type = "s"
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor="2563EB")
        sheet.column_dimensions[get_column_letter(i)].width = 22
    for r, row in enumerate(rows, 2):
        for c, col in enumerate(columns, 1):
            value = row.get(col["key"])
            if isinstance(value, (dict, list)):
                import json
                value = json.dumps(value, ensure_ascii=False)
            cell = sheet.cell(r, c, value)
            if isinstance(value, str):
                cell.data_type = "s"
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(count)}{max(1, len(rows) + 1)}"
    sheet.print_title_rows = "1:1"
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation, sheet.page_setup.paperSize = "landscape", sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight = 1, 0
    out = BytesIO()
    workbook.save(out)
    return out.getvalue()
