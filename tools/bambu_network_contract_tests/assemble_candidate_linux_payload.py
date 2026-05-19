#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN_BUILD = ROOT / "build/bambu_network_rust_plugin"
CONTRACT_DIR = ROOT / "tools/bambu_network_contract_tests"
CONTRACT_BUILD = ROOT / "build/bambu_network_contract_tests"


def read_expected_abi_version() -> str:
    header = ROOT / "src/slic3r/Utils/bambu_networking.hpp"
    text = header.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r'BAMBU_NETWORK_AGENT_VERSION\s+"([^"]+)"', text)
    if not match:
        raise RuntimeError(f"failed to extract BAMBU_NETWORK_AGENT_VERSION from {header}")
    return match.group(1)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_elf(path: pathlib.Path) -> None:
    magic = path.read_bytes()[:4]
    if magic != b"\x7fELF":
        if magic in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe"):
            raise RuntimeError(f"{path} is a Mach-O binary, not a Linux ELF .so")
        raise RuntimeError(f"{path} is not a Linux ELF .so")


def default_payload_file(name: str) -> pathlib.Path:
    return PLUGIN_BUILD / name


def copy_payload_file(source: pathlib.Path, out_dir: pathlib.Path, name: str) -> dict[str, Any]:
    if not source.exists():
        raise RuntimeError(f"missing {name}: {source}")
    require_elf(source)
    destination = out_dir / name
    shutil.copy2(source, destination)
    return {"name": name, "sha256": sha256(destination)}


def run_symbol_probe(probe: pathlib.Path, plugin: pathlib.Path, symbols: pathlib.Path) -> dict[str, Any]:
    if not probe.exists():
        raise RuntimeError(f"missing contract probe: {probe}")
    completed = subprocess.run(
        [
            str(probe),
            "--plugin",
            str(plugin),
            "--symbols",
            str(symbols),
            "--json",
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
        raise RuntimeError(f"symbol probe did not emit JSON: {error}\n{completed.stdout}") from error
    if completed.returncode != 0 or not payload.get("ok"):
        raise RuntimeError(f"symbol probe failed for {plugin}")
    return {
        "plugin": str(plugin),
        "symbols": str(symbols),
        "method": "dlopen/dlsym",
        "present_count": payload.get("present_count"),
        "missing_count": payload.get("missing_count"),
        "ok": True,
    }


def run_elf_symbol_probe(plugin: pathlib.Path, symbols: pathlib.Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(CONTRACT_DIR / "verify_elf_exports.py"),
            "--plugin",
            str(plugin),
            "--symbols",
            str(symbols),
            "--json",
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
        raise RuntimeError(f"ELF symbol probe did not emit JSON: {error}\n{completed.stdout}") from error
    if completed.returncode != 0 or not payload.get("ok"):
        raise RuntimeError(f"ELF symbol probe failed for {plugin}")
    return payload


def run_elf_cxx_abi_probe(plugin: pathlib.Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(CONTRACT_DIR / "verify_elf_cxx_abi.py"),
            "--plugin",
            str(plugin),
            "--json",
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
        raise RuntimeError(f"ELF C++ ABI probe did not emit JSON: {error}\n{completed.stdout}") from error
    if completed.returncode != 0 or not payload.get("ok"):
        raise RuntimeError(f"ELF C++ ABI probe failed for {plugin}")
    return payload


def run_bridge_probe(host: pathlib.Path, out_dir: pathlib.Path, source_so: pathlib.Path | None) -> dict[str, Any]:
    command = [
        sys.executable,
        str(CONTRACT_DIR / "bridge_rpc_probe.py"),
        "--host",
        str(host),
        "--plugin-dir",
        str(out_dir),
    ]
    if source_so:
        command.extend(["--source-so", str(source_so)])

    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"bridge probe did not emit JSON: {error}\n{completed.stdout}") from error
    if completed.returncode != 0:
        raise RuntimeError("bridge probe failed")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--network-so", type=pathlib.Path, default=default_payload_file("libbambu_networking.so"))
    parser.add_argument("--source-so", type=pathlib.Path, default=default_payload_file("libBambuSource.so"))
    parser.add_argument("--out-dir", type=pathlib.Path, default=ROOT / "build/bambu_network_rust_plugin/linux-payload")
    parser.add_argument("--host", type=pathlib.Path, default=None, help="optional pjarczak_bambu_linux_host path for a bridge RPC smoke run")
    parser.add_argument("--contract-probe", type=pathlib.Path, default=CONTRACT_BUILD / "bambu_network_contract_probe")
    parser.add_argument("--no-clean", action="store_true", help="do not delete the output directory before assembling")
    parser.add_argument("--skip-symbol-probes", action="store_true", help="copy ELF files without dlopen/dlsym symbol checks")
    args = parser.parse_args()

    out_dir = args.out_dir
    if out_dir.exists() and not args.no_clean:
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    expected_abi = read_expected_abi_version()
    entries = []
    network_entry = copy_payload_file(args.network_so, out_dir, "libbambu_networking.so")
    network_entry["abi_version"] = expected_abi
    network_entry["source"] = "clean-room-rust-plugin"
    entries.append(network_entry)

    source_entry = copy_payload_file(args.source_so, out_dir, "libBambuSource.so")
    source_entry["source"] = "clean-room-rust-plugin"
    entries.append(source_entry)

    manifest: dict[str, Any] = {
        "format": 1,
        "kind": "bambu-network-clean-room-candidate",
        "files": entries,
        "symbol_probes": {},
    }

    manifest["elf_symbol_probes"] = {
        "network": run_elf_symbol_probe(
            out_dir / "libbambu_networking.so",
            CONTRACT_DIR / "required_symbols.txt",
        ),
        "source": run_elf_symbol_probe(
            out_dir / "libBambuSource.so",
            CONTRACT_DIR / "source_symbols.txt",
        ),
    }
    manifest["elf_cxx_abi"] = {
        "network": run_elf_cxx_abi_probe(out_dir / "libbambu_networking.so"),
        "source": run_elf_cxx_abi_probe(out_dir / "libBambuSource.so"),
    }

    if args.skip_symbol_probes:
        manifest["symbol_probes"] = {"skipped": True, "reason": "dlopen/dlsym probes require a Linux process"}
    else:
        manifest["symbol_probes"] = {
            "network": run_symbol_probe(
                args.contract_probe,
                out_dir / "libbambu_networking.so",
                CONTRACT_DIR / "required_symbols.txt",
            ),
            "source": run_symbol_probe(
                args.contract_probe,
                out_dir / "libBambuSource.so",
                CONTRACT_DIR / "source_symbols.txt",
            ),
        }

    if args.host:
        manifest["bridge_probe"] = run_bridge_probe(args.host, out_dir, out_dir / "libBambuSource.so")

    manifest_path = out_dir / "linux_payload_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({"ok": True, "out_dir": str(out_dir), "manifest": str(manifest_path), "files": entries}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
