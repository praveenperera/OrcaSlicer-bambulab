#!/usr/bin/env python3
import argparse
import json
import pathlib
import shutil
import subprocess
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "tools/bambu_network_contract_tests"
DEFAULT_PLUGIN_BUILD = ROOT / "build/bambu_network_rust_plugin_linux_x86_64"
DEFAULT_HOST_BUILD = ROOT / "build/pjarczak_bambu_linux_host_linux_x86_64/tools/pjarczak_bambu_linux_host"
DEFAULT_OUT_DIR = ROOT / "build/bambu_network_macos_bridge_runtime"
SOURCE_RUNTIME_DIR = ROOT / "tools/pjarczak_bambu_linux_host/runtime/linux-x86_64"


def sha256(path: pathlib.Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_file(path: pathlib.Path, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing {label}: {path}")


def require_elf(path: pathlib.Path, label: str) -> None:
    require_file(path, label)
    if path.read_bytes()[:4] != b"\x7fELF":
        raise RuntimeError(f"{label} is not a Linux ELF file: {path}")


def copy_file(source: pathlib.Path, destination: pathlib.Path, *, executable: bool = False) -> dict[str, Any]:
    require_file(source, destination.name)
    shutil.copy2(source, destination)
    if executable:
        destination.chmod(destination.stat().st_mode | 0o111)
    return {"name": destination.name, "sha256": sha256(destination), "size": destination.stat().st_size}


def run_payload_assembler(network_so: pathlib.Path, source_so: pathlib.Path, out_dir: pathlib.Path, skip_loader: bool) -> None:
    command = [
        sys.executable,
        str(CONTRACT_DIR / "assemble_candidate_linux_payload.py"),
        "--network-so",
        str(network_so),
        "--source-so",
        str(source_so),
        "--out-dir",
        str(out_dir),
    ]
    if skip_loader:
        command.append("--skip-symbol-probes")
    subprocess.run(command, cwd=ROOT, check=True)


def run_bridge_probe(host: pathlib.Path, out_dir: pathlib.Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(CONTRACT_DIR / "bridge_rpc_probe.py"),
            "--host",
            str(host),
            "--plugin-dir",
            str(out_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"bridge probe did not emit JSON: {error}\n{completed.stdout}") from error
    if completed.returncode != 0:
        raise RuntimeError(f"bridge probe failed for {host}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--network-so", type=pathlib.Path, default=DEFAULT_PLUGIN_BUILD / "libbambu_networking.so")
    parser.add_argument("--source-so", type=pathlib.Path, default=DEFAULT_PLUGIN_BUILD / "libBambuSource.so")
    parser.add_argument("--host-abi1", type=pathlib.Path, default=DEFAULT_HOST_BUILD / "pjarczak_bambu_linux_host_abi1")
    parser.add_argument("--host-abi0", type=pathlib.Path, default=DEFAULT_HOST_BUILD / "pjarczak_bambu_linux_host_abi0")
    parser.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--source-runtime-dir", action="store_true", help="write to the runtime directory consumed by Orca's macOS packaging")
    parser.add_argument("--replace-existing", action="store_true", help="allow replacing an existing source runtime directory")
    parser.add_argument("--skip-loader-probes", action="store_true", help="assemble on non-Linux hosts without dlopen/dlsym probes")
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args()

    out_dir = SOURCE_RUNTIME_DIR if args.source_runtime_dir else args.out_dir
    if args.source_runtime_dir and out_dir.exists() and any(out_dir.iterdir()) and not args.no_clean and not args.replace_existing:
        raise RuntimeError(f"{out_dir} already exists; pass --replace-existing or --no-clean")
    if out_dir.exists() and not args.no_clean:
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_payload_assembler(args.network_so, args.source_so, out_dir, args.skip_loader_probes)

    copied: list[dict[str, Any]] = []
    require_elf(args.host_abi1, "host ABI1 binary")
    require_elf(args.host_abi0, "host ABI0 binary")
    copied.append(copy_file(ROOT / "tools/pjarczak_bambu_linux_host/pjarczak-bambu-linux-host-wrapper", out_dir / "pjarczak-bambu-linux-host-wrapper", executable=True))
    copied.append(copy_file(ROOT / "tools/pjarczak_bambu_runtime/macos/pjarczak_install_macos_runtime.sh", out_dir / "install_runtime_macos.sh", executable=True))
    copied.append(copy_file(ROOT / "tools/pjarczak_bambu_runtime/macos/pjarczak_verify_macos_runtime.sh", out_dir / "verify_runtime_macos.sh", executable=True))
    copied.append(copy_file(ROOT / "tools/pjarczak_bambu_runtime/macos/pjarczak_lima_instance.txt", out_dir / "pjarczak_lima_instance.txt"))
    copied.append(copy_file(CONTRACT_DIR / "bridge_rpc_probe.py", out_dir / "bridge_rpc_probe.py", executable=True))
    copied.append(copy_file(CONTRACT_DIR / "verify_linux_bridge_runtime.py", out_dir / "verify_linux_bridge_runtime.py", executable=True))
    copied.append(copy_file(args.host_abi1, out_dir / "pjarczak_bambu_linux_host_abi1", executable=True))
    copied.append(copy_file(args.host_abi0, out_dir / "pjarczak_bambu_linux_host_abi0", executable=True))
    copied.append(copy_file(args.host_abi1, out_dir / "pjarczak_bambu_linux_host", executable=True))

    for source, name in [
        (ROOT / "resources/cert/ca-certificates.crt", "ca-certificates.crt"),
        (ROOT / "resources/cert/slicer_base64.cer", "slicer_base64.cer"),
    ]:
        copied.append(copy_file(source, out_dir / name))

    required = [
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
    ]
    missing = [name for name in required if not (out_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"runtime bundle missing required files: {missing}")

    bridge_probes: dict[str, Any] = {}
    if not args.skip_loader_probes:
        bridge_probes["abi1"] = run_bridge_probe(out_dir / "pjarczak_bambu_linux_host_abi1", out_dir)
        bridge_probes["abi0"] = run_bridge_probe(out_dir / "pjarczak_bambu_linux_host_abi0", out_dir)

    report = {
        "ok": True,
        "out_dir": str(out_dir),
        "copied_files": copied,
        "required_files": required,
        "loader_probes_skipped": args.skip_loader_probes,
        "bridge_probes": bridge_probes,
    }
    report_path = out_dir / "macos_bridge_runtime_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
