#!/usr/bin/env python3
import argparse
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
NETWORK_SOURCES = [
    ROOT / "src/slic3r/Utils/BBLNetworkPlugin.cpp",
    ROOT / "src/slic3r/Utils/FileTransferUtils.cpp",
    ROOT / "tools/pjarczak_bambu_linux_host/LinuxPluginHost.cpp",
]
SOURCE_HEADER = ROOT / "src/slic3r/GUI/Printer/BambuTunnel.h"
CONTRACT_DIR = ROOT / "tools/bambu_network_contract_tests"
NETWORK_PATTERN = re.compile(r'"((?:bambu_network|ft)_[A-Za-z0-9_]+)"')
SOURCE_PATTERN = re.compile(r"BAMBU_FUNC\((Bambu_[A-Za-z0-9_]+)\)")


def generated_network_symbols() -> list[str]:
    symbols = set()
    for source in NETWORK_SOURCES:
        text = source.read_text(encoding="utf-8", errors="ignore")
        symbols.update(NETWORK_PATTERN.findall(text))
    return sorted(symbols)


def generated_source_symbols() -> list[str]:
    text = SOURCE_HEADER.read_text(encoding="utf-8", errors="ignore")
    return sorted(set(SOURCE_PATTERN.findall(text)))


def read_manifest(path: pathlib.Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_manifest(name: str, expected: list[str], manifest_path: pathlib.Path) -> list[str]:
    actual = read_manifest(manifest_path)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if not missing and not extra:
        return []

    failures = [f"{name} symbol manifest drift: {manifest_path}"]
    if missing:
        failures.append("  missing from manifest:")
        failures.extend(f"    {symbol}" for symbol in missing)
    if extra:
        failures.append("  extra in manifest:")
        failures.extend(f"    {symbol}" for symbol in extra)
    return failures


def print_symbols(symbols: list[str]) -> None:
    for symbol in symbols:
        print(symbol)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("network", "source", "all"), default="network")
    parser.add_argument("--check", action="store_true", help="verify checked-in symbol manifests match generated symbols")
    args = parser.parse_args()

    network_symbols = generated_network_symbols()
    source_symbols = generated_source_symbols()

    if args.check:
        failures = []
        failures.extend(check_manifest("network", network_symbols, CONTRACT_DIR / "required_symbols.txt"))
        failures.extend(check_manifest("source", source_symbols, CONTRACT_DIR / "source_symbols.txt"))
        if failures:
            print("\n".join(failures), file=sys.stderr)
            return 1
        print("required symbol manifests match public loader sources")
        return 0

    if args.kind == "network":
        print_symbols(network_symbols)
    elif args.kind == "source":
        print_symbols(source_symbols)
    else:
        print_symbols(network_symbols)
        print_symbols(source_symbols)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
