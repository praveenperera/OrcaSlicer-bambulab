#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Any


def require_elf(path: pathlib.Path) -> None:
    magic = path.read_bytes()[:4]
    if magic != b"\x7fELF":
        raise RuntimeError(f"{path} is not an ELF binary")


def run_command(command: list[str]) -> subprocess.CompletedProcess:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{command[0]} failed for {command[-1]}: {completed.stderr.strip()}")
    return completed


def dynamic_symbols(path: pathlib.Path) -> list[str]:
    completed = run_command([os.environ.get("NM", "nm"), "-D", "--demangle", str(path)])
    return completed.stdout.splitlines()


def needed_libraries(path: pathlib.Path) -> list[str]:
    objdump = os.environ.get("OBJDUMP", "objdump")
    if not shutil.which(objdump):
        return []

    completed = run_command([objdump, "-p", str(path)])
    libraries: list[str] = []
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "NEEDED":
            libraries.append(parts[1])
    return libraries


def truncated_samples(lines: list[str], marker: str) -> list[str]:
    samples = [line.strip() for line in lines if marker in line]
    return [sample[:300] for sample in samples[:8]]


def infer_abi(symbols: list[str], needed: list[str]) -> str:
    has_libcxx = any("std::__1" in symbol for symbol in symbols) or any("libc++" in library for library in needed)
    has_libstdcxx = (
        any("std::__cxx11" in symbol or "GLIBCXX_" in symbol for symbol in symbols)
        or any("libstdc++" in library for library in needed)
    )
    if has_libcxx and has_libstdcxx:
        return "mixed"
    if has_libcxx:
        return "libc++"
    if has_libstdcxx:
        return "libstdc++"
    return "unknown"


def verify(path: pathlib.Path, expect: str) -> dict[str, Any]:
    require_elf(path)
    symbols = dynamic_symbols(path)
    needed = needed_libraries(path)
    inferred = infer_abi(symbols, needed)
    ok = expect == "any" or inferred == expect
    return {
        "plugin": str(path),
        "method": "nm -D --demangle plus objdump -p",
        "expected": expect,
        "inferred": inferred,
        "ok": ok,
        "needed_libraries": needed,
        "libcxx_symbol_count": sum(1 for symbol in symbols if "std::__1" in symbol),
        "libstdcxx_symbol_count": sum(1 for symbol in symbols if "std::__cxx11" in symbol or "GLIBCXX_" in symbol),
        "libcxx_samples": truncated_samples(symbols, "std::__1"),
        "libstdcxx_samples": truncated_samples(symbols, "std::__cxx11"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin", type=pathlib.Path, required=True)
    parser.add_argument("--expect", choices=["any", "libc++", "libstdc++"], default="any")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = verify(args.plugin, args.expect)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"inferred: {report['inferred']}")
        print(f"expected: {report['expected']}")
        print(f"needed: {', '.join(report['needed_libraries'])}")
        print(f"libc++ symbols: {report['libcxx_symbol_count']}")
        print(f"libstdc++ symbols: {report['libstdcxx_symbol_count']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
