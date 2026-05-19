#!/usr/bin/env python3
import json
import pathlib
import sys


IGNORED_KEYS = {
    "diagnostics",
    "network_plugin",
    "plugin",
    "source_plugin",
    "log_dir",
}


def load_json(path: pathlib.Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return data


def comparable(data: dict) -> dict:
    return {key: value for key, value in sorted(data.items()) if key not in IGNORED_KEYS}


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <official.json> <candidate.json>", file=sys.stderr)
        return 2

    official_path = pathlib.Path(sys.argv[1])
    candidate_path = pathlib.Path(sys.argv[2])
    official = comparable(load_json(official_path))
    candidate = comparable(load_json(candidate_path))

    all_keys = sorted(set(official) | set(candidate))
    differences = []
    for key in all_keys:
        if official.get(key) != candidate.get(key):
            differences.append((key, official.get(key), candidate.get(key)))

    if not differences:
        print("transcripts match")
        return 0

    print("transcripts differ")
    for key, official_value, candidate_value in differences:
        print(f"{key}:")
        print(f"  official:  {json.dumps(official_value, sort_keys=True)}")
        print(f"  candidate: {json.dumps(candidate_value, sort_keys=True)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
