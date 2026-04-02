# yfinance to MCP API Mapping

This document maps the latest supported yfinance API surface to explicit MCP tools for yfinance-mcp-server.

## Mapping Rules

- Source of truth: official yfinance API reference and documented behavior for the latest supported upstream release.
- MCP tool names use stable snake case without repeating the server name prefix.
- The server should prefer canonical upstream concepts over duplicate aliases.
- Upstream aliases should either map to the same MCP tool or be documented as compatibility aliases.
- Tools should return structured JSON-safe payloads, even when upstream returns pandas objects.

## Status Legend

- implemented: explicit MCP tool exists in the current server
- alias: upstream alias handled by an existing implemented tool
- not-implemented: documented upstream capability that does not currently have a dedicated MCP tool
- internal: internal wrapper behavior, not exposed directly as an MCP tool
- documented-out-of-scope: documented for completeness but not part of the MCP information-tool surface

## Top-Level Information APIs

| Upstream API | Kind | MCP Tool | Status | Notes |
| --- | --- | --- | --- | --- |
| yf.download(...) | function | download_history | implemented | Multi-ticker historical download with explicit history parameters. |
| yf.screen(...) | function | screen | not-implemented | Screener support is documented in the spec but no MCP screener tool exists yet. |
| yf.Search(...) | class constructor | search | implemented | Returns structured search payload and selected views. |
| yf.Lookup(...) | class constructor | lookup | implemented | Returns grouped lookup data. |
| yf.Market(market) | class constructor | get_market | implemented | Returns summary and status for a market code. |
| yf.Calendars(...) | class constructor | get_calendars | implemented | Returns default calendar bundle for a date range. |
| yf.Sector(key) | class constructor | get_sector | implemented | Returns sector overview and linked data. |
| yf.Industry(key) | class constructor | get_industry | implemented | Returns industry overview and linked data. |
| yf.EquityQuery(...) | class constructor | build_equity_query | not-implemented | Query-builder helper tools are not currently exposed. |
| yf.FundQuery(...) | class constructor | build_fund_query | not-implemented | Query-builder helper tools are not currently exposed. |

## Ticker Construction and Core Access

| Upstream API | Kind | MCP Tool | Status | Notes |
| --- | --- | --- | --- | --- |
| yf.Ticker(symbol, session=None) | class constructor | internal | internal | Internal wrapper entry point; not exposed directly. |
| Ticker.history(...) | method | get_history | implemented | Canonical single-symbol price history tool. |
| Ticker.get_history_metadata() | method | get_history_metadata | implemented | Returns history metadata dict. |
| Ticker.info | property | get_info | implemented | Canonical info tool. |
| Ticker.get_info() | method | get_info | alias | Same MCP tool as info. |
| Ticker.fast_info | property | get_quote_snapshot | implemented | Lightweight quote/profile snapshot exposed with a more natural MCP name. |
| Ticker.get_fast_info() | method | get_quote_snapshot | alias | Same MCP tool as fast_info. |
| Ticker.isin | property | get_isin | implemented | Canonical ISIN tool. |
| Ticker.get_isin() | method | get_isin | alias | Same MCP tool as isin. |
| Ticker.news | property | get_news | implemented | News list with default upstream behavior. |
| Ticker.get_news(count=10, tab='news') | method | get_news | alias | MCP tool should expose count and tab. |
| Ticker.options | property | get_option_expirations | implemented | Returns available option expiration dates. |
| Ticker.option_chain(date=None, tz=None) | method | get_option_chain | implemented | Returns calls and puts in structured schema. |

## Ticker Price, Corporate Actions, and Ownership Time Series

| Upstream API | Kind | MCP Tool | Status | Notes |
| --- | --- | --- | --- | --- |
| Ticker.actions | property | get_actions | implemented | Combined dividends and splits table. |
| Ticker.get_actions(period='max') | method | get_actions | alias | MCP tool should expose period. |
| Ticker.dividends | property | get_dividends | implemented | Dividend series. |
| Ticker.get_dividends(period='max') | method | get_dividends | alias | Canonical dividends tool. |
| Ticker.splits | property | get_splits | implemented | Split series. |
| Ticker.get_splits(period='max') | method | get_splits | alias | Canonical splits tool. |
| Ticker.get_shares_full(start=None, end=None) | method | get_shares_full | implemented | Extended share count history. |

