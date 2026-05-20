#!/usr/bin/env python3
import argparse
import ctypes
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "tools/bambu_network_contract_tests"
MACHO_MAGICS = (
    b"\xcf\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xce",
    b"\xca\xfe\xba\xbe",
    b"\xca\xfe\xba\xbf",
)
REJECTED_NETWORK_NAMES = {"libpjarczak_bambu_networking_bridge.dylib"}
NETWORK_NAME_RE = re.compile(r"^libbambu_networking(?:_[A-Za-z0-9_.-]+)?\.dylib$")
SOURCE_NAME = "libBambuSource.dylib"


def sha256_file(path: pathlib.Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_symbols(path: pathlib.Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def is_macho(path: pathlib.Path) -> bool:
    if not path.is_file():
        return False
    try:
        header = path.read_bytes()[:4]
    except OSError:
        return False
    return header in MACHO_MAGICS


def run(cmd: list[str]) -> dict[str, Any]:
    completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    return {
        "command": cmd,
        "exit_code": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def file_summary(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "command": ["file", str(path)], "stdout": "", "stderr": "missing input"}
    return run(["file", str(path)])


def dylib_metadata(path: pathlib.Path, expected_name: str, *, network: bool) -> dict[str, Any]:
    name = path.name
    rejected_bridge = network and name in REJECTED_NETWORK_NAMES
    rejected_linux_so = path.suffix == ".so" or ".so." in name
    expected_native_name = NETWORK_NAME_RE.fullmatch(name) is not None if network else name == SOURCE_NAME
    return {
        "path": str(path),
        "name": name,
        "expected_name": expected_name,
        "exists": path.is_file(),
        "size": path.stat().st_size if path.is_file() else None,
        "sha256": sha256_file(path),
        "is_macho": is_macho(path),
        "is_dylib_name": name.endswith(".dylib"),
        "is_expected_native_name": expected_native_name,
        "rejected_bridge_dylib": rejected_bridge,
        "rejected_linux_so": rejected_linux_so,
        "file": file_summary(path),
    }


def dlsym_probe(path: pathlib.Path, symbols: list[str]) -> dict[str, Any]:
    if not path.is_file():
        return {
            "ok": False,
            "dlopen": False,
            "missing": symbols,
            "present": [],
            "error": "input file does not exist",
        }
    try:
        lib = ctypes.CDLL(str(path))
    except OSError as error:
        return {
            "ok": False,
            "dlopen": False,
            "missing": symbols,
            "present": [],
            "error": str(error),
        }

    present: list[str] = []
    missing: list[str] = []
    for symbol in symbols:
        try:
            getattr(lib, symbol)
        except AttributeError:
            missing.append(symbol)
        else:
            present.append(symbol)
    return {
        "ok": not missing,
        "dlopen": True,
        "present": present,
        "missing": missing,
        "present_count": len(present),
        "required_count": len(symbols),
    }


def validation_checks(report: dict[str, Any]) -> dict[str, bool]:
    network = report["inputs"]["network"]
    source = report["inputs"]["source"]
    probes = report["probes"]
    commands = report["commands"]
    return {
        "network_exists": network["exists"] is True,
        "source_exists": source["exists"] is True,
        "network_is_macho": network["is_macho"] is True,
        "source_is_macho": source["is_macho"] is True,
        "network_is_dylib": network["is_dylib_name"] is True and network["is_expected_native_name"] is True,
        "source_is_dylib": source["is_dylib_name"] is True and source["is_expected_native_name"] is True,
        "network_expected_native_name": network["is_expected_native_name"] is True,
        "source_expected_native_name": source["is_expected_native_name"] is True,
        "network_rejects_bridge_dylib": network["rejected_bridge_dylib"] is False,
        "network_rejects_linux_so": network["rejected_linux_so"] is False,
        "source_rejects_linux_so": source["rejected_linux_so"] is False,
        "source_is_separate_dylib": network["path"] != source["path"],
        "network_dlopen_dlsym": probes["network"]["ok"] is True,
        "source_dlopen_dlsym": probes["source"]["ok"] is True,
        "abi_mirror": commands["abi_mirror"]["ok"] is True,
        "cpp_signature_mirror": commands["cpp_signature_mirror"]["ok"] is True,
        "clean_room_artifact_self_test": commands["clean_room_artifact_self_test"]["ok"] is True,
    }


def verify(network_dylib: pathlib.Path, source_dylib: pathlib.Path) -> dict[str, Any]:
    network_symbols = load_symbols(CONTRACT_DIR / "required_symbols.txt")
    source_symbols = load_symbols(CONTRACT_DIR / "source_symbols.txt")
    report: dict[str, Any] = {
        "target": "macos_native_plugin",
        "inputs": {
            "network": dylib_metadata(network_dylib, "libbambu_networking.dylib", network=True),
            "source": dylib_metadata(source_dylib, "libBambuSource.dylib", network=False),
        },
        "probes": {
            "network": dlsym_probe(network_dylib, network_symbols),
            "source": dlsym_probe(source_dylib, source_symbols),
        },
        "commands": {
            "abi_mirror": run([sys.executable, str(CONTRACT_DIR / "verify_abi_mirror.py")]),
            "cpp_signature_mirror": run([sys.executable, str(CONTRACT_DIR / "verify_cpp_signature_mirror.py")]),
            "clean_room_artifact_self_test": run([sys.executable, str(CONTRACT_DIR / "verify_clean_room_artifacts.py"), "--self-test"]),
        },
    }
    checks = validation_checks(report)
    failed = [name for name, ok in checks.items() if not ok]
    report["checks"] = checks
    report["failed"] = failed
    report["ok"] = not failed
    return report


def self_test() -> None:
    network = ROOT / "build/bambu_network_rust_plugin_release/libbambu_networking.dylib"
    source = ROOT / "build/bambu_network_rust_plugin_release/libBambuSource.dylib"
    if not network.is_file() or not source.is_file():
        raise RuntimeError("self-test requires build/bambu_network_rust_plugin_release native dylibs")

    ok_report = verify(network, source)
    if ok_report["ok"] is not True:
        raise RuntimeError(f"native dylib verifier rejected current native dylibs: {ok_report['failed']}")

    with tempfile.TemporaryDirectory(prefix="bambu-native-plugin-verify-") as tmp:
        work = pathlib.Path(tmp)
        renamed_network = work / "libnot_bambu_networking.dylib"
        renamed_source = work / "libNotBambuSource.dylib"
        versioned_network = work / "libbambu_networking_02.05.02.58.dylib"
        shutil.copy2(network, renamed_network)
        shutil.copy2(source, renamed_source)
        shutil.copy2(network, versioned_network)

        versioned_network_report = verify(versioned_network, source)
        if versioned_network_report["ok"] is not True:
            raise RuntimeError(f"versioned native network dylib was rejected: {versioned_network_report['failed']}")

        wrong_network = verify(renamed_network, source)
        if wrong_network["ok"] is True or "network_is_dylib" not in wrong_network["failed"]:
            raise RuntimeError(f"renamed network dylib was accepted: {wrong_network['failed']}")

        wrong_source = verify(network, renamed_source)
        if wrong_source["ok"] is True or "source_is_dylib" not in wrong_source["failed"]:
            raise RuntimeError(f"renamed source dylib was accepted: {wrong_source['failed']}")

        bridge_network = work / "libpjarczak_bambu_networking_bridge.dylib"
        linux_network = work / "libbambu_networking.so"
        linux_source = work / "libBambuSource.so"
        shutil.copy2(network, bridge_network)
        shutil.copy2(network, linux_network)
        shutil.copy2(source, linux_source)

        bridge_report = verify(bridge_network, source)
        if bridge_report["ok"] is True or "network_rejects_bridge_dylib" not in bridge_report["failed"]:
            raise RuntimeError(f"bridge network dylib was accepted: {bridge_report['failed']}")

        linux_network_report = verify(linux_network, source)
        if linux_network_report["ok"] is True or "network_rejects_linux_so" not in linux_network_report["failed"]:
            raise RuntimeError(f"Linux network .so was accepted: {linux_network_report['failed']}")

        linux_source_report = verify(network, linux_source)
        if linux_source_report["ok"] is True or "source_rejects_linux_so" not in linux_source_report["failed"]:
            raise RuntimeError(f"Linux source .so was accepted: {linux_source_report['failed']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify native macOS Bambu network/source dylib evidence")
    parser.add_argument("--network-dylib", type=pathlib.Path)
    parser.add_argument("--source-dylib", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print("macOS native plugin validation checks passed")
        return 0
    if args.network_dylib is None:
        parser.error("--network-dylib is required unless --self-test is used")
    if args.source_dylib is None:
        parser.error("--source-dylib is required unless --self-test is used")
    if args.out is None:
        parser.error("--out is required unless --self-test is used")

    report = verify(args.network_dylib, args.source_dylib)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "failed": report["failed"], "out": str(args.out)}, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
