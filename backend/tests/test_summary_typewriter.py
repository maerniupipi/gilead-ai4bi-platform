"""Smooth display preserves exact text, bounds added delay and stops on cancellation."""
import asyncio
import pytest
from app.services.autobi.lab_pipeline_runner import _typewriter_pieces


@pytest.mark.parametrize("text", ["", "短总结", "0123456789", "分析结论。" * 80, "a" * 10001])
def test_typewriter_preserves_content_and_caps_added_delay(monkeypatch, text):
    sleeps = []
    async def sleep(seconds):
        sleeps.append(seconds)
    monkeypatch.setattr(asyncio, "sleep", sleep)
    async def collect():
        return [piece async for piece in _typewriter_pieces(text)]
    pieces = asyncio.run(collect())
    assert "".join(pieces) == text
    assert len(pieces) <= 100
    assert len(sleeps) == max(0, len(pieces) - 1)
    assert sum(sleeps) <= 5
    if len(text) <= 10:
        assert sleeps == []


def test_typewriter_first_piece_is_immediate_and_cancellation_stops_the_remainder(monkeypatch):
    async def run():
        sleeping = asyncio.Event()
        blocker = asyncio.Event()
        async def sleep(seconds):
            sleeping.set()
            await blocker.wait()
        monkeypatch.setattr(asyncio, "sleep", sleep)
        stream = _typewriter_pieces("a" * 50)
        assert await anext(stream) == "a" * 10
        assert not sleeping.is_set()
        next_piece = asyncio.create_task(anext(stream))
        await sleeping.wait()
        next_piece.cancel()
        with pytest.raises(asyncio.CancelledError):
            await next_piece
        await stream.aclose()
    asyncio.run(run())
