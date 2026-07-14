"""Guard: every knob that changes detector output must reach detector_config().

The config is hashed into each proposal run's provenance, so an omitted knob
would let two genuinely different detector runs share a hash — and stale or
mock-derived proposals could then masquerade as a fresh real run.
"""

import inspect

from pipeline import ingest

# Params that carry data rather than tune behaviour — they cannot change what
# the detector does for a given video, so they are not provenance knobs.
NON_TUNING = {"source", "audio_peaks", "scene_cuts", "motion_peaks"}


def _tunables(func, prefix: str = "") -> set[str]:
    return {
        f"{prefix}{name}"
        for name, param in inspect.signature(func).parameters.items()
        if param.default is not inspect.Parameter.empty and name not in NON_TUNING
    }


def test_every_detector_knob_is_in_the_provenance_config():
    config = ingest.detector_config()

    knobs = (
        _tunables(ingest.detect_audio_peaks, "audio_")
        | _tunables(ingest.detect_motion_peaks, "motion_")
        | _tunables(ingest.detect_scene_cuts, "scene_")
        | _tunables(ingest.build_candidate_windows)
    )

    missing = knobs - set(config)
    assert not missing, (
        f"detector knob(s) {sorted(missing)} never reach detector_config(). Add "
        "them and bump DETECTOR_VERSION, or two different runs will share a "
        "provenance hash."
    )


def test_config_carries_a_detector_version():
    assert ingest.detector_config()["detector_version"] == ingest.DETECTOR_VERSION
    assert isinstance(ingest.DETECTOR_VERSION, str) and ingest.DETECTOR_VERSION
