import pytest

from app.briefs import analyst_narrative, brief_evidence


def test_moderation_verdict_is_not_a_brief():
    with pytest.raises(ValueError):
        analyst_narrative(
            "User Safety: safe", "nvidia/nemotron-3.5-content-safety:free"
        )


def test_incomplete_or_missing_brief_is_rejected():
    for content in (None, "", "No change detected."):
        with pytest.raises(ValueError):
            analyst_narrative(content, "general-instruct:free")
    with pytest.raises(ValueError):
        analyst_narrative("A narrative without a model identifier.", None)


def test_complete_analyst_narrative_is_retained():
    narrative = (
        "The January and February comparison produced zero disturbance candidates "
        "over the supplied study boundary. Clear optical overlap and valid radar "
        "overlap were both one hundred percent. These measurements describe this "
        "comparison only and do not establish an absence of mining. No authoritative "
        "concession boundary was supplied, so legal context remains unknown. Review "
        "the dated imagery and source acquisition records before drawing conclusions. "
        "Further comparisons can assess whether changes persist across later dates."
    )
    assert analyst_narrative(narrative, "general-instruct:free") == narrative


def test_zero_disturbance_does_not_mean_missing_study_area():
    evidence = brief_evidence(
        {
            "area_name": "Study boundary",
            "area_km2": 4.897,
            "before_start": "2025-01-01",
            "before_end": "2025-01-31",
            "after_start": "2025-02-01",
            "after_end": "2025-02-28",
            "result": {
                "candidate_count": 0,
                "area_ha": 0,
                "quality": {"clear_optical_fraction": 1.0, "radar_valid_fraction": 1.0},
                "resolution_m": 30,
                "scenes": [],
                "radar_source": "digital-earth-africa",
                "engine": "physical",
                "score_type": "uncalibrated",
                "limitations": [],
            },
        }
    )
    assert evidence["study_area"]["size_km2"] == 4.897
    assert evidence["measurements"]["candidate_disturbance_area_ha"] == 0
    assert evidence["measurements"]["clear_optical_overlap_percent"] == 100
    assert "applied" in evidence["field_definitions"]["clear_optical_overlap_percent"]
