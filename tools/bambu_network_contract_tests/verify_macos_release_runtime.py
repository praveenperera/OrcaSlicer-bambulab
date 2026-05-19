#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_DIR = ROOT / "build/bambu_network_macos_bridge_runtime"
REQUIRED_RUNTIME_FILES = (
    "pjarczak_bambu_linux_host",
    "pjarczak_bambu_linux_host_abi1",
    "pjarczak_bambu_linux_host_abi0",
    "pjarczak-bambu-linux-host-wrapper",
    "install_runtime_macos.sh",
    "verify_runtime_macos.sh",
    "bridge_rpc_probe.py",
    "verify_linux_bridge_runtime.py",
    "pjarczak_lima_instance.txt",
    "libbambu_networking.so",
    "libBambuSource.so",
    "linux_payload_manifest.json",
    "ca-certificates.crt",
    "slicer_base64.cer",
)
ELF_RUNTIME_FILES = (
    "pjarczak_bambu_linux_host",
    "pjarczak_bambu_linux_host_abi1",
    "pjarczak_bambu_linux_host_abi0",
    "libbambu_networking.so",
    "libBambuSource.so",
)
EXECUTABLE_RUNTIME_FILES = (
    "pjarczak_bambu_linux_host",
    "pjarczak_bambu_linux_host_abi1",
    "pjarczak_bambu_linux_host_abi0",
    "pjarczak-bambu-linux-host-wrapper",
    "install_runtime_macos.sh",
    "verify_runtime_macos.sh",
    "bridge_rpc_probe.py",
    "verify_linux_bridge_runtime.py",
)
COPIED_APP_FILES = REQUIRED_RUNTIME_FILES + ("libpjarczak_bambu_networking_bridge.dylib",)
BRIDGE_DYLIB_FIXTURE_KIND = "copy-path-fixture"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_metadata(path: pathlib.Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": sha256(path),
        "size": path.stat().st_size,
    }


