"""Command-line interface for DAMN-Q experiments."""

import argparse
import json
import sys

from damn_q.manifest import COMPONENT_MANIFEST, MANIFEST_VERSION
from damn_q.runner import SIMULATOR_VERSION, load_experiment, run_experiment
from damn_q.schema import ExperimentValidationError, SCHEMA_VERSION, validate_experiment
from damn_q.server import serve_workbench


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m damn_q",
        description="Validate and run versioned DAMN-Q quantum network experiments.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="Validate an experiment JSON file without running it.")
    p_val.add_argument("experiment", help="Path to experiment JSON file.")

    p_run = sub.add_parser("run", help="Validate and run an experiment JSON file.")
    p_run.add_argument("experiment", help="Path to experiment JSON file.")
    p_run.add_argument("--seed", type=int, default=None, help="Override RNG seed.")
    p_run.add_argument("--until", type=float, default=None, help="Override simulation duration.")
    p_run.add_argument("--json", action="store_true", dest="as_json", help="Print machine-readable JSON output.")

    sub.add_parser("manifest", help="Print the component manifest as JSON.")

    p_serve = sub.add_parser("serve", help="Launch the local browser workbench.")
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1).")
    p_serve.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000).")
    p_serve.add_argument("--no-browser", action="store_true", help="Do not open a browser window automatically.")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "manifest":
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "simulator_version": SIMULATOR_VERSION,
                    "manifest_version": MANIFEST_VERSION,
                    "components": COMPONENT_MANIFEST,
                },
                indent=2,
            )
        )
        return 0

    if args.command == "validate":
        try:
            doc = load_experiment(args.experiment)
            validate_experiment(doc)
        except (OSError, json.JSONDecodeError, ExperimentValidationError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"OK: {args.experiment} is valid (schema {SCHEMA_VERSION}).")
        return 0

    if args.command == "run":
        try:
            result = run_experiment(
                args.experiment,
                seed_override=args.seed,
                until_override=args.until,
            )
        except (OSError, json.JSONDecodeError, ExperimentValidationError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1

        if args.as_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Experiment: {result['name'] or args.experiment}")
            print(f"Final time: {result['final_time']} (seed={result['seed']})")
            for rid, counts in result["readers"].items():
                print(
                    f"Reader {rid}: 00:{counts['00']}, 01:{counts['01']}, "
                    f"10:{counts['10']}, 11:{counts['11']}"
                )
            for m in result["measurements"]:
                if m["type"] == "bell_fidelity":
                    print(
                        f"Bell fidelity ({m['probes'][0]}, {m['probes'][1]}): "
                        f"pairs={m['pairs']}, shared_register={m['all_shared_register']}, "
                        f"mean_fidelity={m['mean_fidelity']}"
                    )
        return 0

    if args.command == "serve":
        serve_workbench(host=args.host, port=args.port, open_browser=not args.no_browser)
        return 0

    return 2
