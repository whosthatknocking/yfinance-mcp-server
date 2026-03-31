# yfinance-mcp-server

`yfinance-mcp-server` is a Python MCP server that exposes the information-collection parts of the `yfinance` library as discoverable, type-safe tools for AI hosts.

## Objective

The objective is to provide a production-ready MCP server that maps the latest supported `yfinance` data APIs into explicit read-only tools for local and remote MCP clients. This allows AI hosts to retrieve market data, company information, financial statements, analyst signals, options data, search results, calendars, and related financial reference data through stable structured tool contracts.
