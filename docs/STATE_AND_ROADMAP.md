# PredExchange: Current State & Improvement Ideas

Assessment of the API, web app, and backend as of the codebase review. Use this to prioritize next steps.

---

## 1. Current State Summary

### API (FastAPI)

| Area | Status |
|------|--------|
| **Endpoints** | 11 routes: health, markets list, events/stats, events/by_market (with category + sparkline), markets/{id}/asset (with title/category), timeseries, chart/series, chart/book_heatmap, sim/runs, sim/runs/{id}. |
| **Docs** | OpenAPI via FastAPI (e.g. `/docs`, `/redoc`) — not mentioned in README. |
| **CORS** | `allow_origins=["*"]` — fine for local dev; tighten for production. |
| **Auth** | None. All endpoints are public. |
| **Config** | Uses TOML (`config/default.toml`); API reads DB path, WS URL, etc. from settings. No `--profile` passed from `predex api`. |
| **Errors** | 404s return JSON where implemented (e.g. asset); not all paths validated (e.g. invalid market_id). |
| **Validation** | Query params use FastAPI `Query()`; no Pydantic response models or shared request/response schemas. |

### Web app (Next.js)

| Page | Purpose | Notes |
|------|---------|--------|
| **Home** | Top N events by live update count, category filter, sparklines, link to event detail. | Uses `events/by_market`; good use of space. |
| **Markets** | List tracked markets (title, vol, liq, category), link to chart. | Fetches `GET /markets?tracked_only=true`. |
| **Markets / [market_id]** | Event detail: orderbook depth, spread/depth chart, OFI + mid. | Fetches asset → chart/series + book_heatmap; shows title when in DB. |
| **Compare** | Overlay mid-price for 2+ markets (same time axis). | Uses `/timeseries` (not `/chart/series`); only first 30 markets in list. |
| **Sim** | List sim run IDs. | Simple list with link to detail. |
| **Sim / [id]** | Run summary (strategy, market, events, fills, PnL). | No params shown; no link to market detail. |

- **API base URL**: `NEXT_PUBLIC_API` or `http://127.0.0.1:8000` in each page.
- **Data loading**: All client-side fetch; no shared client, no React Query/SWR. Polling on Home/Markets/detail (e.g. 10s).
- **Error/loading**: Some pages show “API not running” and loading states; Compare and Sim could be more consistent.

### Backend (ingestion, storage, replay, sim)

- **Polymarket**: Gamma (discover), CLOB WebSocket (book, price_change, last_trade_price), normalize → raw_events. `prepare_polymarket_rows` expands price_change so asset_id is stored.
- **Storage**: DuckDB (raw_events, markets, tracked_markets, orderbook_snapshots, sim_runs). Schema in `storage/db.py`.
- **Replay**: Python orderbook engine (Rust optional), stream_raw_events, replay_to_chart_series, replay_to_book_snapshots, replay_to_mid_series.
- **Sim**: run_simulation (replay + strategy + touch-fill + portfolio), save_run_result, get_run_result. One strategy (mm_basic) in repo.
- **Kalshi**: Stub only (`ingestion/kalshi`).

### CLI & config

- Commands: markets (discover, list), track (start, status, stop), log (stats, export), replay run, sim run, api, tui.
- Config: `config/default.toml` (+ optional profile); README does not mention web or API startup.

### Tests

- **Present**: `tests/test_replay.py` (replay determinism), `tests/test_orderbook.py`.
- **Missing**: No API/integration tests (e.g. pytest + TestClient). No frontend or E2E tests.

---

## 2. Gaps & Improvement Areas

### Documentation and onboarding

- **README**: Does not describe the web app or how to run API + web together (e.g. `predex api --with-ingestion` and `npm run dev` in web/).
- **API**: No pointer to `/docs` or `/redoc` in README or in-app.
- **Config**: No table of env vars (e.g. `NEXT_PUBLIC_API`) or production-oriented options (CORS, DB path).

**Suggestions:** Add a “Running the stack” section (API, optional ingestion, web). Document `NEXT_PUBLIC_API` and link to OpenAPI docs. Optionally add a short “Event vs market” terminology note in README or docs.

---

### API robustness and consistency

- **404 / errors**: Some endpoints return JSON with `detail`/`message`; others may rely on FastAPI defaults. Standardize error shape (e.g. `{ "detail": "...", "code": "no_events" }`).
- **Validation**: Long or malformed `market_id`/`asset_id` could be rejected with 422 via length/format checks or Pydantic models.
- **Response models**: Introduce Pydantic response models for main endpoints so OpenAPI and clients get stable, documented shapes.
- **Profile**: `predex api` does not accept `--profile`; config is loaded without profile. Add `--profile dev` (or similar) if you use profile-based config.