## Ticker Financial Statements and Filings

| Upstream API | Kind | MCP Tool | Status | Notes |
| --- | --- | --- | --- | --- |
| Ticker.income_stmt | property | get_income_stmt | implemented | Canonical income statement tool. |
| Ticker.get_income_stmt(as_dict=False, pretty=False, freq='yearly') | method | get_income_stmt | alias | Expose freq, pretty, and serialization options. |
| Ticker.get_incomestmt(...) | method | get_income_stmt | alias | Upstream alias. |
| Ticker.financials | property | get_income_stmt | alias | Common upstream alias for annual income statement. |
| Ticker.quarterly_income_stmt | property | get_income_stmt | alias | Represent as freq='quarterly'. |
| Ticker.quarterly_incomestmt | property | get_income_stmt | alias | Upstream alias. |
| Ticker.quarterly_financials | property | get_income_stmt | alias | Upstream alias. |
| Ticker.ttm_income_stmt | property | get_income_stmt | alias | Represent as freq='trailing'. |
| Ticker.ttm_incomestmt | property | get_income_stmt | alias | Upstream alias. |
| Ticker.ttm_financials | property | get_income_stmt | alias | Upstream alias. |
| Ticker.balance_sheet | property | get_balance_sheet | implemented | Canonical balance sheet tool. |
| Ticker.get_balance_sheet(as_dict=False, pretty=False, freq='yearly') | method | get_balance_sheet | alias | Expose freq. |
| Ticker.get_balancesheet(...) | method | get_balance_sheet | alias | Upstream alias. |
| Ticker.balancesheet | property | get_balance_sheet | alias | Upstream alias. |
| Ticker.quarterly_balance_sheet | property | get_balance_sheet | alias | Represent as freq='quarterly'. |
| Ticker.quarterly_balancesheet | property | get_balance_sheet | alias | Upstream alias. |
| Ticker.cashflow | property | get_cashflow | implemented | Canonical cashflow tool. |
| Ticker.cash_flow | property | get_cashflow | alias | Upstream alias. |
| Ticker.get_cashflow(as_dict=False, pretty=False, freq='yearly') | method | get_cashflow | alias | Expose freq. |
| Ticker.get_cash_flow(...) | method | get_cashflow | alias | Upstream alias. |
| Ticker.quarterly_cashflow | property | get_cashflow | alias | Represent as freq='quarterly'. |
| Ticker.quarterly_cash_flow | property | get_cashflow | alias | Upstream alias. |
| Ticker.ttm_cashflow | property | get_cashflow | alias | Represent as freq='trailing'. |
| Ticker.ttm_cash_flow | property | get_cashflow | alias | Upstream alias. |
| Ticker.calendar | property | get_ticker_calendar | implemented | Ticker-specific calendar/events dict. |
| Ticker.get_calendar() | method | get_ticker_calendar | alias | Same MCP tool as calendar. |
| Ticker.earnings_dates | property | get_earnings_dates | implemented | Earnings date DataFrame/records. |
| Ticker.get_earnings_dates(limit=12, offset=0) | method | get_earnings_dates | alias | Expose pagination arguments. |
| Ticker.sec_filings | property | get_sec_filings | implemented | SEC filings list/dict. |
| Ticker.get_sec_filings() | method | get_sec_filings | alias | Same MCP tool as sec_filings. |

## Ticker Analysis, Estimates, and Recommendations

