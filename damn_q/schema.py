"""Validation for DAMN-Q versioned JSON experiment graphs."""

import math

from damn_q.manifest import get_component_spec
from Hardware_models import validate_storage_times

SCHEMA_VERSION = "1.0"

_FIBRE_KEYS = ("length_km", "attenuation_db_per_km", "coupling_loss_db")


class ExperimentValidationError(ValueError):
    """Raised when an experiment graph fails static validation before execution."""

    def __init__(self, errors):
        self.errors = list(errors)
        message = "Invalid DAMN-Q experiment:\n" + "\n".join(f"  - {e}" for e in self.errors)
        super().__init__(message)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_param(comp_id, param_name, value, spec, errors):
    ptype = spec["type"]
    if ptype == "integer":
        if not _is_integer(value):
            errors.append(f"Component {comp_id!r} parameter {param_name!r} must be an integer, got {value!r}.")
            return
    elif ptype == "number":
        if not _is_number(value):
            errors.append(f"Component {comp_id!r} parameter {param_name!r} must be a number, got {value!r}.")
            return

    if "enum" in spec and value not in spec["enum"]:
        errors.append(f"Component {comp_id!r} parameter {param_name!r} must be one of {spec['enum']}, got {value!r}.")
    if "gt" in spec and value <= spec["gt"]:
        errors.append(f"Component {comp_id!r} parameter {param_name!r} must be > {spec['gt']}, got {value!r}.")
    if "min" in spec and value < spec["min"]:
        errors.append(f"Component {comp_id!r} parameter {param_name!r} must be >= {spec['min']}, got {value!r}.")
    if "max" in spec and value > spec["max"]:
        errors.append(f"Component {comp_id!r} parameter {param_name!r} must be <= {spec['max']}, got {value!r}.")


def _resolved_params(spec, raw_params):
    resolved = {}
    for pname, pspec in spec.get("parameters", {}).items():
        resolved[pname] = raw_params.get(pname, pspec["default"])
    return resolved


def _port_is_active(port_spec, params):
    cond = port_spec.get("active_when")
    if not cond:
        return True
    return all(params.get(k) == v for k, v in cond.items())


def _classical_types_compatible(src_port_spec, dst_port_spec):
    src_mt = src_port_spec.get("message_type")
    dst_accepts = dst_port_spec.get("accepts")
    dst_mt = dst_port_spec.get("message_type")
    if src_mt is None:
        return True
    if dst_accepts is not None:
        return src_mt in dst_accepts
    if dst_mt is not None:
        return src_mt == dst_mt
    return True


