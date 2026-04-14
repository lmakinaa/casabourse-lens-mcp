# CA Ingestion — Phase 1 Progress

Tracks implementation of the Bourse de Casablanca dividends ingestion pipeline
(plan: `~/.claude/plans/jolly-wishing-unicorn.md`).

Goal: close the corporate-actions write path so `get_adjusted_price_history`
returns real back-adjusted bars instead of unadjusted data with a "no source"
warning.

---

## Done

- [x] **Dependencies** — `httpx>=0.28`, `tenacity>=9.0`, `certifi>=2024.2.2`
  pinned in [requirements.txt](requirements.txt); installed in `.venv`.

- [x] **TLS fix** — `api.casablanca-bourse.com` serves only the leaf cert (no
  intermediate). Bundled the Sectigo R36 intermediate under
  [ingestion/http/ca_extras/](ingestion/http/ca_extras/) and load it alongside
  certifi in `PoliteClient`. Verified against production: 200 OK, 823 dividend
  records, pagination works.

- [x] **`ingestion/http/client.py`** — `PoliteClient`:
  - Certifi + pinned intermediates for TLS (`verify=SSLContext`, never
    `verify=False`)
  - Per-host throttle via `threading.Lock` + `time.monotonic()`
  - Retry via `tenacity`: exp backoff (1→8s), 3 attempts, retries only on 5xx
    and transport errors (4xx raises immediately — 404 is not transient)
  - `follow_redirects=True` (BC redirects `/api/...` → `/fr/api/...`)
  - Structured logs per request: `{url, status, duration_ms}`
  - Context-manager API (`__enter__` / `__exit__` / `close`)

- [x] **`ingestion/agents/base.py`** — `BaseAgent` ABC with `SOURCE`,
  `CONFIDENCE` class attrs and abstract `run(since, until) -> Iterator[...]`.
  Docstring explains why `ManualAgent` intentionally doesn't inherit.

- [x] **`ingestion/mappings/issuer_symbols.json`** — 94-entry name→ticker map,
  seeded from a live BC scrape cross-referenced with WafaBourse `Libelle`.
  Handles name variants (e.g. `ITISSALAT AL-MAGHRIB` / `ITISSALAT AL MAGHRIB`
  both → `IAM`). Keys normalized to uppercase with collapsed whitespace.

- [x] **`ingestion/agents/bourse_casa.py`** — `BourseCasaAgent`:
  - Hits `/fr/api/emetteurs/dividendes`
  - Parses `"Dividendes (ISSUER) - YYYY"` → issuer → ticker via lookup map
  - Filters client-side on `dateDetachement ∈ [since, until]`
  - Emits `CandidateObservation(EventType.DIVIDEND, source="bourse_casablanca",
    confidence=OPERATIONAL, source_ref="bc_tid=<n>")`
  - Pagination follows `links.next` (supports both string + `{href:...}` forms)
  - Logs and skips records with unknown issuer, missing/bad ex_date, or bad
    amount rather than raising

- [x] **`ingestion/agents/__init__.py`** — re-exports `BaseAgent`,
  `BourseCasaAgent`, `load_issuer_map`, `ManualAgent`.

- [x] **`ingestion/cli.py`** — `scrape-bourse` subparser added (argument
  parsing + main dispatch). Wires `--since`, `--until`, `--dry-run`,
  `--user-agent`, `--min-interval`.

---

## Left to finish Phase 1

### 1. CLI command handler — the `_cmd_scrape_bourse` function itself
The subparser is in place and `main()` dispatches to
`_cmd_scrape_bourse(store, args)`, but the function body doesn't exist yet.
Needs to:
- Parse `--since` / `--until` as ISO dates (default until = today)
- Instantiate `PoliteClient(user_agent=..., min_interval=...)`
- Instantiate `BourseCasaAgent(client)`
- Collect observations from `agent.run(since, until)`
- If `--dry-run`: print observations as JSON, skip the pipeline
- Otherwise: `IngestionPipeline(store).ingest(observations)` and print the
  `IngestionResult` (same JSON shape as `record` / `record-file`)
- Exit code 0 if `result.rejected == []` else 1
- Close the `PoliteClient` (context manager) regardless of outcome

### 2. Tests — nothing is written yet

