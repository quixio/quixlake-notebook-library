"""Level-of-detail math: picks a bucket size from visible pixels.

Ported from quix-ts-datalake-ui/svelte-app/src/lib/stores/viz.store.ts.
Keeping the behaviour identical so users get the same bucket choices as
the Svelte UI for a given zoom/width.
"""

from __future__ import annotations

import math

DEFAULT_CSS_WIDTH_PX = 1200
MIN_BUCKET_MS = 1


def nice_ceil(n: float) -> float:
    """Round up to the next 1·10^k, 2·10^k, or 5·10^k.

    Snapping to these "nice" values means sub-pixel zoom/pan nudges don't
    re-issue a query for a slightly different bucket size.
    """
    if n <= 0:
        return MIN_BUCKET_MS
    pow10 = 10 ** math.floor(math.log10(n))
    frac = n / pow10
    if frac <= 1:
        nice = 1
    elif frac <= 2:
        nice = 2
    elif frac <= 5:
        nice = 5
    else:
        nice = 10
    return nice * pow10


def compute_bucket_ms(
    x_min: float,
    x_max: float,
    css_width_px: int = DEFAULT_CSS_WIDTH_PX,
    dpr: float = 1.0,
) -> float:
    """Pick a bucket size (in ms) for the visible window.

    Target: ~1 bucket per physical pixel. `dpr` lets retina displays
    double the bucket count.
    """
    if x_max <= x_min:
        raise ValueError("x_max must be greater than x_min")
    if css_width_px <= 10:
        css_width_px = DEFAULT_CSS_WIDTH_PX
    if dpr <= 0:
        dpr = 1.0
    physical = css_width_px * dpr
    ideal = (x_max - x_min) / physical
    return max(MIN_BUCKET_MS, nice_ceil(ideal))


def ms_to_interval(ms: float) -> str:
    """Convert a bucket size in ms to a DuckDB INTERVAL literal body.

    Chooses the coarsest clean unit so the generated SQL is readable.
    """
    ms = max(1, int(round(ms)))
    if ms >= 1000 and ms % 1000 == 0:
        s = ms // 1000
        if s >= 60 and s % 60 == 0:
            m = s // 60
            if m >= 60 and m % 60 == 0:
                h = m // 60
                if h >= 24 and h % 24 == 0:
                    d = h // 24
                    return f"{d} days"
                return f"{h} hours"
            return f"{m} minutes"
        return f"{s} seconds"
    return f"{ms} milliseconds"
