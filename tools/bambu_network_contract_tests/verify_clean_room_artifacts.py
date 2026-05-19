#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import pathlib
import sys
import tempfile
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
BINARY_MAGICS = (
    (b"\x7fELF", "ELF"),
    (b"\xcf\xfa\xed\xfe", "Mach-O"),
    (b"\xfe\xed\xfa\xcf", "Mach-O"),
    (b"\xca\xfe\xba\xbe", "Mach-O universal"),
    (b"\xca\xfe\xba\xbf", "Mach-O universal"),
    (b"MZ", "PE/COFF"),
)
MIN_SECRET_LENGTH = 8
SECRET_KEY_PARTS = ("token", "ticket", "password", "secret")


def is_relative_to(path: pathlib.Path, parent: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def load_report(path: pathlib.Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("parity report is not a JSON object")
    return payload


def require_artifact_policy(report: dict[str, Any]) -> dict[str, Any]:
    inputs = report.get("inputs")
    if not isinstance(inputs, dict):
        raise RuntimeError("parity report is missing inputs")
    policy = inputs.get("artifact_policy")
    if not isinstance(policy, dict):
        raise RuntimeError("parity report is missing artifact_policy")
    if policy.get("copies_input_binaries") is not False:
        raise RuntimeError("artifact policy does not forbid copying input binaries")
    if policy.get("stores_hashes_and_probe_transcripts_only") is not True:
        raise RuntimeError("artifact policy does not limit artifacts to hashes and transcripts")
    return inputs


def require_official_inputs_outside_repo(inputs: dict[str, Any]) -> list[str]:
    official = inputs.get("official")
    if not isinstance(official, dict):
        raise RuntimeError("parity report is missing official input metadata")
    checked: list[str] = []
    for label in ("network", "source"):
        metadata = official.get(label)
        if not isinstance(metadata, dict):
            raise RuntimeError(f"parity report is missing official {label} metadata")
        path = pathlib.Path(str(metadata.get("path", "")))
        if not metadata.get("exists"):
            raise RuntimeError(f"official {label} input did not exist when parity was captured")
        if is_relative_to(path, ROOT):
            raise RuntimeError(f"official {label} input is inside the repository: {path}")
        checked.append(str(path))
    return checked


def scan_for_binary_artifacts(artifact_dir: pathlib.Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in artifact_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            header = path.read_bytes()[:8]
        except OSError:
            continue
        for magic, kind in BINARY_MAGICS:
            if header.startswith(magic):
                findings.append({
                    "path": str(path),
                    "kind": kind,
                    "size": path.stat().st_size,
                })
                break
    return findings


def official_binary_metadata(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    official = inputs.get("official")
    if not isinstance(official, dict):
        raise RuntimeError("parity report is missing official input metadata")

    metadata: list[dict[str, Any]] = []
    for label in ("network", "source"):
        item = official.get(label)
        if not isinstance(item, dict):
            raise RuntimeError(f"parity report is missing official {label} metadata")
        sha256 = item.get("sha256")
        size = item.get("size")
        if isinstance(sha256, str) and isinstance(size, int):
            metadata.append({
                "label": label,
                "path": item.get("path"),
                "sha256": sha256,
                "size": size,
            })
    return metadata


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def secret_fingerprint(value: str) -> dict[str, Any]:
    return {
        "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        "length": len(value),
    }


def candidate_secret(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if len(stripped) < MIN_SECRET_LENGTH:
        return None
    return stripped


def extract_json_secret_values(value: Any, key_hint: str = "") -> list[str]:
    if isinstance(value, dict):
        found: list[str] = []
        for key, item in value.items():
            found.extend(extract_json_secret_values(item, str(key)))
        return found
    if isinstance(value, list):
        found = []
        for item in value:
            found.extend(extract_json_secret_values(item, key_hint))
        return found
    if isinstance(value, str) and any(part in key_hint.lower() for part in SECRET_KEY_PARTS):
        secret = candidate_secret(value)
        return [secret] if secret else []
    return []


def read_secret_file_values(path: pathlib.Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    values = []
    whole_file = candidate_secret(text)
    if whole_file:
        values.append(whole_file)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return values
    values.extend(extract_json_secret_values(payload))
    return values


def collect_forbidden_secrets(secret_env_names: list[str], secret_files: list[pathlib.Path]) -> list[dict[str, Any]]:
    secrets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in secret_env_names:
        value = candidate_secret(os.environ.get(name))
        if value and value not in seen:
            seen.add(value)
            secrets.append({"source": f"env:{name}", "value": value, **secret_fingerprint(value)})
    for path in secret_files:
        for value in read_secret_file_values(path):
            if value and value not in seen:
                seen.add(value)
                secrets.append({"source": f"file:{path}", "value": value, **secret_fingerprint(value)})
    return secrets


def scan_for_secret_leaks(artifact_dir: pathlib.Path, secrets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not secrets:
        return []

    findings: list[dict[str, Any]] = []
    for path in artifact_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for secret in secrets:
            value = secret["value"]
            if value in text:
                findings.append({
                    "path": str(path),
                    "secret_source": secret["source"],
                    "secret_sha256": secret["sha256"],
                    "secret_length": secret["length"],
                })
    return findings


def scan_for_official_binary_copies(
    scan_dirs: list[pathlib.Path],
    official_metadata: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not official_metadata:
        return []

    official_by_size: dict[int, list[dict[str, Any]]] = {}
    for item in official_metadata:
        official_by_size.setdefault(item["size"], []).append(item)

    findings: list[dict[str, Any]] = []
    for directory in scan_dirs:
        if not directory.is_dir():
            raise RuntimeError(f"copy-scan directory does not exist: {directory}")
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            candidates = official_by_size.get(path.stat().st_size, [])
            if not candidates:
                continue
            file_hash = sha256_file(path)
            for item in candidates:
                if file_hash == item["sha256"]:
                    findings.append({
                        "path": str(path),
                        "matches_official": item["label"],
                        "official_path": item.get("path"),
                        "sha256": file_hash,
                        "size": path.stat().st_size,
                    })
    return findings


def validate_clean_room_artifacts(
    parity_report: pathlib.Path,
    artifact_dir: pathlib.Path | None,
    allow_official_inside_repo: bool,
    official_binary_copy_scan_dirs: list[pathlib.Path],
    forbidden_secret_env_names: list[str] | None = None,
    forbidden_secret_files: list[pathlib.Path] | None = None,
) -> dict[str, Any]:
    report = load_report(parity_report)
    inputs = require_artifact_policy(report)
    official_metadata = official_binary_metadata(inputs)
    official_inputs = []
    if allow_official_inside_repo:
        official = inputs.get("official", {})
        if isinstance(official, dict):
            official_inputs = [
                str(metadata.get("path"))
                for metadata in official.values()
                if isinstance(metadata, dict) and metadata.get("path")
            ]
    else:
        official_inputs = require_official_inputs_outside_repo(inputs)

    artifact_dir = artifact_dir or parity_report.parent
    binary_artifacts = scan_for_binary_artifacts(artifact_dir)
    if binary_artifacts:
        raise RuntimeError(f"artifact directory contains binary files: {binary_artifacts}")

    forbidden_secrets = collect_forbidden_secrets(
        forbidden_secret_env_names or [],
        forbidden_secret_files or [],
    )
    secret_leak_findings = scan_for_secret_leaks(artifact_dir, forbidden_secrets)
    if secret_leak_findings:
        raise RuntimeError(f"artifact directory contains forbidden secret values: {secret_leak_findings}")

    official_copy_findings = scan_for_official_binary_copies(
        official_binary_copy_scan_dirs,
        official_metadata,
    )
    if official_copy_findings:
        raise RuntimeError(f"release/source directories contain official binary copies: {official_copy_findings}")

    return {
        "ok": True,
        "parity_report": str(parity_report),
        "artifact_dir": str(artifact_dir),
        "official_inputs": official_inputs,
        "official_inputs_allowed_inside_repo": allow_official_inside_repo,
        "binary_artifacts": binary_artifacts,
        "forbidden_secret_sources": [
            {
                "source": secret["source"],
                "sha256": secret["sha256"],
                "length": secret["length"],
            }
            for secret in forbidden_secrets
        ],
        "secret_leak_findings": secret_leak_findings,
        "official_binary_copy_scan_dirs": [str(path) for path in official_binary_copy_scan_dirs],
        "official_binary_copy_findings": official_copy_findings,
    }


def write_fixture_report(path: pathlib.Path, official_network: pathlib.Path, official_source: pathlib.Path) -> None:
    payload = {
        "inputs": {
            "official": {
                "network": {
                    "path": str(official_network),
                    "exists": True,
                    "size": official_network.stat().st_size,
                    "sha256": sha256_file(official_network),
                },
                "source": {
                    "path": str(official_source),
                    "exists": True,
                    "size": official_source.stat().st_size,
                    "sha256": sha256_file(official_source),
                },
            },
            "artifact_policy": {
                "copies_input_binaries": False,
                "stores_hashes_and_probe_transcripts_only": True,
            },
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def expect_failure(description: str, action: Any, expected: str) -> None:
    try:
        action()
    except RuntimeError as error:
        if expected not in str(error):
            raise RuntimeError(f"{description} failed with wrong error: {error}") from error
        return
    raise RuntimeError(f"{description} unexpectedly passed")


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="bambu-clean-room-artifacts-") as tmp:
        work = pathlib.Path(tmp)
        official_dir = work / "official"
        artifact_dir = work / "artifacts"
        clean_release_dir = work / "clean-release"
        copied_release_dir = work / "copied-release"
        official_dir.mkdir()
        artifact_dir.mkdir()
        clean_release_dir.mkdir()
        copied_release_dir.mkdir()

        official_network = official_dir / "libbambu_networking.dylib"
        official_source = official_dir / "libBambuSource.dylib"
        official_network.write_bytes(b"official-network-fixture")
        official_source.write_bytes(b"official-source-fixture")
        (artifact_dir / "network.json").write_text('{"ok": true}\n', encoding="utf-8")
        (clean_release_dir / "libbambu_networking.dylib").write_bytes(b"clean-room-candidate-fixture")
        report = artifact_dir / "parity_report.json"
        write_fixture_report(report, official_network, official_source)

        clean = validate_clean_room_artifacts(
            report,
            artifact_dir,
            True,
            [clean_release_dir],
        )
        if clean["official_binary_copy_findings"] != []:
            raise RuntimeError(f"clean release directory reported official copies: {clean}")

        (copied_release_dir / "libBambuSource.dylib").write_bytes(official_source.read_bytes())
        expect_failure(
            "official binary copy detection",
            lambda: validate_clean_room_artifacts(report, artifact_dir, True, [copied_release_dir]),
            "official binary copies",
        )

        secret_file = work / "secret-login.json"
        secret_file.write_text('{"access_token":"real-secret-token-value"}\n', encoding="utf-8")
        (artifact_dir / "leaked-secret.json").write_text(
            '{"bad":"real-secret-token-value"}\n',
            encoding="utf-8",
        )
        expect_failure(
            "secret leak detection",
            lambda: validate_clean_room_artifacts(report, artifact_dir, True, [], [], [secret_file]),
            "forbidden secret values",
        )
        (artifact_dir / "leaked-secret.json").unlink()

        (artifact_dir / "copied-binary.so").write_bytes(b"\x7fELFfixture")
        expect_failure(
            "binary artifact detection",
            lambda: validate_clean_room_artifacts(report, artifact_dir, True, []),
            "artifact directory contains binary files",
        )
        (artifact_dir / "copied-binary.so").unlink()

        repo_fixture = work / "repo-official.json"
        write_fixture_report(repo_fixture, ROOT / "README.md", official_source)
        expect_failure(
            "official input inside repo detection",
            lambda: validate_clean_room_artifacts(repo_fixture, work, False, []),
            "official network input is inside the repository",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parity-report", type=pathlib.Path)
    parser.add_argument("--artifact-dir", type=pathlib.Path, default=None)
    parser.add_argument("--allow-official-inside-repo", action="store_true", help="only for harness self-tests")
    parser.add_argument(
        "--forbid-official-binary-copies-in",
        action="append",
        default=[],
        type=pathlib.Path,
        help="scan a release/source directory and fail if it contains a byte-for-byte copy of an official input binary",
    )
    parser.add_argument(
        "--forbid-secret-env",
        action="append",
        default=[],
        help="scan artifacts and fail if the current value of this environment variable is written",
    )
    parser.add_argument(
        "--forbid-secret-file",
        action="append",
        default=[],
        type=pathlib.Path,
        help="scan artifacts and fail if this file's content is written",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print("clean-room artifact validation checks passed")
        return 0
    if args.parity_report is None:
        parser.error("--parity-report is required unless --self-test is used")

    result = validate_clean_room_artifacts(
        args.parity_report,
        args.artifact_dir,
        args.allow_official_inside_repo,
        args.forbid_official_binary_copies_in,
        args.forbid_secret_env,
        args.forbid_secret_file,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