- **`tests/test_ingestion_http_client.py`**
  - Retry behavior with `httpx.MockTransport` (5xx retries, 4xx does not)
  - Rate-limit pacing with monkeypatched `time.monotonic` + `time.sleep` spy
  - TLS: verify `ssl.SSLContext` is configured (not `verify=False`)
  - Extra-CA loading: put a PEM in ca_extras, confirm it's added to the
    trust store (inspect `SSLContext.get_ca_certs()`)

- **`tests/test_bourse_casa_agent.py`**
  - Use a `FakeClient` that returns canned JSON:API responses (2 pages
    chained via `links.next`)
  - Assertions:
    - Known issuer → 1 observation emitted with correct `symbol`, `ex_date`,
      `amount`, `source`, `confidence`, `source_ref`
    - Unknown issuer → skipped, logged, not yielded
    - `dateDetachement` outside window → skipped
    - Malformed `montantDividende` → skipped, logged
    - Pagination: agent consumes both pages and yields the union
    - Idempotent `observation_hash`: running `.run()` twice yields
      hash-equal observations

- **`tests/fixtures/ingestion/bc_dividendes_page1.json`,
  `bc_dividendes_page2.json`** — committed fixtures captured from a real
  two-page slice of the BC API (strip PII if any; it's public data so none
  expected)

- **`tests/test_cli_scrape.py`** — end-to-end:
  - Monkeypatch `PoliteClient.get_json` to return canned fixtures
  - Run `cli.main(["--db", tmp, "scrape-bourse", "--since", "2024-01-01"])`
  - Assert store has N rows, `show` returns reconciled events,
    `coverage` reports `bourse_casablanca` present
  - Run the command twice → second run's `accepted == 0` (idempotency)

### 3. Verification against production

- `python -m ingestion scrape-bourse --since 2024-01-01 --dry-run` — inspect
  JSON output, confirm the rows look sane
- `python -m ingestion scrape-bourse --since 2015-01-01 --db /tmp/ca_test.sqlite`
  — full backfill run, ~823 observations
- `python -m ingestion show --db /tmp/ca_test.sqlite --symbol ATW` — confirm
  reconciled ATW dividends appear with `winning_source="bourse_casablanca"`
- Through the MCP tool:
  ```python
  t = TradingTools(..., corporate_actions=svc_with_populated_store)
  t.execute_tool('get_adjusted_price_history', {'symbol': 'ATW', 'days': 400})
  ```
  Must show `adjustments_applied` populated with real dividends.

### 4. Regression gate

- `./scripts/test-both-branches.sh` — cross-branch contract tests still green
- `.venv/bin/python -m pytest tests/ -q` — 98 existing tests + new ingestion
  tests all pass

### 5. Docs

- README: add one-liner cron example for the containerized worker the user
  will set up separately. No scheduler code in this PR.

---

## Explicitly out of scope (Phase 2+)

- **AMMC agent** — HTML listing + PDF extraction. Required eventually as
  the authoritative source for dividend `amount` and the only structured
  source for splits.
- **Capital increases** — BC's `/api/emetteurs/augmentation-capital` is
  available but `adjuster.py` v1 only adjusts DIVIDEND + SPLIT. Wire this
  when the adjuster grows support.
- **Splits** — not in BC's API at all. Manual entry until Phase 2 AMMC.
- **Scheduler** — user will containerize; we ship only the CLI.

---

## Key files touched

| File | Status |
|---|---|
| [requirements.txt](requirements.txt) | modified |
| [ingestion/http/__init__.py](ingestion/http/__init__.py) | NEW |
| [ingestion/http/client.py](ingestion/http/client.py) | NEW |
| [ingestion/http/ca_extras/sectigo_public_server_auth_ca_dv_r36.pem](ingestion/http/ca_extras/sectigo_public_server_auth_ca_dv_r36.pem) | NEW |
| [ingestion/agents/base.py](ingestion/agents/base.py) | NEW |
| [ingestion/agents/bourse_casa.py](ingestion/agents/bourse_casa.py) | NEW |
| [ingestion/agents/__init__.py](ingestion/agents/__init__.py) | extended |
| [ingestion/mappings/issuer_symbols.json](ingestion/mappings/issuer_symbols.json) | NEW |
| [ingestion/cli.py](ingestion/cli.py) | subparser added; **handler body still TODO** |
| `tests/test_ingestion_http_client.py` | TODO |
| `tests/test_bourse_casa_agent.py` | TODO |
| `tests/fixtures/ingestion/bc_dividendes_page{1,2}.json` | TODO |
| `tests/test_cli_scrape.py` | TODO |
