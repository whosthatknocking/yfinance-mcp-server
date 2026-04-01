from unittest.mock import patch

from starlette.testclient import TestClient

from yfinance_mcp import server


def test_healthz_returns_ok():
    app = server._build_http_app()

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_returns_version_metadata():
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
    app = server._build_http_app()
    mounted_paths = [route.path for route in app.routes if hasattr(route, "path")]
    assert "/mcp" in mounted_paths


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
