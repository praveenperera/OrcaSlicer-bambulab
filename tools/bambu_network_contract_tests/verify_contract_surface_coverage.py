#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "tools/bambu_network_contract_tests"


def load_symbols(path: pathlib.Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def behavior_probe_sources() -> list[pathlib.Path]:
    return sorted(path for path in CONTRACT_DIR.glob("*.cpp") if path.name != "contract_probe.cpp")


def coverage_for(symbols: list[str], sources: list[pathlib.Path]) -> dict[str, list[str]]:
    source_text = {path.name: path.read_text(encoding="utf-8") for path in sources}
    return {
        symbol: [name for name, text in source_text.items() if symbol in text]
        for symbol in symbols
    }


def summarize(symbols: list[str], coverage: dict[str, list[str]]) -> dict[str, object]:
    missing = [symbol for symbol in symbols if not coverage[symbol]]
    return {
        "required_count": len(symbols),
        "behavior_covered_count": len(symbols) - len(missing),
        "behavior_missing_count": len(missing),
        "behavior_missing": missing,
        "covered_by": coverage,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    sources = behavior_probe_sources()
    network_symbols = load_symbols(CONTRACT_DIR / "required_symbols.txt")
    source_symbols = load_symbols(CONTRACT_DIR / "source_symbols.txt")
    network = summarize(network_symbols, coverage_for(network_symbols, sources))
    source = summarize(source_symbols, coverage_for(source_symbols, sources))
    ok = network["behavior_missing_count"] == 0 and source["behavior_missing_count"] == 0
    report = {
        "ok": ok,
        "behavior_probe_sources": [str(path.relative_to(ROOT)) for path in sources],
        "network": network,
        "source": source,
    }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif ok:
        print(
            "contract behavior probes cover "
            f"{network['behavior_covered_count']}/{network['required_count']} network symbols and "
            f"{source['behavior_covered_count']}/{source['required_count']} source symbols"
        )
    else:
        print(json.dumps(report, indent=2, sort_keys=True), file=sys.stderr)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
