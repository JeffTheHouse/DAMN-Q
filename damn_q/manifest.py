"""Component and channel manifest shared by validation, the runner, and the browser UI.

Schema keys (component types, port names, and parameter keys) are kept stable
for schema 1.0 JSON compatibility, while display labels, categories, units,
and model descriptions serve as the single source of public terminology.
"""

MANIFEST_VERSION = "1.0"

CHANNEL_MANIFEST = {
    "quantum": {
        "label": "Quantum Channel",
        "parameters": {
            "delay": {
                "label": "Propagation delay",
                "unit": "simulation ticks",
                "description": "Transmission latency in simulation ticks.",
            },
            "loss_p": {
                "label": "Qubit loss probability per transmission",
                "unit": "[0, 1]",
                "description": "Probability that a transmitted qubit is lost (traced out of its register).",
            },
            "depolarization_p": {
                "label": "Pauli error probability per transmission",
                "unit": "[0, 1]",
                "description": (
                    "Total probability p of applying X, Y, or Z (each with probability p/3; "
                    "no error with probability 1 - p)."
                ),
            },
            "length_km": {
                "label": "Fibre length",
                "unit": "km",
                "description": (
                    "Optional fibre length. Adds propagation delay length/200000 km/s (rounded to whole "
                    "ticks; requires run.tick_duration_s) and attenuation loss. 0 disables fibre effects."
                ),
            },
            "attenuation_db_per_km": {
                "label": "Fibre attenuation",
                "unit": "dB/km",
                "description": "Fibre attenuation alpha; loss = 1 - 10^(-(alpha*L + coupling)/10). Default 0.2 dB/km.",
            },
            "coupling_loss_db": {
                "label": "Coupling loss",
                "unit": "dB",
                "description": "Fixed loss per fibre link (connector and coupling), independent of length.",
            },
        },
    },
    "classical": {
        "label": "Classical Channel",
        "parameters": {
            "delay": {
                "label": "Propagation delay",
                "unit": "simulation ticks",
                "description": "Classical message latency in simulation ticks.",
            },
        },
    },
}

