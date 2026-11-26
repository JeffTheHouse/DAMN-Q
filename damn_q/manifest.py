"""Component manifest shared by Python validation, the runner, and the browser UI."""

MANIFEST_VERSION = "1.0"

COMPONENT_MANIFEST = {
    "source": {
        "label": "Entanglement / Qubit Source",
        "category": "sources",
        "version": "1.0",
        "ports": {
            "out_ch_1": {"direction": "out", "kind": "quantum"},
            "out_ch_2": {"direction": "out", "kind": "quantum"},
        },
        "parameters": {
            "delay": {"type": "number", "gt": 0, "default": 1, "description": "Emission period (ticks, > 0)"},
            "type": {"type": "integer", "enum": [1, 2], "default": 2, "description": "1 = single |0>, 2 = Bell |Phi+>"},
        },
    },
    "quantum_memory": {
        "label": "Quantum Memory",
        "category": "memories",
        "version": "1.0",
        "ports": {
            "ch_in_q": {"direction": "in", "kind": "quantum"},
            "ch_out_q": {"direction": "out", "kind": "quantum"},
            "ch_in_c": {"direction": "in", "kind": "classical"},
            "ch_out_c": {"direction": "out", "kind": "classical"},
            "ch_in_paired_memory": {"direction": "in", "kind": "classical"},
            "ch_out_paired_memory": {"direction": "out", "kind": "classical"},
        },
        "parameters": {
            "depolarization_p": {"type": "number", "min": 0.0, "max": 1.0, "default": 0.0, "description": "Per-tick local depolarization probability"},
            "delay": {"type": "number", "min": 0, "default": 0, "description": "Readout delay (ticks)"},
            "capacity": {"type": "integer", "min": 1, "default": 100, "description": "Maximum stored slots"},
            "fifo": {"type": "integer", "enum": [0, 1], "default": 1, "description": "1 = FIFO, 0 = LIFO"},
        },
    },
    "entanglement_swapper": {
        "label": "Entanglement Swapper",
        "category": "processors",
        "version": "1.0",
        "ports": {
            "ch_in_q_1": {"direction": "in", "kind": "quantum"},
            "ch_in_q_2": {"direction": "in", "kind": "quantum"},
            "ch_out_c_1": {"direction": "out", "kind": "classical"},
            "ch_out_c_2": {"direction": "out", "kind": "classical"},
        },
        "parameters": {
            "delay": {"type": "number", "min": 0, "default": 1, "description": "Bell-measurement delay (ticks)"},
        },
    },
    "orchestrator": {
        "label": "Orchestrator",
        "category": "controllers",
        "version": "1.0",
        "ports": {
            "ch_in_memory_1": {"direction": "in", "kind": "classical"},
            "ch_in_memory_2": {"direction": "in", "kind": "classical"},
            "ch_out_memory_1": {"direction": "out", "kind": "classical"},
            "ch_out_memory_2": {"direction": "out", "kind": "classical"},
        },
        "parameters": {
            "delay": {"type": "number", "min": 0, "default": 0, "description": "Controller delay (ticks)"},
        },
    },
    "pauli_corrector": {
        "label": "Pauli Corrector",
        "category": "processors",
        "version": "1.0",
        "ports": {
            "ch_in_q": {"direction": "in", "kind": "quantum"},
            "ch_out_q": {"direction": "out", "kind": "quantum"},
            "ch_in_es": {"direction": "in", "kind": "classical"},
            "ch_in_memory": {"direction": "in", "kind": "classical"},
            "ch_out_memory": {"direction": "out", "kind": "classical"},
        },
        "parameters": {
            "delay": {"type": "number", "min": 0, "default": 0, "description": "Correction delay (ticks)"},
        },
    },
    "measurer": {
        "label": "Measuring Device",
        "category": "detectors",
        "version": "1.0",
        "ports": {
            "ch_in_q": {"direction": "in", "kind": "quantum"},
            "ch_out_result": {"direction": "out", "kind": "classical"},
        },
        "parameters": {
            "delay": {"type": "number", "min": 0, "default": 0, "description": "Measurement delay (ticks)"},
            "x_basis_p": {"type": "number", "min": 0.0, "max": 1.0, "default": 0.0, "description": "Probability of measuring in X basis"},
            "p_depolarization": {"type": "number", "min": 0.0, "max": 1.0, "default": 0.0, "description": "Measurement depolarization parameter"},
        },
    },
    "measurer_memory_paired": {
        "label": "Memory-Paired Measurer",
        "category": "detectors",
        "version": "1.0",
        "ports": {
            "ch_in_q": {"direction": "in", "kind": "quantum"},
            "ch_in_es": {"direction": "in", "kind": "classical"},
            "ch_in_memory_c": {"direction": "in", "kind": "classical"},
            "ch_out_memory_c": {"direction": "out", "kind": "classical"},
            "ch_out_result": {"direction": "out", "kind": "classical"},
        },
        "parameters": {
            "delay": {"type": "number", "min": 0, "default": 0, "description": "Measurement delay (ticks)"},
            "x_basis_p": {"type": "number", "min": 0.0, "max": 1.0, "default": 0.0, "description": "Probability of measuring in X basis"},
            "p_depolarization": {"type": "number", "min": 0.0, "max": 1.0, "default": 0.0, "description": "Measurement depolarization parameter"},
        },
    },
    "classic_data_reader": {
        "label": "Classical Data Reader",
        "category": "detectors",
        "version": "1.0",
        "ports": {
            "input_1": {"direction": "in", "kind": "classical"},
            "input_2": {"direction": "in", "kind": "classical"},
        },
        "parameters": {},
    },
    "detector_module": {
        "label": "Detector Module",
        "category": "detectors",
        "version": "1.0",
        "ports": {
            "input_a_1": {"direction": "in", "kind": "quantum"},
            "input_a_2": {"direction": "in", "kind": "quantum"},
            "output_a_1": {"direction": "out", "kind": "quantum"},
            "output_a_2": {"direction": "out", "kind": "quantum"},
        },
        "parameters": {},
    },
    "endpoint_probe": {
        "label": "Quantum Endpoint Probe",
        "category": "detectors",
        "version": "1.0",
        "ports": {
            "ch_in_q": {"direction": "in", "kind": "quantum"},
        },
        "parameters": {},
    },
}


def get_component_spec(component_type):
    return COMPONENT_MANIFEST.get(component_type)
