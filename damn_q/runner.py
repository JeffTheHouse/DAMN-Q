"""Experiment loader and runner executing validated DAMN-Q JSON graphs."""

import json
from pathlib import Path

import numpy as np

from Auto_connector import connect
from Classic_data_reader import Classic_data_reader
from Detector_module import Detector_module
from Emitter import Handler
from Entanglment_swapping_module import Entaglment_swapping_module
from Measurer import Measuring_Device
from Measurer_memory_paired import Measurer_memory_paired
from Memory import Quantum_memory
from Orchestrator import Orchestrator
from Pauli_corrector import Pauli_corrector
from Simulation import Simulation
from Source import Source
from States import phi_plus

from damn_q.manifest import get_component_spec
from damn_q.schema import SCHEMA_VERSION, validate_experiment

SIMULATOR_VERSION = "0.2.0"


class EndpointProbe:
    """Captures arriving qubits for joint-state and fidelity inspection."""

    def __init__(self, id, sim):
        self.id = id
        self.sim = sim
        self.ch_in_q = Handler(self.handle_qubit)
        self.qubits = []

    def handle_qubit(self, qubit):
        self.qubits.append((self.sim.time, qubit))


def _resolve_params(ctype, raw_params):
    spec = get_component_spec(ctype)
    resolved = {}
    for name, pspec in spec["parameters"].items():
        resolved[name] = raw_params.get(name, pspec["default"])
    return resolved


def _instantiate_component(comp_id, ctype, params, sim):
    if ctype == "source":
        return Source(comp_id, params["delay"], params["type"], sim=sim)
    if ctype == "quantum_memory":
        return Quantum_memory(
            comp_id,
            params["depolarization_p"],
            delay=params["delay"],
            capacity=params["capacity"],
            fifo=params["fifo"],
            sim=sim,
        )
    if ctype == "entanglement_swapper":
        return Entaglment_swapping_module(comp_id, delay=params["delay"], sim=sim)
    if ctype == "orchestrator":
        return Orchestrator(comp_id, delay=params["delay"], sim=sim)
    if ctype == "pauli_corrector":
        return Pauli_corrector(comp_id, delay=params["delay"], sim=sim)
    if ctype == "measurer":
        return Measuring_Device(
            comp_id,
            params["delay"],
            x_basis_p=params["x_basis_p"],
            p_depolarization=params["p_depolarization"],
            sim=sim,
        )
    if ctype == "measurer_memory_paired":
        return Measurer_memory_paired(
            comp_id,
            params["delay"],
            x_basis_p=params["x_basis_p"],
            p_depolarization=params["p_depolarization"],
            sim=sim,
        )
    if ctype == "classic_data_reader":
        return Classic_data_reader(comp_id, sim=sim)
    if ctype == "detector_module":
        return Detector_module(comp_id, trace=bool(params["trace"]), sim=sim)
    if ctype == "endpoint_probe":
        return EndpointProbe(comp_id, sim)
    raise ValueError(f"Unsupported component type: {ctype!r}")


def load_experiment(path):
    with open(Path(path), "r", encoding="utf-8") as f:
        return json.load(f)


def run_experiment(doc_or_path, *, seed_override=None, until_override=None):
    """Validate and execute a DAMN-Q experiment, returning a JSON-serializable result.

    Each call builds its own Simulation, so runs never share clock, queue,
    random stream, or process-global state.
    """
    doc = load_experiment(doc_or_path) if isinstance(doc_or_path, (str, Path)) else dict(doc_or_path)

    # Apply overrides on a shallow copy of run config before validation
    run_cfg = dict(doc.get("run", {})) if isinstance(doc.get("run"), dict) else doc.get("run")
    if isinstance(run_cfg, dict):
        if seed_override is not None:
            run_cfg["seed"] = seed_override
        if until_override is not None:
            run_cfg["until"] = until_override
        doc = dict(doc, run=run_cfg)

    # Static validation MUST run before building the simulation or components
    validate_experiment(doc)

    until = doc["run"]["until"]
    seed = doc["run"].get("seed")
    sim = Simulation(seed)

    instances = {}
    types = {}
    for comp in doc["components"]:
        cid = comp["id"]
        ctype = comp["type"]
        params = _resolve_params(ctype, comp.get("params", {}))
        instances[cid] = _instantiate_component(cid, ctype, params, sim)
        types[cid] = ctype

    for conn in doc.get("connections", []):
        src_obj = instances[conn["from"]["component"]]
        dst_obj = instances[conn["to"]["component"]]
        src_port = getattr(src_obj, conn["from"]["port"])
        dst_port = getattr(dst_obj, conn["to"]["port"])
        connect(
            src_port,
            dst_port,
            delay=conn.get("delay", 0),
            loss_p=conn.get("loss_p", 0.0),
            depolarization_p=conn.get("depolarization_p", 0.0),
            sim=sim,
        )

    sim.run(until)

    readers = {}
    detectors = {}
    probes = {}
    for cid, obj in instances.items():
        ctype = types[cid]
        if ctype == "classic_data_reader":
            readers[cid] = {
                "00": obj.count_00,
                "01": obj.count_01,
                "10": obj.count_10,
                "11": obj.count_11,
            }
        elif ctype == "detector_module":
            detectors[cid] = {
                "total_1": obj.Total_qubits_1,
                "total_2": obj.Total_qubits_2,
                "ebits_1": obj.ebits_1,
                "ebits_2": obj.ebits_2,
                "single_1": obj.single_qubits_1,
                "single_2": obj.single_qubits_2,
            }
        elif ctype == "endpoint_probe":
            probes[cid] = {"count": len(obj.qubits)}

    measurements = []
    for m in doc.get("measurements", []):
        if m["type"] == "bell_fidelity":
            p1_id, p2_id = m["probes"]
            q_list_1 = instances[p1_id].qubits
            q_list_2 = instances[p2_id].qubits
            n_pairs = min(len(q_list_1), len(q_list_2))
            fidelities = []
            shared_register = []
            for idx in range(n_pairs):
                _, q1 = q_list_1[idx]
                _, q2 = q_list_2[idx]
                same_reg = (q1.register is not None) and (q1.register is q2.register)
                shared_register.append(same_reg)
                if same_reg:
                    joint = q1.register.reduced_density_matrix([q1, q2])
                    f_val = float(np.real(np.trace(phi_plus @ joint)))
                elif q1.register is not None and q2.register is not None:
                    joint = np.kron(
                        q1.register.reduced_density_matrix([q1]),
                        q2.register.reduced_density_matrix([q2]),
                    )
                    f_val = float(np.real(np.trace(phi_plus @ joint)))
                else:
                    f_val = 0.0
                fidelities.append(f_val)

            measurements.append(
                {
                    "type": "bell_fidelity",
                    "probes": [p1_id, p2_id],
                    "pairs": n_pairs,
                    "all_shared_register": all(shared_register) if shared_register else False,
                    "fidelities": fidelities,
                    "mean_fidelity": (sum(fidelities) / len(fidelities)) if fidelities else None,
                }
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "simulator_version": SIMULATOR_VERSION,
        "name": doc.get("name", ""),
        "seed": seed,
        "until": until,
        "final_time": sim.time,
        "readers": readers,
        "detectors": detectors,
        "probes": probes,
        "measurements": measurements,
    }