| Upstream API | Kind | MCP Tool | Status | Notes |
| --- | --- | --- | --- | --- |
| Ticker.recommendations | property | get_recommendations | implemented | Recommendations table. |
| Ticker.get_recommendations(as_dict=False) | method | get_recommendations | alias | Same MCP tool as property. |
| Ticker.recommendations_summary | property | get_recommendations_summary | implemented | Summary table. |
| Ticker.get_recommendations_summary(as_dict=False) | method | get_recommendations_summary | alias | Same MCP tool as property. |
| Ticker.upgrades_downgrades | property | get_upgrades_downgrades | implemented | Broker ratings changes. |
| Ticker.get_upgrades_downgrades(as_dict=False) | method | get_upgrades_downgrades | alias | Same MCP tool as property. |
| Ticker.analyst_price_targets | property | get_analyst_price_targets | implemented | Returns current, low, high, mean, median. |
| Ticker.get_analyst_price_targets() | method | get_analyst_price_targets | alias | Same MCP tool as property. |
| Ticker.earnings_estimate | property | get_earnings_estimate | implemented | Estimate table. |
| Ticker.get_earnings_estimate(as_dict=False) | method | get_earnings_estimate | alias | Same MCP tool as property. |
| Ticker.revenue_estimate | property | get_revenue_estimate | implemented | Revenue estimate table. |
| Ticker.get_revenue_estimate(as_dict=False) | method | get_revenue_estimate | alias | Same MCP tool as property. |
| Ticker.earnings_history | property | get_earnings_history | implemented | Historical EPS surprise data. |
| Ticker.get_earnings_history(as_dict=False) | method | get_earnings_history | alias | Same MCP tool as property. |
| Ticker.eps_trend | property | get_eps_trend | implemented | EPS trend table. |
| Ticker.get_eps_trend(as_dict=False) | method | get_eps_trend | alias | Same MCP tool as property. |
| Ticker.eps_revisions | property | get_eps_revisions | implemented | EPS revisions table. |
| Ticker.get_eps_revisions(as_dict=False) | method | get_eps_revisions | alias | Same MCP tool as property. |
| Ticker.growth_estimates | property | get_growth_estimates | implemented | Growth estimates table. |
| Ticker.get_growth_estimates(as_dict=False) | method | get_growth_estimates | alias | Same MCP tool as property. |
## Ticker Holders, Insider Data, and Fund Data

| Upstream API | Kind | MCP Tool | Status | Notes |
| --- | --- | --- | --- | --- |
| Ticker.insider_purchases | property | get_insider_purchases | implemented | Insider purchases table. |
| Ticker.get_insider_purchases(as_dict=False) | method | get_insider_purchases | alias | Same MCP tool as property. |
| Ticker.insider_transactions | property | get_insider_transactions | implemented | Insider transactions table. |
| Ticker.get_insider_transactions(as_dict=False) | method | get_insider_transactions | alias | Same MCP tool as property. |
| Ticker.insider_roster_holders | property | get_insider_roster_holders | implemented | Insider roster holdings table. |
| Ticker.get_insider_roster_holders(as_dict=False) | method | get_insider_roster_holders | alias | Same MCP tool as property. |
| Ticker.major_holders | property | get_major_holders | implemented | Major holders table. |
| Ticker.get_major_holders(as_dict=False) | method | get_major_holders | alias | Same MCP tool as property. |
| Ticker.institutional_holders | property | get_institutional_holders | implemented | Institutional holders table. |
| Ticker.get_institutional_holders(as_dict=False) | method | get_institutional_holders | alias | Same MCP tool as property. |
| Ticker.mutualfund_holders | property | get_mutualfund_holders | implemented | Mutual fund holders table. |
| Ticker.get_mutualfund_holders(as_dict=False) | method | get_mutualfund_holders | alias | Same MCP tool as property. |
| Ticker.funds_data | property | get_funds_data | implemented | Canonical fund-data bundle for ETFs and mutual funds. |
| Ticker.get_funds_data() | method | get_funds_data | alias | Same MCP tool as property. |
| FundsData.asset_classes | property | get_fund_asset_classes | implemented | Nested fund-data accessor. |
| FundsData.bond_holdings | property | get_fund_bond_holdings | implemented | Nested fund-data accessor. |
| FundsData.bond_ratings | property | get_fund_bond_ratings | implemented | Nested fund-data accessor. |
| FundsData.description | property | get_fund_description | implemented | Nested fund-data accessor. |
| FundsData.equity_holdings | property | get_fund_equity_holdings | implemented | Nested fund-data accessor. |
| FundsData.fund_operations | property | get_fund_operations | implemented | Nested fund-data accessor. |
| FundsData.fund_overview | property | get_fund_overview | implemented | Nested fund-data accessor. |
| FundsData.sector_weightings | property | get_fund_sector_weightings | implemented | Nested fund-data accessor. |
| FundsData.top_holdings | property | get_fund_top_holdings | implemented | Nested fund-data accessor. |
| FundsData.quote_type() | method | get_fund_quote_type | implemented | Nested fund-data accessor. |

