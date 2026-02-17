"""Export raw events to Parquet."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def export_events_to_parquet(
    conn: DuckDBPyConnection,
    output_path: str | Path,
    market_id: str | None = None,
) -> int:
    """Export raw_events to a Parquet file. Optional filter by market_id. Returns row count."""
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path_str = str(path).replace("\\", "\\\\")
    if market_id:
        conn.execute(
            f"COPY (SELECT * FROM raw_events WHERE market_id = ?) TO '{path_str}' (FORMAT PARQUET)",
            [market_id],
        )
        count = conn.execute("SELECT COUNT(*) FROM raw_events WHERE market_id = ?", [market_id]).fetchone()[0]
    else:
        conn.execute(
            f"COPY (SELECT * FROM raw_events) TO '{path_str}' (FORMAT PARQUET)",
        )
        count = conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
    return count
