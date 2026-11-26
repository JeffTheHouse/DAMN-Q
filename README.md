***DAMN-Q***
=====================
A discrete-event, modular, lossy and noisy quantum network simulator.

## Quick start

Requirements: Python 3, NumPy, and pytest (for the test suite).

```powershell
pip install numpy pytest
python -m pytest                       # run the 66-test validation suite
```

### Run an experiment from the command line

```powershell
python -m damn_q validate experiments/repeater_ideal.json
python -m damn_q run experiments/repeater_ideal.json
python -m damn_q run experiments/repeater_noisy_memory.json --seed 7 --json
python -m damn_q manifest              # component types, ports, and parameters
```

### Open the browser workbench

```powershell
python -m damn_q serve                 # http://127.0.0.1:8000/
python -m damn_q serve --port 8765 --no-browser
```

The workbench is a local page that edits the same JSON experiment format and runs it through the same validator and runner as the CLI. Use **Import JSON** / **Export JSON** to move experiments between the two.

## Experiment format

Experiments are versioned JSON documents (`"schema_version": "1.0"`) with a `run` block (`until`, `seed`), `components` (typed, with parameters), `connections` (typed ports, with `delay`, `loss_p`, and `depolarization_p` for quantum links), and `measurements` (e.g. `bell_fidelity` between two `endpoint_probe` nodes). Invalid graphs are rejected before any event runs. See `damn_q/manifest.py` for the component catalogue and `damn_q/schema.py` for the validation rules.

Built-in examples in `experiments/`:

| File | Description | Bell fidelity |
|---|---|---|
| `repeater_ideal.json` | Ideal three-node repeater | `1.0` |
| `repeater_noisy_memory.json` | Same topology, memory depolarization `(0.01, 0.02, 0.015, 0.025)` | `0.5701501371007607` |
| `repeater_tutorial_z.json` | Z-basis tutorial counts (seed 1234, until 100) | `00: 39`, `11: 44` |

The noisy value matches the analytic formula \(F = \tfrac{1}{4}\bigl(1 + 3\prod_i (1 - \tfrac{4p_i}{3})^{t_i}\bigr)\) with storage times \(t = (12, 6, 6, 12)\).

## Simulator design

- **Per-run `Simulation`** (`Simulation.py`): owns the clock, event queue, random stream, and link IDs. Components take an optional `sim=` argument; omitting it uses the process-wide default. Two simulations in one process do not interfere, and cross-simulation wiring is rejected.
- **Quantum state:** density matrices over a multi-qubit `Register` with ownership invariants. Depolarizing, loss, and Bell-measurement channels are exact.
- **Memories:** slot-based with FIFO or LIFO readout. Readiness is announced as `Ready(slot_id)`, and controllers release exact slots with `Release(slot_id)`. A bare untagged request keeps the legacy FIFO/LIFO behavior. Releases for evicted slots are no-ops.
- **Detectors:** streaming counters by default; qubit traces are opt-in with `trace: 1`.

## Validation status

- **Test suite:** `python -m pytest` runs 66 tests covering the scheduler, channels, register ownership, Bell swapping and Pauli correction, memory slot lifecycle and stale-release handling, storage noise, the simulation container, the experiment validator, the CLI, and the workbench server (including the release gate: edit memory noise in the workbench, export, rerun via the CLI, and compare with the analytic fidelity).
- **Analytic checks:** the wired repeater produces the exact \(\lvert\Phi^+\rangle\!\langle\Phi^+\rvert\) endpoint state in both Z and X basis runs, and the noisy repeater matches the storage-depolarization formula above.

Please check the [Tutorial](./Tutorial.ipynb). The lossy-link example is in [Tutorial_lossy.ipynb](./Tutorial_lossy.ipynb).

## License

MIT. See [LICENSE](./LICENSE).
