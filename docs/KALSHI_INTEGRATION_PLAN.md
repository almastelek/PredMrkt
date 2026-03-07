# Kalshi Integration: Research & Implementation Plan

## Goal

Incorporate the Kalshi API so you can **compare and contrast identical (or equivalent) events** that exist on both Polymarket and Kalshi—e.g. same Fed decision, same election, same economic release—and see both venues’ prices side by side.

---

## 1. Is it possible?

**Yes.** Both platforms expose public (or minimally restricted) APIs that allow:

| Capability | Polymarket (current) | Kalshi |
|------------|----------------------|--------|
| List events | Gamma `GET /events` | `GET /events` (no auth for market data) |
| Event → markets | Gamma event has `markets[]` | `GET /events?with_nested_markets=true` or `GET /markets?event_ticker=...` |
| Market identifiers | `conditionId`, token (asset) IDs | `event_ticker`, `ticker` (market ticker) |
| Price history | Your ingestion (CLOB WS → `raw_events`) or CLOB `GET /prices-history` | `GET /markets/{ticker}/candlesticks` or historical endpoint |
| Live order book | CLOB WebSocket (you ingest) | `GET /markets/{ticker}/orderbook` (REST) |
| Auth for read-only | Not needed (Gamma + CLOB public) | Not needed for events/markets/orderbook/candlesticks |

**Kalshi base URL (public market data):** `https://api.elections.kalshi.com/trade-api/v2`  
*(“elections” is legacy; the API serves all categories: economics, climate, sports, etc.)*

So you can, without API keys:

- List Kalshi events and markets.
- Get orderbook and candlestick (price) history per market.
- Build a comparison layer that shows Polymarket vs Kalshi for the same real-world event.

The hard part is **matching**: there is no shared canonical ID. “Identical” has to be defined by you (see below).

---

## 2. How “identical” events can be matched

Neither Polymarket nor Kalshi exposes a common event ID. Matching has to be inferred or curated.

### Option A: Curated mapping table (recommended for MVP)

- **Table:** e.g. `event_pairs` or `canonical_events` with:
  - `polymarket_entity` (event slug or condition_id; or one market’s condition_id per “side”)
  - `kalshi_event_ticker`
  - `kalshi_market_ticker` (which market to use if the event has several)
  - Optional: `label`, `resolution_date`, `category`
- You (or an admin) add rows when you know two markets refer to the same real-world event (e.g. “Fed rate decision March 2025”, “Will X win state Y?”).
- **Pros:** Accurate, full control. **Cons:** Manual; doesn’t scale to thousands of events.

### Option B: Heuristic matching by title + date

- **Polymarket:** event `title` and `endDate` (or slug-derived date) from Gamma.
- **Kalshi:** event `title` and `strike_date` (or market `close_time`) from `GET /events`.
- Normalize titles (lowercase, strip punctuation, maybe remove common words), align dates (same day or same week), and pair events that score above a similarity threshold.
- **Pros:** Discovers pairs automatically. **Cons:** False positives/negatives; needs tuning and possibly a “confirm pair” step.

### Option C: Series / category mapping

- **Kalshi:** events have `series_ticker` (e.g. recurring “Monthly CPI”, “Fed Funds rate”).
- **Polymarket:** events have `category` and tags (from Gamma).
- Maintain a small mapping: e.g. Kalshi `series_ticker` “FEDFUNDS” ↔ Polymarket tag or slug pattern; then match by date within that series.
- **Pros:** Good for recurring events (economics, weather). **Cons:** Doesn’t help one-off or ad-hoc events; still need date/instance matching.

**Practical recommendation:** Start with **Option A** (curated pairs) so the “compare identical events” experience is correct and understandable. Add Option B or C later to suggest pairs for you to approve and insert into the mapping table.

---

## 3. Data model and storage

Your app today:

- **Polymarket:** `markets` (market_id, venue=polymarket, …), `tracked_markets`, `raw_events` (venue, market_id, asset_id, …), `last_mid`. Replay and chart endpoints are keyed by `market_id` + `asset_id` and read from `raw_events`.
- **Kalshi:** No storage yet. Markets are binary (yes/no only); no separate “asset_id”. Price can be represented as a single series (e.g. “yes” price in [0,1]).

Ways to integrate Kalshi:

1. **Extend existing tables with `venue`:**
   - `markets`: already has `venue`; use it. For Kalshi, `market_id` = Kalshi market `ticker` (e.g. `KXBTC-25DEC31-T44999`). No `condition_id`; `outcomes` can be `[{ name: "Yes", token_id: ticker }, { name: "No", token_id: ticker }]` or a single synthetic outcome.
   - `raw_events`: today only Polymarket CLOB WS writes here. Kalshi doesn’t push the same style of order book deltas; you’d either **poll** Kalshi REST (orderbook or candlesticks) and **append** rows with `venue=kalshi`, or store Kalshi in a separate table (see below).
2. **Separate Kalshi tables (simpler for a first cut):**
   - `kalshi_events`: event_ticker, series_ticker, title, strike_date, status, etc.
   - `kalshi_markets`: ticker, event_ticker, title, status, yes_bid, yes_ask, last_price, close_time, etc.
   - `kalshi_candlesticks` or `kalshi_snapshots`: time-bucketed price (e.g. open/high/low/close or mid) per market ticker, so you can serve “price from start” without calling the API on every request.
