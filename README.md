***DAMN-Q***
=====================
An open-source discrete-event simulator and browser workbench for composing quantum network experiments, with density-matrix simulation and validated three-node repeater examples.

## Quick start

Requirements: Python 3, NumPy, and pytest (for the test suite).

```powershell
pip install numpy pytest
python -m pytest                       # run the validation test suite
```

### Run an experiment from the command line

```powershell
python -m damn_q validate experiments/repeater_ideal.json
python -m damn_q run experiments/repeater_ideal.json
python -m damn_q run experiments/repeater_noisy_memory.json --seed 7 --json
python -m damn_q manifest              # component & channel manifest as JSON
```

### Open the browser workbench

```powershell
python -m damn_q serve                 # http://127.0.0.1:8000/
python -m damn_q serve --port 8765 --no-browser
```

The workbench edits the same versioned JSON experiment graph and executes it through the same validator and runner as the CLI. Use **Import JSON** / **Export JSON** to move experiments between the browser and the command line.

## Component reference

Public labels, categories, ports, and units are defined in `damn_q/manifest.py`. Schema keys (`type` and port IDs) are kept stable for `schema_version: "1.0"` JSON compatibility.

| Workbench label | Category | Schema `type` | Model |
|---|---|---|---|
| **Quantum State Source** | Sources | `source` | Ideal state preparation (\(\lvert0\rangle\) or \(\lvert\Phi^+\rangle\)) |
| **Quantum Memory** | Memories | `quantum_memory` | Slot-based memory with local per-tick Pauli depolarization |
| **Bell-State Measurement (BSM)** | Operations | `entanglement_swapper` | Ideal projective Bell-basis measurement |
| **Qubit Measurement (X/Z)** | Operations | `measurer` | Ideal projective single-qubit measurement in X or Z basis |
| **Swap Controller** | Controllers | `orchestrator` | Matches ready slots from two memories and requests readout |
| **Pauli Feed-Forward** | Controllers | `pauli_corrector` | Applies \(X\) and \(Z\) Pauli corrections from the Bell outcome |
| **Swap-Triggered Memory Measurement** | Controllers | `measurer_memory_paired` | Requests memory readout on Bell outcome, then measures in X or Z basis |
| **Joint Outcome Counter** | Diagnostics | `classic_data_reader` | Pairs two classical outcome streams by arrival order (`00`/`01`/`10`/`11`) |
| **Qubit Arrival Monitor** | Diagnostics | `detector_module` | Counts arrivals and forwards only qubits in \(4\times 4\) (two-qubit) registers |
| **Endpoint State Probe** | Diagnostics | `endpoint_probe` | Retains arriving qubit handles for run-end density-matrix inspection |

Connections model either a **Quantum Channel** (`delay`, `loss_p`, `depolarization_p`) or a **Classical Channel** (`delay` only).

### Noise and timing conventions

- **Time units:** all delays and horizons are in **simulation ticks**.
- **Pauli depolarization (`depolarization_p`):** total probability \(p\) of applying \(X\), \(Y\), or \(Z\) (\(p/3\) each), corresponding to a maximally mixed weight of \(4p/3\): \(\mathcal{E}(\rho) = (1 - p)\rho + \frac{p}{3}(X\rho X + Y\rho Y + Z\rho Z)\).
- **Operation time vs. output latency:** Bell-State Measurement, Qubit Measurement, and Pauli Feed-Forward apply their quantum operation immediately on arrival and delay only the emitted classical outcome or corrected qubit.

## Built-in experiments

Examples live in `experiments/` (`schema_version: "1.0"`):

| File | Description | Reference result |
|---|---|---|
| `repeater_ideal.json` | Ideal three-node repeater | Mean simulated fidelity to \(\lvert\Phi^+\rangle\) (run-end): `1.0` |
| `repeater_noisy_memory.json` | Same topology, storage Pauli error \(p = (0.01, 0.02, 0.015, 0.025)\) per tick | Mean simulated fidelity to \(\lvert\Phi^+\rangle\) (run-end): `0.5701501371007607` |
| `repeater_tutorial_z.json` | Z-basis tutorial counts (`seed: 1234`, `until: 100`) | Joint Outcome Counter: `00: 39`, `01: 0`, `10: 0`, `11: 44` |

The noisy repeater fidelity matches the analytic formula \(F = \tfrac{1}{4}\bigl(1 + 3\prod_i (1 - \tfrac{4p_i}{3})^{t_i}\bigr)\) for storage durations \(t = (12, 6, 6, 12)\) simulation ticks.

## Simulator design

- **Per-run `Simulation`** (`Simulation.py`): owns the clock, heap event queue, random stream, and link IDs. Components accept an optional `sim=` argument (defaulting to the process-wide instance). Two simulations in one process do not interfere, and cross-simulation wiring is rejected.
- **Density-matrix register** (`Qubits.py`): multi-qubit `Register` with ownership invariants and exact single-qubit depolarization, partial-trace loss, projective Z/X measurement, and Bell-basis measurement.
- **Memory slots** (`Memory.py`, `Signals.py`): memories announce `Ready(slot_id)` and controllers reply with `Release(slot_id)` (bare untagged requests retain legacy FIFO/LIFO behavior). Releases for evicted slots are no-ops.
- **Bounded monitoring** (`Detector_module.py`): arrival counters run in \(O(1)\) memory by default; handle retention is opt-in with `trace: 1`.

## Validation status

`python -m pytest` covers:

- **Register and channel operations:** slot-aware Z/X measurement, local single-qubit depolarization, general partial-trace loss, register joining, and ownership invariants.
- **Bell-state measurement and Pauli feed-forward:** exact joint \(\lvert\Phi^+\rangle\!\langle\Phi^+\rvert\) output for all four Bell outcomes, plus analytic swapping fidelity for \(\Phi^+\)-isotropic (Bell-diagonal) input states.
- **Wired three-node repeater:** exact joint \(\lvert\Phi^+\rangle\!\langle\Phi^+\rvert\) endpoint state before measurement, separate X-basis and Z-basis correlation runs, and noisy storage-depolarization fidelity matching the analytic formula.
- **Core hygiene, CLI, and workbench:** per-run simulation isolation, cross-simulation wiring rejection, FIFO/LIFO eviction tombstones, bounded arrival monitor counters, static graph validation, and the end-to-end release gate (edit memory noise in the workbench, export JSON, rerun via CLI, and match the analytic fidelity).

Please check the [Tutorial](./Tutorial.ipynb) and the lossy-link example in [Tutorial_lossy.ipynb](./Tutorial_lossy.ipynb).

## License

MIT. See [LICENSE](./LICENSE).
