# predexchange-core

Rust extension for PredExchange orderbook engine. Build with:

```bash
pip install maturin
maturin develop
```

Then the Python package will use the Rust orderbook when available; otherwise it falls back to the pure-Python engine.
