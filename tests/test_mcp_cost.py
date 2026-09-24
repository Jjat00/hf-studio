import pytest
from mcp.server.mcpserver.exceptions import ToolError

from hf_studio import mcp_server


def _fake(price):
    """Simula la API: las cotizaciones devuelven `price`; registra si hubo generación real."""
    generated = []

    def call(method, path, **kw):
        body = kw.get("json", {})
        if path == "/v1/estimate":
            return dict(price)
        if body.get("dry_run", False) is False:
            generated.append(path)
            return {"ok": True}
        return {"total": dict(price), "estimate": dict(price)}

    return call, generated


ITEMS = [{"model": "m", "input": {"prompt": "x"}}]


def test_generating_without_a_quote_is_refused(monkeypatch):
    call, generated = _fake({"usd": 1.2, "complete": True, "missing": []})
    monkeypatch.setattr(mcp_server, "_call", call)
    with pytest.raises(ToolError, match="quote_id"):
        mcp_server.generate_batch(ITEMS, dry_run=False)
    with pytest.raises(ToolError, match="quote_id"):
        mcp_server.generate("m", {"prompt": "x"}, quote_id="q_inventado")
    assert generated == []


def test_quote_then_generate_with_the_same_request(monkeypatch):
    call, generated = _fake({"usd": 1.2, "complete": True, "missing": []})
    monkeypatch.setattr(mcp_server, "_call", call)
    q = mcp_server.generate_batch(ITEMS, dry_run=True)["quote_id"]
    assert mcp_server.generate_batch(ITEMS, dry_run=False, quote_id=q) == {"ok": True}
    # Otro lote con el quote_id anterior: rechazado.
    with pytest.raises(ToolError, match="stale"):
        mcp_server.generate_batch(ITEMS * 2, dry_run=False, quote_id=q)
    q1 = mcp_server.estimate_cost("m", {"prompt": "x"})["quote_id"]
    mcp_server.generate("m", {"prompt": "x"}, quote_id=q1)
    assert len(generated) == 2


def test_incomplete_price_needs_explicit_acceptance(monkeypatch):
    call, generated = _fake({"usd": None, "missing": ["input video duration"]})
    monkeypatch.setattr(mcp_server, "_call", call)
    q = mcp_server.run_preset("ad-multiplier", {}, dry_run=True)["quote_id"]
    with pytest.raises(ToolError, match="input video duration"):
        mcp_server.run_preset("ad-multiplier", {}, dry_run=False, quote_id=q)
    mcp_server.run_preset("ad-multiplier", {}, dry_run=False, quote_id=q, confirm_unknown_cost=True)
    assert generated == ["/v1/presets/ad-multiplier/run"]
