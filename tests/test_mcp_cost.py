import time

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from hf_studio import mcp_server


def _fake(price):
    """Simula la API: las cotizaciones devuelven `price`; registra cada generación y su clave."""
    generated = []

    def call(method, path, **kw):
        body = kw.get("json", {})
        if path == "/v1/estimate":
            return dict(price)
        if body.get("dry_run", False) is False:
            generated.append(path)
            keys.append(kw["headers"]["Idempotency-Key"])
            return {"ok": True}
        return {"total": dict(price), "estimate": dict(price)}

    return call, generated


keys: list[str] = []


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
    with pytest.raises(ToolError, match="mismatched"):
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


def test_a_quote_pays_for_one_run_only(monkeypatch):
    call, _ = _fake({"usd": 1.2, "complete": True, "missing": []})
    monkeypatch.setattr(mcp_server, "_call", call)
    keys.clear()
    q = mcp_server.estimate_cost("m", {"prompt": "x"})["quote_id"]
    mcp_server.generate("m", {"prompt": "x"}, quote_id=q, allow_duplicate=True)
    # Reintento: misma clave de idempotencia, la API deduplica y no cobra otra vez.
    mcp_server.generate("m", {"prompt": "x"}, quote_id=q, allow_duplicate=True)
    assert keys[0] == keys[1]
    with pytest.raises(ToolError, match="already used"):
        mcp_server.generate("m", {"prompt": "x"}, quote_id=q, idempotency_key="otra", allow_duplicate=True)


def test_expired_quote_is_refused(monkeypatch):
    call, _ = _fake({"usd": 1.2, "complete": True, "missing": []})
    monkeypatch.setattr(mcp_server, "_call", call)
    q = mcp_server.estimate_cost("m", {"prompt": "x"})["quote_id"]
    mcp_server._quotes[q]["expires"] = 0
    with pytest.raises(ToolError, match="expired"):
        mcp_server.generate("m", {"prompt": "x"}, quote_id=q)


def test_concurrent_redeems_accept_a_single_key(monkeypatch):
    import threading

    call, _ = _fake({"usd": 1.2, "complete": True, "missing": []})
    monkeypatch.setattr(mcp_server, "_call", call)
    payload = {"model": "m", "input": {"prompt": "x"}, "hints": {}}
    q = mcp_server.estimate_cost("m", {"prompt": "x"})["quote_id"]
    start, accepted = threading.Barrier(8), []

    # Simula que el hilo pierde la CPU justo después de leer la clave usada: sin lock,
    # varios hilos verían «sin usar» y la cotización pagaría varias ejecuciones.
    class SlowQuote(dict):
        def __getitem__(self, name):
            value = super().__getitem__(name)
            if name == "key":
                time.sleep(0.05)
            return value

    mcp_server._quotes[q] = SlowQuote(mcp_server._quotes[q])

    def redeem(n):
        start.wait()
        try:
            accepted.append(mcp_server._redeem_quote(payload, q, f"k{n}", False))
        except ToolError:
            pass

    threads = [threading.Thread(target=redeem, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(accepted) == 1
