"""Build the JSON source bundle consumed by `damn_q/web/pyodide_worker.js`.

Usage:
    python -m damn_q.web_bundle --out damn_q_bundle.json
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Core simulator modules at repo root + all damn_q package modules
_ROOT_MODULES = (
    "Channels.py",
    "Detector.py",
    "Emitter.py",
    "Entanglement_Swapping.py",
    "Memory.py",
    "Operators.py",
    "Orchestrator.py",
    "Pauli_correction.py",
    "Qubits.py",
    "Scheduler.py",
    "Signals.py",
    "Simulation.py",
    "States.py",
    "endpoint_probe.py",
    "measure.py",
)


def build_pyodide_bundle(root: Path = ROOT) -> dict:
    """Return a mapping of relative POSIX paths -> UTF-8 Python source strings."""
    root = Path(root)
    files = {}
    for name in _ROOT_MODULES:
        p = root / name
        if p.is_file():
            files[name] = p.read_text(encoding="utf-8")
    pkg_dir = root / "damn_q"
    for p in sorted(pkg_dir.glob("*.py")):
        files[f"damn_q/{p.name}"] = p.read_text(encoding="utf-8")
    return files


def write_pyodide_bundle(output_path: Path, root: Path = ROOT) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bundle = build_pyodide_bundle(root=root)
    output_path.write_text(json.dumps(bundle), encoding="utf-8")
    return output_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build DAMN-Q Pyodide worker bundle JSON.")
    parser.add_argument("--out", default="damn_q_bundle.json", help="Output JSON path (default: damn_q_bundle.json).")
    args = parser.parse_args(argv)
    out = write_pyodide_bundle(Path(args.out))
    print(f"Wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
