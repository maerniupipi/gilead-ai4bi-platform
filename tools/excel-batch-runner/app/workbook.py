"""Workbook inspection and versioned output columns; only G is a request input."""
from copy import copy
from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook

from app.models import CURRENT_OUTPUT_FORMAT, SPLIT_FORMATS, RowResult

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_ROWS_PER_SHEET = 100000
INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def _load(source, data_only=False):
    if not source or len(source) > MAX_UPLOAD_BYTES:
        raise ValueError("工作簿为空或超过 20 MB")
    try:
        with ZipFile(BytesIO(source)) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_EXPANDED_BYTES:
                raise ValueError("工作簿解压后超过 100 MB")
        return load_workbook(BytesIO(source), data_only=data_only)
    except (BadZipFile, KeyError, OSError) as exc:
        raise ValueError("文件不是可读取的 .xlsx 工作簿") from exc


def _validate_start(start_row):
    if not isinstance(start_row, int) or not 1 <= start_row <= 1048576:
        raise ValueError("起始行必须为 1 至 1048576 的整数")


def _rows(workbook, cached, names, start_row, overwrite, output_format="trace"):
    result = []
    for sheet in workbook.worksheets:
        if sheet.title not in names:
            continue
        if sheet.max_row > MAX_ROWS_PER_SHEET:
            raise ValueError(f"sheet「{sheet.title}」使用区域超过 100000 行，请先缩小文件")
        for number in range(start_row, sheet.max_row + 1):
            source_cell = sheet.cell(number, 7)
            value = source_cell.value
            if value is None or not str(value).strip():
                continue
            error = ""
            if source_cell.data_type == "f":
                cached_cell = cached[sheet.title].cell(number, 7)
                value = cached_cell.value
                if value is None:
                    error = "G 列公式没有缓存值，请在 Excel 中计算并保存后重新上传"
                elif cached_cell.data_type == "e":
                    error = "G 列公式计算结果包含 Excel 错误值"
            elif source_cell.data_type == "e":
                error = "G 列包含 Excel 错误值"
            question = "" if value is None else str(value).strip()
            if not question and not error:
                continue
            row = RowResult(sheet=sheet.title, row=number, question=question, output_format=output_format)
            columns = (8, 9, 10) if output_format == "split_trace" else (8, 9) if output_format == "split" else (8,)
            if any(area.min_col <= column <= area.max_col
                   and area.min_row <= number <= area.max_row
                   for area in sheet.merged_cells.ranges for column in columns):
                error = "输出列目标单元格属于合并区域，不能回填"
            if error:
                row.status, row.error = "invalid", error
            elif not overwrite and any(sheet.cell(number, column).value is not None for column in columns):
                row.status, row.error = "skipped", "输出列已有内容"
            result.append(row)
    return result


def inspect_workbook(source: bytes, start_row: int = 2) -> list[dict]:
    _validate_start(start_row)
    workbook, cached = _load(source), _load(source, data_only=True)
    try:
        result = []
        for sheet in workbook.worksheets:
            rows = _rows(workbook, cached, {sheet.title}, start_row, False, CURRENT_OUTPUT_FORMAT)
            result.append({"name": sheet.title, "questions": len(rows),
                           "existing": sum(r.status == "skipped" for r in rows),
                           "invalid": sum(r.status == "invalid" for r in rows),
                           "eligible": sum(r.status == "pending" for r in rows)})
        return result
    finally:
        workbook.close()
        cached.close()


def select_rows(source: bytes, sheets: list[str], start_row: int = 2,
                overwrite: bool = False, output_format: str = "trace") -> list[RowResult]:
    _validate_start(start_row)
    workbook, cached = _load(source), _load(source, data_only=True)
    try:
        if not sheets or len(set(sheets)) != len(sheets):
            raise ValueError("请至少选择一个 sheet，且不能重复")
        if not set(sheets).issubset(workbook.sheetnames):
            raise ValueError("所选 sheet 不存在")
        return _rows(workbook, cached, set(sheets), start_row, overwrite, output_format)
    finally:
        workbook.close()
        cached.close()


def excel_text(value: str) -> str:
    return INVALID_XML.sub(lambda m: "\\u%04x" % ord(m.group()), value)


def cell_output(row: RowResult) -> str:
    if row.output_format in SPLIT_FORMATS:
        return split_cells(row)[8]
    text = excel_text(row.output or ("[error] " + row.error if row.error else ""))
    if len(text.encode("utf-16-le")) // 2 > 32767:
        row.export_warning = "结果超过 Excel 单元格 32767 字符容量"
        return f"[超限] 完整过程请下载任务日志；row_id={row.row_id}"
    row.export_warning = ""
    return text


def split_cells(row: RowResult) -> dict[int, str]:
    answer = row.answer or "[未返回回答]"
    if row.status in {"failed", "interrupted"}:
        answer = "[未完成] " + (row.error or row.status) + "\n" + answer
    values = {8: row.sql or "[未返回 SQL]", 9: answer}
    if row.output_format == "split_trace":
        values[10] = "\n".join(row.lab_trace_ids) or "[未返回实验室 TraceID]"
    warnings = []
    for column, value in values.items():
        text = excel_text(value)
        if len(text.encode("utf-16-le")) // 2 > 32767:
            label = {8: "SQL", 9: "回答", 10: "实验室 TraceID"}[column]
            warnings.append(label + "超过单元格 32767 字符容量")
            text = f"[超限] {label} 本身超过单元格容量，完整内容保留于任务详情与日志；row_id={row.row_id}"
        values[column] = text
    row.export_warning = "；".join(warnings)
    return values


def export_workbook(source: bytes, rows: list[RowResult]) -> bytes:
    workbook = _load(source)
    try:
        for row in rows:
            if row.status not in {"success", "failed", "interrupted"}:
                continue
            values = split_cells(row) if row.output_format in SPLIT_FORMATS else {8: cell_output(row)}
            if row.output_format == "split_trace" and row.row > 1:
                header = workbook[row.sheet].cell(1, 10)
                if header.value is None and not any(area.min_col <= 10 <= area.max_col and area.min_row <= 1 <= area.max_row
                                                    for area in workbook[row.sheet].merged_cells.ranges):
                    header.value = "实验室 TraceID"
            for column, value in values.items():
                cell = workbook[row.sheet].cell(row.row, column)
                cell.value = value
                cell.data_type = "s"
                alignment = copy(cell.alignment)
                alignment.wrap_text = True
                cell.alignment = alignment
        output = BytesIO()
        workbook.save(output)
        return output.getvalue()
    finally:
        workbook.close()
