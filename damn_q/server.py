"""Local HTTP server for the DAMN-Q browser workbench.

Serves the static web UI and exposes JSON endpoints backed directly by
`damn_q.manifest`, `damn_q.schema.validate_experiment`, and
`damn_q.runner.run_experiment` — the exact same path used by the CLI.
"""

import json
import mimetypes
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from damn_q.manifest import CHANNEL_MANIFEST, COMPONENT_MANIFEST, MANIFEST_VERSION
from damn_q.runner import SIMULATOR_VERSION, load_experiment, run_experiment
from damn_q.schema import ExperimentValidationError, SCHEMA_VERSION, validate_experiment

WEB_DIR = Path(__file__).resolve().parent / "web"
DEFAULT_EXPERIMENTS_DIR = Path(__file__).resolve().parent.parent / "experiments"
MAX_BODY_BYTES = 5 * 1024 * 1024


def _json_bytes(payload):
    return json.dumps(payload, indent=2).encode("utf-8")


def _list_examples(experiments_dir):
    if not experiments_dir.is_dir():
        return []
    items = []
    for path in sorted(experiments_dir.glob("*.json")):
        try:
            doc = load_experiment(path)
        except (OSError, json.JSONDecodeError):
            continue
        items.append(
            {
                "filename": path.name,
                "name": doc.get("name", path.stem),
                "description": doc.get("description", ""),
            }
        )
    return items


def _make_handler(web_dir, experiments_dir):
    web_root = web_dir.resolve()
    exp_root = experiments_dir.resolve()

    class WorkbenchHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Keep server stdout/stderr clean during tests and CLI usage
            return

        def _send_bytes(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status, payload):
            self._send_bytes(status, _json_bytes(payload), "application/json; charset=utf-8")

        def _read_json_body(self):
            raw_len = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_len)
            except ValueError:
                return None, "Invalid Content-Length header."
            if length < 0 or length > MAX_BODY_BYTES:
                return None, f"Request body size out of range (max {MAX_BODY_BYTES} bytes)."
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8")), None
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                return None, f"Invalid JSON payload: {exc}"

        def _serve_file(self, rel_path):
            candidate = (web_root / rel_path).resolve()
            if web_root not in candidate.parents and candidate != web_root:
                self._send_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Forbidden path."})
                return
            if not candidate.is_file():
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "File not found."})
                return
            ctype, _ = mimetypes.guess_type(str(candidate))
            if ctype is None:
                ctype = "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype = f"{ctype}; charset=utf-8"
            self._send_bytes(HTTPStatus.OK, candidate.read_bytes(), ctype)

        def do_GET(self):
            parsed = urllib.parse.urlsplit(self.path)
            path = parsed.path

            if path == "/" or path == "/index.html":
                self._serve_file("index.html")
                return

            if path.startswith("/static/"):
                rel = urllib.parse.unquote(path[len("/static/"):])
                self._serve_file(rel)
                return

            if path == "/api/manifest":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "schema_version": SCHEMA_VERSION,
                        "manifest_version": MANIFEST_VERSION,
                        "simulator_version": SIMULATOR_VERSION,
                        "channels": CHANNEL_MANIFEST,
                        "components": COMPONENT_MANIFEST,
                    },
                )
                return

            if path == "/api/examples":
                self._send_json(HTTPStatus.OK, {"examples": _list_examples(exp_root)})
                return

            if path.startswith("/api/examples/"):
                filename = urllib.parse.unquote(path[len("/api/examples/"):])
                if "/" in filename or "\\" in filename or not filename.endswith(".json"):
                    self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Invalid example filename."})
                    return
                candidate = (exp_root / filename).resolve()
                if exp_root not in candidate.parents or not candidate.is_file():
                    self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": f"Example {filename!r} not found."})
                    return
                try:
                    doc = load_experiment(candidate)
                except (OSError, json.JSONDecodeError) as exc:
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
                    return
                self._send_json(HTTPStatus.OK, doc)
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": f"Unknown route: {path}"})

        def do_POST(self):
            parsed = urllib.parse.urlsplit(self.path)
            path = parsed.path

            if path == "/api/validate":
                doc, err = self._read_json_body()
                if err is not None:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "errors": [err], "error": err})
                    return
                try:
                    validate_experiment(doc)
                except ExperimentValidationError as exc:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"ok": False, "errors": exc.errors, "error": str(exc)},
                    )
                    return
                self._send_json(HTTPStatus.OK, {"ok": True, "schema_version": SCHEMA_VERSION})
                return

            if path == "/api/run":
                doc, err = self._read_json_body()
                if err is not None:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "errors": [err], "error": err})
                    return
                try:
                    result = run_experiment(doc)
                except ExperimentValidationError as exc:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"ok": False, "errors": exc.errors, "error": str(exc)},
                    )
                    return
                except ValueError as exc:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"ok": False, "errors": [str(exc)], "error": str(exc)},
                    )
                    return
                self._send_json(HTTPStatus.OK, {"ok": True, "result": result})
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": f"Unknown route: {path}"})

    return WorkbenchHandler


def create_server(host="127.0.0.1", port=8000, *, web_dir=None, experiments_dir=None):
    """Create a configured ThreadingHTTPServer for the DAMN-Q workbench."""
    handler_cls = _make_handler(
        Path(web_dir) if web_dir is not None else WEB_DIR,
        Path(experiments_dir) if experiments_dir is not None else DEFAULT_EXPERIMENTS_DIR,
    )
    return ThreadingHTTPServer((host, port), handler_cls)


def serve_workbench(host="127.0.0.1", port=8000, *, open_browser=True):
    """Start the DAMN-Q browser workbench and block until interrupted."""
    server = create_server(host=host, port=port)
    actual_host, actual_port = server.server_address
    url = f"http://{actual_host}:{actual_port}/"
    print(f"DAMN-Q Workbench running at {url} (Press Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping DAMN-Q Workbench.")
    finally:
        server.server_close()
