import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest

from damn_q.server import create_server

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def workbench_url():
    server = create_server(host="127.0.0.1", port=0)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _get(url):
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read()


def _post_json(url, payload):
    body = json.dumps(payload).encode("utf-8") if not isinstance(payload, bytes) else payload
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_workbench_serves_ui_manifest_and_examples(workbench_url):
    status, ctype, html = _get(f"{workbench_url}/")
    assert status == 200
    assert "text/html" in ctype
    assert b"DAMN-Q Workbench" in html

    for asset in ("app.js", "styles.css"):
        s, _, body = _get(f"{workbench_url}/static/{asset}")
        assert s == 200
        assert len(body) > 100

    # Path traversal outside web/ must be blocked
    s_bad, _, _ = _get(f"{workbench_url}/static/../server.py")
    assert s_bad in (403, 404)

    s_man, _, raw_man = _get(f"{workbench_url}/api/manifest")
    assert s_man == 200
    man = json.loads(raw_man.decode("utf-8"))
    assert man["schema_version"] == "1.0"
    assert isinstance(man["simulator_version"], str) and man["simulator_version"]
    assert "quantum_memory" in man["components"]

    s_ex, _, raw_ex = _get(f"{workbench_url}/api/examples")
    assert s_ex == 200
    names = [e["filename"] for e in json.loads(raw_ex.decode("utf-8"))["examples"]]
    assert "repeater_ideal.json" in names
    assert "repeater_noisy_memory.json" in names
    assert "repeater_tutorial_z.json" in names


def test_workbench_validate_endpoint_reports_errors(workbench_url):
    bad_doc = {
        "schema_version": "1.0",
        "run": {"until": 10},
        "components": [
            {"id": "s", "type": "source", "params": {"delay": 1}},
            {"id": "r", "type": "classic_data_reader"},
        ],
        "connections": [
            {"from": {"component": "s", "port": "out_ch_1"}, "to": {"component": "r", "port": "input_1"}}
        ],
    }
    status, payload = _post_json(f"{workbench_url}/api/validate", bad_doc)
    assert status == 400
    assert payload["ok"] is False
    assert any("incompatible port types" in e for e in payload["errors"])

    status_malformed, payload_malformed = _post_json(f"{workbench_url}/api/run", b"{not-json")
    assert status_malformed == 400
    assert payload_malformed["ok"] is False


def test_workbench_release_gate_edit_run_export_cli_rerun_matches_analytic(workbench_url, tmp_path):
    # 1. Load ideal repeater from the workbench API
    status, _, raw_doc = _get(f"{workbench_url}/api/examples/repeater_ideal.json")
    assert status == 200
    doc = json.loads(raw_doc.decode("utf-8"))

    # 2. Edit memory noise on all four quantum memories
    noise_by_id = {
        "memory_a_1": 0.01,
        "memory_a_2": 0.02,
        "memory_b_1": 0.015,
        "memory_b_2": 0.025,
    }
    for comp in doc["components"]:
        if comp["id"] in noise_by_id:
            comp["params"]["depolarization_p"] = noise_by_id[comp["id"]]

    # 3. Validate & run via the workbench HTTP API
    v_status, v_payload = _post_json(f"{workbench_url}/api/validate", doc)
    assert v_status == 200 and v_payload["ok"] is True

    r_status, r_payload = _post_json(f"{workbench_url}/api/run", doc)
    assert r_status == 200 and r_payload["ok"] is True
    wb_res = r_payload["result"]

    # 4. Export the edited JSON and rerun via the CLI
    exported = tmp_path / "exported_repeater.json"
    exported.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "damn_q", "run", str(exported), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    cli_res = json.loads(proc.stdout)

    # 5. Workbench, CLI, and analytic fidelity must all agree
    p_mem = (0.01, 0.02, 0.015, 0.025)
    t_mem = (12, 6, 6, 12)
    prod = 1.0
    for p_i, t_i in zip(p_mem, t_mem):
        prod *= (1.0 - 4.0 * p_i / 3.0) ** t_i
    analytic_f = (1.0 + 3.0 * prod) / 4.0

    assert wb_res == cli_res
    wb_f = wb_res["measurements"][0]["mean_fidelity"]
    cli_f = cli_res["measurements"][0]["mean_fidelity"]
    assert np.isclose(wb_f, analytic_f, atol=1e-12)
    assert np.isclose(cli_f, analytic_f, atol=1e-12)

    # 6. Subsequent ideal run in the same server stays clean (1.0)
    _, _, raw_ideal = _get(f"{workbench_url}/api/examples/repeater_ideal.json")
    s_ideal, ideal_payload = _post_json(f"{workbench_url}/api/run", json.loads(raw_ideal.decode("utf-8")))
    assert s_ideal == 200
    assert np.isclose(ideal_payload["result"]["measurements"][0]["mean_fidelity"], 1.0, atol=1e-12)


def test_manifest_exposes_terminology_channels_and_hides_inactive_controls(workbench_url):
    status, _, raw = _get(f"{workbench_url}/api/manifest")
    assert status == 200
    man = json.loads(raw.decode("utf-8"))

    # Channels metadata present with Pauli error convention
    assert "quantum" in man["channels"] and "classical" in man["channels"]
    assert man["channels"]["quantum"]["label"] == "Quantum Channel"
    assert "4p/3" in man["channels"]["quantum"]["parameters"]["depolarization_p"]["description"]

    comps = man["components"]
    assert comps["entanglement_swapper"]["label"] == "Bell-State Measurement (BSM)"
    assert comps["entanglement_swapper"]["category"] == "operations"
    assert comps["orchestrator"]["label"] == "Swap Controller"
    assert comps["detector_module"]["label"] == "Qubit Arrival Monitor"
    assert comps["classic_data_reader"]["label"] == "Joint Outcome Counter"
    assert comps["endpoint_probe"]["category"] == "diagnostics"

    # Every component has a model note and every port has a display label
    for ctype, spec in comps.items():
        assert spec.get("model"), f"{ctype} missing model description"
        for pname, pspec in spec["ports"].items():
            assert pspec.get("label"), f"{ctype}.{pname} missing display label"

    # Inactive parameters are hidden from the UI while kept in schema 1.0
    assert comps["orchestrator"]["parameters"]["delay"].get("ui_hidden") is True
    assert comps["measurer"]["parameters"]["p_depolarization"].get("ui_hidden") is True
    assert comps["measurer_memory_paired"]["parameters"]["p_depolarization"].get("ui_hidden") is True