def validate_experiment(doc):
    """Validate an experiment dictionary. Raises ExperimentValidationError if invalid."""
    errors = []
    if not isinstance(doc, dict):
        raise ExperimentValidationError(["Experiment document must be a JSON object."])

    version = doc.get("schema_version")
    if version != SCHEMA_VERSION:
        errors.append(f"Unsupported schema_version {version!r}; expected {SCHEMA_VERSION!r}.")

    run_cfg = doc.get("run")
    if not isinstance(run_cfg, dict):
        errors.append("Missing or invalid 'run' object.")
    else:
        until = run_cfg.get("until")
        if not _is_number(until) or until <= 0:
            errors.append(f"'run.until' must be a positive number, got {until!r}.")
        seed = run_cfg.get("seed")
        if seed is not None and not _is_integer(seed):
            errors.append(f"'run.seed' must be an integer or null, got {seed!r}.")
        tick_s = run_cfg.get("tick_duration_s")
        if tick_s is not None and (not _is_number(tick_s) or tick_s <= 0):
            errors.append(f"'run.tick_duration_s' must be a positive number or null, got {tick_s!r}.")

    components = doc.get("components")
    comp_map = {}
    if not isinstance(components, list) or not components:
        errors.append("'components' must be a non-empty list.")
    else:
        for idx, comp in enumerate(components):
            if not isinstance(comp, dict):
                errors.append(f"components[{idx}] must be an object.")
                continue
            cid = comp.get("id")
            ctype = comp.get("type")
            if not isinstance(cid, str) or not cid.strip():
                errors.append(f"components[{idx}].id must be a non-empty string.")
                continue
            if cid in comp_map:
                errors.append(f"Duplicate component id {cid!r}.")
                continue
            if not isinstance(ctype, str):
                errors.append(f"Component {cid!r} type must be a string, got {ctype!r}.")
                continue
            spec = get_component_spec(ctype)
            if spec is None:
                errors.append(f"Component {cid!r} has unknown type {ctype!r}.")
                continue

            params = comp.get("params", {})
            if not isinstance(params, dict):
                errors.append(f"Component {cid!r} 'params' must be an object.")
                comp_map[cid] = (ctype, spec, _resolved_params(spec, {}))
                continue
            for pname, pval in params.items():
                if pname not in spec["parameters"]:
                    errors.append(f"Component {cid!r} ({ctype}) has unknown parameter {pname!r}.")
                else:
                    _validate_param(cid, pname, pval, spec["parameters"][pname], errors)
            resolved = _resolved_params(spec, params)
            comp_map[cid] = (ctype, spec, resolved)
            if ctype == "quantum_memory":
                t1, t2 = resolved.get("t1_ticks"), resolved.get("t2_ticks")
                if _is_number(t1) and _is_number(t2) and t1 >= 0 and t2 >= 0:
                    try:
                        validate_storage_times(t1, t2)
                    except ValueError as exc:
                        errors.append(f"Component {cid!r} (quantum_memory): {exc}")

    connections = doc.get("connections", [])
    run_tick_s = run_cfg.get("tick_duration_s") if isinstance(run_cfg, dict) else None
    seen_edges = set()
    out_counts = {}
    in_counts = {}
    if not isinstance(connections, list):
        errors.append("'connections' must be a list.")
    else:
        for idx, conn in enumerate(connections):
            if not isinstance(conn, dict):
                errors.append(f"connections[{idx}] must be an object.")
                continue
            src = conn.get("from")
            dst = conn.get("to")
            if not isinstance(src, dict) or not isinstance(dst, dict):
                errors.append(f"connections[{idx}] must have 'from' and 'to' objects.")
                continue

            src_cid, src_port = src.get("component"), src.get("port")
            dst_cid, dst_port = dst.get("component"), dst.get("port")
            if not isinstance(src_cid, str) or not isinstance(src_port, str):
                errors.append(f"connections[{idx}].from component and port must be strings.")
                continue
            if not isinstance(dst_cid, str) or not isinstance(dst_port, str):
                errors.append(f"connections[{idx}].to component and port must be strings.")
                continue
            src_info = comp_map.get(src_cid)
            dst_info = comp_map.get(dst_cid)

            if src_info is None:
                errors.append(f"connections[{idx}].from references unknown component {src_cid!r}.")
                continue
            if dst_info is None:
                errors.append(f"connections[{idx}].to references unknown component {dst_cid!r}.")
                continue

            src_port_spec = src_info[1]["ports"].get(src_port)
            dst_port_spec = dst_info[1]["ports"].get(dst_port)
            if src_port_spec is None:
                errors.append(f"connections[{idx}].from references unknown port {src_port!r} on {src_cid!r}.")
                continue
            if dst_port_spec is None:
                errors.append(f"connections[{idx}].to references unknown port {dst_port!r} on {dst_cid!r}.")
                continue

            if src_port_spec["direction"] != "out":
                errors.append(f"connections[{idx}].from port {src_cid}.{src_port} is not an output port.")
            if dst_port_spec["direction"] != "in":
                errors.append(f"connections[{idx}].to port {dst_cid}.{dst_port} is not an input port.")

            if not _port_is_active(src_port_spec, src_info[2]):
                errors.append(
                    f"connections[{idx}].from port {src_cid}.{src_port} is inactive under the component's current parameters."
                )
            if not _port_is_active(dst_port_spec, dst_info[2]):
                errors.append(
                    f"connections[{idx}].to port {dst_cid}.{dst_port} is inactive under the component's current parameters."
                )

            edge_key = (src_cid, src_port, dst_cid, dst_port)
            if edge_key in seen_edges:
                errors.append(
                    f"connections[{idx}] duplicates existing connection "
                    f"{src_cid}.{src_port} -> {dst_cid}.{dst_port}."
                )
            else:
                seen_edges.add(edge_key)

            if src_port_spec["kind"] != dst_port_spec["kind"]:
                errors.append(
                    f"connections[{idx}] connects incompatible port types: "
                    f"{src_cid}.{src_port} ({src_port_spec['kind']}) -> "
                    f"{dst_cid}.{dst_port} ({dst_port_spec['kind']})."
                )
            else:
                if src_port_spec["kind"] == "classical" and not _classical_types_compatible(
                    src_port_spec, dst_port_spec
                ):
                    src_mt = src_port_spec.get("message_type")
                    dst_mt = dst_port_spec.get("accepts") or dst_port_spec.get("message_type")
                    errors.append(
                        f"connections[{idx}] connects incompatible classical message types: "
                        f"{src_cid}.{src_port} ({src_mt}) -> {dst_cid}.{dst_port} (expects {dst_mt})."
                    )

                # Output fan-out limit
                out_key = (src_cid, src_port)
                out_counts[out_key] = out_counts.get(out_key, 0) + 1
                out_max = src_port_spec.get("max_connections")
                if out_max is not None and out_counts[out_key] > out_max:
                    if src_port_spec["kind"] == "quantum":
                        errors.append(
                            f"connections[{idx}] fans out quantum output port {src_cid}.{src_port}; "
                            f"a quantum connection must transfer ownership to a single destination."
                        )
                    else:
                        errors.append(
                            f"connections[{idx}] fans out classical output port {src_cid}.{src_port} "
                            f"beyond max_connections={out_max}."
                        )

                # Input fan-in limit
                in_key = (dst_cid, dst_port)
                in_counts[in_key] = in_counts.get(in_key, 0) + 1
                in_max = dst_port_spec.get("max_connections")
                if in_max is not None and in_counts[in_key] > in_max:
                    errors.append(
                        f"connections[{idx}] fans in to {dst_port_spec['kind']} input port "
                        f"{dst_cid}.{dst_port} beyond max_connections={in_max}."
                    )

            delay = conn.get("delay", 0)
            loss_p = conn.get("loss_p", 0.0)
            depol_p = conn.get("depolarization_p", 0.0)
            if not _is_number(delay) or delay < 0:
                errors.append(f"connections[{idx}].delay must be >= 0, got {delay!r}.")
            if not _is_number(loss_p) or not (0.0 <= loss_p <= 1.0):
                errors.append(f"connections[{idx}].loss_p must be in [0, 1], got {loss_p!r}.")
            if not _is_number(depol_p) or not (0.0 <= depol_p <= 1.0):
                errors.append(f"connections[{idx}].depolarization_p must be in [0, 1], got {depol_p!r}.")
            if src_port_spec["kind"] == "classical" and (loss_p != 0.0 or depol_p != 0.0):
                errors.append(
                    f"connections[{idx}] is classical and cannot set quantum loss_p or depolarization_p."
                )

            fibre_present = [k for k in _FIBRE_KEYS if k in conn]
            if fibre_present and src_port_spec["kind"] == "classical":
                errors.append(
                    f"connections[{idx}] is classical and cannot set fibre parameters {fibre_present}."
                )
            for key in fibre_present:
                value = conn[key]
                if not _is_number(value) or value < 0:
                    errors.append(f"connections[{idx}].{key} must be a non-negative number, got {value!r}.")
            length_km = conn.get("length_km", 0.0)
            if _is_number(length_km) and length_km > 0 and run_tick_s is None:
                errors.append(
                    f"connections[{idx}] sets length_km and requires 'run.tick_duration_s' to convert fibre "
                    f"propagation delay to ticks."
                )

    measurements = doc.get("measurements", [])
    if not isinstance(measurements, list):
        errors.append("'measurements' must be a list.")
    else:
        for idx, m in enumerate(measurements):
            if not isinstance(m, dict):
                errors.append(f"measurements[{idx}] must be an object.")
                continue
            mtype = m.get("type")
            if mtype == "bell_fidelity":
                probes = m.get("probes")
                if not isinstance(probes, list) or len(probes) != 2:
                    errors.append(f"measurements[{idx}].probes must be a 2-element list of endpoint_probe IDs.")
                elif not all(isinstance(pid, str) for pid in probes):
                    errors.append(f"measurements[{idx}].probes entries must be strings.")
                elif probes[0] == probes[1]:
                    errors.append(f"measurements[{idx}].probes must reference two distinct endpoint probes.")
                else:
                    for pid in probes:
                        info = comp_map.get(pid)
                        if info is None or info[0] != "endpoint_probe":
                            errors.append(
                                f"measurements[{idx}] references {pid!r}, which is not an endpoint_probe."
                            )
            else:
                errors.append(f"measurements[{idx}] has unknown type {mtype!r}.")

    if errors:
        raise ExperimentValidationError(errors)
