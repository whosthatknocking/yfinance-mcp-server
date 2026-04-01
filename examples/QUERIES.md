# Example Queries

These are example prompts you can use in an AI host connected to yfinance-mcp-server.

## Basic Data Retrieval

- Get the latest stock price and quote snapshot for TSLA.
- Get the latest quote snapshot for TSLA.
- Get a quick quote snapshot for AAPL.
- Show me 6 months of daily price history for MSFT.
- Download 1 year of weekly price history for AAPL, MSFT, and NVDA.
- Get the latest news for TSLA.
- Show the option chain for SPY for the nearest expiration.
- Get the annual income statement for AMZN.
- Get the quarterly balance sheet for META.
- Get the trailing cashflow data for GOOGL.
- Get the Yahoo Finance market summary for the us market code.

## Tool Discovery Style Prompts

- What tools are available for price history and quote snapshots?
- Which tool should I use for recent news about Tesla?
- I want the latest stock price for TSLA. Use the best matching tool.
- For AAPL, use the ticker quote tool rather than the market-summary tool.
- I want options data for SPY. First find the available expirations, then get the option chain.
- I need annual financial statement data for Amazon. Which tools should be used?
- For a multi-ticker historical download, use the best matching tool.

## Comparison Prompts

- Compare Apple and Microsoft using the latest quote snapshots, recent price history, and latest news.
- Compare Nvidia and AMD using recent price history and current quote snapshots.
- Show the latest quote snapshots and recent price history for Amazon and Tesla, then summarize key differences.

## Analysis-Oriented Prompts

- Get Nvidia's recent history and latest news, then summarize the current trend.
- Fetch Amazon's income statement, balance sheet, and cashflow and highlight the biggest changes.
- Get Apple's latest quote snapshot, 3 months of price history, and recent news, then summarize the overall picture.
- Get Tesla's latest quote snapshot and explain the key fields briefly.
- Show Microsoft's quarterly balance sheet and yearly income statement, then highlight any notable changes.
- For Apple, decide whether get_info or get_quote_snapshot is more appropriate for a quick ticker quote request and explain why.
