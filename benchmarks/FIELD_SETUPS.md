# Field setups in DAMN-Q

Choose a preset from **Project** in the workbench, or run the same JSON with Python.

```sh
python -m damn_q run experiments/field_hefei_swap.json --json
python -m damn_q run experiments/field_delft_eindhoven.json --json
```

Both presets retain editable links, local quantum memories, Bell measurement, classical control, and delivery-time endpoint probes. The probes report fidelity to Φ⁺ after the correction has arrived. **Pair counts, rates, and latencies are outputs of the proxy models.** Both use 1 µs ticks, a chosen 200 µs source interval, and a fixed seed for repeatable demos. The default runs are short examples.

## Hefei optical entanglement swapping

[Sun et al., *Physical Review A* 95, 032306 (2017)](https://doi.org/10.1103/PhysRevA.95.032306) performed photonic entanglement swapping over deployed telecommunications fibre. The topology is Alice → Eve ← Bob, with a central optical Bell measurement.

| Input | Alice to Eve | Bob to Eve |
|---|---:|---:|
| Published fibre length | 14.7 km | 10.6 km |
| Reported fibre loss | 3 dB | 6 dB |
| Model transmission, ignoring other losses | 50.1% | 25.1% |
| One-way propagation in the model | 74 µs | 53 µs |

The JSON sets the attenuation coefficient to zero and puts the **total reported fibre loss** in `coupling_loss_db` so the model applies it once. The model uses the same one-way delay on the corresponding classical paths. It sets the Bell measurement visibility to the reported mean of 79.9%. In DAMN-Q this gives expected fidelity `(1 + 3V)/4 = 0.84925` under the model's ideal-or-mixed Bell measurement. The paper infers 0.849 ± 0.036 from visibility under a Werner-state assumption. The agreement in expectation follows from this calibration.

At seed 42 the 20 ms proxy run delivers 30 pairs with mean fidelity 0.850. DAMN-Q buffers arrivals and pairs surviving arms from potentially different emission times. The experiment processes coincidences from synchronized optical trials. Its pump and pair-number statistics, detector efficiency and dark counts, filtering and insertion losses, detection timing, and partial linear-optical Bell measurement are outside this proxy. Those differences rule out comparing the simulated rate with the experiment's fourfold coincidence rate.

## Delft–Eindhoven fibre route

[Avis et al., *npj Quantum Information* 9, 100 (2023), Fig. 1a](https://doi.org/10.1038/s41534-023-00765-x) studied a proposed processing-node repeater on a real Dutch fibre route. Their text reports 226.5 km in total. This preset uses the rounded labels in the figure, which sum to 227 km.

| Segment | Rounded length | Model transmission at 0.2 dB/km | Model one-way delay |
|---|---:|---:|---:|
| Delft–Utrecht (via Rotterdam) | 83 km | 2.19% | 415 µs |
| Utrecht–Nieuwegein | 19 km | 41.7% | 95 µs |
| Nieuwegein–Den Bosch | 75 km | 3.16% | 375 µs |
| Den Bosch–Eindhoven | 50 km | 10.0% | 250 µs |

Uniform attenuation is an assumption of this baseline. In the paper the end nodes send spin-photon signals to the herald stations. Here the station components send two halves of a prepared Bell pair outward, modelling independent fibre erasure and propagation in a simpler architecture. The classical memory and correction routes use the model segment sums (510 µs and 625 µs). The preset uses ideal source pairs, storage, and local operations. At seed 42 the 240 ms proxy run delivers four jointly registered Bell pairs, all with fidelity 1. This isolates fibre loss and propagation. Reproducing the processing-node study would require its hardware and protocol as well as its fidelity and rate benchmarks.

## What these exercises expose

1. **Model a herald as a detector event.** Match emitted photons by trial and apply the optical detection rule to arrivals inside the coincidence window. Include clock offset, jitter, detector efficiency and dark clicks before deciding whether a herald is true or false. DAMN-Q can already count detector coincidences downstream. The optical Bell measurement itself needs to use that timing and click information to condition the remote state.
2. **Model the source and encoding.** Add probabilistic zero-, one- and multipair emissions for photonic setups, then define how spin-photon entanglement and optical loss propagate to the stationary qubits. Add a record of detection signatures so a two-outcome optical Bell analyser is distinguishable from a four-outcome ideal Bell measurement.
3. **Compose processing-node operations.** Put communication and storage qubits on the same node with gate durations, contention, wait-for-herald and cutoff policies. Use the existing T₁/T₂ support where it matches the hardware, and add attempt-induced dephasing and correlated noise for the hardware that requires them.
4. **Compare against observables that were actually measured.** For Hefei, generate coincidence histograms, separate true and accidental heralds and compare raw and background-corrected visibility. For Delft–Eindhoven, compare matched hardware and control assumptions against the study’s simulations. Report confidence intervals across seeds and keep per-trial tracing optional for large runs.
