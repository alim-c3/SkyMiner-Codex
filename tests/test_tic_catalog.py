from __future__ import annotations

import uuid
from pathlib import Path

from skyminer.config import SkyMinerConfig
from skyminer.ingestion.tic_catalog import TicSampleResult, load_or_create_tic_sample


def test_load_or_create_tic_sample_uses_cache(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    cfg = SkyMinerConfig()

    scratch = Path.home() / "skyminer_test_tmp" / "tic_cache"
    scratch.mkdir(parents=True, exist_ok=True)
    cache_path = scratch / f"tic_sample_{uuid.uuid4().hex}.json"

    created = TicSampleResult(
        generated_at_utc="2026-01-01T00:00:00Z",
        seed=123,
        requested_n=3,
        returned_n=3,
        tmag_max=12.0,
        cone_radius_deg=0.35,
        max_query_points=10,
        tic_ids=["1", "2", "3"],
    )

    # Force the create path once by patching the sampler.
    import skyminer.ingestion.tic_catalog as tc

    monkeypatch.setattr(tc, "sample_tic_ids_public", lambda *a, **k: created)
    res1 = load_or_create_tic_sample(
        cfg,
        n=3,
        seed=123,
        tmag_max=12.0,
        cone_radius_deg=0.35,
        max_query_points=10,
        cache_path=cache_path,
    )
    assert res1.tic_ids == ["1", "2", "3"]

    # Now ensure it uses the cache and does not call the sampler.
    monkeypatch.setattr(tc, "sample_tic_ids_public", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("should not run")))
    res2 = load_or_create_tic_sample(
        cfg,
        n=3,
        seed=123,
        tmag_max=12.0,
        cone_radius_deg=0.35,
        max_query_points=10,
        cache_path=cache_path,
    )
    assert res2.tic_ids == ["1", "2", "3"]