## Tickers Batch APIs

| Upstream API | Kind | MCP Tool | Status | Notes |
| --- | --- | --- | --- | --- |
| yf.Tickers(tickers, session=None) | class constructor | internal | internal | Internal wrapper entry point for batch operations. |
| Tickers.history(...) | method | get_batch_history | not-implemented | Multi-symbol history tool is not exposed separately; use `download_history`. |
| Tickers.download(...) | method | download_history | alias | Same behavior family as top-level yf.download. |
| Tickers.news() | method | get_batch_news | implemented | Returns news grouped by symbol or upstream response shape. |
| Tickers.tickers[...] | attribute access | get_batch_info | implemented | Expose common batch getter helpers without raw object traversal. |
| Tickers.tickers[...].fast_info | attribute access | get_batch_quote_snapshot | implemented | Expose lightweight quote snapshots for multiple symbols. |

## Market, Calendars, Search, and Lookup

| Upstream API | Kind | MCP Tool | Status | Notes |
| --- | --- | --- | --- | --- |
| Market(market) | class constructor | get_market | implemented | Aggregate market tool returning summary and status in one normalized payload. |
| Market.status | property | get_market_status | implemented | Market open/closed state and metadata. |
| Market.summary | property | get_market_summary | implemented | Market summary payload. |
| Calendars(...) | class constructor | get_calendars | implemented | Aggregate calendars tool returning the supported calendar views in one normalized payload. |
| Calendars.earnings_calendar | property | get_earnings_calendar | implemented | Default range earnings calendar. |
| Calendars.get_earnings_calendar(...) | method | get_earnings_calendar | alias | Expose market_cap, filter_most_active, start, end, limit, offset, force. |
| Calendars.economic_events_calendar | property | get_economic_events_calendar | implemented | Default range economic events. |
| Calendars.get_economic_events_calendar(...) | method | get_economic_events_calendar | alias | Same MCP tool as property. |
| Calendars.ipo_info_calendar | property | get_ipo_calendar | implemented | Default range IPO calendar. |
| Calendars.get_ipo_info_calendar(...) | method | get_ipo_calendar | alias | Same MCP tool as property. |
| Calendars.splits_calendar | property | get_splits_calendar | implemented | Default range splits calendar. |
| Calendars.get_splits_calendar(...) | method | get_splits_calendar | alias | Same MCP tool as property. |
| Search.response | property | search | alias | Raw response can be included in main search result. |
| Search.all | property | search | alias | Include normalized all view in output. |
| Search.quotes | property | search | alias | Include quotes view in output. |
| Search.news | property | search | alias | Include news view in output. |
| Search.lists | property | search | alias | Include lists view in output. |
| Search.nav | property | search | alias | Include navigation links view in output. |
| Search.research | property | search | alias | Include research view in output. |
| Search.search() | method | search | alias | Constructor-plus-search should collapse into one MCP call. |
| Lookup(...) | class constructor | lookup | implemented | Aggregate lookup tool returning grouped results across supported instrument types. |
| Lookup.all | property | lookup_all | not-implemented | The current MCP surface returns grouped results through `lookup` rather than per-view tools. |
| Lookup.get_all(count=25) | method | lookup_all | not-implemented | Use `lookup`. |
| Lookup.stock | property | lookup_stock | not-implemented | Use `lookup`. |
| Lookup.get_stock(count=25) | method | lookup_stock | not-implemented | Use `lookup`. |
| Lookup.etf | property | lookup_etf | not-implemented | Use `lookup`. |
| Lookup.get_etf(count=25) | method | lookup_etf | not-implemented | Use `lookup`. |
| Lookup.mutualfund | property | lookup_mutualfund | not-implemented | Use `lookup`. |
| Lookup.get_mutualfund(count=25) | method | lookup_mutualfund | not-implemented | Use `lookup`. |
| Lookup.index | property | lookup_index | not-implemented | Use `lookup`. |
| Lookup.get_index(count=25) | method | lookup_index | not-implemented | Use `lookup`. |
| Lookup.future | property | lookup_future | not-implemented | Use `lookup`. |
| Lookup.get_future(count=25) | method | lookup_future | not-implemented | Use `lookup`. |
| Lookup.currency | property | lookup_currency | not-implemented | Use `lookup`. |
| Lookup.get_currency(count=25) | method | lookup_currency | not-implemented | Use `lookup`. |
| Lookup.cryptocurrency | property | lookup_cryptocurrency | not-implemented | Use `lookup`. |
| Lookup.get_cryptocurrency(count=25) | method | lookup_cryptocurrency | not-implemented | Use `lookup`. |

