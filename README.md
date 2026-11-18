# Casabourse Lens

**An MCP server that turns Claude into a research analyst for the Casablanca Stock Exchange.**
It gives the model 27 tools over live quotes, order books, technicals, fundamentals, macro,
FX, commodities, news and corporate actions. It also does the unglamorous data-quality work
that makes analysis on a frontier market trustworthy.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![MCP](https://img.shields.io/badge/MCP-compatible-purple)
![Tests](https://img.shields.io/badge/tests-157%20passing-brightgreen)

> "Give me a technical analysis of IAM."
> "Compare BCP, ATW and CIH. Which looks best right now, and how correlated are they?"
> "Find stocks up today on unusual volume, and flag any going ex-dividend."

---

## Why it matters — business impact

The Bourse de Casablanca, a frontier market of fewer than 100 listed companies, is poorly served by the tools retail
investors and small advisers use elsewhere. Terminals are expensive, coverage is thin, and
free sites show raw, unadjusted prices. An LLM pointed at that data will confidently
produce wrong analysis.

| Problem | What Casabourse Lens does | Effect |
|---|---|---|
| Research a professional does in an hour (quotes, chart, ratios, macro, news) | One natural-language question; Claude calls the tools it needs | Analyst-grade context in seconds, at near-zero cost |
| **Dividends create fake price drops**, so RSI/MACD across an ex-date are false signals | Corporate-actions store plus **back-adjusted price history** feeding every indicator | Removes a class of silent, systematic errors |
| Sources disagree on dividend amounts and ex-dates | A deterministic **reconciler** with per-field source precedence; disagreements are marked `DISPUTED`, and splits need two sources | The agent reports uncertainty instead of picking a number |
| One flaky upstream API takes everything down | A `DataProvider` abstraction plus a **DuckDB write-through cache** with per-data-class TTLs | Keeps working through outages and enables history-based features |
| "Is this stock risky?" answered from a point estimate | `get_beta` returns standard error, R² and a 95% CI against a cap-weighted synthetic MASI | Confidence is explicit, so the agent can't overclaim |

**Who it's for:** Moroccan retail investors, independent advisers, finance students, and
anyone building agents on frontier-market data.

---

## What I built

All of it: the provider layer and cache, the indicator library (no TA dependencies), the
corporate-actions event store, validator, reconciler and adjuster, the ingestion pipeline,
and the 157-test regression suite.

```
Claude ⇄ MCP (stdio) ⇄ TradingTools ── decorator-based tool registry (27 tools)
                          │
                          ├─ CachingDataProvider (DuckDB, TTL per data class)
                          │     └─ WafaBourse · Bank Al-Maghrib · World Bank · Yahoo (FX/commodities) · RSS news
                          │
                          └─ CorporateActionService
                                ├─ event log (SQLite) ← ingestion agents (Bourse de Casablanca, manual)
                                ├─ validator → reconciler (source precedence, disputes)
                                └─ adjuster → back-adjusted OHLCV for every indicator
```

### Engineering choices worth calling out

- **TLS done properly.** `api.casablanca-bourse.com` serves only its leaf certificate. Instead of `verify=False`, the missing Sectigo intermediates are bundled and loaded alongside certifi ([`ingestion/http/`](ingestion/http/)).
- **Polite ingestion.** The client applies a per-host throttle, retries with exponential backoff on 5xx and transport errors only (a 404 is not transient), and writes structured per-request logs.
- **Precedence is per field, not per source.** AMMC is authoritative for a dividend *amount*, and the exchange is authoritative for the *ex-date*. Treating those the same is how retail tools end up one day off ([`reconciler.py`](trading_tools/corporate_actions/reconciler.py)).
- **Write access is opt-in.** The optional MASI trading-simulator tools (place and cancel orders, portfolio) register only when `MASI_PLAYGROUND_URL` and `MASI_API_KEY` are both set. By default the server is read-only.

---

## Tools

| Category | Tools |
|---|---|
| **Market** | `get_market_overview` `get_market_breadth` `get_all_stocks` `screen_stocks` |
| **Stock analysis** | `get_stock_snapshot` `get_technical_analysis` `get_order_book` `get_price_history` `get_recent_trades` |
| **Trading** | `analyze_volume_profile` `get_volatility_analysis` `get_support_resistance` `get_intraday_momentum` `compare_stocks` |
| **Fundamentals** | `get_company_profile` `get_shareholders` `get_financial_metrics` |
| **Macro / cross-asset** | `get_macro_snapshot` `get_fx_rates` `get_commodity_prices` |
| **News & sentiment** | `get_news` `get_news_sentiment` |
| **Flows** | `analyze_orderflow_imbalance` |
| **Portfolio & risk** | `get_correlation_matrix` `get_beta` |
| **Corporate actions** | `get_corporate_actions` `get_adjusted_price_history` |

Indicators are computed in-house: SMA/EMA, RSI(14), MACD(12/26/9), Bollinger(20, 2σ), ATR,
VWAP, and swing-based support/resistance.

---

## Setup

```bash
git clone https://github.com/lmakinaa/casabourse-lens-mcp.git
cd casabourse-lens-mcp
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

Add it to Claude Desktop's config (`claude_desktop_config.json`), then restart Claude Desktop:

```json
{
  "mcpServers": {
    "casabourse-lens": {
      "command": "/full/path/to/casabourse-lens-mcp/.venv/bin/python",
      "args": ["/full/path/to/casabourse-lens-mcp/server.py"]
    }
  }
}
```

No API keys are needed. The market data sources are public.

### Corporate-actions ingestion

```bash
python -m ingestion scrape-bourse --since 2024-01-01            # write to the event store
python -m ingestion scrape-bourse --since 2024-01-01 --dry-run  # print candidates only
```

Run it daily (e.g. cron at 06:10) to keep adjusted prices current.

### Tests

```bash
pip install -r requirements-dev.txt
pytest          # 157 tests, upstreams mocked, no network
```

---

## Status and roadmap

All 27 tools are live. The AMMC earnings-calendar and regulatory-filings tools are built and
tested but currently **disabled** (their decorators are commented out, so the server doesn't
expose them). Next up are the yield curve, multi-year financial
statements, sector peers and a `backtest_signal` tool. The full ranked list is in
[`ROADMAP.md`](ROADMAP.md).

## Disclaimer

Unofficial, and not affiliated with WafaBourse, the Bourse de Casablanca or AMMC. This is
not investment advice. Respect each data source's terms of service.

## License

MIT
