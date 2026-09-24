import pytest
from mcp.server.mcpserver.exceptions import ToolError

from hf_studio import mcp_server


def _fake(total):
    calls = []

    def call(method, path, **kw):
        calls.append(kw["json"]["dry_run"])
        if kw["json"]["dry_run"]:
            return {"total": total, "estimate": total}
        return {"ok": True}

    return call, calls


def test_batch_without_complete_price_is_refused(monkeypatch):
    call, calls = _fake({"usd": None, "complete": False})
    monkeypatch.setattr(mcp_server, "_call", call)
    with pytest.raises(ToolError, match="confirm_unknown_cost"):
        mcp_server.generate_batch([{"model": "m", "input": {}}], dry_run=False)
    assert calls == [True]  # solo cotizó, nunca generó


def test_batch_generates_with_price_or_explicit_confirmation(monkeypatch):
    call, calls = _fake({"usd": 1.2, "complete": True})
    monkeypatch.setattr(mcp_server, "_call", call)
    assert mcp_server.generate_batch([{"model": "m", "input": {}}], dry_run=False) == {"ok": True}
    call, calls = _fake({"usd": None, "complete": False})
    monkeypatch.setattr(mcp_server, "_call", call)
    mcp_server.generate_batch([{"model": "m", "input": {}}], dry_run=False, confirm_unknown_cost=True)
    assert calls == [True, False]


def test_preset_with_missing_media_length_is_refused(monkeypatch):
    call, _ = _fake({"usd": None, "missing": ["input video duration"]})
    monkeypatch.setattr(mcp_server, "_call", call)
    with pytest.raises(ToolError, match="input video duration"):
        mcp_server.run_preset("ad-multiplier", {}, dry_run=False)