**Suggestions:** Add response models for `/markets`, `/events/by_market`, `/markets/{id}/asset`, and sim runs. Optionally add a small middleware or exception handler for consistent error JSON. Add `--profile` to the API command if needed.

---

### Web app consistency and DX

- **API client**: Each page defines `API = process.env.NEXT_PUBLIC_API || '...'` and uses raw `fetch`. Duplicated error handling and no retries.
- **Compare page**: Uses `/timeseries` (mid only); could optionally use `/chart/series` for consistency with event detail (same bucketing). Also only shows first 30 markets in the list.
- **Sim detail**: Does not show `params` (strategy params are stored in DB); no link to the market’s event detail page.
- **Terminology**: “Event” used on detail page; “Market” in nav and some copy. Consider a one-line glossary or shared labels so event vs market is clear everywhere.

**Suggestions:** Extract a small `api.ts` (or similar) with `baseUrl()` and `get/post` helpers and optional error handling. Add params display and a “View event” link on Sim detail. Optionally align Compare with chart/series or document why timeseries is used.

---

### Testing

- No tests that hit the API (e.g. FastAPI TestClient + pytest).
- No frontend or E2E tests.

**Suggestions:** Add a few API tests (health, events/by_market, markets/{id}/asset 404, chart/series with a test DB). E2E can come later (e.g. Playwright) if you invest in the web app.

---

### Deployment and production readiness

- No Dockerfile or docker-compose; README does not describe deployment.
- CORS is open; for production you’d set `allow_origins` from env.
- Single process: `predex api --with-ingestion` runs API + ingestion in one process (avoids DuckDB lock). No guidance for scaling (e.g. separate ingestion worker) or backup/restore of DuckDB.

**Suggestions:** Add a minimal Dockerfile (or Compose) that runs API + optional ingestion and documents env (DB path, CORS, `NEXT_PUBLIC_API` for the frontend). Document that ingestion can run in the same process or separately.

---

### Feature and product gaps

- **Kalshi**: Stub only; no real ingestion or UI.
- **Search / filter**: Markets list is “tracked only” with no search; Home has category filter but no text search. Events/by_market could support a `category` query param to mirror the UI.
- **Event detail**: Only one asset (first outcome) is used per event; no UI to switch outcome (e.g. Yes vs No) when an event has multiple.
- **Sim**: No way to trigger a sim run from the UI; CLI only. Sim list/detail could show strategy params and link to market.
- **Export**: CLI has `predex log export` (Parquet); no export-from-UI (e.g. CSV of chart data).

**Suggestions:** Prioritize by product need: e.g. event-level API filter by category, then multi-outcome support, then “run sim” from UI or export chart data.

---

### Security and performance

- **Auth**: No auth on API; fine for local/demo. If you add sensitive data or multi-tenant use, add API keys or auth.
- **Rate limiting**: Not implemented; consider for public or shared deployments.
- **DB**: DuckDB is file-based; concurrent writers (e.g. separate ingestion process) need to be coordinated or use a single writer.

---

## 3. Suggested next steps (prioritized)

1. **Docs and onboarding**  
   - Update README: how to run API (+ optional ingestion) and web, link to `/docs`, document `NEXT_PUBLIC_API`.  
   - Low effort, high impact for new contributors and yourself.

2. **API consistency**  
   - Add Pydantic response models for 2–3 main endpoints; standardize 404/error JSON.  
   - Optional: `--profile` for API if you use it.

3. **Web: shared API client and small UX fixes**  
   - Centralize `baseUrl` and fetch; add “View event” and params on Sim detail.  
   - Optionally align Compare with chart/series or document the choice.

4. **API tests**  
   - A few tests with TestClient and a test DB (health, events/by_market, asset 404).  
   - Establishes a pattern for future tests.

5. **Deployment**  
   - Dockerfile or Compose + env table (DB, CORS, `NEXT_PUBLIC_API`).  
   - Do when you need to run the stack outside your machine.

6. **Product features**  
   - Category filter in API for events/by_market; then multi-outcome support and/or “run sim” from UI as needed.

---

## 4. Where the app stands today

- **Strengths:** Polymarket ingestion and replay are in place; event detail page (depth, spread, OFI) is solid; Home uses space and categories well; sim pipeline (replay → strategy → results) works from CLI.
- **Weaknesses:** Docs and deployment are minimal; no API or frontend tests; some inconsistency in API errors and web copy (event vs market); Compare and Sim pages are thinner than Home and event detail.

Focusing on **documentation**, **API consistency**, and a **shared API client + Sim/Compare polish** will improve day-to-day use and set you up for deployment and new features (multi-outcome, Kalshi, auth) when you need them.
