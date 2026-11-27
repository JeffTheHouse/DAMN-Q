"""Build the JSON source bundle consumed by `damn_q/web/pyodide_worker.js`.

Automatically walks the AST import closure of `damn_q/` so every local runtime
dependency (including top-level simulator modules) is packaged and never drifts.

Usage:
    python -m damn_q.web_bundle --out damn_q_bundle.json
"""

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _resolve_local_module(root: Path, mod_name: str):
    """Return relative POSIX path(s) for a local module name if it exists under `root`."""
    if not mod_name:
        return []
    parts = mod_name.split(".")
    # Check module.py
    py_file = root.joinpath(*parts).with_suffix(".py")
    if py_file.is_file():
        return [py_file.relative_to(root).as_posix()]
    # Check package/__init__.py
    pkg_init = root.joinpath(*parts, "__init__.py")
    if pkg_init.is_file():
        return [pkg_init.relative_to(root).as_posix()]
    return []


def _extract_imported_modules(source: str):
    tree = ast.parse(source)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
            names.add(node.module.split(".")[0])
            for alias in node.names:
                if alias.name != "*":
                    names.add(f"{node.module}.{alias.name}")
    return names


def build_pyodide_bundle(root: Path = ROOT) -> dict:
    """Return a mapping of relative POSIX paths -> UTF-8 Python source strings.

    Seeds with all `damn_q/*.py` files and recursively includes every local
    top-level module imported anywhere in the closure.
    """
    root = Path(root).resolve()
    files = {}
    queue = []

    pkg_dir = root / "damn_q"
    for p in sorted(pkg_dir.glob("*.py")):
        rel = p.relative_to(root).as_posix()
        queue.append(rel)

    while queue:
        rel = queue.pop(0)
        if rel in files:
            continue
        full_path = root / rel
        if not full_path.is_file():
            continue
        src = full_path.read_text(encoding="utf-8")
        files[rel] = src
        for mod_name in sorted(_extract_imported_modules(src)):
            for dep_rel in _resolve_local_module(root, mod_name):
                if dep_rel not in files:
                    queue.append(dep_rel)

    return dict(sorted(files.items()))


def write_pyodide_bundle(output_path: Path, root: Path = ROOT) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bundle = build_pyodide_bundle(root=root)
    output_path.write_text(json.dumps(bundle), encoding="utf-8")
    return output_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build DAMN-Q Pyodide worker bundle JSON.")
    parser.add_argument("--out", default="damn_q_bundle.json", help="Output JSON path (default: damn_q_bundle.json).")
    args = parser.parse_args(argv)
    out = write_pyodide_bundle(Path(args.out))
    print(f"Wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
