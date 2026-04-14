# Casabourse Lens

An MCP (Model Context Protocol) server that gives Claude real-time access to the Casablanca Stock Exchange (Bourse de Casablanca). Ask Claude to analyze stocks, scan the market, run technical analysis, and more — all with live data.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![MCP](https://img.shields.io/badge/MCP-compatible-purple)

---

## What It Does

Connect this server to Claude Desktop and you can ask things like:

> "What's the market doing today?"
>
> "Give me a technical analysis of IAM"
>
> "Compare BCP, ATW, and CIH — which one looks best right now?"
>
> "Find me stocks that are up today with high volume"

Claude gets **21 tools** for market data, technicals, fundamentals, macro/cross-asset context, and corporate-actions-aware analysis.

## Tools

| Category | Tools |
|---|---|
| **Market** | `get_market_overview` `get_market_breadth` `get_all_stocks` `screen_stocks` |
| **Stock Analysis** | `get_stock_snapshot` `get_technical_analysis` `get_order_book` `get_price_history` `get_recent_trades` |
| **Trading** | `analyze_volume_profile` `get_volatility_analysis` `get_support_resistance` `get_intraday_momentum` `compare_stocks` |
| **Fundamentals** | `get_company_profile` `get_shareholders` `get_financial_metrics` |
| **Macro / Cross-asset** | `get_fx_rates` `get_commodity_prices` |
| **Corporate Actions** | `get_corporate_actions` `get_adjusted_price_history` |

## Setup

**1. Clone and install dependencies**

```bash
git clone https://github.com/lmakinaa/casabourse-lens.git
cd casabourse-lens
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

**2. Add to Claude Desktop**

Open your Claude Desktop config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

Add the server:

```json
{
  "mcpServers": {
    "casabourse-lens": {
      "command": "python",
      "args": ["/full/path/to/casabourse-lens/server.py"]
    }
  }
}
```

**3. Restart Claude Desktop** — the tools will appear automatically.

## Project Structure

```
casabourse-lens/
├── server.py                  # MCP server entry point
├── ingestion/                 # Corporate-actions ingestion pipeline + CLI agents
├── trading_tools/
│   ├── providers/             # Data providers (WafaBourse + cache)
│   ├── corporate_actions/     # Event store, reconciler, adjuster
│   ├── technical_analysis.py  # SMA, EMA, RSI, MACD, Bollinger, ATR, VWAP
│   ├── tools/                 # Tool implementations
│   └── config.py              # API configuration
├── requirements.txt
└── README.md
```

## How It Works

The server connects to Claude Desktop via MCP's stdio transport. When Claude calls a tool, the server fetches live data from the WafaBourse API, processes it (including technical indicator calculations), and returns structured JSON results.

```
Claude Desktop  <-->  MCP Server  <-->  WafaBourse API
                       (stdio)          (Casablanca Stock Exchange)
```

No API keys needed — WafaBourse/BC data is publicly accessible.

## Corporate Actions Ingestion

Run the Bourse de Casablanca dividends scraper:

```bash
python -m ingestion scrape-bourse --since 2024-01-01
```

Dry-run (prints candidate observations, no DB writes):

```bash
python -m ingestion scrape-bourse --since 2024-01-01 --dry-run
```

Container worker cron example (daily at 06:10):

```cron
10 6 * * * /app/.venv/bin/python -m ingestion --db /data/corporate_actions.sqlite scrape-bourse --since 2015-01-01 >> /var/log/casabourse-ingestion.log 2>&1
```

## Technical Indicators

Calculated from historical price data, no external TA libraries required:

- **SMA / EMA** — Simple & Exponential Moving Averages
- **RSI** — Relative Strength Index (14-period)
- **MACD** — Moving Average Convergence Divergence (12/26/9)
- **Bollinger Bands** — 20-period with 2 standard deviations
- **ATR** — Average True Range for volatility
- **VWAP** — Volume Weighted Average Price
- **Support / Resistance** — Swing high/low detection

## Contributing

Contributions are welcome. Open an issue or submit a PR.

## License

MIT

## Disclaimer

This project is unofficial and not affiliated with WafaBourse. Use at your own risk. Respect WafaBourse's terms of service.
