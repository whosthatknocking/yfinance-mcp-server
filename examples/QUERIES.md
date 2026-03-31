# Example Queries

These are example prompts you can use in an AI host connected to `yfinance-mcp-server`.

## Basic Data Retrieval

- Get the latest fast info for AAPL.
- Show me 6 months of daily price history for MSFT.
- Download 1 year of weekly data for AAPL, MSFT, and NVDA.
- Get the latest news for TSLA.
- Show the option chain for SPY for the nearest expiration.
- Get the annual income statement for AMZN.
- Get the quarterly balance sheet for META.
- Get the trailing cashflow data for GOOGL.
- Get the market summary for us.

## Tool Discovery Style Prompts

- What tools are available for price history and quote snapshots?
- Which tool should I use for recent news about Tesla?
- I want options data for SPY. First find the available expirations, then get the option chain.
- I need annual financial statement data for Amazon. Which tools should be used?
- For a multi-ticker historical download, use the best matching tool.

## Comparison Prompts

- Compare Apple and Microsoft using latest fast info, recent price history, and latest news.
- Compare Nvidia and AMD using recent price history and latest fast info.
- Show the latest fast info and recent price history for Amazon and Tesla, then summarize key differences.

## Analysis-Oriented Prompts

- Get Nvidia's recent history and latest news, then summarize the current trend.
- Fetch Amazon's income statement, balance sheet, and cashflow and highlight the biggest changes.
- Get Apple's latest fast info, 3 months of price history, and recent news, then summarize the overall picture.
- Show Microsoft's quarterly balance sheet and yearly income statement, then highlight any notable changes.
- For Apple, decide whether `get_info` or `get_fast_info` is more appropriate for a quick market snapshot and explain why.