def require_file(path: pathlib.Path, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing {label}: {path}")


def require_elf(path: pathlib.Path, label: str) -> None:
    require_file(path, label)
    if path.read_bytes()[:4] != b"\x7fELF":
        raise RuntimeError(f"{label} is not a Linux ELF file: {path}")


def require_executable(path: pathlib.Path, label: str) -> None:
    require_file(path, label)
    if not os.access(path, os.X_OK):
        raise RuntimeError(f"{label} is not executable: {path}")


def load_manifest(runtime_dir: pathlib.Path) -> dict[str, Any]:
    manifest_path = runtime_dir / "linux_payload_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("kind") != "bambu-network-clean-room-candidate":
        raise RuntimeError("linux payload manifest is not for the clean-room candidate")
    entries = {entry.get("name"): entry for entry in payload.get("files", []) if isinstance(entry, dict)}
    for name in ("libbambu_networking.so", "libBambuSource.so"):
        entry = entries.get(name)
        if not entry:
            raise RuntimeError(f"manifest is missing payload entry for {name}")
        actual_hash = sha256(runtime_dir / name)
        if entry.get("sha256") != actual_hash:
            raise RuntimeError(f"manifest hash mismatch for {name}")
    return payload


def verify_runtime_dir(runtime_dir: pathlib.Path) -> dict[str, Any]:
    for name in REQUIRED_RUNTIME_FILES:
        require_file(runtime_dir / name, name)
    for name in ELF_RUNTIME_FILES:
        require_elf(runtime_dir / name, name)
    for name in EXECUTABLE_RUNTIME_FILES:
        require_executable(runtime_dir / name, name)

    manifest = load_manifest(runtime_dir)
    report_path = runtime_dir / "macos_bridge_runtime_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
    if report is not None and report.get("ok") is not True:
        raise RuntimeError("macOS bridge runtime report is not ok")

    return {
        "required_files": list(REQUIRED_RUNTIME_FILES),
        "elf_files": list(ELF_RUNTIME_FILES),
        "executable_files": list(EXECUTABLE_RUNTIME_FILES),
        "manifest": str(runtime_dir / "linux_payload_manifest.json"),
        "runtime_report": str(report_path) if report_path.exists() else None,
        "payload_manifest_format": manifest.get("format"),
    }


def run_release_script_copy(build_script: pathlib.Path, runtime_dir: pathlib.Path, out_dir: pathlib.Path) -> dict[str, Any]:
    scratch = out_dir / "copy_scratch"
    if scratch.exists():
        shutil.rmtree(scratch)
    macos_dir = scratch / "OrcaSlicer.app/Contents/MacOS"
    install_root = scratch / "install_root"
    macos_dir.mkdir(parents=True)
    install_root.mkdir(parents=True)
    bridge_dylib = install_root / "libpjarczak_bambu_networking_bridge.dylib"
    bridge_dylib.write_text("fake bridge dylib for runtime-copy verification\n", encoding="utf-8")

    env = os.environ.copy()
    env.update({
        "PJARCZAK_BAMBU_COPY_RUNTIME_ONLY": "1",
        "PJARCZAK_BAMBU_COPY_APP_PATH": str(scratch / "OrcaSlicer.app"),
        "PJARCZAK_BAMBU_COPY_INSTALL_ROOT": str(install_root),
        "PJARCZAK_BAMBU_HOST_RUNTIME_DIR": str(runtime_dir),
        "PJARCZAK_BAMBU_HOST_WRAPPER": str(runtime_dir / "pjarczak-bambu-linux-host-wrapper"),
    })
    completed = subprocess.run(
        ["bash", str(build_script)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    (out_dir / "copy_stdout.txt").write_text(completed.stdout, encoding="utf-8")
    if completed.stderr:
        (out_dir / "copy_stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"release runtime copy failed with exit code {completed.returncode}")

    missing = [name for name in COPIED_APP_FILES if not (macos_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"release runtime copy missed files: {missing}")
    for name in (
        "pjarczak_bambu_linux_host",
        "pjarczak-bambu-linux-host-wrapper",
        "install_runtime_macos.sh",
        "verify_runtime_macos.sh",
        "bridge_rpc_probe.py",
        "verify_linux_bridge_runtime.py",
    ):
        require_executable(macos_dir / name, f"copied {name}")

    copied_metadata: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_RUNTIME_FILES:
        source = runtime_dir / name
        copied = macos_dir / name
        source_metadata = file_metadata(source)
        copied_metadata[name] = file_metadata(copied)
        if copied_metadata[name]["sha256"] != source_metadata["sha256"]:
            raise RuntimeError(f"release runtime copy changed {name}")
        if copied_metadata[name]["size"] != source_metadata["size"]:
            raise RuntimeError(f"release runtime copy changed {name} size")

    bridge_metadata = file_metadata(bridge_dylib)
    copied_metadata["libpjarczak_bambu_networking_bridge.dylib"] = file_metadata(macos_dir / "libpjarczak_bambu_networking_bridge.dylib")
    if copied_metadata["libpjarczak_bambu_networking_bridge.dylib"]["sha256"] != bridge_metadata["sha256"]:
        raise RuntimeError("release runtime copy changed libpjarczak_bambu_networking_bridge.dylib")

    return {
        "command": ["bash", str(build_script)],
        "exit_code": completed.returncode,
        "stdout": str(out_dir / "copy_stdout.txt"),
        "stderr": str(out_dir / "copy_stderr.txt") if completed.stderr else None,
        "app_macos_dir": str(macos_dir),
        "copied_files": list(COPIED_APP_FILES),
        "copied_file_metadata": copied_metadata,
        "bridge_dylib_fixture": {
            "kind": BRIDGE_DYLIB_FIXTURE_KIND,
            "path": str(bridge_dylib),
            "note": "copy-path verification uses a fixture dylib and does not prove the built bridge dylib loads",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=pathlib.Path, default=DEFAULT_RUNTIME_DIR)
    parser.add_argument("--build-script", type=pathlib.Path, default=ROOT / "build_release_macos.sh")
    parser.add_argument("--out-dir", type=pathlib.Path, default=ROOT / "build/bambu_network_macos_bridge_runtime_verify")
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args()

    if args.out_dir.exists() and not args.no_clean:
        shutil.rmtree(args.out_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    runtime = verify_runtime_dir(args.runtime_dir)
    copy = run_release_script_copy(args.build_script, args.runtime_dir, args.out_dir)
    report = {
        "ok": True,
        "runtime_dir": str(args.runtime_dir),
        "runtime": runtime,
        "release_script_copy": copy,
    }
    report_path = args.out_dir / "macos_release_runtime_verify_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
