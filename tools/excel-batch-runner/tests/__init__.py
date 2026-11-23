"""Offline tests; all inputs are constructed within this package."""
import io
import json
import socket
import unittest
from unittest.mock import patch

from openpyxl import Workbook


class OfflineMixin:
    def setUp(self):
        super().setUp()
        for name in ("connect", "connect_ex"):
            guard = patch.object(socket.socket, name, side_effect=AssertionError("Network forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        guard = patch("socket.create_connection", side_effect=AssertionError("Network forbidden"))
        guard.start()
        self.addCleanup(guard.stop)


class OfflineCase(OfflineMixin, unittest.TestCase):
    pass


class OfflineAsyncCase(OfflineMixin, unittest.IsolatedAsyncioTestCase):
    pass


def workbook_bytes():
    workbook = Workbook()
    first = workbook.active
    first.title = "销售"
    first["G1"] = "原始问题"
    first["A2"] = "保持原样"
    first["G2"] = "你好"
    first["G3"] = "   "
    first["G4"] = "第二个问题"
    first["H4"] = "旧结果"
    second = workbook.create_sheet("市场")
    second["G1"] = "原始问题"
    second["G2"] = "市场情况"
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def event_bytes(end=False, content="", kind="text", progress=None, **extra):
    message = {"actionId": "same-id", "content": content, "features": {}, "type": kind}
    if progress is not None:
        message["features"]["progress"] = progress
    data = {"data": {"end": end, "messages": [message], "outSessionId": "test",
                     "questionId": 1, "rewriteQuestion": "", "role": "assistant"},
            "id": "0", "event": str(end).lower(), **extra}
    return ("data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode("utf-8")
