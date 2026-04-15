# Casabourse Lens — Tool Roadmap

Tools to add next, ranked by impact on recommendation quality.

**Difficulty scale:** 🟢 Easy (1–2 days, public API/RSS, no scraping) · 🟡 Medium (scraping, parsing, or new infra) · 🔴 Hard (multi-source, persistence, or modeling logic)

## Proposed Tools

| # | Tool | Description | Category | Why it matters | Difficulty |
|---|---|---|---|---|---|
| 1 | `get_corporate_actions` ✅ **done** | Ex-dividend dates, dividend amounts, stock splits, capital increases per ticker. Backed by an event-log + reconciler store with per-field source precedence and point-in-time queries. | Data quality | Without this, every RSI/MACD across an ex-div date is a false signal. Non-negotiable. | 🟡 |
| 2 | `get_adjusted_price_history` ✅ **done** | OHLCV back-adjusted for dividends & splits. Replaces raw history for indicator inputs. | Data quality | Technical indicators on unadjusted series are garbage. Depends on #1. | 🟡 |
| 3 | `get_earnings_calendar` ✅ **done** | Next earnings/publication date per ticker from AMMC filings. | Event risk | Stops the agent from recommending a trade 2 days before a binary event. | 🟡 |
| 4 | `get_regulatory_filings` | AMMC notices: tender offers (OPA/OPR/OPE), profit warnings, material disclosures. | Event risk | Catches market-moving news the tape hasn't priced yet. | 🟡 |
| 5 | `get_macro_snapshot` ✅ **done** | BAM policy rate, 13w/52w T-bill yield, CPI YoY, equity risk premium vs. MASI dividend yield. | Macro | Moroccan equities (esp. banks ≈35% of MASI) are rate-sensitive. Context the ticker doesn't show. | 🟢 |
| 6 | `get_fx_rates` ✅ **done** | EUR/MAD, USD/MAD spot + 20-day change. | Macro | Drives earnings for exporters (OCP, IAM international, tourism). | 🟢 |
| 7 | `get_yield_curve` | BAM primary auction results by tenor. | Macro | Lets the agent compare equity earnings yield to risk-free. | 🟢 |
| 8 | `get_financial_statements` | Multi-year income statement, balance sheet, cash flow per issuer. | Fundamentals | Current `get_financial_metrics` is a ratio snapshot — no trend, no quality check. | 🔴 |
| 9 | `get_sector_peers` | Peer basket by sector with relative valuation table (P/E, P/B, EV/EBITDA, DY, ROE). | Fundamentals | Answers "is this cheap?" properly. Depends on #8. | 🟡 |
| 10 | `get_foreign_ownership` | Foreign holding % per stock + weekly delta from Maroclear data. | Flows | Institutional positioning signal — retail traders can't see this. | 🔴 |
| 11 | `get_block_trades` | Off-market / cross trades above a size threshold. | Flows | Leaks institutional accumulation or distribution. | 🟡 |
| 12 | `analyze_orderflow_imbalance` ✅ **done** | Cumulative bid/ask imbalance computed from existing `get_recent_trades` tick data. | Flows | Pure computation over data you already fetch — high ROI, zero new sources. | 🟢 |
| 13 | `get_news` ✅ **phase 1 live** | Moroccan finance/economy press filtered per ticker (RSS-first). Current coverage: Médias24 + La Vie Éco. | Sentiment | Technical + fundamental without news = recommending the stock the day the CEO resigned. | 🟡 |
| 14 | `get_news_sentiment` ✅ **phase 1 live** | Rolling sentiment score per ticker + mention volume delta vs. 7-day baseline, computed from #13 mention stream. | Sentiment | Converts #13 from raw text into a signal the agent can weigh. | 🟡 |
| 15 | `get_commodity_prices` ✅ **done** | Phosphate rock, Brent crude, gold spot + 30-day change. | Cross-asset | OCP ≈ phosphate. TAQA ≈ oil. Mining names ≈ metals. Core driver, not optional. | 🟢 |
| 16 | `get_global_benchmarks` | MSCI EM, MSCI Frontier, CAC40, S&P 500 daily change. | Cross-asset | MASI tracks EM risk-on/risk-off with a ~1 day lag. | 🟢 |
| 17 | `get_sovereign_spread` | Morocco 10Y USD bond yield vs. US 10Y Treasury. | Cross-asset | Proxy for country-risk repricing — early warning signal. | 🟡 |
| 18 | `backtest_signal` | Given a signal definition, return historical win rate, avg return, max drawdown, Sharpe over N years on a ticker or basket. | Calibration | Converts "looks bullish" into "this setup has a 55% hit rate on this name." Requires persistence (#21). | 🔴 |
| 19 | `get_correlation_matrix` ✅ **done** | Rolling 30/90/180-day correlations across a basket of tickers. | Portfolio | Flags concentration risk when the agent builds a multi-name recommendation. | 🟢 |
| 20 | `get_beta` ✅ **done** | Rolling OLS beta with standard error, R², and 95% CI. Benchmark defaults to a cap-weighted synthetic MASI (top-30 constituents covering ~91% of market cap); ticker benchmarks supported for sector/peer beta. | Portfolio | Point estimates lie. Returning the error bar keeps the agent honest about confidence. | 🟢 |
| 21 | **DuckDB cache layer** *(infra, not a tool)* ✅ **done** | Write-through cache for quotes, OHLCV, fundamentals, corporate actions with per-class TTLs. | Infra | Unlocks #18, fixes the WafaBourse single-point-of-failure, enables historical features. | 🔴 |
| 22 | **`DataProvider` refactor** *(infra, not a tool)* ✅ **done** | Pluggable provider interface so WafaBourse isn't hardcoded into every tool. | Infra | Without this, adding AMMC, BAM, news, and FX means touching 17 tool methods. Do this *before* #1. | 🟡 |

## Current Milestone Status (Apr 2026)

- ✅ Corporate-actions read path is live (`get_corporate_actions`, `get_adjusted_price_history`).
- ✅ Corporate-actions write path Phase 1 is live for BC dividends:
	- `ingestion scrape-bourse` handler implemented
	- TLS/retry/throttle HTTP client in place
	- BC agent + issuer mapping in place
	- end-to-end ingestion tests added and passing
- ✅ Macro, FX, and commodities are live (`get_macro_snapshot`, `get_fx_rates`, `get_commodity_prices`).
- ✅ Orderflow and portfolio-correlation are live (`analyze_orderflow_imbalance`, `get_correlation_matrix`).
- ✅ `get_beta` is live with a cap-weighted synthetic MASI proxy (top-30 constituents) as the default benchmark and optional ticker benchmarks for sector/peer beta.
- ✅ News + sentiment Phase 1 are live (`get_news`, `get_news_sentiment`) on `feat/news-sentiment`:
	- RSS ingestion/provider path implemented with ticker mention extraction + deterministic sentiment scoring
	- cache classes and TTLs added (`NEWS`, `NEWS_SENTIMENT`)
	- current source coverage: Médias24, La Vie Éco
	- additional RSS probes completed for Aujourd'hui le Maroc, La Nouvelle Tribune, and Hespress, but they were excluded from the finance/economy set because their feeds are general-news heavy
	- L'Économiste probe returned homepage HTML/redirects rather than a usable RSS feed; defer unless an API fallback is approved
	- Finances News exposes sitemaps/HTML, not a usable RSS feed; keep it out of the RSS-first scope until a non-RSS adapter is approved
- ✅ `get_earnings_calendar` is live (`#3`) with AMMC HTML extraction path:
	- AMMC issuer pages scraped from communiqués, issuer documents, and financial-statement listings
	- normalized output includes `next_event_date`, `next_event_kind`, coverage stats, and event list
	- cache class + provider contract wired (`EARNINGS_CALENDAR`)
	- tests added for parser extraction, tool contract, and cache behavior

## Suggested Build Order

Build in this sequence for maximum recommendation-quality gain per unit of work:

1. ~~**#22** (provider refactor) — foundation, makes everything else 3× cheaper.~~ ✅ shipped on `v2`
2. ~~**#21** (DuckDB cache) — unlocks history, backtesting, and resilience.~~ ✅ shipped on `v2`
3. ~~**#1 + #2** (corporate actions + adjusted prices) — biggest data-quality fix.~~ ✅ shipped on `feat/corporate-actions-adjusted-prices`
	- ✅ Phase 1 ingestion (BC dividends write path + `scrape-bourse` CLI + tests) completed.
4. ~~**#5** (macro snapshot), **#6, #15** (FX, commodities)~~ ✅ completed.
5. ~~**#12, #19, #20** (orderflow imbalance, correlation, beta)~~ ✅ completed.
6. ~~**#13 + #14** (news + sentiment) — the thing the tape doesn't show.~~ ✅ **Phase 1 shipped on `feat/news-sentiment`**
7. ~~**#3** (earnings calendar)~~ ✅ completed; **#4** (regulatory filings) remains next for event-risk guard.
8. **#8, #9** (financial statements, peers) — deep fundamentals.
9. **#18** (backtest) — calibration layer, requires everything above.
10. **#10, #11, #17** (flows, blocks, sovereign spread) — the last mile.

The two infra items (#21, #22) are not optional — skip them and the codebase will need rewriting by tool #5 anyway. Pay the cost once, upfront.

## Design Principle

**Tools return facts, not opinions.** Every tool on this list outputs raw data or historical statistics — never a "BUY/SELL" verdict or AI-generated price target. The LLM composes recommendations *from* the tools; no tool pretends to be an analyst. See the architectural notes for the reasoning.

## Deferred Source Candidates (end-of-roadmap backlog)

- L'Économiste (current probe returns homepage HTML/redirects; no usable RSS endpoint found)
- Finances News (sitemaps/HTML available, but no usable RSS endpoint)
- Aujourd'hui le Maroc (RSS reachable but general-news heavy)
- La Nouvelle Tribune (RSS reachable but general-news heavy)
- Hespress (RSS reachable but general-news heavy)