## Sector and Industry Domain APIs

| Upstream API | Kind | MCP Tool | Status | Notes |
| --- | --- | --- | --- | --- |
| Sector.key | property | get_sector | alias | Include in base sector payload. |
| Sector.name | property | get_sector | alias | Include in base sector payload. |
| Sector.symbol | property | get_sector | alias | Include in base sector payload. |
| Sector.overview | property | get_sector_overview | implemented | Sector overview dict. |
| Sector.research_reports | property | get_sector_research_reports | implemented | Sector research reports. |
| Sector.industries | property | get_sector_industries | implemented | Industry membership table. |
| Sector.top_companies | property | get_sector_top_companies | implemented | Top companies table. |
| Sector.top_etfs | property | get_sector_top_etfs | implemented | ETF mapping. |
| Sector.top_mutual_funds | property | get_sector_top_mutual_funds | implemented | Mutual fund mapping. |
| Sector.ticker | property | get_sector_ticker | implemented | Resolved sector-linked ticker summary. |
| Industry.key | property | get_industry | alias | Include in base industry payload. |
| Industry.name | property | get_industry | alias | Include in base industry payload. |
| Industry.symbol | property | get_industry | alias | Include in base industry payload. |
| Industry.sector_key | property | get_industry | alias | Include in base industry payload. |
| Industry.sector_name | property | get_industry | alias | Include in base industry payload. |
| Industry.overview | property | get_industry_overview | implemented | Industry overview dict. |
| Industry.research_reports | property | get_industry_research_reports | implemented | Industry research reports. |
| Industry.top_companies | property | get_industry_top_companies | implemented | Top companies table. |
| Industry.top_growth_companies | property | get_industry_top_growth_companies | implemented | Top growth companies table. |
| Industry.top_performing_companies | property | get_industry_top_performing_companies | implemented | Top performing companies table. |
| Industry.ticker | property | get_industry_ticker | implemented | Resolved industry-linked ticker summary. |

## Screener and Query APIs

| Upstream API | Kind | MCP Tool | Status | Notes |
| --- | --- | --- | --- | --- |
| EquityQuery.to_dict() | method | build_equity_query | not-implemented | Query-builder helper tools are not currently exposed. |
| EquityQuery.valid_fields | attribute | get_equity_query_fields | not-implemented | Query-field metadata is not currently exposed. |
| FundQuery.to_dict() | method | build_fund_query | not-implemented | Query-builder helper tools are not currently exposed. |
| FundQuery.valid_fields | attribute | get_fund_query_fields | not-implemented | Query-field metadata is not currently exposed. |
| screen(query, ...) with predefined name | function | screen | not-implemented | Screener support is not currently exposed. |
| screen(query, ...) with EquityQuery | function | screen | not-implemented | Screener support is not currently exposed. |
| screen(query, ...) with FundQuery | function | screen | not-implemented | Screener support is not currently exposed. |

## Documented Out-of-Scope APIs