3. **Comparison / pairing:**
   - `event_pairs`: id, polymarket_market_id (or event_slug), polymarket_asset_id (optional), kalshi_event_ticker, kalshi_market_ticker, label, created_at. This is the “canonical” link for “identical” events.

Recommendation: **Separate Kalshi tables** plus **event_pairs** for pairing. Keep Polymarket ingestion and replay as-is. Add a small Kalshi client that fetches events/markets/candlesticks and fills `kalshi_*` tables; comparison API joins via `event_pairs`.

---

## 4. Implementation phases

### Phase 1: Kalshi read-only client and storage

- **Kalshi REST client** (e.g. `ingestion/kalshi/client.py` or `api/kalshi_client.py`):
  - Base URL: `https://api.elections.kalshi.com/trade-api/v2`
  - No auth for: `GET /events`, `GET /events/{event_ticker}`, `GET /markets`, `GET /markets/{ticker}`, `GET /markets/{ticker}/orderbook`, `GET /markets/{ticker}/candlesticks`.
  - Methods: `list_events()`, `get_event(event_ticker)`, `get_markets(event_ticker=...)`, `get_market(ticker)`, `get_candlesticks(ticker, start_ts, end_ts, period)`.
- **DB:**
  - `kalshi_events` and `kalshi_markets` (or one unified `kalshi_markets` with event fields denormalized).
  - Optional: `kalshi_candlesticks` for caching so comparison doesn’t hit Kalshi on every page load.
- **API (optional for Phase 1):** `GET /kalshi/events`, `GET /kalshi/markets`, `GET /kalshi/markets/{ticker}` so the frontend or you can explore Kalshi.

Deliverable: You can list Kalshi events/markets and, for any Kalshi market, get current orderbook or candlestick history from the API (or from your DB if you cache).

### Phase 2: Event pairing and comparison API

- **DB:** `event_pairs` table (see above).
- **Seeding:** Manually insert a few pairs (e.g. 2–3 Fed or CPI events you can identify on both platforms).
- **API:**
  - `GET /events/compare` — list paired events (join event_pairs with Polymarket and Kalshi metadata).
  - `GET /events/compare/{pair_id}` or `GET /events/compare?polymarket_market_id=...&kalshi_market_ticker=...` — return both sides’ time series for the same window (Polymarket from your `raw_events` replay or timeseries endpoint; Kalshi from candlesticks or your cached table).
- **Response shape:** e.g. `{ polymarket: { market_id, asset_id, series: [{t, mid}] }, kalshi: { ticker, series: [{t, yes_price}] } }` so the frontend can render two lines (or two panels) for “identical” events.

Deliverable: For each curated pair, the app shows Polymarket vs Kalshi price (or mid) over time in one view.

### Phase 3: Frontend comparison view

- **Route:** e.g. `/compare` or `/events/compare/[pairId]`.
- **UI:** List of paired events; click one → side-by-side (or overlaid) chart of Polymarket vs Kalshi price from start to now, with clear labels and legend (e.g. “Polymarket (Yes)”, “Kalshi (Yes)”).
- Optionally: from an existing Polymarket market page, “Find on Kalshi” / “Add to compare” that looks up `event_pairs` by polymarket_market_id and links to the comparison view.

Deliverable: Users can open a comparison page and see identical events compared.

### Phase 4 (later): Matching heuristics and scaling

- Implement title + date (and optionally series) similarity; suggest candidate pairs for an admin to approve and insert into `event_pairs`.
- Optionally: Kalshi WebSocket for live tick (if you need real-time comparison); or just poll candlesticks/orderbook on a timer and refresh the comparison view.

---

## 5. Technical notes

- **Kalshi market structure:** Binary only. One market = one ticker; “yes” and “no” prices (yes_ask, yes_bid, etc.). For charts, a single series (e.g. “yes” mid or last trade) is enough. No need for an `asset_id` in your schema; use `ticker` as the market key.
- **Time alignment:** Use Unix timestamps (seconds or ms) consistently. Kalshi uses seconds in many params; your app uses ms in places—normalize when building comparison series so both series share the same time axis.
- **Rate limits:** Kalshi documents rate limits; for read-only polling (events, markets, candlesticks), stay within limits and cache in your DB to avoid repeated calls for the same data.
- **Auth:** Not required for the endpoints above. If you later add trading or private endpoints, you’ll need Kalshi API keys and signed headers (separate from this plan).

---

## 6. Summary

| Question | Answer |
|----------|--------|
| Is it possible? | Yes. Both APIs support listing events/markets and price (or orderbook) data without blocking on auth for read-only. |
| What’s the main difficulty? | Matching “identical” events—no shared ID. Solve with a curated mapping table first, then optional heuristics. |
| How would it work when implemented? | (1) Kalshi client + DB for events/markets (and optionally candlesticks). (2) `event_pairs` table linking Polymarket market (or event) to Kalshi event_ticker + market ticker. (3) Comparison API that returns both venues’ price series for a pair. (4) Frontend comparison page that charts both. |

This plan keeps your existing Polymarket flow unchanged and adds Kalshi and comparison as a parallel, optional path so you can compare and contrast identical events once pairs are defined.
