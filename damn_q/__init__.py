"""DAMN-Q experiment format, validation, runner, and CLI."""

from damn_q.manifest import CHANNEL_MANIFEST, COMPONENT_MANIFEST, get_component_spec
from damn_q.runner import SIMULATOR_VERSION, run_experiment
from damn_q.schema import ExperimentValidationError, SCHEMA_VERSION, validate_experiment

__version__ = SIMULATOR_VERSION

__all__ = [
    "CHANNEL_MANIFEST",
    "COMPONENT_MANIFEST",
    "ExperimentValidationError",
    "SCHEMA_VERSION",
    "SIMULATOR_VERSION",
    "__version__",
    "get_component_spec",
    "run_experiment",
    "validate_experiment",
]
