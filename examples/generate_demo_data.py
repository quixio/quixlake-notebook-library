"""Generate a dense synthetic telemetry parquet for LOD demos.

Produces `examples/demo_telemetry.parquet` with signals designed so
each zoom level reveals new structure:

  - 24-hour envelope (slow drift across the whole range)
  - 1-hour session cycles (visible when zoomed to a day)
  - 1-minute lap rhythm (visible when zoomed to an hour)
  - 1-second tick jitter + noise (visible when zoomed to a minute)

Run once; the marimo / jupyter demos point at the resulting file.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def generate(
    out: Path,
    *,
    hours: float = 24.0,
    sample_hz: float = 50.0,
    drivers: int = 3,
    seed: int = 42,
) -> Path:
    rng = np.random.default_rng(seed)

    n = int(hours * 3600 * sample_hz)
    # Anchor the dataset at a fixed wall-clock so the demo is reproducible.
    start_ms = int(pd.Timestamp("2026-04-01T00:00:00Z").value // 1_000_000)
    step_ms = 1000.0 / sample_hz
    t_ms = start_ms + np.arange(n, dtype=np.float64) * step_ms

    # Seconds since start, used as the argument to every sinusoid.
    t_s = (t_ms - start_ms) / 1000.0

    def layered(amp24h, amp1h, amp1m, amp1s, noise_sd, baseline):
        return (
            baseline
            + amp24h * np.sin(2 * np.pi * t_s / (24 * 3600))
            + amp1h * np.sin(2 * np.pi * t_s / 3600)
            + amp1m * np.sin(2 * np.pi * t_s / 60)
            + amp1s * np.sin(2 * np.pi * t_s / 1.0)
            + rng.normal(0, noise_sd, n)
        )

    speed = np.clip(layered(60, 40, 25, 8, 2.5, 130), 0, 320)
    rpm = np.clip(layered(1500, 2000, 1200, 400, 80, 6500), 800, 13000)
    throttle = np.clip(layered(0.15, 0.2, 0.25, 0.1, 0.03, 0.55), 0, 1)
    g_lat = layered(0.3, 0.6, 1.2, 0.4, 0.08, 0.0)

    # Rotate drivers through the day so group_by has something to split on.
    driver_ids = [f"driver_{i+1}" for i in range(drivers)]
    bucket = (t_s // (hours * 3600 / drivers)).astype(np.int64)
    driver = np.array(driver_ids, dtype=object)[np.clip(bucket, 0, drivers - 1)]

    df = pd.DataFrame({
        "timestamp_ms": t_ms.astype(np.int64),
        "driver_id": driver,
        "speedKmh": speed.astype(np.float32),
        "rpm": rpm.astype(np.float32),
        "throttle": throttle.astype(np.float32),
        "gForceLateral": g_lat.astype(np.float32),
    })

    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)

    span_h = (t_ms[-1] - t_ms[0]) / 3_600_000
    size_mb = out.stat().st_size / (1024 * 1024)
    print(
        f"Wrote {len(df):,} rows spanning {span_h:.2f}h across "
        f"{drivers} drivers -> {out} ({size_mb:.1f} MB)"
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent / "demo_telemetry.parquet",
    )
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--hz", type=float, default=50.0, dest="sample_hz")
    parser.add_argument("--drivers", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    generate(
        args.out,
        hours=args.hours,
        sample_hz=args.sample_hz,
        drivers=args.drivers,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
