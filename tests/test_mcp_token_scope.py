"""El token HF_STUDIO_TOKEN del servidor MCP solo viaja a rutas relativas de HF Studio, nunca a URLs absolutas."""

from pathlib import Path

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from hf_studio import mcp_server

MOCK_AUTH = "Bearer test-token"


def _studio(seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(("studio", str(request.url), request.headers.get("authorization")))
        return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})

    return lambda: httpx.Client(
        base_url="http://studio",
        headers={"Authorization": MOCK_AUTH},
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize(
    "url",
    [
        "HTTPS://cdn.example/x.png",
        "Https://cdn.example/x.png",
        "  https://cdn.example/x.png",
        "//cdn.example/x.png",
        "file:///etc/hosts",
        "/v1/generations/../secret",
    ],
)
def test_generation_preview_never_sends_token_to_non_studio_urls(monkeypatch, url):
    job = {"status": "completed", "outputs": [{"kind": "image", "url": url}]}
    monkeypatch.setattr(mcp_server, "_call", lambda *a, **k: job)
    seen = []
    monkeypatch.setattr(mcp_server, "_client", _studio(seen))
    remote_seen = []
    real_client = httpx.Client

    def remote_client(*args, **kwargs):
        def handler(request: httpx.Request) -> httpx.Response:
            remote_seen.append((str(request.url), request.headers.get("authorization")))
            return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})

        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(mcp_server.httpx, "Client", remote_client)
    if url.lstrip().lower().startswith(("http://", "https://")):
        out = mcp_server.generation_preview("g1", 0)
        assert out["bytes"] == 4
        assert len(remote_seen) == 1
    else:
        with pytest.raises(ToolError, match="URL válida"):
            mcp_server.generation_preview("g1", 0)
    assert seen == []
    assert all(auth is None for _, auth in remote_seen)


def test_generation_preview_relative_ref_uses_studio_client(monkeypatch):
    job = {"status": "completed", "outputs": [{"kind": "video", "url": "/v1/generations/g1/files/0.mp4"}]}
    monkeypatch.setattr(mcp_server, "_call", lambda *a, **k: job)
    seen = []
    monkeypatch.setattr(mcp_server, "_client", _studio(seen))
    mcp_server.generation_preview("g1", 0)
    assert seen == [("studio", "http://studio/v1/generations/g1/files/0.mp4", MOCK_AUTH)]


@pytest.mark.parametrize("file_url", ["HTTPS://cdn.example/0.png", "  https://cdn.example/0.png"])
def test_download_outputs_absolute_file_url_goes_without_token(monkeypatch, tmp_path, file_url):
    job = {
        "status": "completed",
        "outputs": [{"kind": "image", "url": "https://cdn.example/fallback.png", "file_url": file_url}],
    }
    monkeypatch.setattr(mcp_server, "_call", lambda *a, **k: job)
    seen = []
    monkeypatch.setattr(mcp_server, "_client", _studio(seen))
    plain = []

    def fake_get(url, **kwargs):
        plain.append(url)
        return httpx.Response(200, content=b"x", request=httpx.Request("GET", "https://cdn.example/0.png"))

    monkeypatch.setattr(mcp_server.httpx, "get", fake_get)
    res = mcp_server.download_outputs("g1", str(tmp_path))
    assert seen == []
    assert plain == [file_url.strip()]
    assert Path(res["files"][0]).read_bytes() == b"x"


def test_download_outputs_rejects_non_http_external_scheme(monkeypatch, tmp_path):
    job = {
        "status": "completed",
        "outputs": [{"kind": "image", "url": "file:///etc/hosts"}],
    }
    monkeypatch.setattr(mcp_server, "_call", lambda *a, **k: job)
    monkeypatch.setattr(mcp_server, "_client", _studio([]))
    with pytest.raises(ToolError, match="URL válida"):
        mcp_server.download_outputs("g1", str(tmp_path))


def test_download_outputs_relative_file_url_uses_studio_client(monkeypatch, tmp_path):
    job = {
        "status": "completed",
        "outputs": [
            {
                "kind": "image",
                "url": "https://cdn.example/x.png",
                "file_url": "/v1/generations/g1/files/0.png",
            }
        ],
    }
    monkeypatch.setattr(mcp_server, "_call", lambda *a, **k: job)
    seen = []
    monkeypatch.setattr(mcp_server, "_client", _studio(seen))
    mcp_server.download_outputs("g1", str(tmp_path))
    assert [s[2] for s in seen] == [MOCK_AUTH]