COMPONENT_MANIFEST = {
    "source": {
        "label": "Quantum State Source",
        "category": "sources",
        "model": "Ideal state preparation (|0> or |Phi+>)",
        "version": "1.0",
        "ports": {
            "out_ch_1": {"direction": "out", "kind": "quantum", "label": "Qubit out 1", "max_connections": 1},
            "out_ch_2": {"direction": "out", "kind": "quantum", "label": "Qubit out 2", "max_connections": 1, "active_when": {"type": 2}},
        },
        "parameters": {
            "delay": {
                "type": "number",
                "gt": 0,
                "default": 1,
                "label": "Emission period",
                "unit": "simulation ticks",
                "description": "Interval between state emissions (simulation ticks, > 0).",
            },
            "type": {
                "type": "integer",
                "enum": [1, 2],
                "enum_labels": {
                    "1": "Single-Qubit Source (|0>)",
                    "2": "Bell-Pair Source (|Phi+>)",
                },
                "default": 2,
                "label": "Source preset",
                "description": "1 = single |0> qubit on out_ch_1; 2 = Bell pair |Phi+> on out_ch_1 and out_ch_2.",
            },
            "initial_fidelity": {
                "type": "number",
                "min": 0.25,
                "max": 1.0,
                "default": 1.0,
                "label": "Initial Bell-pair fidelity",
                "unit": "[0.25, 1]",
                "description": (
                    "Fidelity of emitted Bell pairs with |Phi+> (Werner state). 1 = ideal pair. "
                    "Applies to the Bell-pair preset (type 2) only."
                ),
            },
            "emission_p": {
                "type": "number",
                "gt": 0.0,
                "max": 1.0,
                "default": 1.0,
                "label": "Emission probability per attempt",
                "unit": "(0, 1]",
                "description": (
                    "Probability of emitting a state on each clock tick (1.0 = deterministic). "
                    "Models probabilistic pulsed photonic sources (e.g. SPDC)."
                ),
            },
        },
    },
    "quantum_memory": {
        "label": "Quantum Memory",
        "category": "memories",
        "model": "Slot-based memory with local per-tick Pauli depolarization",
        "version": "1.0",
        "ports": {
            "ch_in_q": {"direction": "in", "kind": "quantum", "label": "Qubit in", "max_connections": 1},
            "ch_out_q": {"direction": "out", "kind": "quantum", "label": "Qubit out", "max_connections": 1},
            "ch_in_c": {
                "direction": "in",
                "kind": "classical",
                "label": "Readout request",
                "message_type": "MemoryReadoutRequest",
                "accepts": ["MemoryReadoutRequest", "BellOutcome"],
                "max_connections": 1,
            },
            "ch_out_c": {
                "direction": "out",
                "kind": "classical",
                "label": "Slot ready",
                "message_type": "MemoryReady",
                "max_connections": None,
            },
            "ch_in_paired_memory": {
                "direction": "in",
                "kind": "classical",
                "label": "Peer herald in",
                "message_type": "PeerHerald",
                "max_connections": 1,
            },
            "ch_out_paired_memory": {
                "direction": "out",
                "kind": "classical",
                "label": "Peer herald out",
                "message_type": "PeerHerald",
                "max_connections": 1,
            },
        },
        "parameters": {
            "depolarization_p": {
                "type": "number",
                "min": 0.0,
                "max": 1.0,
                "default": 0.0,
                "label": "Storage Pauli error probability per tick",
                "unit": "[0, 1]",
                "description": (
                    "Total probability p of applying X, Y, or Z per simulation tick "
                    "(each with probability p/3; no error with probability 1 - p)."
                ),
            },
            "t1_ticks": {
                "type": "number",
                "min": 0,
                "default": 0,
                "label": "Energy relaxation time T1",
                "unit": "simulation ticks",
                "description": (
                    "Amplitude-damping time T1 applied for the total storage duration. 0 disables T1 decay."
                ),
            },
            "t2_ticks": {
                "type": "number",
                "min": 0,
                "default": 0,
                "label": "Coherence time T2",
                "unit": "simulation ticks",
                "description": (
                    "Coherence time T2 (dephasing plus T1 contribution); requires T2 <= 2*T1 when both are set. "
                    "0 disables dephasing."
                ),
            },
            "delay": {
                "type": "number",
                "min": 0,
                "default": 0,
                "label": "Readout output delay",
                "unit": "simulation ticks",
                "description": "Delay between readout request and qubit emission (simulation ticks).",
            },
            "capacity": {
                "type": "integer",
                "min": 1,
                "default": 100,
                "label": "Memory slot capacity",
                "unit": "slots",
                "description": "Maximum number of occupied memory slots before evicting the oldest.",
            },
            "fifo": {
                "type": "integer",
                "enum": [0, 1],
                "enum_labels": {
                    "1": "FIFO (oldest slot first)",
                    "0": "LIFO (newest slot first)",
                },
                "default": 1,
                "label": "Untagged readout order",
                "description": "Order used for legacy untagged readout requests (1 = FIFO, 0 = LIFO).",
            },
        },
    },
    "entanglement_swapper": {
        "label": "Bell-State Measurement (BSM)",
        "category": "operations",
        "model": "Ideal projective Bell-basis measurement",
        "version": "1.0",
        "ports": {
            "ch_in_q_1": {"direction": "in", "kind": "quantum", "label": "Qubit in 1", "max_connections": 1},
            "ch_in_q_2": {"direction": "in", "kind": "quantum", "label": "Qubit in 2", "max_connections": 1},
            "ch_out_c_1": {
                "direction": "out",
                "kind": "classical",
                "label": "Bell outcome 1",
                "message_type": "BellOutcome",
                "max_connections": None,
            },
            "ch_out_c_2": {
                "direction": "out",
                "kind": "classical",
                "label": "Bell outcome 2",
                "message_type": "BellOutcome",
                "max_connections": None,
            },
        },
        "parameters": {
            "delay": {
                "type": "number",
                "min": 0,
                "default": 1,
                "label": "Bell-outcome notification delay",
                "unit": "simulation ticks",
                "description": (
                    "Bell projection is applied immediately on arrival; classical Bell outcome is "
                    "emitted after this delay (simulation ticks)."
                ),
            },
            "queue_capacity": {
                "type": "integer",
                "min": 1,
                "default": 1,
                "label": "Input queue capacity per side",
                "unit": "qubits",
                "description": (
                    "1 = reject-when-busy (default). Values > 1 enable a bounded per-side queue "
                    "matching arrivals by swap_request_id."
                ),
            },
            "visibility": {
                "type": "number",
                "min": 0.0,
                "max": 1.0,
                "default": 1.0,
                "label": "Bell-measurement visibility",
                "unit": "[0, 1]",
                "description": (
                    "Interference visibility V: with probability V the ideal Bell measurement is performed; "
                    "otherwise the outcome is uniform and both qubits are discarded. V = 1 is ideal."
                ),
            },
            "queue_ttl": {
                "type": "number",
                "min": 0,
                "default": 0,
                "label": "Queue expiry timeout (0 = none)",
                "unit": "simulation ticks",
                "description": (
                    "Maximum ticks a queued qubit waits for its swap partner before expiring "
                    "(0 disables expiry)."
                ),
            },
        },
    },
    "optical_bsm": {
        "label": "Optical BSM (Time-Gated)",
        "category": "operations",
        "model": "Click-driven time-gated optical Bell analyser with jitter, efficiency, dark counts, and visibility",
        "version": "1.0",
        "ports": {
            "ch_in_q_1": {"direction": "in", "kind": "quantum", "label": "Photon in 1", "max_connections": 1},
            "ch_in_q_2": {"direction": "in", "kind": "quantum", "label": "Photon in 2", "max_connections": 1},
            "ch_out_c_1": {
                "direction": "out",
                "kind": "classical",
                "label": "Herald out 1",
                "message_type": "BellOutcome",
                "max_connections": None,
            },
            "ch_out_c_2": {
                "direction": "out",
                "kind": "classical",
                "label": "Herald out 2",
                "message_type": "BellOutcome",
                "max_connections": None,
            },
        },
        "parameters": {
            "delay": {
                "type": "number",
                "min": 0,
                "default": 1,
                "label": "Herald notification delay",
                "unit": "simulation ticks",
                "description": "Classical delay before emitting the BSM herald after a coincidence.",
            },
            "coincidence_window": {
                "type": "number",
                "min": 0.0,
                "default": 1.0,
                "label": "Coincidence window",
                "unit": "simulation ticks",
                "description": "Maximum |t1 - t2| between clicks on the two arms to form a BSM herald.",
            },
            "jitter_std": {
                "type": "number",
                "min": 0.0,
                "default": 0.0,
                "label": "Timing jitter (sigma)",
                "unit": "simulation ticks",
                "description": "Gaussian per-photon detection timing jitter standard deviation (0 = none).",
            },
            "detector_efficiency": {
                "type": "number",
                "gt": 0.0,
                "max": 1.0,
                "default": 1.0,
                "label": "Detector efficiency",
                "unit": "(0, 1]",
                "description": "Probability each arriving photon triggers a detector click.",
            },
            "dark_count_rate": {
                "type": "number",
                "min": 0.0,
                "max": 1.0,
                "default": 0.0,
                "label": "Dark-count rate",
                "unit": "per tick",
                "description": "Per-tick dark-click probability on each BSM detector arm.",
            },
            "visibility": {
                "type": "number",
                "min": 0.0,
                "max": 1.0,
                "default": 1.0,
                "label": "Two-photon HOM visibility",
                "unit": "[0, 1]",
                "description": "Hong-Ou-Mandel interference visibility V for true two-photon coincidences.",
            },
            "linear_optical_efficiency": {
                "type": "number",
                "gt": 0.0,
                "max": 1.0,
                "default": 0.5,
                "label": "Linear-optical BSM efficiency",
                "unit": "(0, 1]",
                "description": "Fraction of Bell states distinguishable by the analyser (0.5 for standard linear optics).",
            },
        },
    },
    "orchestrator": {
        "label": "Swap Controller",
        "category": "controllers",
        "model": "Matches ready slots from two memories and requests readout",
        "version": "1.0",
        "ports": {
            "ch_in_memory_1": {
                "direction": "in",
                "kind": "classical",
                "label": "Slot ready 1",
                "message_type": "MemoryReady",
                "max_connections": 1,
            },
            "ch_in_memory_2": {
                "direction": "in",
                "kind": "classical",
                "label": "Slot ready 2",
                "message_type": "MemoryReady",
                "max_connections": 1,
            },
            "ch_out_memory_1": {
                "direction": "out",
                "kind": "classical",
                "label": "Readout request 1",
                "message_type": "MemoryReadoutRequest",
                "max_connections": 1,
            },
            "ch_out_memory_2": {
                "direction": "out",
                "kind": "classical",
                "label": "Readout request 2",
                "message_type": "MemoryReadoutRequest",
                "max_connections": 1,
            },
        },
        "parameters": {
            "delay": {
                "type": "number",
                "min": 0,
                "default": 0,
                "label": "Readout-request delay",
                "unit": "simulation ticks",
                "description": (
                    "Delay between matching two ready slots and emitting their readout "
                    "requests (simulation ticks)."
                ),
            },
        },
    },
    "pauli_corrector": {
        "label": "Pauli Feed-Forward",
        "category": "controllers",
        "model": "Applies X and Z Pauli corrections from the Bell outcome",
        "version": "1.0",
        "ports": {
            "ch_in_q": {"direction": "in", "kind": "quantum", "label": "Qubit in", "max_connections": 1},
            "ch_out_q": {"direction": "out", "kind": "quantum", "label": "Qubit out", "max_connections": 1},
            "ch_in_es": {
                "direction": "in",
                "kind": "classical",
                "label": "Bell outcome",
                "message_type": "BellOutcome",
                "max_connections": 1,
            },
            "ch_in_memory": {
                "direction": "in",
                "kind": "classical",
                "label": "Slot ready",
                "message_type": "MemoryReady",
                "max_connections": 1,
            },
            "ch_out_memory": {
                "direction": "out",
                "kind": "classical",
                "label": "Readout request",
                "message_type": "MemoryReadoutRequest",
                "max_connections": 1,
            },
        },
        "parameters": {
            "delay": {
                "type": "number",
                "min": 0,
                "default": 0,
                "label": "Corrected-qubit output delay",
                "unit": "simulation ticks",
                "description": (
                    "Pauli X/Z correction is applied immediately once qubit and Bell outcome meet; "
                    "qubit is emitted after this delay (simulation ticks)."
                ),
            },
        },
    },
    "measurer": {
        "label": "Qubit Measurement (X/Z)",
        "category": "operations",
        "model": "Ideal projective single-qubit measurement in X or Z basis",
        "version": "1.0",
        "ports": {
            "ch_in_q": {"direction": "in", "kind": "quantum", "label": "Qubit in", "max_connections": 1},
            "ch_out_result": {
                "direction": "out",
                "kind": "classical",
                "label": "Outcome out",
                "message_type": "MeasurementOutcome",
                "max_connections": None,
            },
        },
        "parameters": {
            "delay": {
                "type": "number",
                "min": 0,
                "default": 0,
                "label": "Outcome notification delay",
                "unit": "simulation ticks",
                "description": (
                    "Measurement projection happens immediately; classical bit is emitted after "
                    "this delay (simulation ticks)."
                ),
            },
            "x_basis_p": {
                "type": "number",
                "min": 0.0,
                "max": 1.0,
                "default": 0.0,
                "label": "X-basis selection probability",
                "unit": "[0, 1]",
                "description": "Probability of measuring in X basis (otherwise Z basis).",
            },
            "p_depolarization": {
                "type": "number",
                "min": 0.0,
                "max": 1.0,
                "default": 0.0,
                "label": "Pre-measurement Pauli error probability",
                "unit": "[0, 1]",
                "description": (
                    "Local single-qubit Pauli depolarization p applied immediately before "
                    "projective measurement (X, Y, Z each with probability p/3; no error with probability 1 - p)."
                ),
            },
            "detector_efficiency": {
                "type": "number",
                "gt": 0.0,
                "max": 1.0,
                "default": 1.0,
                "label": "Detector efficiency",
                "unit": "(0, 1]",
                "description": "Probability that an arriving qubit is detected. Missed qubits leave no outcome.",
            },
            "dark_count_rate": {
                "type": "number",
                "min": 0.0,
                "max": 1.0,
                "default": 0.0,
                "label": "Dark-count rate",
                "unit": "per tick",
                "description": (
                    "Probability per simulation tick of a spurious click without pair ID. "
                    "Excluded from pair-ID-matched outcomes; counted in windowed physical coincidences."
                ),
            },
        },
    },
    "measurer_memory_paired": {
        "label": "Swap-Triggered Memory Measurement",
        "category": "controllers",
        "model": "Requests memory readout on Bell outcome, then measures in X or Z basis",
        "version": "1.0",
        "ports": {
            "ch_in_q": {"direction": "in", "kind": "quantum", "label": "Qubit in", "max_connections": 1},
            "ch_in_es": {
                "direction": "in",
                "kind": "classical",
                "label": "Bell outcome",
                "message_type": "BellOutcome",
                "max_connections": 1,
            },
            "ch_in_memory_c": {
                "direction": "in",
                "kind": "classical",
                "label": "Slot ready",
                "message_type": "MemoryReady",
                "max_connections": 1,
            },
            "ch_out_memory_c": {
                "direction": "out",
                "kind": "classical",
                "label": "Readout request",
                "message_type": "MemoryReadoutRequest",
                "max_connections": 1,
            },
            "ch_out_result": {
                "direction": "out",
                "kind": "classical",
                "label": "Outcome out",
                "message_type": "MeasurementOutcome",
                "max_connections": None,
            },
        },
        "parameters": {
            "delay": {
                "type": "number",
                "min": 0,
                "default": 0,
                "label": "Outcome notification delay",
                "unit": "simulation ticks",
                "description": (
                    "Measurement projection happens immediately; classical bit is emitted after "
                    "this delay (simulation ticks)."
                ),
            },
            "x_basis_p": {
                "type": "number",
                "min": 0.0,
                "max": 1.0,
                "default": 0.0,
                "label": "X-basis selection probability",
                "unit": "[0, 1]",
                "description": "Probability of measuring in X basis (otherwise Z basis).",
            },
            "p_depolarization": {
                "type": "number",
                "min": 0.0,
                "max": 1.0,
                "default": 0.0,
                "label": "Pre-measurement Pauli error probability",
                "unit": "[0, 1]",
                "description": (
                    "Local single-qubit Pauli depolarization p applied immediately before "
                    "projective measurement (X, Y, Z each with probability p/3; no error with probability 1 - p)."
                ),
            },
            "detector_efficiency": {
                "type": "number",
                "gt": 0.0,
                "max": 1.0,
                "default": 1.0,
                "label": "Detector efficiency",
                "unit": "(0, 1]",
                "description": "Probability that an arriving qubit is detected. Missed qubits leave no outcome.",
            },
            "dark_count_rate": {
                "type": "number",
                "min": 0.0,
                "max": 1.0,
                "default": 0.0,
                "label": "Dark-count rate",
                "unit": "per tick",
                "description": (
                    "Probability per simulation tick of a spurious click without pair ID. "
                    "Excluded from pair-ID-matched outcomes; counted in windowed physical coincidences."
                ),
            },
        },
    },
    "classic_data_reader": {
        "label": "Joint Outcome Counter",
        "category": "diagnostics",
        "model": "Matches outcomes by pair ID (00/01/10/11) and counts windowed physical coincidences",
        "version": "1.0",
        "ports": {
            "input_1": {
                "direction": "in",
                "kind": "classical",
                "label": "Outcome in 1",
                "message_type": "MeasurementOutcome",
                "max_connections": 1,
            },
            "input_2": {
                "direction": "in",
                "kind": "classical",
                "label": "Outcome in 2",
                "message_type": "MeasurementOutcome",
                "max_connections": 1,
            },
        },
        "parameters": {
            "coincidence_window": {
                "type": "number",
                "min": 0.0,
                "default": 0.0,
                "label": "Coincidence window",
                "unit": "simulation ticks",
                "description": (
                    "Maximum arrival-time difference |t1 - t2| for physical detector coincidences "
                    "(including dark counts). Pair-ID-matched counts exclude untagged clicks."
                ),
            },
        },
    },
    "detector_module": {
        "label": "Qubit Arrival Monitor",
        "category": "diagnostics",
        "model": "Counts arrivals and forwards only qubits in 4x4 (two-qubit) registers",
        "version": "1.0",
        "ports": {
            "input_a_1": {"direction": "in", "kind": "quantum", "label": "Qubit in 1", "max_connections": 1},
            "input_a_2": {"direction": "in", "kind": "quantum", "label": "Qubit in 2", "max_connections": 1},
            "output_a_1": {"direction": "out", "kind": "quantum", "label": "2-qubit reg out 1", "max_connections": 1},
            "output_a_2": {"direction": "out", "kind": "quantum", "label": "2-qubit reg out 2", "max_connections": 1},
        },
        "parameters": {
            "trace": {
                "type": "integer",
                "enum": [0, 1],
                "enum_labels": {
                    "0": "Counters only (bounded memory)",
                    "1": "Retain arriving qubit handles",
                },
                "default": 0,
                "label": "Arrival trace mode",
                "description": "1 retains arriving qubit handles in list_a_1/list_a_2; 0 keeps counters only.",
            },
        },
    },
    "endpoint_probe": {
        "label": "Endpoint State Probe",
        "category": "diagnostics",
        "model": "Matches endpoint arrivals by pair ID and captures joint fidelity at delivery time",
        "version": "1.0",
        "ports": {
            "ch_in_q": {"direction": "in", "kind": "quantum", "label": "Qubit in", "max_connections": 1},
        },
        "parameters": {},
    },
}


def get_component_spec(component_type):
    return COMPONENT_MANIFEST.get(component_type)
