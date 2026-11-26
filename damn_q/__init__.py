"""DAMN-Q experiment format, validation, runner, and CLI."""

from damn_q.manifest import COMPONENT_MANIFEST, get_component_spec
from damn_q.runner import run_experiment
from damn_q.schema import ExperimentValidationError, SCHEMA_VERSION, validate_experiment

__all__ = [
    "COMPONENT_MANIFEST",
    "ExperimentValidationError",
    "SCHEMA_VERSION",
    "get_component_spec",
    "run_experiment",
    "validate_experiment",
]
