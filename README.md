***DAMN-Q***
=====================
A discrete-event, modular, lossy and noisy quantum network simulator!

## Validation status

The core density-matrix simulator is covered by an assertion-based test suite (`python -m pytest`, currently 45 tests) that validates:

- **Multi-qubit register operations:** slot-aware Z/X measurement, local single-qubit depolarization, general partial-trace loss, register joining, and ownership invariants.
- **Bell-basis swapping and Pauli correction:** outcome-conditioned Bell measurement and FIFO Pauli correction producing the exact joint \(\lvert\Phi^+\rangle\!\langle\Phi^+\rvert\) state for all four Bell outcomes, plus analytic Werner-state swapping fidelity.
- **Wired three-node repeater with memories:** exact joint \(\lvert\Phi^+\rangle\!\langle\Phi^+\rvert\) endpoint state before measurement, separate X- and Z-basis correlation runs, and noisy storage-depolarization fidelity matching the analytic formula.

Please check the [Tutorial](./Tutorial.ipynb). Don't be shy!
