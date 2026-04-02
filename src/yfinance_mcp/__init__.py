"""yfinance MCP server package."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("yfinance-mcp-server")
except PackageNotFoundError:  # pragma: no cover - fallback for local/uninstalled execution
    __version__ = "0.0.0+unknown"
