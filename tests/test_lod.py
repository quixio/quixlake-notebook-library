"""LOD math parity with the Svelte viz.store.ts."""

from __future__ import annotations

import pytest

from quixviz.lod import compute_bucket_ms, ms_to_interval, nice_ceil


class TestNiceCeil:
    @pytest.mark.parametrize(
        "n, expected",
        [
            (0.9, 1),
            (1.0, 1),
            (1.5, 2),
            (2.0, 2),
            (3.0, 5),
            (5.0, 5),
            (6.0, 10),
            (9.9, 10),
            (15, 20),
            (42, 50),
            (51, 100),
            (999, 1000),
            (0.3, 0.5),
            (0.07, 0.1),
        ],
    )
    def test_snaps_up_to_1_2_5_decade(self, n, expected):
        assert nice_ceil(n) == pytest.approx(expected)

    def test_zero_returns_min(self):
        assert nice_ceil(0) == 1


class TestComputeBucketMs:
    def test_simple_range(self):
        # 1200s range over 1200 css px at 1x dpr -> 1s per pixel, snap to 1000ms
        bucket = compute_bucket_ms(0, 1_200_000, css_width_px=1200, dpr=1.0)
        assert bucket == 1000

    def test_retina_doubles_resolution(self):
        normal = compute_bucket_ms(0, 1_200_000, css_width_px=1200, dpr=1.0)
        retina = compute_bucket_ms(0, 1_200_000, css_width_px=1200, dpr=2.0)
        assert retina <= normal

    def test_rejects_inverted_range(self):
        with pytest.raises(ValueError):
            compute_bucket_ms(1000, 500)

    def test_tiny_width_falls_back_to_default(self):
        # Width <= 10 should be treated as the default (matches the Svelte store)
        bucket_tiny = compute_bucket_ms(0, 1_200_000, css_width_px=5, dpr=1.0)
        bucket_default = compute_bucket_ms(0, 1_200_000, css_width_px=1200, dpr=1.0)
        assert bucket_tiny == bucket_default


class TestMsToInterval:
    @pytest.mark.parametrize(
        "ms, expected",
        [
            (1, "1 milliseconds"),
            (250, "250 milliseconds"),
            (1_000, "1 seconds"),
            (5_000, "5 seconds"),
            (60_000, "1 minutes"),
            (120_000, "2 minutes"),
            (3_600_000, "1 hours"),
            (86_400_000, "1 days"),
            (604_800_000, "7 days"),
        ],
    )
    def test_picks_coarsest_clean_unit(self, ms, expected):
        assert ms_to_interval(ms) == expected
