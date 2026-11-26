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
    """Captures arriving qubits and notifies delivery-time measurement recorders."""

    def __init__(self, id, sim):
        self.id = id
        self.sim = sim
        self.ch_in_q = Handler(self.handle_qubit, sim=self.sim, kind="quantum", max_connections=1)
        self.qubits = []
        self._listeners = []

    def add_listener(self, callback):
        self._listeners.append(callback)

    def handle_qubit(self, qubit):
        arrival_time = self.sim.time
        self.qubits.append((arrival_time, qubit))
        for cb in self._listeners:
            cb(arrival_time, qubit)


class _BellFidelityRecorder:
    """Pairs arrivals across two EndpointProbes by `pair_id` and captures fidelity at delivery."""

    def __init__(self, p1_id, p2_id, probe_a, probe_b):
        self.p1_id = p1_id
        self.p2_id = p2_id
        self._pending_a = {}
        self._pending_b = {}
        self._untagged_a = []
        self._untagged_b = []
        self.fidelities = []
        self.shared_register = []
        self.delivery_times = []
        self.latencies = []

        probe_a.add_listener(self._on_a)
        probe_b.add_listener(self._on_b)

    def _capture(self, t_a, q1, t_b, q2):
        delivery_time = max(t_a, t_b)
        same_reg = (q1.register is not None) and (q1.register is q2.register)
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

        self.shared_register.append(same_reg)
        self.fidelities.append(f_val)
        self.delivery_times.append(delivery_time)

        c1 = getattr(q1, "created_at", None)
        c2 = getattr(q2, "created_at", None)
        if c1 is not None and c2 is not None:
            self.latencies.append(delivery_time - min(c1, c2))
        elif c1 is not None:
            self.latencies.append(delivery_time - c1)
        elif c2 is not None:
            self.latencies.append(delivery_time - c2)

    def _on_a(self, t, qubit):
        pid = getattr(qubit, "pair_id", None)
        if pid is not None:
            if pid in self._pending_b:
                t_b, q2 = self._pending_b.pop(pid)
                self._capture(t, qubit, t_b, q2)
            else:
                self._pending_a[pid] = (t, qubit)
            return
        if self._untagged_b:
            t_b, q2 = self._untagged_b.pop(0)
            self._capture(t, qubit, t_b, q2)
        else:
            self._untagged_a.append((t, qubit))

    def _on_b(self, t, qubit):
        pid = getattr(qubit, "pair_id", None)
        if pid is not None:
            if pid in self._pending_a:
                t_a, q1 = self._pending_a.pop(pid)
                self._capture(t_a, q1, t, qubit)
            else:
                self._pending_b[pid] = (t, qubit)
            return
        if self._untagged_a:
            t_a, q1 = self._untagged_a.pop(0)
            self._capture(t_a, q1, t, qubit)
        else:
            self._untagged_b.append((t, qubit))

    def to_dict(self):
        n_pairs = len(self.fidelities)
        return {
            "type": "bell_fidelity",
            "probes": [self.p1_id, self.p2_id],
            "captured_at": "delivery",
            "pairs": n_pairs,
            "unmatched_a": len(self._pending_a) + len(self._untagged_a),
            "unmatched_b": len(self._pending_b) + len(self._untagged_b),
            "all_shared_register": all(self.shared_register) if self.shared_register else False,
            "fidelities": self.fidelities,
            "mean_fidelity": (sum(self.fidelities) / n_pairs) if n_pairs else None,
            "delivery_times": self.delivery_times,
            "latencies": self.latencies,
            "mean_latency": (sum(self.latencies) / len(self.latencies)) if self.latencies else None,
        }


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
    random stream, or process-global state. Bell fidelity probes pair arrivals
    by `pair_id` and capture joint states at delivery time.
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

    # Attach delivery-time Bell fidelity recorders before running the simulation
    recorders = []
    for m in doc.get("measurements", []):
        if m["type"] == "bell_fidelity":
            p1_id, p2_id = m["probes"]
            recorders.append(_BellFidelityRecorder(p1_id, p2_id, instances[p1_id], instances[p2_id]))

    sim.run(until)

    readers = {}
    detectors = {}
    probes = {}
    sources_metrics = {}
    memories_metrics = {}
    swappers_metrics = {}
    readers_unmatched = {}

    for cid, obj in instances.items():
        ctype = types[cid]
        if ctype == "source":
            sources_metrics[cid] = {"attempts": obj.attempts}
        elif ctype == "quantum_memory":
            memories_metrics[cid] = {
                "heralded_pairs": obj.heralded_count,
                "evicted": obj.evicted_count,
            }
        elif ctype == "entanglement_swapper":
            swappers_metrics[cid] = {
                "completed": obj.counter,
                "rejected": obj.rejected_count,
            }
        elif ctype == "classic_data_reader":
            readers[cid] = {
                "00": obj.count_00,
                "01": obj.count_01,
                "10": obj.count_10,
                "11": obj.count_11,
            }
            readers_unmatched[cid] = {
                "unmatched_1": obj.unmatched_1,
                "unmatched_2": obj.unmatched_2,
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

    measurements = [rec.to_dict() for rec in recorders]

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
        "metrics": {
            "sources": sources_metrics,
            "memories": memories_metrics,
            "swappers": swappers_metrics,
            "readers_unmatched": readers_unmatched,
        },
    }
