#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
from typing import Any


REQUIRED_FILES = (
    "pjarczak_bambu_linux_host",
    "pjarczak_bambu_linux_host_abi1",
    "pjarczak_bambu_linux_host_abi0",
    "libbambu_networking.so",
    "libBambuSource.so",
    "linux_payload_manifest.json",
    "bridge_rpc_probe.py",
)
ELF_FILES = (
    "pjarczak_bambu_linux_host",
    "pjarczak_bambu_linux_host_abi1",
    "pjarczak_bambu_linux_host_abi0",
    "libbambu_networking.so",
    "libBambuSource.so",
)


def require_file(path: pathlib.Path, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing {label}: {path}")


def require_elf(path: pathlib.Path, label: str) -> None:
    require_file(path, label)
    if path.read_bytes()[:4] != b"\x7fELF":
        raise RuntimeError(f"{label} is not a Linux ELF file: {path}")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload_file_metadata(runtime_dir: pathlib.Path) -> dict[str, dict[str, Any]]:
    payload_files: dict[str, dict[str, Any]] = {}
    for name in ("libbambu_networking.so", "libBambuSource.so"):
        path = runtime_dir / name
        payload_files[name] = {
            "sha256": sha256(path),
            "size": path.stat().st_size,
        }
    return payload_files


def load_payload_manifest(runtime_dir: pathlib.Path, payload_files: dict[str, dict[str, Any]]) -> dict[str, Any]:
    manifest_path = runtime_dir / "linux_payload_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("kind") != "bambu-network-clean-room-candidate":
        raise RuntimeError("linux payload manifest is not for the clean-room candidate")
    entries = {entry.get("name"): entry for entry in manifest.get("files", []) if isinstance(entry, dict)}
    for name, metadata in payload_files.items():
        entry = entries.get(name)
        if not entry:
            raise RuntimeError(f"linux payload manifest is missing {name}")
        if entry.get("sha256") != metadata["sha256"]:
            raise RuntimeError(f"linux payload manifest hash does not match {name}")
    return {
        "path": str(manifest_path),
        "format": manifest.get("format"),
        "kind": manifest.get("kind"),
        "files": entries,
    }


def run_bridge_probe(runtime_dir: pathlib.Path, host_name: str) -> dict[str, Any]:
    command = [
        sys.executable,
        str(runtime_dir / "bridge_rpc_probe.py"),
        "--host",
        str(runtime_dir / host_name),
        "--plugin-dir",
        str(runtime_dir),
    ]
    completed = subprocess.run(
        command,
        cwd=runtime_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        payload = {
            "error": f"bridge probe did not emit JSON: {error}",
            "stdout": completed.stdout[-4000:],
        }
    return {
        "command": command,
        "exit_code": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout_json": payload,
        "stderr": completed.stderr[-4000:] if completed.stderr else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent)
    parser.add_argument("--out", type=pathlib.Path, default=None)
    args = parser.parse_args()

    runtime_dir = args.runtime_dir.resolve()
    for name in REQUIRED_FILES:
        require_file(runtime_dir / name, name)
    for name in ELF_FILES:
        require_elf(runtime_dir / name, name)

    payload_files = payload_file_metadata(runtime_dir)
    payload_manifest = load_payload_manifest(runtime_dir, payload_files)
    abi1 = run_bridge_probe(runtime_dir, "pjarczak_bambu_linux_host_abi1")
    abi0 = run_bridge_probe(runtime_dir, "pjarczak_bambu_linux_host_abi0")
    report = {
        "ok": abi1["ok"] and abi0["ok"],
        "runtime_dir": str(runtime_dir),
        "required_files": list(REQUIRED_FILES),
        "elf_files": list(ELF_FILES),
        "payload_files": payload_files,
        "payload_manifest": payload_manifest,
        "bridge_probes": {
            "abi1": abi1,
            "abi0": abi0,
        },
    }

    out = args.out or runtime_dir / "linux_bridge_runtime_verify_report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
