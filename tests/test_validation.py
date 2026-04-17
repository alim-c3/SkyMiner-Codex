from skyminer.config import SkyMinerConfig
from skyminer.models.schemas import Candidate, SkyCoordLike, ValidationResult
from skyminer.validation.catalogs import CatalogValidator


def test_validation_unknown_when_missing_coord() -> None:
    cfg = SkyMinerConfig()
    v = CatalogValidator(cfg)
    cand = Candidate(candidate_id=Candidate.build_id("local_sample", "t"), target_id="t", source="local_sample")
    res = v.validate(cand)
    assert res.status == "unknown"


def test_validation_uses_mocked_queries(monkeypatch) -> None:
    cfg = SkyMinerConfig()
    v = CatalogValidator(cfg)
    cand = Candidate(
        candidate_id=Candidate.build_id("tess", "t"),
        target_id="t",
        source="tess",
        coord=SkyCoordLike(ra_deg=10.0, dec_deg=20.0),
    )

    def fake_simbad(_cand):
        return {"matched": True, "main_id": "FakeStar", "otype": "V*", "separation_arcsec": None}

    def fake_vizier(_cand):
        return {"matched": False}

    monkeypatch.setattr(v, "_query_simbad", fake_simbad)
    monkeypatch.setattr(v, "_query_vizier", fake_vizier)
    res = v._validate_live(cand)
    assert res.status == "known_classified"
    assert res.matched_name == "FakeStar"
