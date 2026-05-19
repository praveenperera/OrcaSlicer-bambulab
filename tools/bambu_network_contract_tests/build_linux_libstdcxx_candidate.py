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
CONTRACT_DIR = ROOT / "tools/bambu_network_contract_tests"
DEFAULT_OUT_DIR = ROOT / "build/bambu_network_rust_plugin_linux_x86_64_libstdcxx"
DEFAULT_RUST_CORE = (
    ROOT
    / "build/bambu_network_rust_plugin_linux_x86_64/cargo/x86_64-unknown-linux-gnu/release/libbambu_network_rust_core.a"
)


def resolve_tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"missing required tool: {name}")
    return found


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, env: dict[str, str] | None = None) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False, env=env)
    return {
        "command": command,
        "exit_code": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run_json(command: list[str], *, env: dict[str, str] | None = None) -> dict[str, Any]:
    result = run(command, env=env)
    try:
        payload = json.loads(result["stdout"])
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{command[0]} did not emit JSON: {error}\n{result['stdout']}") from error
    if not result["ok"] or payload.get("ok") is not True:
        raise RuntimeError(f"{command[0]} failed: {payload}")
    return {
        "command": command,
        "ok": True,
        "payload": payload,
        "stderr": result["stderr"],
    }


def require_elf(path: pathlib.Path) -> None:
    if path.read_bytes()[:4] != b"\x7fELF":
        raise RuntimeError(f"{path} is not a Linux ELF file")


def compile_shared(
    compiler: str,
    source: pathlib.Path,
    output: pathlib.Path,
    rust_core: pathlib.Path | None,
) -> dict[str, Any]:
    command = [
        compiler,
        "-std=c++17",
        "-fPIC",
        "-shared",
        "-O2",
        "-I",
        str(ROOT / "tools/bambu_network_rust_plugin"),
        "-I",
        str(ROOT / "deps_src"),
        str(source),
    ]
    if rust_core is not None:
        command.append(str(rust_core))
    command.extend(["-pthread", "-ldl", "-lm", "-o", str(output)])
    result = run(command)
    if not result["ok"]:
        raise RuntimeError(f"compile failed for {output}: {result['stderr']}")
    require_elf(output)
    return result


def compile_contract_probe(compiler: str, output: pathlib.Path) -> dict[str, Any]:
    command = [
        compiler,
        "-std=c++17",
        "-O2",
        str(CONTRACT_DIR / "contract_probe.cpp"),
        "-ldl",
        "-o",
        str(output),
    ]
    result = run(command)
    if not result["ok"]:
        raise RuntimeError(f"contract probe compile failed: {result['stderr']}")
    require_elf(output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--rust-core", type=pathlib.Path, default=DEFAULT_RUST_CORE)
    parser.add_argument("--cxx", default=os.environ.get("CXX", "x86_64-linux-gnu-g++"))
    parser.add_argument("--nm", default=os.environ.get("NM", "x86_64-linux-gnu-nm"))
    parser.add_argument("--objdump", default=os.environ.get("OBJDUMP", "x86_64-linux-gnu-objdump"))
    parser.add_argument("--run-dlopen-probes", action="store_true")
    parser.add_argument("--ld-library-path", default=os.environ.get("LD_LIBRARY_PATH", ""))
    args = parser.parse_args()

    compiler = resolve_tool(args.cxx)
    nm = resolve_tool(args.nm)
    objdump = resolve_tool(args.objdump)
    if not args.rust_core.is_file():
        raise RuntimeError(f"missing Rust GNU static library: {args.rust_core}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    network_so = args.out_dir / "libbambu_networking.so"
    source_so = args.out_dir / "libBambuSource.so"

    build = {
        "network": compile_shared(
            compiler,
            ROOT / "tools/bambu_network_rust_plugin/shim/bambu_networking_shim.cpp",
            network_so,
            args.rust_core,
        ),
        "source": compile_shared(
            compiler,
            ROOT / "tools/bambu_network_rust_plugin/shim/bambu_source_shim.cpp",
            source_so,
            args.rust_core,
        ),
    }
    env = {**os.environ, "NM": nm, "OBJDUMP": objdump}
    checks = {
        "network_exports": run_json([
            sys.executable,
            str(CONTRACT_DIR / "verify_elf_exports.py"),
            "--plugin",
            str(network_so),
            "--symbols",
            str(CONTRACT_DIR / "required_symbols.txt"),
            "--json",
        ], env=env),
        "source_exports": run_json([
            sys.executable,
            str(CONTRACT_DIR / "verify_elf_exports.py"),
            "--plugin",
            str(source_so),
            "--symbols",
            str(CONTRACT_DIR / "source_symbols.txt"),
            "--json",
        ], env=env),
        "network_cxx_abi": run_json([
            sys.executable,
            str(CONTRACT_DIR / "verify_elf_cxx_abi.py"),
            "--plugin",
            str(network_so),
            "--expect",
            "libstdc++",
            "--json",
        ], env=env),
        "source_cxx_abi": run_json([
            sys.executable,
            str(CONTRACT_DIR / "verify_elf_cxx_abi.py"),
            "--plugin",
            str(source_so),
            "--expect",
            "libstdc++",
            "--json",
        ], env=env),
    }

    if args.run_dlopen_probes:
        probe = args.out_dir / "bambu_network_contract_probe"
        build["contract_probe"] = compile_contract_probe(compiler, probe)
        probe_env = dict(env)
        probe_env["LD_LIBRARY_PATH"] = os.pathsep.join(
            value for value in [args.ld_library_path, str(args.out_dir)] if value
        )
        checks["network_dlopen"] = run_json([
            str(probe),
            "--plugin",
            str(network_so),
            "--symbols",
            str(CONTRACT_DIR / "required_symbols.txt"),
            "--json",
        ], env=probe_env)
        checks["source_dlopen"] = run_json([
            str(probe),
            "--plugin",
            str(source_so),
            "--symbols",
            str(CONTRACT_DIR / "source_symbols.txt"),
            "--json",
        ], env=probe_env)

    report = {
        "ok": True,
        "out_dir": str(args.out_dir),
        "network_so": str(network_so),
        "source_so": str(source_so),
        "compiler": compiler,
        "nm": nm,
        "objdump": objdump,
        "rust_core": str(args.rust_core),
        "inputs": {
            "network_shim": {
                "path": str(ROOT / "tools/bambu_network_rust_plugin/shim/bambu_networking_shim.cpp"),
                "sha256": sha256(ROOT / "tools/bambu_network_rust_plugin/shim/bambu_networking_shim.cpp"),
            },
            "source_shim": {
                "path": str(ROOT / "tools/bambu_network_rust_plugin/shim/bambu_source_shim.cpp"),
                "sha256": sha256(ROOT / "tools/bambu_network_rust_plugin/shim/bambu_source_shim.cpp"),
            },
            "rust_core": {
                "path": str(args.rust_core),
                "sha256": sha256(args.rust_core),
            },
        },
        "outputs": {
            "network_so": {
                "path": str(network_so),
                "sha256": sha256(network_so),
            },
            "source_so": {
                "path": str(source_so),
                "sha256": sha256(source_so),
            },
        },
        "build": build,
        "checks": checks,
    }
    report_path = args.out_dir / "linux_libstdcxx_candidate_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
