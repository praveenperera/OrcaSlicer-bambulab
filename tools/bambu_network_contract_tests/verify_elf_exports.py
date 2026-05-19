#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import subprocess
import sys
from typing import Any


def load_symbols(path: pathlib.Path) -> list[str]:
    symbols: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        symbol = line.strip()
        if symbol and not symbol.startswith("#"):
            symbols.append(symbol)
    return sorted(set(symbols))


def exported_symbols(path: pathlib.Path) -> set[str]:
    nm = os.environ.get("NM", "nm")
    completed = subprocess.run(
        [nm, "-D", "--defined-only", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{nm} failed for {path}: {completed.stderr.strip()}")

    exports: set[str] = set()
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            exports.add(parts[-1])
    return exports


def verify(plugin: pathlib.Path, symbols_path: pathlib.Path) -> dict[str, Any]:
    expected = load_symbols(symbols_path)
    exports = exported_symbols(plugin)
    present = [symbol for symbol in expected if symbol in exports]
    missing = [symbol for symbol in expected if symbol not in exports]
    return {
        "plugin": str(plugin),
        "symbols_file": str(symbols_path),
        "method": f"{os.environ.get('NM', 'nm')} -D --defined-only",
        "ok": not missing,
        "present_count": len(present),
        "missing_count": len(missing),
        "missing": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin", type=pathlib.Path, required=True)
    parser.add_argument("--symbols", type=pathlib.Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = verify(args.plugin, args.symbols)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"present: {report['present_count']}")
        print(f"missing: {report['missing_count']}")
        for symbol in report["missing"]:
            print(f"missing {symbol}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
