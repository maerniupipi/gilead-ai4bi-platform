import io
import json

from openpyxl import load_workbook

from tests import OfflineCase, event_bytes, workbook_bytes

try:
    from app.models import RunConfig, RowResult
    from app.sse import SSEDecoder, format_frame
    from app.workbook import inspect_workbook, select_rows, export_workbook
except ModuleNotFoundError:
    RunConfig = None


class CoreTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.assertIsNotNone(RunConfig, "Core implementation is missing")

    def test_workbook_keeps_sheet_and_original_row_numbers(self):
        payload = workbook_bytes()
        overview = inspect_workbook(payload, 2)
        self.assertEqual([(s["name"], s["questions"], s["existing"]) for s in overview],
                         [("销售", 2, 1), ("市场", 1, 0)])
        rows = select_rows(payload, ["销售", "市场"], 2, False)
        self.assertEqual([(r.sheet, r.row, r.question, r.status) for r in rows],
                         [("销售", 2, "你好", "pending"), ("销售", 4, "第二个问题", "skipped"),
                          ("市场", 2, "市场情况", "pending")])

    def test_select_sheet_overwrite_and_configurable_start(self):
        rows = select_rows(workbook_bytes(), ["销售"], 4, True)
        self.assertEqual([(r.row, r.status) for r in rows], [(4, "pending")])
        with self.assertRaises(ValueError):
            select_rows(workbook_bytes(), ["不存在"], 2, False)
        with self.assertRaises(ValueError):
            select_rows(workbook_bytes(), [], 2, False)

    def test_export_preserves_source_other_cells_and_existing_output(self):
        source = workbook_bytes()
        rows = select_rows(source, ["销售"], 2, False)
        rows[0].status = "success"
        rows[0].output = "=1+1\n完整过程"
        result = load_workbook(io.BytesIO(export_workbook(source, rows)))
        self.assertEqual(result.sheetnames, ["销售", "市场"])
        self.assertEqual(result["销售"]["A2"].value, "保持原样")
        self.assertEqual(result["销售"]["H2"].value, "=1+1\n完整过程")
        self.assertEqual(result["销售"]["H2"].data_type, "s")
        self.assertEqual(result["销售"]["H4"].value, "旧结果")
        original = load_workbook(io.BytesIO(source))
        self.assertIsNone(original["销售"]["H2"].value)
        result.close()
        original.close()

    def test_overflow_is_explicit_and_full_output_retained(self):
        rows = select_rows(workbook_bytes(), ["市场"], 2, False)
        rows[0].status = "success"
        rows[0].output = "字" * 32768
        result = load_workbook(io.BytesIO(export_workbook(workbook_bytes(), rows)))
        self.assertIn("超限", result["市场"]["H2"].value)
        self.assertEqual(len(rows[0].output), 32768)
        self.assertTrue(rows[0].export_warning)
        result.close()

    def test_unicode_and_xml_control_characters_export_safely(self):
        rows = select_rows(workbook_bytes(), ["市场"], 2, False)
        rows[0].status = "failed"
        rows[0].output = "内容\x00\x0b结束"
        result = load_workbook(io.BytesIO(export_workbook(workbook_bytes(), rows)))
        self.assertEqual(result["市场"]["H2"].value, r"内容\u0000\u000b结束")
        result.close()
        rows[0].output = "😀" * 16384
        result = load_workbook(io.BytesIO(export_workbook(workbook_bytes(), rows)))
        self.assertIn("超限", result["市场"]["H2"].value)
        result.close()

    def test_formula_without_cache_and_merged_target_are_not_sent(self):
        workbook = load_workbook(io.BytesIO(workbook_bytes()))
        workbook["销售"]["G2"] = '=CONCAT("问题", "一")'
        workbook["销售"].merge_cells("H4:I4")
        out = io.BytesIO()
        workbook.save(out)
        workbook.close()
        rows = select_rows(out.getvalue(), ["销售"], 2, True)
        self.assertEqual([r.status for r in rows], ["invalid", "invalid"])
        self.assertIn("缓存", rows[0].error)
        self.assertIn("合并", rows[1].error)

    def test_cached_formula_errors_are_invalid_but_text_results_are_questions(self):
        from xml.etree import ElementTree as ET
        from zipfile import ZipFile

        namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        for cell_type, value, expected in [
                ("e", "#DIV/0!", "invalid"),
                ("e", "#REF!", "invalid"),
                ("str", "有效问题", "pending"),
                ("str", "#DIV/0!", "pending")]:
            with self.subTest(cell_type=cell_type, value=value):
                output = io.BytesIO()
                with ZipFile(io.BytesIO(workbook_bytes())) as original, ZipFile(output, "w") as modified:
                    for item in original.infolist():
                        content = original.read(item.filename)
                        if item.filename == "xl/worksheets/sheet2.xml":
                            sheet = ET.fromstring(content)
                            cell = sheet.find(f".//{namespace}c[@r='G2']")
                            cell.clear()
                            cell.attrib.update({"r": "G2", "t": cell_type})
                            ET.SubElement(cell, namespace + "f").text = (
                                "1/0" if cell_type == "e" else '"' + value + '"')
                            ET.SubElement(cell, namespace + "v").text = value
                            content = ET.tostring(sheet)
                        modified.writestr(item, content)
                source = output.getvalue()
                row = select_rows(source, ["市场"], output_format="split")[0]
                self.assertEqual(row.status, expected)
                self.assertEqual(row.question, value)
                if expected == "invalid":
                    self.assertIn("Excel 错误值", row.error)
                overview = next(sheet for sheet in inspect_workbook(source) if sheet["name"] == "市场")
                self.assertEqual(overview["invalid"], int(expected == "invalid"))
                self.assertEqual(overview["eligible"], int(expected == "pending"))

    def test_config_rejects_invalid_concurrency_url_and_headers(self):
        for config in ({"concurrency": 0}, {"concurrency": 33}, {"url": "file:///a"},
                       {"url": "http://user:pass@localhost/"},
                       {"headers": {"Host": "different"}},
                       {"headers": {"Authorization": "x\nbad"}},
                       {"total_timeout": float("inf")}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                RunConfig(**config)

    def test_sse_utf8_byte_chunks_preserve_order_and_unknown_fields(self):
        stream = b": heartbeat\r\n\r\n" + event_bytes(
            kind="progress", progress="智能体执行中", unusual={"keep": 1})
        stream += event_bytes(content="你好", end=True)
        decoder = SSEDecoder()
        frames = []
        for value in stream:
            frames.extend(decoder.feed(bytes([value])))
        frames.extend(decoder.finish())
        self.assertEqual(len(frames), 3)
        output = "\n\n".join(format_frame(frame, n + 1) for n, frame in enumerate(frames))
        self.assertIn("heartbeat", output)
        self.assertIn("智能体执行中", output)
        self.assertIn('"unusual": {"keep": 1}', output)
        self.assertLess(output.index("智能体"), output.index("你好"))
        self.assertTrue(frames[-1].is_end)

    def test_sse_multiline_and_eof_without_blank_line(self):
        decoder = SSEDecoder()
        frames = decoder.feed(b'event: token\r\nid: 9\r\ndata: {"data":\r\ndata: {"end":true,"messages":[]}}')
        frames += decoder.finish()
        self.assertEqual(len(frames), 1)
        self.assertTrue(frames[0].is_end)
        self.assertEqual(frames[0].event, "token")
        self.assertEqual(frames[0].event_id, "9")

    def test_malformed_and_unknown_messages_remain_visible(self):
        decoder = SSEDecoder()
        frames = decoder.feed(b'data: not-json\n\n')
        self.assertIn("not-json", format_frame(frames[0], 1))
        self.assertTrue(frames[0].parse_error)
        data = {"data": {"end": False, "messages": [
            {"type": "custom", "content": {"answer": 42}, "features": {"other": "保留"}}]}}
        frames = SSEDecoder().feed(("data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode())
        formatted = format_frame(frames[0], 1)
        self.assertIn("保留", formatted)
        self.assertIn("42", formatted)

    def test_string_true_does_not_mean_complete(self):
        frame = SSEDecoder().feed(b'data: {"data":{"end":"true","messages":[]}}\n\n')[0]
        self.assertFalse(frame.is_end)


class SplitOutputTests(OfflineCase):
    def test_report_extracts_full_sql_and_final_answer(self):
        from app.report import Report
        from app.sse import SSEFrame
        report = Report()
        report.add(SSEFrame(raw="", data="", payload={"data": {"messages": [
            {"type": "sql_citations", "features": {"sql_citations": [
                {"query": "q1", "sql": "SELECT 1;\n-- 完整SQL"},
                {"query": "q2", "sql": "SELECT 2;"}]}},
            {"type": "text", "content": "=正文\n"}]}}), 1)
        report.add(SSEFrame(raw="", data="", payload={"data": {"end": True,
            "messages": [{"type": "text", "content": "结束"}]}}), 2)
        row = RowResult("市场", 2, "q", status="success", output_format="split")
        report.update_row(row)
        self.assertIn("SELECT 1;\n-- 完整SQL", row.sql)
        self.assertIn("SELECT 2;", row.sql)
        self.assertEqual(row.answer, "=正文\n结束")
        wb = load_workbook(io.BytesIO(export_workbook(workbook_bytes(), [row])))
        self.assertEqual(wb["市场"]["H2"].value, row.sql)
        self.assertEqual(wb["市场"]["I2"].value, row.answer)
        self.assertEqual(wb["市场"]["I2"].data_type, "s")
        wb.close()

    def test_trace_size_does_not_block_split_cells_and_overflow_is_independent(self):
        row = RowResult("市场", 2, "q", status="success", output_format="split",
                        output="过程" * 40000, sql="SELECT 1", answer="回答")
        for sql, answer, expected_column in [
                ("SELECT 1", "回答", None),
                ("长" * 32768, "回答", "H"),
                ("SELECT 1", "😀" * 16384, "I")]:
            row.sql, row.answer = sql, answer
            wb = load_workbook(io.BytesIO(export_workbook(workbook_bytes(), [row])))
            if expected_column:
                self.assertIn("超限", wb["市场"][expected_column + "2"].value)
                other = "I" if expected_column == "H" else "H"
                self.assertEqual(wb["市场"][other + "2"].value, answer if other == "I" else sql)
            else:
                self.assertEqual(wb["市场"]["I2"].value, "回答")
                self.assertFalse(row.export_warning)
            wb.close()

    def test_split_selection_checks_both_destination_columns(self):
        wb = load_workbook(io.BytesIO(workbook_bytes()))
        wb["市场"]["I2"] = "原有回答"
        out = io.BytesIO()
        wb.save(out)
        rows = select_rows(out.getvalue(), ["市场"], output_format="split")
        self.assertEqual(rows[0].status, "skipped")
        rows = select_rows(out.getvalue(), ["市场"], overwrite=True, output_format="split")
        self.assertEqual(rows[0].status, "pending")
        wb["市场"].merge_cells("I2:J2")
        out = io.BytesIO()
        wb.save(out)
        wb.close()
        rows = select_rows(out.getvalue(), ["市场"], overwrite=True, output_format="split")
        self.assertEqual(rows[0].status, "invalid")


class ReportTests(OfflineCase):
    def test_report_compacts_chunks_and_preserves_queries_and_metadata(self):
        from app.report import Report
        from app.sse import SSEFrame
        report = Report()
        rows = [{"name": "产品甲", "value": 123}]
        messages = [
            {"type": "progress_result", "features": {"progress": "多轮改写结果：销售额是多少？"}},
            {"type": "progress", "features": {"progress": "生成SQL中"}},
            {"type": "sql_citations", "features": {"sql_citations": [
                {"query": "销售额", "sql": "SELECT 123"}, {"query": "另一个问题", "sql": "SELECT 456"}]}},
            {"type": "data_citations", "features": {"data_citations": [{"query": "销售额", "data": rows}]}},
            {"type": "text", "actionId": "same", "content": "销售 "},
            {"type": "text", "actionId": "same", "content": "额为123。"},
            {"type": "chart_citations", "features": {"chart_citations": [
                {"query": "销售额", "chart": {"type": "A", "columns": ["name", "value"], "data": rows}}]}},
            {"type": "statistics", "features": {"first_token_rt": 77, "total_tokens": 8}},
        ]
        for index, message in enumerate(messages, 1):
            report.add(SSEFrame(raw="", data="", payload={"data": {
                "messages": [message], "rewriteQuestion": "累计快照",
                "questionId": 42, "outSessionId": "session", "end": False}}), index)
        report.add(SSEFrame(raw="", data="", payload={"data": {"end": True}}), 9)
        row = RowResult(sheet="销售", row=2, question="问题", status="success", event_count=9)
        output = report.render(row)
        for expected in ("【问题理解】", "【SQL】", "SELECT 123", "SELECT 456", "【查询数据】",
                         "销售 额为123。", "引用：查询数据 #1", "first_token_rt", "questionId: 42", "end=true"):
            self.assertIn(expected, output)
        self.assertEqual(output.count('"name": "产品甲"'), 1)
        self.assertNotIn("累计快照", output)
        self.assertNotIn("same", output)

    def test_unknown_fields_partial_and_bad_json_are_visible(self):
        from app.report import Report
        from app.sse import SSEFrame
        report = Report()
        report.add(SSEFrame(raw="data: broken", data="broken", parse_error="bad JSON",
                            partial=True, raw_bytes_hex="e4"), 1)
        report.add(SSEFrame(raw="", data="", payload={"extra": "外层",
            "data": {"messages": [{"type": "text", "content": "保留正文", "new": 7,
                                  "features": {"unknown": "未知特征"}}], "newField": "内层"}}), 2)
        row = RowResult(sheet="s", row=2, question="q", status="failed", error="断流")
        output = report.render(row)
        for value in ("broken", "partial", "e4", "外层", "内层", "未知特征", "保留正文", "断流"):
            self.assertIn(value, output)
        self.assertIn("结束标记: 未收到有效 end=true", output)
        self.assertNotIn("结束标记: end=true", output)

    def test_malformed_message_type_is_preserved_without_stopping_report(self):
        from app.report import Report
        from app.sse import SSEFrame
        report = Report()
        report.add(SSEFrame(raw="", data="", payload={"data": {"messages": [
            {"type": ["new-type"], "content": "未知结构"},
            {"type": "text", "content": "后续正文"}]}}), 1)
        output = report.render(RowResult(sheet="s", row=2, question="q"))
        self.assertIn("未知结构", output)
        self.assertIn("后续正文", output)

    def test_snapshot_is_labeled_fallback_and_distinct_chart_data_remains(self):
        from app.report import Report
        from app.sse import SSEFrame
        report = Report()
        report.add(SSEFrame(raw="", data="", payload={"data": {
            "rewriteQuestion": "仅有快照", "messages": [
                {"type": "chart_citations", "features": {"chart_citations": [
                    {"chart": {"data": [{"different": 9}]}}]}}]}}), 1)
        output = report.render(RowResult(sheet="s", row=2, question="q"))
        self.assertIn("备用快照", output)
        self.assertIn("仅有快照", output)
        self.assertIn('"different": 9', output)


if __name__ == "__main__":
    import unittest
    unittest.main()