| Upstream API | Kind | MCP Tool | Status | Notes |
| --- | --- | --- | --- | --- |
| yf.enable_debug_mode() | function | none | documented-out-of-scope | Process-level helper, not an information tool. |
| yf.set_tz_cache_location(path) | function | none | documented-out-of-scope | Startup configuration, not an information tool. |
| yf.WebSocket(...) | class constructor | none | documented-out-of-scope | Streaming does not fit the core request-response MCP scope. |
| yf.AsyncWebSocket(...) | class constructor | none | documented-out-of-scope | Streaming does not fit the core request-response MCP scope. |
| Ticker.live(message_handler=None, verbose=True) | method | none | documented-out-of-scope | Streaming-oriented behavior. |
| Tickers.live(message_handler=None, verbose=True) | method | none | documented-out-of-scope | Streaming-oriented behavior. |
| WebSocket.subscribe(symbols) | method | none | documented-out-of-scope | Long-lived stream lifecycle operation. |
| WebSocket.unsubscribe(symbols) | method | none | documented-out-of-scope | Long-lived stream lifecycle operation. |
| WebSocket.listen(message_handler=None) | method | none | documented-out-of-scope | Long-lived stream lifecycle operation. |
| WebSocket.close() | method | none | documented-out-of-scope | Long-lived stream lifecycle operation. |
| AsyncWebSocket.subscribe(symbols) | method | none | documented-out-of-scope | Long-lived async stream lifecycle operation. |
| AsyncWebSocket.unsubscribe(symbols) | method | none | documented-out-of-scope | Long-lived async stream lifecycle operation. |
| AsyncWebSocket.listen(message_handler=None) | method | none | documented-out-of-scope | Long-lived async stream lifecycle operation. |
| AsyncWebSocket.close() | method | none | documented-out-of-scope | Long-lived async stream lifecycle operation. |

## Implemented High-Value Tool Set

These tools are implemented today and cover the highest-value yfinance paths in the current server:

- get_info
- get_quote_snapshot
- get_batch_info
- get_batch_quote_snapshot
- get_batch_news
- get_history
- get_history_metadata
- get_isin
- download_history
- get_news
- get_option_expirations
- get_option_chain
- get_actions
- get_dividends
- get_splits
- get_shares_full
- get_income_stmt
- get_balance_sheet
- get_cashflow
- get_earnings_dates
- get_ticker_calendar
- get_recommendations
- get_recommendations_summary
- get_upgrades_downgrades
- get_analyst_price_targets
- get_earnings_estimate
- get_revenue_estimate
- get_earnings_history
- get_eps_trend
- get_eps_revisions
- get_growth_estimates
- get_market_summary
- get_market
- get_market_status
- get_sec_filings
- search
- lookup

## Implementation Notes

- Treat upstream aliases such as financials and income_stmt, or cash_flow and cashflow, as one MCP contract unless there is a strong reason to preserve separate tools.
- For nested objects like FundsData, expose either:
  - one aggregate tool returning the whole normalized object, and
  - optional narrow tools for high-value subfields
- Keep out-of-scope config and streaming APIs out of the default request-response tool set.
- Update this mapping whenever the supported yfinance version changes.
- Keep statuses aligned with the current implementation in `src/yfinance_mcp/server.py` rather than leaving historical planning values in place.

## Upstream References

- API reference overview: https://ranaroussi.github.io/yfinance/reference/index.html
- Ticker: https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.html
- Tickers: https://ranaroussi.github.io/yfinance/reference/api/yfinance.Tickers.html
- Market: https://ranaroussi.github.io/yfinance/reference/api/yfinance.Market.html
- Calendars: https://ranaroussi.github.io/yfinance/reference/api/yfinance.Calendars.html
- Search: https://ranaroussi.github.io/yfinance/reference/api/yfinance.Search.html
- Lookup: https://ranaroussi.github.io/yfinance/reference/api/yfinance.Lookup.html
- Sector: https://ranaroussi.github.io/yfinance/reference/api/yfinance.Sector.html
- Industry: https://ranaroussi.github.io/yfinance/reference/api/yfinance.Industry.html
- EquityQuery: https://ranaroussi.github.io/yfinance/reference/api/yfinance.EquityQuery.html
- FundQuery: https://ranaroussi.github.io/yfinance/reference/api/yfinance.FundQuery.html
- Screen: https://ranaroussi.github.io/yfinance/reference/api/yfinance.screen.html
- WebSocket: https://ranaroussi.github.io/yfinance/reference/api/yfinance.WebSocket.html
- AsyncWebSocket: https://ranaroussi.github.io/yfinance/reference/api/yfinance.AsyncWebSocket.html
- FundsData: https://ranaroussi.github.io/yfinance/reference/api/yfinance.scrapers.funds.FundsData.html
