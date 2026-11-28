import json
from pathlib import Path

import pytest

from damn_q.runner import run_experiment


EXPERIMENTS = Path(__file__).resolve().parents[1] / "experiments"


@pytest.mark.parametrize(
    ("filename", "distances", "delay_ticks", "pairs", "mean_fidelity"),
    [
        ("field_hefei_swap.json", [0, 14.7, 10.6, 0], [0, 74, 53, 0], 30, 0.85),
        ("field_delft_eindhoven.json", [83, 19, 75, 50], [415, 95, 375, 250], 4, 1.0),
    ],
)
def test_field_preset_delivers_endpoint_pairs(filename, distances, delay_ticks, pairs, mean_fidelity):
    doc = json.loads((EXPERIMENTS / filename).read_text(encoding="utf-8"))
    assert [wire["length_km"] for wire in doc["connections"][:4]] == distances

    result = run_experiment(doc, track_flow=True)
    assert result["tick_duration_s"] == 1e-6
    source_period = 200
    first_delivery = {wire["connection"]: wire["first_delivery_tick"] for wire in result["wire_activity"]}
    for index, delay in enumerate(delay_ticks):
        assert (first_delivery[index] - delay) % source_period == 0

    measurement, = result["measurements"]
    assert measurement["captured_at"] == "delivery"
    assert measurement["all_shared_register"]
    assert measurement["pairs"] == pairs
    assert measurement["mean_fidelity"] == pytest.approx(mean_fidelity)
