from __future__ import annotations

from skyminer.config import SkyMinerConfig
from skyminer.ingestion.tess_product_sample import _extract_tics_from_search_table


def test_extract_tics_from_search_table_parses_target_name() -> None:
    class FakeTable(list):
        colnames = ["target_name"]

    tab = FakeTable(
        [
            {"target_name": "TIC 123"},
            {"target_name": "tic 456"},
            {"target_name": "not a tic"},
        ]
    )
    assert _extract_tics_from_search_table(tab) == ["123", "456"]


def test_sample_tess_spoc_product_tic_ids_validates_inputs() -> None:
    cfg = SkyMinerConfig()
    from skyminer.ingestion.tess_product_sample import sample_tess_spoc_product_tic_ids

    try:
        sample_tess_spoc_product_tic_ids(cfg, n=0, seed=1, max_queries=1)
        assert False, "expected ValueError"
    except ValueError:
        pass

