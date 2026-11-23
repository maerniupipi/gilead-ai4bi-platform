"""Incremental SSE framing. Raw fields survive unknown JSON message types."""
import codecs
from dataclasses import dataclass
import json
import re


@dataclass
class SSEFrame:
    raw: str
    data: str
    event: str = ""
    event_id: str = ""
    payload: object = None
    parse_error: str = ""
    partial: bool = False
    raw_bytes_hex: str = ""

    @property
    def is_end(self):
        return (not self.partial and isinstance(self.payload, dict)
                and isinstance(self.payload.get("data"), dict)
                and self.payload["data"].get("end") is True)

    def to_dict(self):
        return {"raw": self.raw, "data": self.data, "event": self.event,
                "event_id": self.event_id, "payload": self.payload,
                "parse_error": self.parse_error, "partial": self.partial,
                "raw_bytes_hex": self.raw_bytes_hex}


class SSEDecoder:
    def __init__(self):
        self._decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
        self._buffer = ""
        self._lines = []
        self._failed_bytes = b""

    def _dispatch(self):
        if not self._lines:
            return None
        raw = "\n".join(self._lines)
        data, event, event_id = [], "", ""
        for line in self._lines:
            if line.startswith(":"):
                continue
            name, sep, value = line.partition(":")
            if value.startswith(" "):
                value = value[1:]
            if name == "data":
                data.append(value)
            elif name == "event":
                event = value
            elif name == "id":
                event_id = value
        self._lines = []
        joined = "\n".join(data)
        frame = SSEFrame(raw, joined, event, event_id)
        if data:
            try:
                frame.payload = json.loads(joined)
            except (ValueError, RecursionError):
                frame.parse_error = "SSE data 不是有效 JSON"
        return frame

    def _drain(self, final=False):
        frames = []
        while True:
            match = re.search(r"[\r\n]", self._buffer)
            if match is None:
                break
            position = match.start()
            char = self._buffer[position]
            if char == "\r" and position == len(self._buffer) - 1 and not final:
                break
            width = 2 if self._buffer[position:position + 2] == "\r\n" else 1
            line, self._buffer = self._buffer[:position], self._buffer[position + width:]
            if line:
                self._lines.append(line)
            else:
                frame = self._dispatch()
                if frame:
                    frames.append(frame)
        if final:
            if self._buffer:
                self._lines.append(self._buffer)
                self._buffer = ""
            frame = self._dispatch()
            if frame:
                frames.append(frame)
        return frames

    def feed(self, chunk: bytes) -> list[SSEFrame]:
        pending = self._decoder.getstate()[0]
        try:
            self._buffer += self._decoder.decode(chunk)
        except UnicodeError:
            self._failed_bytes = pending + chunk
            self._decoder.reset()
            raise
        return self._drain()

    def abort(self) -> list[SSEFrame]:
        """Retain an unfinished tail, including undecodable bytes, without completing it."""
        undecoded = self._failed_bytes or self._decoder.getstate()[0]
        raw = "\n".join(self._lines)
        if self._lines:
            raw += "\n"
        raw += self._buffer
        raw += undecoded.decode("utf-8", errors="backslashreplace")
        self._lines = []
        self._buffer = ""
        self._failed_bytes = b""
        self._decoder.reset()
        if not raw and not undecoded:
            return []
        return [SSEFrame(raw=raw, data="", partial=True,
                         parse_error="流中断：末尾事件未完成",
                         raw_bytes_hex=undecoded.hex())]

    def finish(self) -> list[SSEFrame]:
        self._buffer += self._decoder.decode(b"", final=True)
        return self._drain(final=True)


def _text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def format_frame(frame: SSEFrame, number: int) -> str:
    lines = [f"[{number:04d}] event={frame.event or '-'} id={frame.event_id or '-'}"]
    payload = frame.payload
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        inner = payload["data"]
        if "end" in inner:
            lines.append("end=" + json.dumps(inner["end"], ensure_ascii=False))
        messages = inner.get("messages", [])
        if isinstance(messages, list):
            for message in messages:
                if not isinstance(message, dict):
                    continue
                lines.append("type=" + _text(message.get("type", "unknown")))
                features = message.get("features")
                if isinstance(features, dict) and "progress" in features:
                    lines.append("progress: " + _text(features["progress"]))
                if message.get("content") not in (None, ""):
                    lines.append("content: " + _text(message["content"]))
    if frame.partial:
        lines.append("partial=true")
    if frame.raw_bytes_hex:
        lines.append("raw_bytes_hex: " + frame.raw_bytes_hex)
    if frame.parse_error:
        lines.append("parse_error: " + frame.parse_error)
    lines.append("raw: " + frame.raw)
    return "\n".join(lines)
