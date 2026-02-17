//! PredExchange Rust core - orderbook engine exposed to Python via PyO3.

use pyo3::prelude::*;
use std::collections::BTreeMap;

/// In-memory L2 orderbook: bids and asks as sorted maps (price -> size).
#[pyclass]
struct OrderbookEngine {
    market_id: String,
    asset_id: String,
    bids: BTreeMap<u64, f64>, // price in basis points (0-10000) -> size
    asks: BTreeMap<u64, f64>,
    has_snapshot: bool,
}

#[pymethods]
impl OrderbookEngine {
    #[new]
    fn new(market_id: String, asset_id: String) -> Self {
        OrderbookEngine {
            market_id,
            asset_id,
            bids: BTreeMap::new(),
            asks: BTreeMap::new(),
            has_snapshot: false,
        }
    }

    /// Apply a full snapshot: bids/asks as list of (price, size).
    fn apply_snapshot(&mut self, bids: Vec<(f64, f64)>, asks: Vec<(f64, f64)>) {
        self.bids.clear();
        self.asks.clear();
        for (p, s) in bids {
            if s >= 0.0 && p >= 0.0 && p <= 1.0 {
                self.bids.insert(price_to_key(p), s);
            }
        }
        for (p, s) in asks {
            if s >= 0.0 && p >= 0.0 && p <= 1.0 {
                self.asks.insert(price_to_key(p), s);
            }
        }
        self.has_snapshot = true;
    }

    /// Apply delta: side "BUY" or "SELL", price, size. Size 0 removes level.
    fn apply_delta(&mut self, side: &str, price: f64, size: f64) {
        if !self.has_snapshot {
            return;
        }
        let key = price_to_key(price);
        let map = if side.eq_ignore_ascii_case("BUY") {
            &mut self.bids
        } else {
            &mut self.asks
        };
        if size <= 0.0 {
            map.remove(&key);
        } else {
            map.insert(key, size);
        }
    }

    #[getter]
    fn best_bid(&self) -> Option<f64> {
        self.bids.iter().next_back().map(|(k, _)| key_to_price(*k))
    }

    #[getter]
    fn best_ask(&self) -> Option<f64> {
        self.asks.iter().next().map(|(k, _)| key_to_price(*k))
    }

    #[getter]
    fn mid_price(&self) -> Option<f64> {
        match (self.best_bid(), self.best_ask()) {
            (Some(bb), Some(ba)) => Some((bb + ba) / 2.0),
            (Some(bb), None) => Some(bb),
            (None, Some(ba)) => Some(ba),
            (None, None) => None,
        }
    }

    #[getter]
    fn has_snapshot(&self) -> bool {
        self.has_snapshot
    }
}

fn price_to_key(p: f64) -> u64 {
    (p.clamp(0.0, 1.0) * 1_000_000.0).round() as u64
}

fn key_to_price(k: u64) -> f64 {
    k as f64 / 1_000_000.0
}

/// Python module entry point.
#[pymodule]
fn predexchange_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<OrderbookEngine>()?;
    Ok(())
}
