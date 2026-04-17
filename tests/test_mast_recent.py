from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skyminer.config import SkyMinerConfig
from skyminer.ingestion.mast_recent import fetch_recent_tic_ids


def test_fetch_recent_tic_ids_validates_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = SkyMinerConfig()

    with pytest.raises(ValueError):
        fetch_recent_tic_ids(cfg, hours=0, max_tics=10)
    with pytest.raises(ValueError):
        fetch_recent_tic_ids(cfg, hours=24, max_tics=0)


def test_fetch_recent_tic_ids_parses_tic_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = SkyMinerConfig()

    class FakeTable(list):
        colnames = ["target_name", "obs_id"]

    rows = FakeTable(
        [
            {"target_name": "TIC 123", "obs_id": "foo"},
            {"target_name": "TIC 456", "obs_id": "bar"},
            {"target_name": "not a tic", "obs_id": "TIC 789"},
        ]
    )

    class FakeObs:
        @staticmethod
        def query_criteria(**kwargs):  # type: ignore[no-untyped-def]
            assert kwargs.get("obs_collection") == "TESS"
            assert kwargs.get("dataproduct_type") == "timeseries"
            assert ("t_obs_release" in kwargs) or ("t_min" in kwargs)
            return rows

    class FakeTime:
        def __init__(self, dt):  # type: ignore[no-untyped-def]
            self.mjd = 60000.0

    res = fetch_recent_tic_ids(
        cfg,
        hours=24,
        max_tics=10,
        _now_utc=lambda: datetime(2026, 1, 2, tzinfo=timezone.utc),
        _Observations=FakeObs,
        _Time=FakeTime,
    )
    assert res.products_matched == 3
    assert res.tic_ids == ["123", "456", "789"]
