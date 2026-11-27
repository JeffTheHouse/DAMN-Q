# Step 1 Frozen Reference Benchmark (Three-Node Quantum Repeater)

This specification freezes the Step 1 reference benchmark (`benchmarks/repeater_3node_ref.json`, runner `benchmarks/run_reference_benchmark.py`) so later milestones (N-hop chains, physical noise models, and the Bell-diagonal fast backend) and cross-simulator comparisons against NetSquid and SeQUeNCe have a fixed baseline.

## Topology and Frozen Parameters

- **Topology:** Three-node linear repeater (`A — R — B`) with midpoint Bell-pair sources (`source_a`, `source_b`), four quantum memories (`memory_a_1`, `memory_a_2`, `memory_b_1`, `memory_b_2`), a central Bell-State Measurement (`es`), a Swap Controller (`orchestrator`), Pauli Feed-Forward (`pc`), and two Endpoint State Probes (`probe_a`, `probe_b`).
- **Clock mapping:** `run.tick_duration_s = 1e-6` (1 simulation tick = 1 µs).
- **Attempt timing:** Both sources emit ideal \(\lvert\Phi^+\rangle\) pairs every \(T = 200\) ticks (200 µs; \(5{,}000\) attempts/s per elementary link).
- **Quantum channels:** Four half-links of delay \(d = 50\) ticks (50 µs \(\approx 10\) km in standard fibre at \(c/1.5 = 2\times 10^8\) m/s; 20 km per elementary link, 40 km end-to-end), per-qubit loss probability `loss_p = 0.2` (\(p_{\text{elem}} = (1 - 0.2)^2 = 0.64\) heralded elementary pairs per attempt), and per-qubit Pauli error `depolarization_p = 0.005` (\(X, Y, Z\) each with \(p/3\)).
- **Paired-memory heralding:** Classical peer-herald links of delay \(d = 50\) ticks (plus 1-tick internal herald dispatch = 51 ticks after qubit arrival).
- **Quantum memories:** Per-tick local Pauli depolarization `depolarization_p = 0.0005` per tick, `capacity = 500` (no cutoff/eviction in Step 1 baseline), `fifo = 1`.
- **Swap policy & BSM:** Swap-as-soon-as-both-ready (FIFO, `orchestrator.delay = 0`), projective BSM (`es.delay = 1` tick notification delay, `queue_capacity = 1` reject-when-busy), 50-tick classical feed-forward channels to `memory_a_1` and `pc` (`pc.delay = 0`).
- **Horizon & seeds:** `until = 40000` ticks (40 ms simulated time, 199 complete attempt cycles) across seeds `101..110`.

## Analytic Verification Equations

### Lossless baseline (`loss_p = 0`)

When every elementary attempt succeeds simultaneously on both sides:

- Middle memory storage duration: \(t_{\text{mid}} = d + 1 = 51\) ticks.
- Endpoint memory storage duration: \(t_{\text{end}} = 2d + 1 + d_{\text{swap}} = 102\) ticks.
- End-to-end delivery latency: \(L_{\text{exact}} = 3d + 1 + d_{\text{swap}} = 152\ \text{ticks} = 152\ \mu\text{s}\).
- Delivery-time fidelity to \(\lvert\Phi^+\rangle\):
  \[
  F_{\text{exact}} = \frac{1}{4}\left(1 + 3\left(1 - \frac{4 p_{\text{ch}}}{3}\right)^4 \left(1 - \frac{4 p_{\text{mem}}}{3}\right)^{2 t_{\text{mid}} + 2 t_{\text{end}}}\right) \approx 0.845409392573
  \]

### Lossy baseline (`loss_p = 0.2`)

- Elementary heralding probability per link per attempt: \(p_{\text{elem}} = (1 - 0.2)^2 = 0.64\) (expected elementary rate \(3{,}200\) pairs/s per link).
- Under swap-as-soon-as-both-ready with no cutoff, every delivered pair's latency satisfies \(L \ge L_{\text{exact}} = 152\ \mu\text{s}\) and its delivery fidelity satisfies \(F \le F_{\text{exact}}\), because waiting for the slower link adds storage depolarization ticks.

## Semantic Alignment Across Simulators (DAMN-Q vs. NetSquid vs. SeQUeNCe)

| Aspect | DAMN-Q (Step 1 Baseline) | NetSquid | SeQUeNCe | Notes for Matched Runs |
|---|---|---|---|---|
| **Time representation** | Discrete simulation ticks (`tick_duration_s = 1e-6` s) | Continuous floating-point nanoseconds | Discrete integer picoseconds | Multiply DAMN-Q ticks by `1e3` (ns) or `1e6` (ps) for exact event-time alignment. |
| **Quantum state backend** | Exact multi-qubit density matrices (`Register`) | Density matrix (`DMRepr`) or ket/stabilizer | Density matrix or Bell-diagonal (`QuantumManager`) | Match using NetSquid `DMRepr` and SeQUeNCe density-matrix manager. |
| **Pauli noise convention** | \(\mathcal{E}(\rho) = (1-p)\rho + \frac{p}{3}(X\rho X + Y\rho Y + Z\rho Z)\) | `DepolarNoiseModel`: depolarizing rate \(\gamma\) gives mixed weight \(1 - e^{-\gamma \Delta t} = 4p/3\) | Pauli error / coherence decay mapped to fidelity decay | Translate per-tick \(p\) to continuous rate via \(\gamma = -\frac{1}{\Delta t}\ln(1 - 4p/3)\). |
| **Storage decoherence** | Composed discrete-tick local Pauli depolarization on readout | Continuous-time \(T_1/T_2\) or `DepolarNoiseModel` | Exponential fidelity / \(T_2\) coherence decay | Step 1 matches depolarizing-only memory; elapsed-time \(T_1/T_2\) is added in Step 3. |
| **Heralding & BSM** | Ideal projective BSM; immediate projection + `delay`-tick notification; paired-memory `PeerHerald` with 1-tick internal dispatch + channel `delay` | Explicit optical BSM or `QuantumProcessor` gate + classical channel | Optical BSM (`BSM` + `Detector` dark counts/efficiency) + `EntanglementGenerationA/B` | Match Step 1 by setting detector efficiency = 1, dark count = 0, and classical herald delay = \(d + 1\) ticks; realistic optical heralding is added in Step 3. |
| **Fidelity capture** | Exact joint \(\lvert\Phi^+\rangle\) fidelity captured at delivery time (after classical feed-forward arrives at both endpoints, including endpoint storage noise during feed-forward), paired by `pair_id` | Captured on endpoint protocol callback after classical feed-forward arrives | Must capture at the same endpoint delivery event (including storage decoherence accrued while waiting for classical feed-forward), not at intermediate swap completion | Matched cross-simulator runs must evaluate fidelity at the same delivery event so endpoint storage decoherence during feed-forward is included identically. |
