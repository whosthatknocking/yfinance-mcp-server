import contextlib
from unittest.mock import patch

from starlette.testclient import TestClient
from starlette.responses import PlainTextResponse

from yfinance_mcp import server


@contextlib.asynccontextmanager
async def _noop_lifespan():
    yield


class _FakeSessionManager:
    def run(self):
        return _noop_lifespan()


class _FakeMCP:
    def __init__(self):
        self.session_manager = _FakeSessionManager()

    def streamable_http_app(self):
        async def app(scope, receive, send):
            response = PlainTextResponse("mcp")
            await response(scope, receive, send)

        return app


def test_healthz_returns_ok():
    with patch.object(server, "mcp", _FakeMCP()):
        app = server._build_http_app()

        with TestClient(app) as client:
            response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_returns_version_metadata():
    with patch.object(server, "mcp", _FakeMCP()):
        app = server._build_http_app()

        with TestClient(app) as client:
            response = client.get("/readyz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["server_name"] == "yfinance"
    assert "server_version" in payload
    assert "supported_yfinance_version" in payload
    assert "cache_backend" in payload


def test_mcp_route_is_mounted():
    with patch.object(server, "mcp", _FakeMCP()):
        app = server._build_http_app()

        with TestClient(app) as client:
            response = client.get("/mcp")

    assert response.status_code == 200
    assert response.text == "mcp"


def test_main_runs_stdio_transport_by_default():
    with patch.object(server.mcp, "run") as mocked_run:
        with patch.dict("os.environ", {}, clear=True):
            server.main()

    mocked_run.assert_called_once_with(transport="stdio")


def test_main_runs_streamable_http_server():
    with patch.object(server, "_build_http_app", return_value=object()) as mocked_build:
        with patch.object(server.uvicorn, "run") as mocked_run:
            with patch.dict(
                "os.environ",
                {
                    "YF_TRANSPORT": "streamable-http",
                    "YF_HTTP_HOST": "0.0.0.0",
                    "YF_HTTP_PORT": "9000",
                    "YF_UVICORN_LOG_LEVEL": "warning",
                },
                clear=True,
            ):
                server.main()

    mocked_build.assert_called_once_with()
    mocked_run.assert_called_once()
    _, kwargs = mocked_run.call_args
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 9000
    assert kwargs["log_level"] == "warning"
