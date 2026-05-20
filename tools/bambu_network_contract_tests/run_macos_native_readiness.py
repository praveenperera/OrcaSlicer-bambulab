#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "tools/bambu_network_contract_tests"
DEFAULT_OUT_DIR = ROOT / "build/bambu_network_release_readiness"
DEFAULT_LOCAL_SMOKE_REPORT = DEFAULT_OUT_DIR / "local_candidate_smoke.json"
DEFAULT_NATIVE_PACKAGE_MACOS_DIR = DEFAULT_OUT_DIR / "native_copy_scratch/OrcaSlicer.app/Contents/MacOS"
DEFAULT_NATIVE_PACKAGE_ROOT = None
DEFAULT_NATIVE_GUI_STARTUP_LOG = DEFAULT_OUT_DIR / "gui_native_smoke/native_startup_relevant_logs.txt"
DEFAULT_NATIVE_GUI_STARTUP_PLUGIN_DIR = DEFAULT_OUT_DIR / "gui_native_smoke_datadir/plugins"
DEFAULT_SOURCE_RTSP_LOOPBACK_REPORT = DEFAULT_OUT_DIR / "source_rtsp_loopback_parity/parity_report.json"
DEFAULT_SOURCE_CONTROL_TLS_LOOPBACK_REPORT = DEFAULT_OUT_DIR / "source_control_tls_loopback_parity/parity_report.json"
DEFAULT_REAL_PRINTER_TEST_3MF = ROOT / "resources/handy_models/OrcaCube_v2.3mf"
DEFAULT_BRIDGE_CONFIG_SOURCE = ROOT / "src/slic3r/Utils/PJarczakLinuxBridge/PJarczakLinuxBridgeConfig.cpp"
DEFAULT_LOADER_SOURCE = ROOT / "src/slic3r/Utils/BBLNetworkPlugin.cpp"
SECRET_ENV_NAMES = (
    "BAMBU_NETWORK_PRINTER_PASSWORD",
    "BAMBU_CLOUD_LOGIN_INFO_JSON",
    "BAMBU_CLOUD_TICKET",
    "BAMBU_CLOUD_ACCESS_TOKEN",
)
MACHO_MAGICS = (
    b"\xcf\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xce",
    b"\xca\xfe\xba\xbe",
    b"\xca\xfe\xba\xbf",
)
REJECTED_NATIVE_PACKAGE_NAMES = {
    "libpjarczak_bambu_networking_bridge.dylib",
    "pjarczak_bambu_linux_host",
    "pjarczak_bambu_linux_host_abi0",
    "pjarczak_bambu_linux_host_abi1",
    "pjarczak-bambu-linux-host-wrapper",
    "libbambu_networking.so",
    "libBambuSource.so",
    "linux_payload_manifest.json",
    "install_runtime_macos.sh",
    "verify_runtime_macos.sh",
    "pjarczak_lima_instance.txt",
}
NATIVE_NETWORK_NAME_RE = re.compile(r"^libbambu_networking(?:_[A-Za-z0-9_.-]+)?\.dylib$")
NATIVE_SOURCE_NAME = "libBambuSource.dylib"
REQUIRED_LOCAL_SMOKE_CHECKS = (
    "preflight_python_sources_compile",
    "preflight_symbol_manifest_sources",
    "preflight_abi_mirror",
    "preflight_cpp_signature_mirror",
    "preflight_contract_surface_coverage",
    "preflight_clean_room_artifact_validation",
    "preflight_completion_audit_validation",
    "network_symbols",
    "source_symbols",
    "lifecycle_agent_created",
    "lifecycle_destroy_result",
    "callback_agent_created",
    "callback_transcripts_match",
    "unsupported_no_missing_symbols",
    "unsupported_destroy_result",
    "source_behavior_ok",
    "source_streaming_fixture_ok",
    "source_local_tunnel_ok",
    "event_bridge_payloads",
    "discovery_payload",
    "camera_url_payload",
    "ft_behavior_ok",
)
EXPECTED_NATIVE_COMPLETION_CRITERIA = {
    "native_macos_mode_loads_native_network_and_source_dylibs_directly",
    "native_macos_mode_does_not_require_or_launch_bridge_components",
    "bridge_fallback_remains_available",
    "native_macos_package_staging_path_can_run_without_lima_or_linux_runtime",
    "native_macos_plugin_verification_passes",
    "native_macos_gui_startup_smoke_passes",
    "local_candidate_smoke_passes",
    "native_official_vs_candidate_parity_passes_for_required_local_offline_behavior",
    "native_real_printer_parity_completed",
    "cloud_service_parity_completed_or_approved_scope_out",
    "clean_room_artifact_verification_passes",
    "final_readiness_ok",
}


def load_json(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def sha256_file(path: pathlib.Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_macho(path: pathlib.Path) -> bool:
    if not path.is_file():
        return False
    try:
        header = path.read_bytes()[:4]
    except OSError:
        return False
    return header in MACHO_MAGICS


def is_under_repo(path: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def infer_native_package_root(macos_dir: pathlib.Path) -> pathlib.Path | None:
    if macos_dir.name != "MacOS" or macos_dir.parent.name != "Contents":
        return None
    app_dir = macos_dir.parent.parent
    if app_dir.suffix != ".app":
        return None
    return app_dir.parent


def is_rejected_native_runtime_file(path: pathlib.Path, reject_any_so: bool) -> bool:
    if path.name in REJECTED_NATIVE_PACKAGE_NAMES:
        return True
    return reject_any_so and (path.suffix == ".so" or ".so." in path.name)


def rejected_native_runtime_files(root: pathlib.Path, *, recursive: bool, reject_any_so: bool) -> list[str]:
    if not root.is_dir():
        return []
    paths = root.rglob("*") if recursive else root.iterdir()
    rejected = []
    for path in paths:
        if path.is_file() and is_rejected_native_runtime_file(path, reject_any_so):
            rejected.append(str(path))
    return sorted(rejected)


def native_network_dylib_candidates(macos_dir: pathlib.Path) -> list[pathlib.Path]:
    if not macos_dir.is_dir():
        return []
    return sorted(path for path in macos_dir.iterdir() if path.is_file() and NATIVE_NETWORK_NAME_RE.fullmatch(path.name))


def select_native_network_dylib(macos_dir: pathlib.Path, expected_sha: str | None) -> pathlib.Path:
    candidates = native_network_dylib_candidates(macos_dir)
    if expected_sha:
        for candidate in candidates:
            if sha256_file(candidate) == expected_sha:
                return candidate
    unversioned = macos_dir / "libbambu_networking.dylib"
    if unversioned in candidates:
        return unversioned
    return candidates[0] if candidates else unversioned


def run(cmd: list[str]) -> dict[str, Any]:
    completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    return {
        "command": cmd,
        "exit_code": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def gate(ok: bool, required: bool = True, **extra: Any) -> dict[str, Any]:
    return {"ok": ok, "required": required, **extra}


def add_gate(report: dict[str, Any], name: str, status: dict[str, Any]) -> None:
    report["gates"][name] = status
    if status.get("required") and status.get("ok") is not True:
        report["blockers"].append(name)


def native_plugin_gate(path: pathlib.Path) -> dict[str, Any]:
    payload = load_json(path)
    if payload is None:
        return gate(False, path=str(path), reason="native plugin report is missing or invalid JSON")
    checks = payload.get("checks", {})
    checks = checks if isinstance(checks, dict) else {}
    required = (
        "network_exists",
        "source_exists",
        "network_is_macho",
        "source_is_macho",
        "network_is_dylib",
        "source_is_dylib",
        "network_rejects_bridge_dylib",
        "network_rejects_linux_so",
        "source_rejects_linux_so",
        "source_is_separate_dylib",
        "network_expected_native_name",
        "source_expected_native_name",
        "network_dlopen_dlsym",
        "source_dlopen_dlsym",
        "abi_mirror",
        "cpp_signature_mirror",
        "clean_room_artifact_self_test",
    )
    failed = [name for name in required if checks.get(name) is not True]
    return gate(
        payload.get("ok") is True and not failed,
        path=str(path),
        failed=failed,
        native_plugin_report=payload,
    )


def local_smoke_gate(path: pathlib.Path) -> dict[str, Any]:
    payload = load_json(path)
    if payload is None:
        return gate(False, path=str(path), reason="local candidate smoke report is missing or invalid JSON")
    checks = payload.get("checks", {})
    checks = checks if isinstance(checks, dict) else {}
    validation_checks = {
        "summary_ok": payload.get("ok") is True,
        "no_failed_entries": payload.get("failed") == [],
    }
    validation_checks.update({f"check_{name}": checks.get(name) is True for name in REQUIRED_LOCAL_SMOKE_CHECKS})
    failed = [name for name, ok in validation_checks.items() if not ok]
    return gate(not failed, path=str(path), checks=validation_checks, failed=failed, local_smoke_report=payload)


def input_metadata(report: dict[str, Any], side: str, label: str) -> dict[str, Any]:
    inputs = report.get("inputs", {})
    group = inputs.get(side, {}) if isinstance(inputs, dict) else {}
    item = group.get(label, {}) if isinstance(group, dict) else {}
    return item if isinstance(item, dict) else {}


def official_parity_gate(path: pathlib.Path, native_report: dict[str, Any] | None) -> dict[str, Any]:
    payload = load_json(path)
    if payload is None:
        return gate(False, path=str(path), reason="official parity report is missing or invalid JSON")

    candidate_network = pathlib.Path(str(input_metadata(payload, "candidate", "network").get("path", "")))
    candidate_source = pathlib.Path(str(input_metadata(payload, "candidate", "source").get("path", "")))
    official_network = pathlib.Path(str(input_metadata(payload, "official", "network").get("path", "")))
    official_source = pathlib.Path(str(input_metadata(payload, "official", "source").get("path", "")))

    native_network_sha = None
    native_source_sha = None
    if native_report:
        native_network_sha = native_report.get("inputs", {}).get("network", {}).get("sha256")
        native_source_sha = native_report.get("inputs", {}).get("source", {}).get("sha256")

    checks = {
        "report_ok": payload.get("ok") is True,
        "no_failed_entries": payload.get("failed") == [],
        "official_network_exists": input_metadata(payload, "official", "network").get("exists") is True and official_network.is_file(),
        "official_source_exists": input_metadata(payload, "official", "source").get("exists") is True and official_source.is_file(),
        "official_network_outside_repo": bool(str(official_network)) and not is_under_repo(official_network),
        "official_source_outside_repo": bool(str(official_source)) and not is_under_repo(official_source),
        "official_network_hash_matches_report": sha256_file(official_network) == input_metadata(payload, "official", "network").get("sha256"),
        "official_source_hash_matches_report": sha256_file(official_source) == input_metadata(payload, "official", "source").get("sha256"),
        "candidate_network_is_dylib": NATIVE_NETWORK_NAME_RE.fullmatch(candidate_network.name) is not None,
        "candidate_source_is_dylib": candidate_source.name == NATIVE_SOURCE_NAME,
        "candidate_network_hash_matches_native_report": native_network_sha is not None and sha256_file(candidate_network) == native_network_sha,
        "candidate_source_hash_matches_native_report": native_source_sha is not None and sha256_file(candidate_source) == native_source_sha,
        "official_network_differs_from_candidate": input_metadata(payload, "official", "network").get("sha256")
        != input_metadata(payload, "candidate", "network").get("sha256"),
        "official_source_differs_from_candidate": input_metadata(payload, "official", "source").get("sha256")
        != input_metadata(payload, "candidate", "source").get("sha256"),
    }
    failed = [name for name, ok in checks.items() if not ok]
    missing_or_stale_inputs = [
        name
        for name, ok in {
            "official_network": checks["official_network_exists"] and checks["official_network_hash_matches_report"],
            "official_source": checks["official_source_exists"] and checks["official_source_hash_matches_report"],
        }.items()
        if not ok
    ]
    return gate(
        not failed,
        path=str(path),
        checks=checks,
        failed=failed,
        missing_inputs=missing_or_stale_inputs,
        needed_action=[
            "re-extract current official macOS Bambu network/source dylibs outside the repo",
            "rerun capture_official_parity.py with current official macOS dylibs and current candidate native dylibs",
        ],
        missing_or_stale_inputs=missing_or_stale_inputs,
        official_parity_report=payload,
    )


def clean_room_gate(
    official_parity_report: pathlib.Path,
    artifact_dirs: list[pathlib.Path],
    scan_dirs: list[pathlib.Path],
    secret_env_names: tuple[str, ...] = SECRET_ENV_NAMES,
) -> dict[str, Any]:
    if not official_parity_report.is_file():
        return gate(False, reason="official parity report is required before clean-room artifact policy can be checked")
    commands = []
    failed = []
    for artifact_dir in artifact_dirs:
        if not artifact_dir.is_dir():
            failed.append(f"missing artifact dir: {artifact_dir}")
            continue
        command = [
            sys.executable,
            str(CONTRACT_DIR / "verify_clean_room_artifacts.py"),
            "--parity-report",
            str(official_parity_report),
            "--artifact-dir",
            str(artifact_dir),
        ]
        for env_name in secret_env_names:
            command.extend(["--forbid-secret-env", env_name])
        for scan_dir in scan_dirs:
            if scan_dir.is_dir():
                command.extend(["--forbid-official-binary-copies-in", str(scan_dir)])
        result = run(command)
        commands.append(result)
        if result["ok"] is not True:
            failed.append(str(artifact_dir))
    return gate(not failed, commands=commands, failed=failed, artifact_dirs=[str(path) for path in artifact_dirs])


def source_between(text: str, start: str, end: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        return ""
    if not end:
        return text[start_index:]
    end_index = text.find(end, start_index + len(start))
    if end_index < 0:
        return text[start_index:]
    return text[start_index:end_index]


def bridge_fallback_gate(config_source: pathlib.Path) -> dict[str, Any]:
    try:
        text = config_source.read_text(encoding="utf-8")
    except OSError as error:
        return gate(False, path=str(config_source), reason=str(error))

    enabled_body = source_between(text, "bool enabled()", "bool macos_native_plugin_enabled()")
    native_body = source_between(text, "bool macos_native_plugin_enabled()", "bool use_bridge_network_module()")
    use_bridge_body = source_between(text, "bool use_bridge_network_module()", "bool source_module_is_network_module()")
    source_module_body = source_between(text, "bool source_module_is_network_module()", "bool should_force_linux_plugin_payload")
    checks = {
        "config_source_exists": config_source.is_file(),
        "native_mode_env_flag_present": "PJARCZAK_BAMBU_MACOS_NATIVE_PLUGIN" in native_body,
        "native_mode_false_off_macos": re.search(r"#else\s+return\s+false\s*;", native_body) is not None,
        "enabled_disables_bridge_only_when_native": re.search(
            r"if\s*\(\s*macos_native_plugin_enabled\s*\(\s*\)\s*\)\s*return\s+false\s*;",
            enabled_body,
        ) is not None,
        "bridge_env_override_still_available": "PJARCZAK_LINUX_BRIDGE_ENABLED" in enabled_body,
        "macos_bridge_default_still_enabled": re.search(
            r"#elif\s+defined\(__WXMAC__\)\s*\|\|\s*defined\(__APPLE__\)\s*return\s+true\s*;",
            enabled_body,
        ) is not None,
        "macos_network_module_uses_bridge_unless_native": re.search(
            r"#elif\s+defined\(__WXMAC__\)\s*\|\|\s*defined\(__APPLE__\)\s*return\s+!macos_native_plugin_enabled\s*\(\s*\)\s*;",
            use_bridge_body,
        ) is not None,
        "source_module_uses_same_bridge_decision": re.search(
            r"return\s+use_bridge_network_module\s*\(\s*\)\s*;",
            source_module_body,
        ) is not None,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return gate(not failed, path=str(config_source), checks=checks, failed=failed)


def native_loader_gate(loader_source: pathlib.Path) -> dict[str, Any]:
    try:
        text = loader_source.read_text(encoding="utf-8")
    except OSError as error:
        return gate(False, path=str(loader_source), reason=str(error))

    initialize_body = source_between(text, "int BBLNetworkPlugin::initialize", "void* BBLNetworkPlugin::get_source_module()")
    source_body = source_between(text, "void* BBLNetworkPlugin::get_source_module()", "")
    checks = {
        "loader_source_exists": loader_source.is_file(),
        "initialize_reads_native_mode": "PJarczakLinuxBridge::macos_native_plugin_enabled()" in initialize_body,
        "initialize_reads_bridge_mode": "PJarczakLinuxBridge::enabled()" in initialize_body,
        "bridge_preflight_guarded_by_bridge_mode": re.search(
            r"if\s*\(\s*pj_bridge\s*\)\s*\{.*bridge_payload_preflight",
            initialize_body,
            re.DOTALL,
        ) is not None,
        "native_mode_has_no_preflight_branch": re.search(
            r"else\s+if\s*\(\s*macos_native_plugin\s*\).*macOS native plugin mode enabled",
            initialize_body,
            re.DOTALL,
        ) is not None,
        "macos_network_uses_dylib_extension": re.search(
            r"#if\s+defined\(__WXMAC__\)\s*const\s+std::string\s+lib_ext\s*=\s*\"\.dylib\"",
            initialize_body,
        ) is not None,
        "network_fallback_uses_unversioned_dylib": "fallback_library" in initialize_body and "dlopen(fallback_library.c_str(), RTLD_LAZY)" in initialize_body,
        "network_fallback_records_attempted_path_before_dlopen": re.search(
            r"library\s*=\s*fallback_library;\s*dlerror\(\);\s*m_networking_module\s*=\s*dlopen\(fallback_library\.c_str\(\),\s*RTLD_LAZY\)",
            initialize_body,
            re.DOTALL,
        ) is not None,
        "network_dlopen_error_logs_attempted_path": "dlopen failed for" in initialize_body and "set_load_error" in initialize_body,
        "native_mode_logged": "macos_native_plugin_mode" in initialize_body,
        "source_reuses_network_only_when_bridge_enabled": (
            "PJarczakLinuxBridge::enabled()"
            in source_body
            and "PJarczakLinuxBridge::source_module_is_network_module()"
            in source_body
        ),
        "macos_source_loads_dylib": (
            "BAMBU_SOURCE_LIBRARY" in source_body
            and '".dylib"' in source_body
            and "dlopen(library.c_str(), RTLD_LAZY)" in source_body
        ),
        "native_source_dlopen_success_logged": "loaded native source library" in source_body,
        "native_source_dlopen_error_logged": "native source dlopen failed" in source_body,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return gate(not failed, path=str(loader_source), checks=checks, failed=failed)


def native_packaging_gate(macos_dir: pathlib.Path, native_report: dict[str, Any] | None, package_root: pathlib.Path | None = None) -> dict[str, Any]:
    native_inputs = native_report.get("inputs", {}) if native_report else {}
    native_inputs = native_inputs if isinstance(native_inputs, dict) else {}
    native_network_sha = native_inputs.get("network", {}).get("sha256") if isinstance(native_inputs.get("network"), dict) else None
    native_source_sha = native_inputs.get("source", {}).get("sha256") if isinstance(native_inputs.get("source"), dict) else None

    network = select_native_network_dylib(macos_dir, native_network_sha)
    source = macos_dir / NATIVE_SOURCE_NAME
    network_candidates = native_network_dylib_candidates(macos_dir)
    rejected_files = rejected_native_runtime_files(macos_dir, recursive=False, reject_any_so=True)
    inferred_package_root = package_root or infer_native_package_root(macos_dir)
    package_root_rejected_files = (
        rejected_native_runtime_files(inferred_package_root, recursive=True, reject_any_so=True) if inferred_package_root else []
    )

    checks = {
        "macos_dir_exists": macos_dir.is_dir(),
        "network_exists": network.is_file(),
        "network_name_is_native": NATIVE_NETWORK_NAME_RE.fullmatch(network.name) is not None,
        "source_exists": source.is_file(),
        "network_is_macho": is_macho(network),
        "source_is_macho": is_macho(source),
        "network_hash_matches_native_report": bool(native_network_sha and sha256_file(network) == native_network_sha),
        "source_hash_matches_native_report": bool(native_source_sha and sha256_file(source) == native_source_sha),
        "no_bridge_or_linux_runtime_files": rejected_files == [],
        "package_root_has_no_generated_bridge_or_linux_runtime_files": package_root_rejected_files == [],
    }
    failed = [name for name, ok in checks.items() if not ok]
    return gate(
        not failed,
        path=str(macos_dir),
        package_root=str(inferred_package_root) if inferred_package_root else None,
        checks=checks,
        failed=failed,
        rejected_files=rejected_files,
        package_root_rejected_files=package_root_rejected_files,
        network=str(network),
        network_candidates=[str(candidate) for candidate in network_candidates],
        source=str(source),
    )


def native_gui_startup_gate(log_path: pathlib.Path, plugin_dir: pathlib.Path) -> dict[str, Any]:
    try:
        log_text = log_path.read_text(encoding="utf-8")
    except OSError as error:
        return gate(False, log_path=str(log_path), plugin_dir=str(plugin_dir), reason=str(error))

    plugin_files = sorted(path.name for path in plugin_dir.iterdir() if path.is_file()) if plugin_dir.is_dir() else []
    rejected_plugin_files = rejected_native_runtime_files(plugin_dir, recursive=False, reject_any_so=True)
    rejected_log_markers = (
        "bridge payload preflight",
        "pjarczak_bambu_linux_host",
        "pjarczak-bambu-linux-host-wrapper",
        "libpjarczak_bambu_networking_bridge.dylib",
        "libbambu_networking.so",
        "libBambuSource.so",
        "linux_payload_manifest.json",
        "install_runtime_macos.sh",
        "verify_runtime_macos.sh",
        "pjarczak_lima_instance.txt",
        "Lima",
    )
    checks = {
        "startup_log_exists": log_path.is_file(),
        "plugin_dir_exists": plugin_dir.is_dir(),
        "plugin_dir_contains_only_native_dylibs": (
            len(plugin_files) == 2
            and NATIVE_SOURCE_NAME in plugin_files
            and any(NATIVE_NETWORK_NAME_RE.fullmatch(name) for name in plugin_files)
        ),
        "plugin_dir_has_no_bridge_or_linux_runtime_files": rejected_plugin_files == [],
        "native_mode_logged": "macOS native plugin mode enabled" in log_text,
        "native_network_dylib_logged": re.search(r"libbambu_networking(?:_[A-Za-z0-9_.-]+)?\.dylib", log_text) is not None,
        "native_source_dylib_logged": "loaded native source library" in log_text and NATIVE_SOURCE_NAME in log_text,
        "bridge_mode_false_logged": "bridge_mode=false" in log_text,
        "native_mode_true_logged": "macos_native_plugin_mode=true" in log_text,
        "network_load_success_logged": "on_init_network, load dll ok" in log_text,
        "compatibility_success_logged": "on_init_network, compatibility version" in log_text,
        "network_agent_creation_logged": "on_init_network, create network agent" in log_text,
        "no_bridge_or_linux_runtime_log_markers": not any(marker in log_text for marker in rejected_log_markers),
    }
    failed = [name for name, ok in checks.items() if not ok]
    return gate(
        not failed,
        log_path=str(log_path),
        plugin_dir=str(plugin_dir),
        plugin_files=plugin_files,
        rejected_plugin_files=rejected_plugin_files,
        checks=checks,
        failed=failed,
    )


def parity_probe_ok(report: dict[str, Any], name: str) -> bool:
    probes = report.get("probes", {})
    probe = probes.get(name, {}) if isinstance(probes, dict) else {}
    if not isinstance(probe, dict):
        return False
    official = probe.get("official", {})
    candidate = probe.get("candidate", {})
    return (
        isinstance(official, dict)
        and isinstance(candidate, dict)
        and official.get("ok") is True
        and candidate.get("ok") is True
    )


def parity_comparison_ok(report: dict[str, Any], name: str) -> bool:
    comparisons = report.get("comparisons", {})
    comparison = comparisons.get(name, {}) if isinstance(comparisons, dict) else {}
    return isinstance(comparison, dict) and comparison.get("ok") is True


def load_probe_artifact(report: dict[str, Any], name: str, side: str) -> dict[str, Any] | None:
    return load_probe_artifact_with_base(ROOT, report, name, side)


def load_probe_artifact_with_base(base: pathlib.Path, report: dict[str, Any], name: str, side: str) -> dict[str, Any] | None:
    probes = report.get("probes", {})
    probe = probes.get(name, {}) if isinstance(probes, dict) else {}
    item = probe.get(side, {}) if isinstance(probe, dict) else {}
    path = item.get("path") if isinstance(item, dict) else None
    if not isinstance(path, str) or not path:
        return None
    artifact_path = pathlib.Path(path)
    if not artifact_path.is_absolute():
        artifact_path = base / artifact_path
    return load_json(artifact_path)


def successful_authorized_cloud_service_transcript(transcript: dict[str, Any] | None) -> bool:
    if transcript is None:
        return False
    semantic = transcript.get("semantic", {})
    semantic = semantic if isinstance(semantic, dict) else {}
    return all(
        [
            transcript.get("ok") is True,
            transcript.get("expect_success") is True,
            transcript.get("allow_network") is True,
            transcript.get("agent_created") is True,
            transcript.get("missing_symbols") == [],
            semantic.get("login_ok") is True,
            semantic.get("network_ok") is True,
            semantic.get("service_ok") is True,
            isinstance(semantic.get("non_unsupported_service_results"), int),
            semantic.get("non_unsupported_service_results") > 0,
        ]
    )


def result_value(transcript: dict[str, Any], name: str) -> int | None:
    result = transcript.get("results", {}).get(name)
    return result.get("value") if isinstance(result, dict) else result


def has_successful_connect_event(transcript: dict[str, Any]) -> bool:
    events = transcript.get("events", [])
    if not isinstance(events, list):
        return False
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("name") == "local_connect" and event.get("status") == 0:
            return True
        if event.get("name") == "printer_connected":
            return True
    return False


def has_successful_print_status(transcript: dict[str, Any]) -> bool:
    status_events = transcript.get("status_events", [])
    if not isinstance(status_events, list):
        return False
    saw_finished = False
    for event in status_events:
        if not isinstance(event, dict):
            continue
        if event.get("status") == 7:
            return False
        if event.get("status") == 6 and event.get("code") == 0:
            saw_finished = True
    return saw_finished


def has_printer_identity(transcript: dict[str, Any]) -> bool:
    return bool(transcript.get("dev_id")) and bool(transcript.get("dev_ip"))


def successful_printer_workflow_transcript(transcript: dict[str, Any] | None) -> bool:
    if transcript is None:
        return False
    return all([
        has_printer_identity(transcript),
        transcript.get("password_present") is True,
        transcript.get("agent_created") is True,
        transcript.get("missing_symbols") == [],
        transcript.get("destroy_result") == 0,
        result_value(transcript, "init_log") == 0,
        result_value(transcript, "set_config_dir") == 0,
        result_value(transcript, "set_country_code") == 0,
        result_value(transcript, "start") == 0,
        result_value(transcript, "connect_printer") == 0,
        result_value(transcript, "send_message_to_printer") == 0,
        result_value(transcript, "disconnect_printer") == 0,
        has_successful_connect_event(transcript),
    ])


def successful_print_job_transcript(transcript: dict[str, Any] | None, expected_mode: str) -> bool:
    if transcript is None:
        return False
    return all([
        has_printer_identity(transcript),
        transcript.get("mode") == expected_mode,
        transcript.get("password_present") is True,
        transcript.get("file_present") is True,
        transcript.get("remote_name_present") is True,
        transcript.get("agent_created") is True,
        transcript.get("missing_symbols") == [],
        transcript.get("destroy_result") == 0,
        transcript.get("job_result") == 0,
        transcript.get("ok") is True,
        has_successful_print_status(transcript),
        result_value(transcript, "init_log") == 0,
        result_value(transcript, "set_config_dir") == 0,
        result_value(transcript, "set_country_code") == 0,
        result_value(transcript, "start") == 0,
    ])


def successful_source_streaming_transcript(transcript: dict[str, Any] | None) -> bool:
    if transcript is None:
        return False
    semantic = transcript.get("semantic", {})
    contract = transcript.get("stream_contract", {})
    stream_format_type = contract.get("stream_format_type") if isinstance(contract, dict) else None
    max_frame_size_ok = contract.get("stream_max_frame_size_positive") is True or stream_format_type == 1
    return all([
        transcript.get("ok") is True,
        transcript.get("mode") == "video",
        transcript.get("missing_symbols") == [],
        isinstance(semantic, dict),
        semantic.get("opened") is True,
        semantic.get("stream_started") is True,
        semantic.get("stream_info_available") is True,
        semantic.get("sample_read") is True,
        isinstance(contract, dict),
        contract.get("stream_count_positive") is True,
        isinstance(contract.get("stream_type"), int),
        isinstance(contract.get("stream_sub_type"), int),
        isinstance(contract.get("stream_format_type"), int),
        contract.get("stream_format_size_positive") is True,
        max_frame_size_ok,
        isinstance(contract.get("stream_width"), int) and contract.get("stream_width") > 0,
        isinstance(contract.get("stream_height"), int) and contract.get("stream_height") > 0,
        isinstance(contract.get("stream_frame_rate"), int) and contract.get("stream_frame_rate") > 0,
        contract.get("sample_has_buffer") is True,
        contract.get("sample_size_positive") is True,
    ])


def successful_source_control_tunnel_transcript(transcript: dict[str, Any] | None) -> bool:
    if transcript is None:
        return False
    semantic = transcript.get("semantic", {})
    contract = transcript.get("stream_contract", {})
    return all([
        transcript.get("ok") is True,
        transcript.get("mode") == "control",
        transcript.get("missing_symbols") == [],
        isinstance(semantic, dict),
        semantic.get("opened") is True,
        semantic.get("stream_started") is True,
        semantic.get("message_sent") is True,
        semantic.get("message_received") is True,
        semantic.get("sample_message_sent") is True,
        semantic.get("sample_read") is True,
        isinstance(contract, dict),
        contract.get("sample_has_buffer") is True,
        contract.get("sample_size_positive") is True,
        result_value(transcript, "Bambu_SendMessage") == 0,
        result_value(transcript, "Bambu_SendMessage_sample") == 0,
        result_value(transcript, "Bambu_RecvMessage") == 0,
    ])


def source_control_tunnel_report_ok(report: dict[str, Any]) -> bool:
    if not (
        parity_report_ok(report)
        and parity_probe_ok(report, "source_streaming")
        and parity_comparison_ok(report, "source_streaming")
    ):
        return False
    return (
        successful_source_control_tunnel_transcript(load_probe_artifact(report, "source_streaming", "official"))
        and successful_source_control_tunnel_transcript(load_probe_artifact(report, "source_streaming", "candidate"))
    )


def source_streaming_report_ok(report: dict[str, Any]) -> bool:
    if not (
        parity_report_ok(report)
        and parity_probe_ok(report, "source_streaming")
        and parity_comparison_ok(report, "source_streaming")
        and report.get("source_streaming_parity_ok") is True
    ):
        return False
    return (
        successful_source_streaming_transcript(load_probe_artifact(report, "source_streaming", "official"))
        and successful_source_streaming_transcript(load_probe_artifact(report, "source_streaming", "candidate"))
    )


def source_input_metadata(report: dict[str, Any], side: str) -> dict[str, Any]:
    inputs = report.get("inputs", {})
    group = inputs.get(side, {}) if isinstance(inputs, dict) else {}
    source = group.get("source", {}) if isinstance(group, dict) else {}
    return source if isinstance(source, dict) else {}


def source_control_tls_input_metadata(report: dict[str, Any], side: str) -> dict[str, Any]:
    inputs = report.get("inputs", {})
    item = inputs.get(f"{side}_source", {}) if isinstance(inputs, dict) else {}
    return item if isinstance(item, dict) else {}


def artifact_json(report_path: pathlib.Path, path: str | None) -> dict[str, Any] | None:
    if not isinstance(path, str) or not path:
        return None
    artifact_path = pathlib.Path(path)
    if not artifact_path.is_absolute():
        report_relative = report_path.parent / artifact_path
        artifact_path = report_relative if report_relative.is_file() else ROOT / artifact_path
    return load_json(artifact_path)


def source_rtsp_loopback_gate(path: pathlib.Path, native_report: dict[str, Any] | None) -> dict[str, Any]:
    payload = load_json(path)
    if payload is None:
        return gate(False, path=str(path), reason="source RTSP loopback parity report is missing or invalid JSON")
    candidate_source = pathlib.Path(str(source_input_metadata(payload, "candidate").get("path", "")))
    official_source = pathlib.Path(str(source_input_metadata(payload, "official").get("path", "")))
    native_source_sha = None
    if native_report:
        native_source_sha = native_report.get("inputs", {}).get("source", {}).get("sha256")
    artifact_policy = payload.get("inputs", {}).get("artifact_policy", {})
    artifact_policy = artifact_policy if isinstance(artifact_policy, dict) else {}
    official_transcript = load_probe_artifact_with_base(path.parent, payload, "source_streaming", "official")
    candidate_transcript = load_probe_artifact_with_base(path.parent, payload, "source_streaming", "candidate")
    official_source_sha = source_input_metadata(payload, "official").get("sha256")
    candidate_source_sha = source_input_metadata(payload, "candidate").get("sha256")
    checks = {
        "report_ok": parity_report_ok(payload),
        "probe_ok": parity_probe_ok(payload, "source_streaming"),
        "comparison_ok": parity_comparison_ok(payload, "source_streaming"),
        "official_source_exists": official_source.is_file(),
        "official_source_outside_repo": bool(str(official_source)) and not is_under_repo(official_source),
        "official_source_hash_matches_report": sha256_file(official_source) == official_source_sha,
        "candidate_source_is_dylib": candidate_source.name == "libBambuSource.dylib",
        "candidate_source_hash_matches_native_report": bool(native_source_sha and sha256_file(candidate_source) == native_source_sha),
        "official_source_differs_from_candidate": bool(official_source_sha and candidate_source_sha and official_source_sha != candidate_source_sha),
        "self_compare_rejected": payload.get("inputs", {}).get("self_compare_allowed") is False,
        "artifact_policy_no_binary_copies": artifact_policy.get("copies_input_binaries") is False,
        "artifact_policy_transcripts_only": artifact_policy.get("stores_hashes_and_probe_transcripts_only") is True,
        "official_video_transcript_success": successful_source_streaming_transcript(official_transcript),
        "candidate_video_transcript_success": successful_source_streaming_transcript(candidate_transcript),
    }
    failed = [name for name, ok in checks.items() if not ok]
    return gate(not failed, path=str(path), checks=checks, failed=failed, source_rtsp_loopback_report=payload)


def source_control_tls_loopback_gate(path: pathlib.Path, native_report: dict[str, Any] | None) -> dict[str, Any]:
    payload = load_json(path)
    if payload is None:
        return gate(False, path=str(path), reason="source-control TLS loopback parity report is missing or invalid JSON")
    candidate_source = pathlib.Path(str(source_control_tls_input_metadata(payload, "candidate").get("path", "")))
    official_source = pathlib.Path(str(source_control_tls_input_metadata(payload, "official").get("path", "")))
    native_source_sha = None
    if native_report:
        native_source_sha = native_report.get("inputs", {}).get("source", {}).get("sha256")
    artifacts = payload.get("artifacts", {})
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    comparison = artifact_json(path, artifacts.get("comparison"))
    official_contract = comparison.get("official_contract", {}) if isinstance(comparison, dict) else {}
    candidate_contract = comparison.get("candidate_contract", {}) if isinstance(comparison, dict) else {}
    official_validation = comparison.get("official_validation", {}) if isinstance(comparison, dict) else {}
    candidate_validation = comparison.get("candidate_validation", {}) if isinstance(comparison, dict) else {}
    official_source_sha = source_control_tls_input_metadata(payload, "official").get("sha256")
    candidate_source_sha = source_control_tls_input_metadata(payload, "candidate").get("sha256")
    checks = {
        "report_ok": parity_report_ok(payload),
        "official_source_exists": official_source.is_file(),
        "official_source_outside_repo": bool(str(official_source)) and not is_under_repo(official_source),
        "official_source_hash_matches_report": sha256_file(official_source) == official_source_sha,
        "candidate_source_is_dylib": candidate_source.name == "libBambuSource.dylib",
        "candidate_source_hash_matches_native_report": bool(native_source_sha and sha256_file(candidate_source) == native_source_sha),
        "official_source_differs_from_candidate": bool(official_source_sha and candidate_source_sha and official_source_sha != candidate_source_sha),
        "stores_hashes_and_probe_transcripts_only": payload.get("inputs", {}).get("stores_hashes_and_probe_transcripts_only") is True,
        "passwords_redacted": payload.get("inputs", {}).get("passwords_redacted") is True,
        "official_artifact_exists": artifact_json(path, artifacts.get("official")) is not None,
        "candidate_artifact_exists": artifact_json(path, artifacts.get("candidate")) is not None,
        "comparison_artifact_ok": isinstance(comparison, dict) and comparison.get("ok") is True,
        "official_validation_ok": isinstance(official_validation, dict) and official_validation.get("ok") is True,
        "candidate_validation_ok": isinstance(candidate_validation, dict) and candidate_validation.get("ok") is True,
        "stable_wire_contracts_match": official_contract == candidate_contract and isinstance(official_contract, dict),
    }
    failed = [name for name, ok in checks.items() if not ok]
    return gate(not failed, path=str(path), checks=checks, failed=failed, source_control_tls_loopback_report=payload)


def parity_report_ok(report: dict[str, Any]) -> bool:
    return report.get("ok") is True and report.get("failed") == []


def print_job_probe_name(mode: str, mode_count: int) -> str:
    return "print_job" if mode_count == 1 else f"print_job_{mode.replace('-', '_')}"


def raw_real_printer_parity_ok(official_report: dict[str, Any], source_control_report: dict[str, Any] | None) -> tuple[bool, dict[str, bool]]:
    inputs = official_report.get("inputs", {})
    inputs = inputs if isinstance(inputs, dict) else {}
    requested_modes = inputs.get("print_job_modes")
    requested_modes = requested_modes if isinstance(requested_modes, list) else []
    required_modes = ("upload-only", "local-print", "sdcard-print")
    print_job_checks = {
        f"print_job_{mode.replace('-', '_')}": (
            mode in requested_modes
            and parity_probe_ok(official_report, print_job_probe_name(mode, len(requested_modes)))
            and parity_comparison_ok(official_report, print_job_probe_name(mode, len(requested_modes)))
            and successful_print_job_transcript(load_probe_artifact(official_report, print_job_probe_name(mode, len(requested_modes)), "official"), mode)
            and successful_print_job_transcript(load_probe_artifact(official_report, print_job_probe_name(mode, len(requested_modes)), "candidate"), mode)
        )
        for mode in required_modes
    }
    source_control_report = source_control_report if isinstance(source_control_report, dict) else {}
    checks = {
        "report_ok": parity_report_ok(official_report),
        "printer_workflow": (
            parity_probe_ok(official_report, "printer_workflow")
            and parity_comparison_ok(official_report, "printer_workflow")
            and successful_printer_workflow_transcript(load_probe_artifact(official_report, "printer_workflow", "official"))
            and successful_printer_workflow_transcript(load_probe_artifact(official_report, "printer_workflow", "candidate"))
        ),
        **print_job_checks,
        "source_streaming": source_streaming_report_ok(official_report),
        "source_control_tunnel": source_control_tunnel_report_ok(source_control_report),
    }
    return all(checks.values()), checks


def local_smoke_check(local_smoke_report: dict[str, Any] | None, name: str) -> bool:
    if not isinstance(local_smoke_report, dict):
        return False
    checks = local_smoke_report.get("checks", {})
    return isinstance(checks, dict) and checks.get(name) is True


def existing_path(path: str | pathlib.Path | None) -> pathlib.Path | None:
    if not path:
        return None
    candidate = pathlib.Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return candidate if candidate.is_file() else None


def real_printer_gate(
    official_report: dict[str, Any] | None,
    dry_run: pathlib.Path | None,
    discovery_report_path: pathlib.Path | None,
    source_control_report_path: pathlib.Path | None,
    test_3mf: pathlib.Path | None,
    official_inputs_current: bool,
    local_smoke_report: dict[str, Any] | None,
    defer_manual_testing: bool,
) -> dict[str, Any]:
    official_report = official_report if isinstance(official_report, dict) else {}
    source_control_report = load_json(source_control_report_path) if source_control_report_path else None
    raw_ok, raw_checks = raw_real_printer_parity_ok(official_report, source_control_report)
    if raw_ok and official_inputs_current:
        return gate(True, reason="official-vs-candidate real-printer native parity passed", raw_checks=raw_checks)
    dry_run_payload = load_json(dry_run) if dry_run else None
    discovery_result = load_json(discovery_report_path) if discovery_report_path else None
    selected_test_3mf = existing_path(test_3mf)
    missing_inputs = []
    if dry_run_payload:
        printer = dry_run_payload.get("printer", {})
        printer = printer if isinstance(printer, dict) else {}
        print_job = dry_run_payload.get("print_job", {})
        print_job = print_job if isinstance(print_job, dict) else {}
        dry_run_test_3mf = existing_path(print_job.get("file"))
        if not printer.get("dev_id_present"):
            missing_inputs.append("printer dev id")
        if not printer.get("dev_ip_present"):
            missing_inputs.append("printer IP")
        if not printer.get("password_present"):
            missing_inputs.append(f"{printer.get('password_env', 'printer password/access-code env')}")
        if not dry_run_test_3mf and not selected_test_3mf:
            missing_inputs.append("test 3MF")
    else:
        missing_inputs.extend(["printer dev id", "printer IP", "printer password/access-code env"])
        if not selected_test_3mf:
            missing_inputs.append("test 3MF")
    needed_action = [
        "provide printer dev id",
        "provide printer IP",
        "set printer password/access-code env",
        "run run_real_printer_parity.py with --macos-native-readiness, --include-source-streaming, --include-source-control-tunnel, and --confirm-start-prints",
    ]
    dry_run_validators = {
        "real_printer_wrapper": local_smoke_check(local_smoke_report, "preflight_real_printer_parity_dry_run"),
        "source_streaming_wrapper": local_smoke_check(local_smoke_report, "preflight_source_streaming_parity_dry_run"),
        "source_control_tunnel_wrapper": local_smoke_check(local_smoke_report, "preflight_source_control_tunnel_parity_dry_run"),
    }
    if (
        defer_manual_testing
        and dry_run_payload is not None
        and dry_run_payload.get("ok") is True
        and dry_run_payload.get("dry_run") is True
        and all(dry_run_validators.values())
        and selected_test_3mf is not None
    ):
        return gate(
            True,
            reason="manual real-printer testing deferred by plan contract; dry-run command evidence remains actionable",
            manual_testing_deferred=True,
            missing_inputs=missing_inputs,
            needed_action=needed_action,
            dry_run_validators=dry_run_validators,
            dry_run_report=str(dry_run) if dry_run else None,
            dry_run_loaded=True,
            discovery_report=str(discovery_report_path) if discovery_report_path else None,
            discovery_report_loaded=discovery_result is not None,
            discovery_result=discovery_result,
            raw_checks=raw_checks,
            source_control_report=str(source_control_report_path) if source_control_report_path else None,
            source_control_report_loaded=source_control_report is not None,
            test_3mf=str(selected_test_3mf),
            test_3mf_available=True,
        )
    return gate(
        False,
        reason="native real-printer parity requires printer dev id, printer IP, access code/password env, and a test 3MF before completion",
        missing_inputs=missing_inputs,
        needed_action=needed_action,
        dry_run_validators=dry_run_validators,
        dry_run_report=str(dry_run) if dry_run else None,
        dry_run_loaded=dry_run_payload is not None,
        discovery_report=str(discovery_report_path) if discovery_report_path else None,
        discovery_report_loaded=discovery_result is not None,
        discovery_result=discovery_result,
        raw_checks=raw_checks,
        source_control_report=str(source_control_report_path) if source_control_report_path else None,
        source_control_report_loaded=source_control_report is not None,
        test_3mf=str(selected_test_3mf) if selected_test_3mf else None,
        test_3mf_available=selected_test_3mf is not None,
    )


def cloud_service_gate(
    official_report: dict[str, Any] | None,
    official_inputs_current: bool,
    scoped_out: bool,
    local_smoke_report: dict[str, Any] | None,
    dry_run: pathlib.Path | None = None,
) -> dict[str, Any]:
    official_report = official_report if isinstance(official_report, dict) else {}
    dry_run_payload = load_json(dry_run) if dry_run else None
    cloud_service_official = load_probe_artifact(official_report, "cloud_service", "official")
    cloud_service_candidate = load_probe_artifact(official_report, "cloud_service", "candidate")
    raw_authorized_checks = {
        "probe_ok": parity_probe_ok(official_report, "cloud_service"),
        "comparison_ok": parity_comparison_ok(official_report, "cloud_service"),
        "official_authorized_success": successful_authorized_cloud_service_transcript(cloud_service_official),
        "candidate_authorized_success": successful_authorized_cloud_service_transcript(cloud_service_candidate),
    }
    authorized_cloud_ok = official_inputs_current and official_report.get("ok") is True and all(raw_authorized_checks.values())
    if authorized_cloud_ok:
        return gate(True, reason="authorized native cloud/service parity passed", authorized_cloud_ok=True, raw_authorized_checks=raw_authorized_checks)
    checks = official_report.get("checks", {}) if official_report else {}
    checks = checks if isinstance(checks, dict) else {}
    safe_failure_checks = {
        "report_ok": parity_report_ok(official_report),
        "compare_unsupported": checks.get("compare_unsupported") is True,
        "probe_unsupported_artifacts_match": checks.get("probe_unsupported_artifacts_match") is True,
        "unsupported_probe_ok": parity_probe_ok(official_report, "unsupported"),
        "unsupported_comparison_ok": parity_comparison_ok(official_report, "unsupported"),
    }
    safe_failure_ok = safe_failure_checks["report_ok"] and (
        (
            safe_failure_checks["compare_unsupported"]
            and safe_failure_checks["probe_unsupported_artifacts_match"]
        )
        or (
            safe_failure_checks["unsupported_probe_ok"]
            and safe_failure_checks["unsupported_comparison_ok"]
        )
    )
    if scoped_out and official_inputs_current and safe_failure_ok:
        return gate(
            True,
            reason="cloud/service APIs are scoped out for this native target with concrete safe-failure checks",
            approved_scope_out=True,
            safe_failure_ok=True,
            safe_failure_checks=safe_failure_checks,
            raw_authorized_checks=raw_authorized_checks,
        )
    missing_inputs = [] if authorized_cloud_ok else ["authorized cloud login context"]
    if not official_inputs_current:
        missing_inputs.insert(0, "current official macOS dylibs")
    if dry_run_payload:
        cloud = dry_run_payload.get("cloud", {})
        cloud = cloud if isinstance(cloud, dict) else {}
        dry_run_missing_inputs = []
        if not cloud.get("user_info_file_present") and not cloud.get("user_info_env_present"):
            dry_run_missing_inputs.append(cloud.get("user_info_env") or "cloud user-info file/env")
        if cloud.get("ticket_env") and not cloud.get("ticket_env_present"):
            dry_run_missing_inputs.append(cloud.get("ticket_env"))
        if cloud.get("access_token_env") and not cloud.get("access_token_env_present"):
            dry_run_missing_inputs.append(cloud.get("access_token_env"))
        missing_inputs = dry_run_missing_inputs or missing_inputs
    return gate(
        False,
        reason="authorized native cloud/service parity is missing, or cloud/service scope-out has not been approved and recorded",
        missing_inputs=missing_inputs,
        needed_decision="provide authorized cloud parity inputs or approve a cloud/service scope-out with concrete safe-failure checks",
        needed_action=[
            "provide authorized Bambu cloud login context and run run_authorized_cloud_parity.py with --macos-native-readiness",
            "or approve a cloud/service scope-out for this native target",
            "if scoped out, rerun native readiness with --cloud-service-scoped-out and concrete safe-failure checks",
        ],
        dry_run_validators={
            "authorized_cloud_wrapper": local_smoke_check(local_smoke_report, "preflight_authorized_cloud_parity_dry_run"),
        },
        safe_failure_ok=safe_failure_ok,
        safe_failure_checks=safe_failure_checks,
        raw_authorized_checks=raw_authorized_checks,
        dry_run_report=str(dry_run) if dry_run else None,
        dry_run_loaded=dry_run_payload is not None,
    )


def completion_criteria(report: dict[str, Any]) -> dict[str, bool]:
    gates = report["gates"]
    native_loader_ok = gates.get("native_loader_routing", {}).get("ok") is True
    native_gui_startup_ok = gates.get("native_gui_startup", {}).get("ok") is True
    criteria = {
        "native_macos_mode_loads_native_network_and_source_dylibs_directly": gates.get("macos_native_plugin", {}).get("ok") is True
        and native_loader_ok
        and native_gui_startup_ok,
        "native_macos_mode_does_not_require_or_launch_bridge_components": gates.get("macos_native_plugin", {}).get("ok") is True
        and native_loader_ok
        and native_gui_startup_ok,
        "bridge_fallback_remains_available": gates.get("bridge_fallback_preserved", {}).get("ok") is True,
        "native_macos_package_staging_path_can_run_without_lima_or_linux_runtime": gates.get("native_packaging", {}).get("ok") is True,
        "native_macos_plugin_verification_passes": gates.get("macos_native_plugin", {}).get("ok") is True,
        "native_macos_gui_startup_smoke_passes": native_gui_startup_ok,
        "local_candidate_smoke_passes": gates.get("local_candidate_smoke", {}).get("ok") is True,
        "native_official_vs_candidate_parity_passes_for_required_local_offline_behavior": gates.get("official_parity", {}).get("ok") is True
        and gates.get("source_rtsp_loopback_parity", {}).get("ok") is True
        and gates.get("source_control_tls_loopback_parity", {}).get("ok") is True,
        "native_real_printer_parity_completed": gates.get("real_printer_parity", {}).get("ok") is True,
        "cloud_service_parity_completed_or_approved_scope_out": gates.get("cloud_service_parity", {}).get("ok") is True,
        "clean_room_artifact_verification_passes": gates.get("clean_room_artifacts", {}).get("ok") is True,
    }
    criteria["final_readiness_ok"] = not report.get("blockers") and all(criteria.values())
    if set(criteria) != EXPECTED_NATIVE_COMPLETION_CRITERIA:
        raise RuntimeError("native completion criteria keys drifted")
    return criteria


def blocked_actions(report: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    gates = report.get("gates", {})
    gates = gates if isinstance(gates, dict) else {}
    for name, status in sorted(gates.items()):
        if not isinstance(status, dict) or status.get("ok") is True:
            continue
        missing_inputs = status.get("missing_inputs")
        needed_action = status.get("needed_action")
        if not isinstance(missing_inputs, list) or not missing_inputs:
            continue
        if not isinstance(needed_action, list) or not needed_action:
            continue
        action: dict[str, Any] = {"gate": name, "reason": status.get("reason")}
        for key in ("missing_inputs", "needed_action", "needed_decision"):
            value = status.get(key)
            if value:
                action[key] = value
        actions.append(action)
    return actions


def successful_probe() -> dict[str, Any]:
    return {"official": {"ok": True}, "candidate": {"ok": True}}


def successful_comparison() -> dict[str, Any]:
    return {"ok": True}


def assert_true(value: bool, description: str, detail: Any = None) -> None:
    if not value:
        raise RuntimeError(f"{description} failed: {detail}")


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="bambu-native-cloud-") as tmp_cloud:
        cloud_dir = pathlib.Path(tmp_cloud)
        official_cloud = cloud_dir / "official_cloud.json"
        candidate_cloud = cloud_dir / "candidate_cloud.json"
        cloud_transcript = {
            "ok": True,
            "expect_success": True,
            "allow_network": True,
            "agent_created": True,
            "missing_symbols": [],
            "semantic": {
                "login_ok": True,
                "network_ok": True,
                "service_ok": True,
                "non_unsupported_service_results": 1,
            },
        }
        official_cloud.write_text(json.dumps(cloud_transcript), encoding="utf-8")
        candidate_cloud.write_text(json.dumps(cloud_transcript), encoding="utf-8")
        authorized_cloud = {
            "ok": True,
            "failed": [],
            "cloud_service_parity_ok": True,
            "probes": {"cloud_service": {"official": {"ok": True, "path": str(official_cloud)}, "candidate": {"ok": True, "path": str(candidate_cloud)}}},
            "comparisons": {"cloud_service": successful_comparison()},
        }
        summary_only_cloud = {
            "ok": True,
            "failed": [],
            "cloud_service_parity_ok": True,
        }
        offline_cloud = {
            "ok": True,
            "probes": {"cloud_service": successful_probe()},
            "comparisons": {"cloud_service": successful_comparison()},
        }
        scoped_cloud = {
            "ok": True,
            "failed": [],
            "probes": {"unsupported": successful_probe()},
            "comparisons": {"unsupported": successful_comparison()},
            "checks": {
                "compare_unsupported": True,
                "probe_unsupported_artifacts_match": True,
            },
        }
        partial_scoped_cloud = {
            "ok": True,
            "failed": [],
            "checks": {
                "compare_unsupported": True,
                "probe_unsupported_artifacts_match": False,
            },
        }
        missing_cloud = {"ok": False, "probes": {}, "comparisons": {}}
        assert_true(cloud_service_gate(authorized_cloud, True, False, None)["ok"] is True, "authorized cloud parity")
        assert_true(cloud_service_gate(authorized_cloud, False, False, None)["ok"] is False, "stale authorized cloud parity")
        assert_true(cloud_service_gate(summary_only_cloud, True, False, None)["ok"] is False, "summary-only cloud parity")
        assert_true(cloud_service_gate(offline_cloud, True, False, None)["ok"] is False, "offline cloud parity does not satisfy authorized cloud parity")
        assert_true(cloud_service_gate(scoped_cloud, True, True, None)["ok"] is True, "approved cloud scope-out")
        assert_true(cloud_service_gate(scoped_cloud, False, True, None)["ok"] is False, "stale approved cloud scope-out")
        assert_true(cloud_service_gate(scoped_cloud, True, False, None)["ok"] is False, "unapproved cloud scope-out")
        assert_true(cloud_service_gate(partial_scoped_cloud, True, True, None)["ok"] is False, "partial cloud safe-failure scope-out")
        assert_true(cloud_service_gate(missing_cloud, True, True, None)["ok"] is False, "missing cloud safe-failure evidence")

    with tempfile.TemporaryDirectory(prefix="bambu-native-source-control-summary-") as tmp_summary:
        source_control_dir = pathlib.Path(tmp_summary)
        official_workflow = source_control_dir / "official_workflow.json"
        candidate_workflow = source_control_dir / "candidate_workflow.json"
        official_upload_only = source_control_dir / "official_upload_only.json"
        candidate_upload_only = source_control_dir / "candidate_upload_only.json"
        official_local_print = source_control_dir / "official_local_print.json"
        candidate_local_print = source_control_dir / "candidate_local_print.json"
        official_sdcard_print = source_control_dir / "official_sdcard_print.json"
        candidate_sdcard_print = source_control_dir / "candidate_sdcard_print.json"
        official_source = source_control_dir / "official_source.json"
        candidate_source = source_control_dir / "candidate_source.json"
        official_control = source_control_dir / "official_control.json"
        candidate_control = source_control_dir / "candidate_control.json"
        printer_workflow_transcript = {
            "dev_id": "printer-dev-id",
            "dev_ip": "192.0.2.10",
            "password_present": True,
            "agent_created": True,
            "missing_symbols": [],
            "destroy_result": 0,
            "results": {
                "init_log": 0,
                "set_config_dir": 0,
                "set_country_code": 0,
                "start": 0,
                "connect_printer": 0,
                "send_message_to_printer": 0,
                "disconnect_printer": 0,
            },
            "events": [{"name": "local_connect", "status": 0}],
        }

        def print_job_transcript(mode: str) -> dict[str, Any]:
            return {
                "dev_id": "printer-dev-id",
                "dev_ip": "192.0.2.10",
                "mode": mode,
                "password_present": True,
                "file_present": True,
                "remote_name_present": True,
                "agent_created": True,
                "missing_symbols": [],
                "destroy_result": 0,
                "job_result": 0,
                "ok": True,
                "results": {
                    "init_log": 0,
                    "set_config_dir": 0,
                    "set_country_code": 0,
                    "start": 0,
                },
                "status_events": [{"status": 6, "code": 0, "message": "finished"}],
            }

        source_streaming_transcript = {
            "ok": True,
            "mode": "video",
            "missing_symbols": [],
            "semantic": {
                "opened": True,
                "stream_started": True,
                "stream_info_available": True,
                "sample_read": True,
            },
            "stream_contract": {
                "stream_count_positive": True,
                "stream_type": 0,
                "stream_sub_type": 0,
                "stream_format_type": 1,
                "stream_format_size_positive": True,
                "stream_width": 160,
                "stream_height": 120,
                "stream_frame_rate": 5,
                "sample_has_buffer": True,
                "sample_size_positive": True,
            },
        }
        source_control_transcript = {
            "ok": True,
            "mode": "control",
            "missing_symbols": [],
            "semantic": {
                "opened": True,
                "stream_started": True,
                "message_sent": True,
                "message_received": True,
                "sample_message_sent": True,
                "sample_read": True,
            },
            "stream_contract": {
                "sample_has_buffer": True,
                "sample_size_positive": True,
            },
            "results": {
                "Bambu_SendMessage": {"value": 0},
                "Bambu_SendMessage_sample": {"value": 0},
                "Bambu_RecvMessage": {"value": 0},
            },
        }
        official_workflow.write_text(json.dumps(printer_workflow_transcript), encoding="utf-8")
        candidate_workflow.write_text(json.dumps(printer_workflow_transcript), encoding="utf-8")
        official_upload_only.write_text(json.dumps(print_job_transcript("upload-only")), encoding="utf-8")
        candidate_upload_only.write_text(json.dumps(print_job_transcript("upload-only")), encoding="utf-8")
        official_local_print.write_text(json.dumps(print_job_transcript("local-print")), encoding="utf-8")
        candidate_local_print.write_text(json.dumps(print_job_transcript("local-print")), encoding="utf-8")
        official_sdcard_print.write_text(json.dumps(print_job_transcript("sdcard-print")), encoding="utf-8")
        candidate_sdcard_print.write_text(json.dumps(print_job_transcript("sdcard-print")), encoding="utf-8")
        official_source.write_text(json.dumps(source_streaming_transcript), encoding="utf-8")
        candidate_source.write_text(json.dumps(source_streaming_transcript), encoding="utf-8")
        official_control.write_text(json.dumps(source_control_transcript), encoding="utf-8")
        candidate_control.write_text(json.dumps(source_control_transcript), encoding="utf-8")
        printer_report = {
            "ok": True,
            "failed": [],
            "real_printer_workflows_ok": True,
            "source_streaming_parity_ok": True,
            "inputs": {"print_job_modes": ["upload-only", "local-print", "sdcard-print"]},
            "probes": {
                "printer_workflow": {
                    "official": {"ok": True, "path": str(official_workflow)},
                    "candidate": {"ok": True, "path": str(candidate_workflow)},
                },
                "print_job_upload_only": {
                    "official": {"ok": True, "path": str(official_upload_only)},
                    "candidate": {"ok": True, "path": str(candidate_upload_only)},
                },
                "print_job_local_print": {
                    "official": {"ok": True, "path": str(official_local_print)},
                    "candidate": {"ok": True, "path": str(candidate_local_print)},
                },
                "print_job_sdcard_print": {
                    "official": {"ok": True, "path": str(official_sdcard_print)},
                    "candidate": {"ok": True, "path": str(candidate_sdcard_print)},
                },
                "source_streaming": {
                    "official": {"ok": True, "path": str(official_source)},
                    "candidate": {"ok": True, "path": str(candidate_source)},
                },
            },
            "comparisons": {
                "printer_workflow": successful_comparison(),
                "print_job_upload_only": successful_comparison(),
                "print_job_local_print": successful_comparison(),
                "print_job_sdcard_print": successful_comparison(),
                "source_streaming": successful_comparison(),
            },
        }
        source_control_report = {
            "ok": True,
            "failed": [],
            "source_control_tunnel_parity_ok": True,
            "probes": {
                "source_streaming": {
                    "official": {"ok": True, "path": str(official_control)},
                    "candidate": {"ok": True, "path": str(candidate_control)},
                }
            },
            "comparisons": {"source_streaming": successful_comparison()},
        }
        printer_ok, printer_checks = raw_real_printer_parity_ok(printer_report, source_control_report)
        assert_true(printer_ok, "raw real-printer parity", printer_checks)
        summary_gate = real_printer_gate(printer_report, None, None, None, None, True, None, False)
        assert_true(summary_gate["ok"] is False, "real-printer summary rejects missing source-control report", summary_gate)
        source_control_report_path = pathlib.Path(tmp_summary) / "source_control.json"
        source_control_report_path.write_text(json.dumps(source_control_report), encoding="utf-8")
        summary_gate = real_printer_gate(printer_report, None, None, source_control_report_path, None, True, None, False)
        assert_true(summary_gate["ok"] is True, "real-printer summary accepts source-control report", summary_gate)
        stale_summary_gate = real_printer_gate(printer_report, None, None, source_control_report_path, None, False, None, False)
        assert_true(
            stale_summary_gate["ok"] is False and "current official macOS dylibs" not in stale_summary_gate["missing_inputs"],
            "stale real-printer parity inputs are not accepted and official input status stays in official_parity",
            stale_summary_gate,
        )
        summary_only_printer_report = {
            "ok": True,
            "failed": [],
            "real_printer_workflows_ok": True,
            "source_streaming_parity_ok": True,
            "inputs": {"print_job_modes": ["upload-only", "local-print", "sdcard-print"]},
            "probes": {
                "printer_workflow": successful_probe(),
                "print_job_upload_only": successful_probe(),
                "print_job_local_print": successful_probe(),
                "print_job_sdcard_print": successful_probe(),
                "source_streaming": {
                    "official": {"ok": True, "path": str(official_source)},
                    "candidate": {"ok": True, "path": str(candidate_source)},
                },
            },
            "comparisons": {
                "printer_workflow": successful_comparison(),
                "print_job_upload_only": successful_comparison(),
                "print_job_local_print": successful_comparison(),
                "print_job_sdcard_print": successful_comparison(),
                "source_streaming": successful_comparison(),
            },
        }
        summary_only_printer_gate = real_printer_gate(summary_only_printer_report, None, None, source_control_report_path, None, True, None, False)
        assert_true(not summary_only_printer_gate["ok"], "summary-only real-printer workflow rejection", summary_only_printer_gate)
        summary_only_source_control_report = {
            "ok": True,
            "failed": [],
            "source_control_tunnel_parity_ok": True,
            "probes": {"source_streaming": successful_probe()},
            "comparisons": {"source_streaming": successful_comparison()},
        }
        summary_only_control_ok = source_control_tunnel_report_ok(summary_only_source_control_report)
        assert_true(not summary_only_control_ok, "summary-only source-control tunnel rejection", summary_only_source_control_report)
        summary_only_source_streaming_report = {
            "ok": True,
            "failed": [],
            "source_streaming_parity_ok": True,
            "probes": {"source_streaming": successful_probe()},
            "comparisons": {"source_streaming": successful_comparison()},
        }
        summary_only_source_streaming_ok = source_streaming_report_ok(summary_only_source_streaming_report)
        assert_true(not summary_only_source_streaming_ok, "summary-only source-streaming rejection", summary_only_source_streaming_report)
        missing_control_ok, missing_control_checks = raw_real_printer_parity_ok(printer_report, None)
        assert_true(not missing_control_ok and missing_control_checks["source_control_tunnel"] is False, "missing source-control tunnel rejection", missing_control_checks)
        video_source_report = {
            "ok": True,
            "failed": [],
            "source_streaming_parity_ok": True,
            "probes": {"source_streaming": successful_probe()},
            "comparisons": {"source_streaming": successful_comparison()},
        }
        video_source_control_ok, video_source_control_checks = raw_real_printer_parity_ok(printer_report, video_source_report)
        assert_true(
            not video_source_control_ok and video_source_control_checks["source_control_tunnel"] is False,
            "video source-streaming parity cannot satisfy source-control tunnel evidence",
            video_source_control_checks,
        )

        upload_only_report = {
            "ok": True,
            "failed": [],
            "source_streaming_parity_ok": True,
            "inputs": {"print_job_modes": ["upload-only"]},
            "probes": {
                "printer_workflow": {
                    "official": {"ok": True, "path": str(official_workflow)},
                    "candidate": {"ok": True, "path": str(candidate_workflow)},
                },
                "print_job": {
                    "official": {"ok": True, "path": str(official_upload_only)},
                    "candidate": {"ok": True, "path": str(candidate_upload_only)},
                },
                "source_streaming": {
                    "official": {"ok": True, "path": str(official_source)},
                    "candidate": {"ok": True, "path": str(candidate_source)},
                },
            },
            "comparisons": {
                "printer_workflow": successful_comparison(),
                "print_job": successful_comparison(),
                "source_streaming": successful_comparison(),
            },
        }
        upload_only_ok, upload_only_checks = raw_real_printer_parity_ok(upload_only_report, source_control_report)
        assert_true(
            not upload_only_ok
            and upload_only_checks["print_job_upload_only"] is True
            and upload_only_checks["print_job_local_print"] is False
            and upload_only_checks["print_job_sdcard_print"] is False,
            "incomplete print mode rejection",
            upload_only_checks,
        )
    dry_run_smoke = {
        "checks": {
            "preflight_real_printer_parity_dry_run": True,
            "preflight_source_streaming_parity_dry_run": True,
            "preflight_source_control_tunnel_parity_dry_run": True,
            "preflight_authorized_cloud_parity_dry_run": True,
        }
    }
    with tempfile.TemporaryDirectory(prefix="bambu-native-discovery-") as tmp_discovery:
        tmp_discovery_path = pathlib.Path(tmp_discovery)
        discovery_report = tmp_discovery_path / "discovery.json"
        available_test_3mf = tmp_discovery_path / "OrcaCube_v2.3mf"
        available_test_3mf.write_text("fixture", encoding="utf-8")
        discovery_report.write_text(json.dumps({"ok": False, "devices": [], "send_errors": ["no route"]}), encoding="utf-8")
        missing_printer_gate = real_printer_gate({}, None, discovery_report, None, available_test_3mf, True, dry_run_smoke, False)
        assert_true(
            "current official macOS dylibs" not in missing_printer_gate["missing_inputs"]
            and "printer dev id" in missing_printer_gate["missing_inputs"]
            and "test 3MF" not in missing_printer_gate["missing_inputs"]
            and missing_printer_gate["test_3mf_available"] is True
            and all(missing_printer_gate["dry_run_validators"].values())
            and missing_printer_gate["discovery_report_loaded"] is True
            and missing_printer_gate["discovery_result"]["devices"] == [],
            "real-printer missing inputs omit official dylibs and available test 3MF when official parity is current",
            missing_printer_gate,
        )
        dry_run_report = tmp_discovery_path / "real_printer_dry_run_missing_inputs.json"
        dry_run_report.write_text(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "printer": {
                        "dev_id_present": False,
                        "dev_ip_present": False,
                        "password_env": "BAMBU_NETWORK_PRINTER_PASSWORD",
                        "password_present": False,
                    },
                    "print_job": {"file": str(available_test_3mf)},
                }
            ),
            encoding="utf-8",
        )
        deferred_printer_gate = real_printer_gate({}, dry_run_report, discovery_report, None, available_test_3mf, True, dry_run_smoke, True)
        assert_true(
            deferred_printer_gate["ok"] is True
            and deferred_printer_gate["manual_testing_deferred"] is True
            and deferred_printer_gate["missing_inputs"] == [
                "printer dev id",
                "printer IP",
                "BAMBU_NETWORK_PRINTER_PASSWORD",
            ],
            "manual real-printer testing can be explicitly deferred with actionable dry-run evidence",
            deferred_printer_gate,
        )
    missing_official_gate = real_printer_gate({}, None, None, None, None, False, dry_run_smoke, False)
    assert_true(
        "current official macOS dylibs" not in missing_official_gate["missing_inputs"]
        and "printer dev id" in missing_official_gate["missing_inputs"],
        "real-printer missing inputs stay scoped to printer inputs when official parity is stale or missing",
        missing_official_gate,
    )
    with tempfile.TemporaryDirectory(prefix="bambu-native-cloud-dry-run-") as tmp_cloud_dry_run:
        cloud_dry_run_report = pathlib.Path(tmp_cloud_dry_run) / "authorized_cloud_dry_run.json"
        cloud_dry_run_report.write_text(json.dumps({
            "ok": True,
            "dry_run": True,
            "cloud": {
                "user_info_file_present": False,
                "user_info_env": "BAMBU_CLOUD_LOGIN_INFO_JSON",
                "user_info_env_present": False,
                "ticket_env": "BAMBU_CLOUD_TICKET",
                "ticket_env_present": False,
                "access_token_env": "BAMBU_CLOUD_ACCESS_TOKEN",
                "access_token_env_present": False,
            },
        }), encoding="utf-8")
        missing_cloud_gate = cloud_service_gate(missing_cloud, True, False, dry_run_smoke, cloud_dry_run_report)
        assert_true(
            missing_cloud_gate["dry_run_validators"]["authorized_cloud_wrapper"] is True
            and missing_cloud_gate["dry_run_loaded"] is True
            and missing_cloud_gate["missing_inputs"] == [
                "BAMBU_CLOUD_LOGIN_INFO_JSON",
                "BAMBU_CLOUD_TICKET",
                "BAMBU_CLOUD_ACCESS_TOKEN",
            ],
            "cloud-service blocker carries authorized-cloud dry-run validator evidence",
            missing_cloud_gate,
        )
    blocked_action_report = {"gates": {"real_printer_parity": missing_official_gate, "cloud_service_parity": missing_cloud_gate}}
    blocked_action_summary = blocked_actions(blocked_action_report)
    assert_true(
        len(blocked_action_summary) == 2
        and all("needed_action" in item for item in blocked_action_summary)
        and any(item["gate"] == "real_printer_parity" for item in blocked_action_summary)
        and any(item["gate"] == "cloud_service_parity" for item in blocked_action_summary),
        "blocked action summary includes actionable external gates",
        blocked_action_summary,
    )
    local_failure_blocked_actions = blocked_actions({
        "gates": {
            "native_packaging": {
                "ok": False,
                "reason": "native package contains bridge artifacts",
            },
            "real_printer_parity": missing_official_gate,
        },
    })
    assert_true(
        [item["gate"] for item in local_failure_blocked_actions] == ["real_printer_parity"],
        "blocked action summary excludes non-actionable local gate failures",
        local_failure_blocked_actions,
    )
    criteria_shape_report = {
        "ok": False,
        "gates": {
            "macos_native_plugin": {"ok": True},
            "native_loader_routing": {"ok": True},
            "native_gui_startup": {"ok": True},
            "bridge_fallback_preserved": {"ok": True},
            "native_packaging": {"ok": True},
            "local_candidate_smoke": {"ok": True},
            "official_parity": {"ok": True},
            "real_printer_parity": {"ok": False},
            "cloud_service_parity": {"ok": False},
            "clean_room_artifacts": {"ok": True},
        },
    }
    criteria_shape = completion_criteria(criteria_shape_report)
    assert_true(
        set(criteria_shape) == EXPECTED_NATIVE_COMPLETION_CRITERIA
        and criteria_shape["native_real_printer_parity_completed"] is False
        and criteria_shape["cloud_service_parity_completed_or_approved_scope_out"] is False
        and criteria_shape["final_readiness_ok"] is False,
        "native completion criteria generator emits the expected key set",
        criteria_shape,
    )
    complete_criteria_report = {
        "blockers": [],
        "gates": {
            "macos_native_plugin": {"ok": True},
            "native_loader_routing": {"ok": True},
            "native_gui_startup": {"ok": True},
            "bridge_fallback_preserved": {"ok": True},
            "native_packaging": {"ok": True},
            "local_candidate_smoke": {"ok": True},
            "official_parity": {"ok": True},
            "source_rtsp_loopback_parity": {"ok": True},
            "source_control_tls_loopback_parity": {"ok": True},
            "real_printer_parity": {"ok": True},
            "cloud_service_parity": {"ok": True},
            "clean_room_artifacts": {"ok": True},
        },
    }
    complete_criteria = completion_criteria(complete_criteria_report)
    assert_true(
        complete_criteria["final_readiness_ok"] is True and all(complete_criteria.values()),
        "native completion criteria can become complete when every gate is green",
        complete_criteria,
    )

    with tempfile.TemporaryDirectory(prefix="bambu-native-bridge-config-") as tmp_config:
        config_path = pathlib.Path(tmp_config) / "PJarczakLinuxBridgeConfig.cpp"
        config_path.write_text(
            """
bool enabled()
{
    if (macos_native_plugin_enabled())
        return false;
    bool forced = false;
    if (env_flag("PJARCZAK_LINUX_BRIDGE_ENABLED", forced))
        return forced;
#elif defined(__WXMAC__) || defined(__APPLE__)
    return true;
#endif
}

bool macos_native_plugin_enabled()
{
#if defined(__WXMAC__) || defined(__APPLE__)
    bool forced = false;
    return env_flag("PJARCZAK_BAMBU_MACOS_NATIVE_PLUGIN", forced) && forced;
#else
    return false;
#endif
}

bool use_bridge_network_module()
{
#elif defined(__WXMAC__) || defined(__APPLE__)
    return !macos_native_plugin_enabled();
#endif
}

bool source_module_is_network_module()
{
    return use_bridge_network_module();
}

bool should_force_linux_plugin_payload(const std::string& plugin_name)
{
    return enabled() && use_bridge_network_module() && plugin_name == "plugins";
}
""",
            encoding="utf-8",
        )
        bridge_gate = bridge_fallback_gate(config_path)
        assert_true(bridge_gate["ok"] is True, "bridge fallback source-helper delegation fixture", bridge_gate)
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                "return use_bridge_network_module();",
                "return true;",
            ),
            encoding="utf-8",
        )
        weak_bridge_gate = bridge_fallback_gate(config_path)
        assert_true(
            weak_bridge_gate["ok"] is False
            and weak_bridge_gate["checks"]["source_module_uses_same_bridge_decision"] is False,
            "bridge fallback rejects source helper that bypasses centralized decision",
            weak_bridge_gate,
        )

    with tempfile.TemporaryDirectory(prefix="bambu-native-readiness-") as tmp:
        work = pathlib.Path(tmp)
        plugin_report = work / "plugin.json"
        local_smoke = work / "local_smoke.json"
        official_parity = work / "official_parity.json"
        package_dir = work / "OrcaSlicer.app/Contents/MacOS"
        official_dir = work / "official"
        gui_log = work / "gui_native_smoke/native_startup_relevant_logs.txt"
        gui_plugin_dir = work / "gui_native_smoke_datadir/plugins"
        package_dir.mkdir(parents=True)
        official_dir.mkdir()
        gui_log.parent.mkdir(parents=True)
        gui_plugin_dir.mkdir(parents=True)
        network = package_dir / "libbambu_networking.dylib"
        source = package_dir / "libBambuSource.dylib"
        network.write_bytes(b"\xcf\xfa\xed\xfe" + b"network")
        source.write_bytes(b"\xcf\xfa\xed\xfe" + b"source")
        official_network = official_dir / "libbambu_networking.dylib"
        official_source = official_dir / "libBambuSource.dylib"
        official_network.write_bytes(b"\xcf\xfa\xed\xfe" + b"official-network")
        official_source.write_bytes(b"\xcf\xfa\xed\xfe" + b"official-source")
        (gui_plugin_dir / "libbambu_networking.dylib").write_bytes(network.read_bytes())
        (gui_plugin_dir / "libBambuSource.dylib").write_bytes(source.read_bytes())
        gui_log.write_text(
            "\n".join(
                [
                    "BBLNetworkPlugin::initialize: macOS native plugin mode enabled",
                    "initialize: loaded fallback network library /tmp/plugins/libbambu_networking.dylib",
                    "BBLNetworkPlugin::initialize: bridge_mode=false, macos_native_plugin_mode=true",
                    "on_init_network: on_init_network, load dll ok",
                    "on_init_network: on_init_network, compatibility version",
                    "get_source_module: loaded native source library /tmp/plugins/libBambuSource.dylib",
                    "on_init_network, create network agent...",
                ]
            ),
            encoding="utf-8",
        )
        plugin_report.write_text(
            json.dumps({
                "ok": True,
                "checks": {name: True for name in (
                    "network_exists",
                    "source_exists",
                    "network_is_macho",
                    "source_is_macho",
                    "network_is_dylib",
                    "source_is_dylib",
                    "network_rejects_bridge_dylib",
                    "network_rejects_linux_so",
                    "source_rejects_linux_so",
                    "source_is_separate_dylib",
                    "network_expected_native_name",
                    "source_expected_native_name",
                    "network_dlopen_dlsym",
                    "source_dlopen_dlsym",
                    "abi_mirror",
                    "cpp_signature_mirror",
                    "clean_room_artifact_self_test",
                )},
                "inputs": {
                    "network": {"sha256": sha256_file(network)},
                    "source": {"sha256": sha256_file(source)},
                },
            }),
            encoding="utf-8",
        )
        local_smoke.write_text(
            json.dumps({
                "ok": True,
                "failed": [],
                "checks": {name: True for name in REQUIRED_LOCAL_SMOKE_CHECKS},
            }),
            encoding="utf-8",
        )
        official_parity.write_text(
            json.dumps({
                "ok": True,
                "failed": [],
                "inputs": {
                    "candidate": {
                        "network": {"path": str(network), "sha256": sha256_file(network)},
                        "source": {"path": str(source), "sha256": sha256_file(source)},
                    },
                    "official": {
                        "network": {"path": str(official_network), "exists": True, "sha256": sha256_file(official_network)},
                        "source": {"path": str(official_source), "exists": True, "sha256": sha256_file(official_source)},
                    },
                },
            }),
            encoding="utf-8",
        )
        assert_true(native_plugin_gate(plugin_report)["ok"] is True, "native plugin gate self-test")
        assert_true(local_smoke_gate(local_smoke)["ok"] is True, "local smoke gate self-test")
        assert_true(official_parity_gate(official_parity, native_plugin_gate(plugin_report)["native_plugin_report"])["ok"] is True, "official parity gate self-test")
        source_rtsp_dir = work / "source_rtsp_loopback"
        source_rtsp_dir.mkdir()
        rtsp_official = source_rtsp_dir / "official_source_streaming.json"
        rtsp_candidate = source_rtsp_dir / "candidate_source_streaming.json"
        rtsp_comparison = source_rtsp_dir / "source_streaming_comparison.txt"
        source_loopback_transcript = {
            "ok": True,
            "mode": "video",
            "missing_symbols": [],
            "semantic": {
                "opened": True,
                "stream_started": True,
                "stream_info_available": True,
                "sample_read": True,
            },
            "stream_contract": {
                "stream_count_positive": True,
                "stream_type": 0,
                "stream_sub_type": 0,
                "stream_format_type": 1,
                "stream_format_size_positive": True,
                "stream_width": 160,
                "stream_height": 120,
                "stream_frame_rate": 5,
                "sample_has_buffer": True,
                "sample_size_positive": True,
            },
        }
        rtsp_official.write_text(json.dumps(source_loopback_transcript), encoding="utf-8")
        rtsp_candidate.write_text(json.dumps(source_loopback_transcript), encoding="utf-8")
        rtsp_comparison.write_text("transcripts match\n", encoding="utf-8")
        source_rtsp_report = source_rtsp_dir / "parity_report.json"
        source_rtsp_report.write_text(
            json.dumps({
                "ok": True,
                "failed": [],
                "inputs": {
                    "artifact_policy": {
                        "copies_input_binaries": False,
                        "stores_hashes_and_probe_transcripts_only": True,
                    },
                    "self_compare_allowed": False,
                    "candidate": {"source": {"path": str(source), "sha256": sha256_file(source)}},
                    "official": {"source": {"path": str(official_source), "sha256": sha256_file(official_source)}},
                },
                "probes": {
                    "source_streaming": {
                        "official": {"ok": True, "path": rtsp_official.name},
                        "candidate": {"ok": True, "path": rtsp_candidate.name},
                    },
                },
                "comparisons": {"source_streaming": {"ok": True, "path": rtsp_comparison.name}},
            }),
            encoding="utf-8",
        )
        source_control_tls_dir = work / "source_control_tls_loopback"
        source_control_tls_dir.mkdir()
        tls_official = source_control_tls_dir / "official_source_control_tls.json"
        tls_candidate = source_control_tls_dir / "candidate_source_control_tls.json"
        tls_comparison = source_control_tls_dir / "source_control_tls_comparison.json"
        tls_official.write_text(json.dumps({"label": "official"}), encoding="utf-8")
        tls_candidate.write_text(json.dumps({"label": "candidate"}), encoding="utf-8")
        source_control_contract = {
            "accepted": True,
            "login_header": {"payload_size": 16},
            "credentials": {"user": "bblp", "password_redacted": "<redacted>", "password_length": 6},
            "control_payloads": ['{"mtype":12289,"sequence":1}\n'],
        }
        tls_comparison.write_text(
            json.dumps({
                "ok": True,
                "official_contract": source_control_contract,
                "candidate_contract": source_control_contract,
                "official_validation": {"ok": True, "checks": {"accepted": True}},
                "candidate_validation": {"ok": True, "checks": {"accepted": True}},
            }),
            encoding="utf-8",
        )
        source_control_tls_report = source_control_tls_dir / "parity_report.json"
        source_control_tls_report.write_text(
            json.dumps({
                "ok": True,
                "failed": [],
                "inputs": {
                    "candidate_source": {"path": str(source), "sha256": sha256_file(source)},
                    "official_source": {"path": str(official_source), "sha256": sha256_file(official_source)},
                    "stores_hashes_and_probe_transcripts_only": True,
                    "passwords_redacted": True,
                },
                "artifacts": {
                    "official": tls_official.name,
                    "candidate": tls_candidate.name,
                    "comparison": tls_comparison.name,
                },
            }),
            encoding="utf-8",
        )
        clean_parity_dir = work / "clean_room_parity"
        clean_aux_dir = work / "clean_room_auxiliary"
        clean_parity_dir.mkdir()
        clean_aux_dir.mkdir()
        clean_parity_report = clean_parity_dir / "parity_report.json"
        clean_parity_payload = json.loads(official_parity.read_text(encoding="utf-8"))
        clean_parity_payload["inputs"]["artifact_policy"] = {
            "copies_input_binaries": False,
            "stores_hashes_and_probe_transcripts_only": True,
        }
        clean_parity_report.write_text(json.dumps(clean_parity_payload), encoding="utf-8")
        (clean_aux_dir / "source_loopback_transcript.json").write_text('{"ok": true}\n', encoding="utf-8")
        secret_env_name = "BAMBU_NATIVE_READINESS_SECRET_FIXTURE"
        old_secret = os.environ.get(secret_env_name)
        os.environ[secret_env_name] = "native-readiness-secret-value"
        try:
            clean_gate = clean_room_gate(clean_parity_report, [clean_parity_dir, clean_aux_dir], [clean_aux_dir], (secret_env_name,))
            assert_true(clean_gate["ok"] is True, "clean-room gate scans auxiliary native artifact dirs", clean_gate)
            copied_binary = clean_aux_dir / "copied_binary.dylib"
            copied_binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"copied")
            dirty_clean_gate = clean_room_gate(clean_parity_report, [clean_parity_dir, clean_aux_dir], [clean_aux_dir], (secret_env_name,))
            assert_true(
                dirty_clean_gate["ok"] is False and str(clean_aux_dir) in dirty_clean_gate["failed"],
                "clean-room gate rejects binaries in auxiliary native artifact dirs",
                dirty_clean_gate,
            )
            copied_binary.unlink()
            leaked_secret = clean_aux_dir / "leaked_secret.json"
            leaked_secret.write_text('{"token":"native-readiness-secret-value"}\n', encoding="utf-8")
            secret_clean_gate = clean_room_gate(clean_parity_report, [clean_parity_dir, clean_aux_dir], [clean_aux_dir], (secret_env_name,))
            assert_true(
                secret_clean_gate["ok"] is False and str(clean_aux_dir) in secret_clean_gate["failed"],
                "clean-room gate rejects secret leaks in auxiliary native artifact dirs",
                secret_clean_gate,
            )
            leaked_secret.unlink()
        finally:
            if old_secret is None:
                os.environ.pop(secret_env_name, None)
            else:
                os.environ[secret_env_name] = old_secret
        native_self_report = native_plugin_gate(plugin_report)["native_plugin_report"]
        assert_true(source_rtsp_loopback_gate(source_rtsp_report, native_self_report)["ok"] is True, "source RTSP loopback gate self-test")
        assert_true(
            source_control_tls_loopback_gate(source_control_tls_report, native_self_report)["ok"] is True,
            "source-control TLS loopback gate self-test",
        )
        self_compare_source_rtsp_payload = json.loads(source_rtsp_report.read_text(encoding="utf-8"))
        self_compare_source_rtsp_payload["inputs"]["official"]["source"] = {"path": str(source), "sha256": sha256_file(source)}
        source_rtsp_report.write_text(json.dumps(self_compare_source_rtsp_payload), encoding="utf-8")
        self_compare_source_rtsp_gate = source_rtsp_loopback_gate(source_rtsp_report, native_self_report)
        assert_true(
            self_compare_source_rtsp_gate["ok"] is False
            and self_compare_source_rtsp_gate["checks"]["official_source_differs_from_candidate"] is False,
            "source RTSP loopback self-compare rejection",
            self_compare_source_rtsp_gate,
        )
        self_compare_source_rtsp_payload["inputs"]["official"]["source"] = {
            "path": str(official_source),
            "sha256": sha256_file(official_source),
        }
        source_rtsp_report.write_text(json.dumps(self_compare_source_rtsp_payload), encoding="utf-8")
        self_compare_source_control_payload = json.loads(source_control_tls_report.read_text(encoding="utf-8"))
        self_compare_source_control_payload["inputs"]["official_source"] = {"path": str(source), "sha256": sha256_file(source)}
        source_control_tls_report.write_text(json.dumps(self_compare_source_control_payload), encoding="utf-8")
        self_compare_source_control_gate = source_control_tls_loopback_gate(source_control_tls_report, native_self_report)
        assert_true(
            self_compare_source_control_gate["ok"] is False
            and self_compare_source_control_gate["checks"]["official_source_differs_from_candidate"] is False,
            "source-control TLS loopback self-compare rejection",
            self_compare_source_control_gate,
        )
        self_compare_source_control_payload["inputs"]["official_source"] = {
            "path": str(official_source),
            "sha256": sha256_file(official_source),
        }
        source_control_tls_report.write_text(json.dumps(self_compare_source_control_payload), encoding="utf-8")
        stale_source_report = dict(native_self_report)
        stale_source_report["inputs"] = dict(native_self_report["inputs"])
        stale_source_report["inputs"]["source"] = dict(native_self_report["inputs"]["source"])
        stale_source_report["inputs"]["source"]["sha256"] = "stale-source-sha"
        stale_source_gate = source_rtsp_loopback_gate(source_rtsp_report, stale_source_report)
        assert_true(
            stale_source_gate["ok"] is False
            and stale_source_gate["checks"]["candidate_source_hash_matches_native_report"] is False,
            "stale source RTSP loopback candidate rejection",
            stale_source_gate,
        )
        missing_tls_artifact = json.loads(source_control_tls_report.read_text(encoding="utf-8"))
        missing_tls_artifact["artifacts"]["comparison"] = "missing-comparison.json"
        source_control_tls_report.write_text(json.dumps(missing_tls_artifact), encoding="utf-8")
        missing_tls_gate = source_control_tls_loopback_gate(source_control_tls_report, native_self_report)
        assert_true(
            missing_tls_gate["ok"] is False
            and missing_tls_gate["checks"]["comparison_artifact_ok"] is False,
            "source-control TLS loopback missing comparison rejection",
            missing_tls_gate,
        )
        missing_tls_artifact["artifacts"]["comparison"] = tls_comparison.name
        source_control_tls_report.write_text(json.dumps(missing_tls_artifact), encoding="utf-8")
        stale_candidate_report = native_plugin_gate(plugin_report)["native_plugin_report"]
        stale_candidate_report["inputs"]["network"]["sha256"] = "stale-candidate-sha"
        stale_candidate_official_gate = official_parity_gate(official_parity, stale_candidate_report)
        assert_true(
            stale_candidate_official_gate["ok"] is False
            and stale_candidate_official_gate["checks"]["candidate_network_hash_matches_native_report"] is False,
            "stale candidate parity input rejection",
            stale_candidate_official_gate,
        )
        wrong_named_network = package_dir / "libnot_bambu_networking.dylib"
        wrong_named_network.write_bytes(network.read_bytes())
        wrong_named_official_payload = json.loads(official_parity.read_text(encoding="utf-8"))
        wrong_named_official_payload["inputs"]["candidate"]["network"]["path"] = str(wrong_named_network)
        wrong_named_official_payload["inputs"]["candidate"]["network"]["sha256"] = sha256_file(wrong_named_network)
        official_parity.write_text(json.dumps(wrong_named_official_payload), encoding="utf-8")
        wrong_named_official_gate = official_parity_gate(official_parity, native_plugin_gate(plugin_report)["native_plugin_report"])
        assert_true(
            wrong_named_official_gate["ok"] is False
            and wrong_named_official_gate["checks"]["candidate_network_is_dylib"] is False
            and wrong_named_official_gate["checks"]["candidate_network_hash_matches_native_report"] is True,
            "official parity rejects renamed native candidate network dylib even when hash matches",
            wrong_named_official_gate,
        )
        wrong_named_official_payload["inputs"]["candidate"]["network"]["path"] = str(network)
        wrong_named_official_payload["inputs"]["candidate"]["network"]["sha256"] = sha256_file(network)
        official_parity.write_text(json.dumps(wrong_named_official_payload), encoding="utf-8")
        wrong_named_network.unlink()
        stale_candidate_package_gate = native_packaging_gate(package_dir, stale_candidate_report)
        assert_true(
            stale_candidate_package_gate["ok"] is False
            and stale_candidate_package_gate["checks"]["network_hash_matches_native_report"] is False,
            "stale candidate package input rejection",
            stale_candidate_package_gate,
        )
        official_network.unlink()
        stale_official_gate = official_parity_gate(official_parity, native_plugin_gate(plugin_report)["native_plugin_report"])
        assert_true(
            stale_official_gate["ok"] is False
            and stale_official_gate["checks"]["official_network_exists"] is False
            and stale_official_gate["checks"]["official_network_hash_matches_report"] is False,
            "stale official parity input rejection",
            stale_official_gate,
        )
        assert_true(native_packaging_gate(package_dir, native_plugin_gate(plugin_report)["native_plugin_report"])["ok"] is True, "native packaging gate self-test")
        versioned_package_dir = work / "versioned/OrcaSlicer.app/Contents/MacOS"
        versioned_package_dir.mkdir(parents=True)
        versioned_network = versioned_package_dir / "libbambu_networking_02.05.02.58.dylib"
        versioned_source = versioned_package_dir / NATIVE_SOURCE_NAME
        versioned_network.write_bytes(network.read_bytes())
        versioned_source.write_bytes(source.read_bytes())
        versioned_report = json.loads(json.dumps(native_plugin_gate(plugin_report)["native_plugin_report"]))
        versioned_report["inputs"]["network"]["path"] = str(versioned_network)
        versioned_report["inputs"]["network"]["name"] = versioned_network.name
        versioned_report["inputs"]["network"]["sha256"] = sha256_file(versioned_network)
        versioned_package_gate = native_packaging_gate(versioned_package_dir, versioned_report)
        assert_true(versioned_package_gate["ok"] is True, "native packaging accepts versioned network dylib", versioned_package_gate)
        stale_versioned_report = json.loads(json.dumps(versioned_report))
        stale_versioned_report["inputs"]["network"]["sha256"] = "stale-versioned-candidate-sha"
        stale_versioned_package_gate = native_packaging_gate(versioned_package_dir, stale_versioned_report)
        assert_true(
            stale_versioned_package_gate["ok"] is False
            and stale_versioned_package_gate["checks"]["network_hash_matches_native_report"] is False,
            "native packaging rejects stale versioned network hash",
            stale_versioned_package_gate,
        )
        assert_true(native_gui_startup_gate(gui_log, gui_plugin_dir)["ok"] is True, "native GUI startup gate self-test")
        versioned_gui_plugin_dir = work / "gui_native_smoke_datadir_versioned/plugins"
        versioned_gui_plugin_dir.mkdir(parents=True)
        (versioned_gui_plugin_dir / versioned_network.name).write_bytes(versioned_network.read_bytes())
        (versioned_gui_plugin_dir / NATIVE_SOURCE_NAME).write_bytes(source.read_bytes())
        versioned_gui_log = work / "gui_native_smoke/versioned_native_startup_relevant_logs.txt"
        versioned_gui_log.write_text(
            gui_log.read_text(encoding="utf-8").replace("libbambu_networking.dylib", versioned_network.name),
            encoding="utf-8",
        )
        assert_true(native_gui_startup_gate(versioned_gui_log, versioned_gui_plugin_dir)["ok"] is True, "native GUI startup accepts versioned network dylib")
        (gui_plugin_dir / "pjarczak_bambu_linux_host").write_text("host", encoding="utf-8")
        rejected_gui_gate = native_gui_startup_gate(gui_log, gui_plugin_dir)
        assert_true(
            rejected_gui_gate["ok"] is False and rejected_gui_gate["checks"]["plugin_dir_has_no_bridge_or_linux_runtime_files"] is False,
            "native GUI startup plugin-dir bridge rejection",
            rejected_gui_gate,
        )
        (gui_plugin_dir / "pjarczak_bambu_linux_host").unlink()
        gui_log.write_text(gui_log.read_text(encoding="utf-8") + "\nbridge payload preflight", encoding="utf-8")
        rejected_gui_log_gate = native_gui_startup_gate(gui_log, gui_plugin_dir)
        assert_true(
            rejected_gui_log_gate["ok"] is False and rejected_gui_log_gate["checks"]["no_bridge_or_linux_runtime_log_markers"] is False,
            "native GUI startup log bridge rejection",
            rejected_gui_log_gate,
        )
        rejected_bridge_file = work / "libpjarczak_bambu_networking_bridge.dylib"
        rejected_bridge_file.write_bytes(b"\xcf\xfa\xed\xfe" + b"bridge")
        rejected_package_gate = native_packaging_gate(package_dir, native_plugin_gate(plugin_report)["native_plugin_report"])
        assert_true(
            rejected_package_gate["ok"] is False
            and rejected_package_gate["checks"]["package_root_has_no_generated_bridge_or_linux_runtime_files"] is False,
            "native package root bridge rejection",
            rejected_package_gate,
        )
        rejected_bridge_file.unlink()
        rejected_lima_file = work / "pjarczak_lima_instance.txt"
        rejected_lima_file.write_text("lima-instance", encoding="utf-8")
        rejected_lima_gate = native_packaging_gate(package_dir, native_plugin_gate(plugin_report)["native_plugin_report"])
        assert_true(
            rejected_lima_gate["ok"] is False
            and rejected_lima_gate["checks"]["package_root_has_no_generated_bridge_or_linux_runtime_files"] is False,
            "native package root Lima marker rejection",
            rejected_lima_gate,
        )
        rejected_unknown_so = work / "Contents/Resources/libunexpected_linux_payload.so.1"
        rejected_unknown_so.parent.mkdir(parents=True)
        rejected_unknown_so.write_text("linux so", encoding="utf-8")
        rejected_unknown_so_gate = native_packaging_gate(package_dir, native_plugin_gate(plugin_report)["native_plugin_report"])
        assert_true(
            rejected_unknown_so_gate["ok"] is False
            and rejected_unknown_so_gate["checks"]["package_root_has_no_generated_bridge_or_linux_runtime_files"] is False,
            "native package root arbitrary Linux .so rejection",
            rejected_unknown_so_gate,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate macOS native Bambu plugin readiness evidence")
    parser.add_argument("--native-plugin-report", type=pathlib.Path, default=None)
    parser.add_argument("--local-smoke-report", type=pathlib.Path, default=DEFAULT_LOCAL_SMOKE_REPORT)
    parser.add_argument("--official-parity-report", type=pathlib.Path, default=None)
    parser.add_argument("--real-printer-parity-report", type=pathlib.Path, default=None)
    parser.add_argument("--cloud-service-parity-report", type=pathlib.Path, default=None)
    parser.add_argument("--source-rtsp-loopback-report", type=pathlib.Path, default=DEFAULT_SOURCE_RTSP_LOOPBACK_REPORT)
    parser.add_argument("--source-control-tls-loopback-report", type=pathlib.Path, default=DEFAULT_SOURCE_CONTROL_TLS_LOOPBACK_REPORT)
    parser.add_argument("--native-package-macos-dir", type=pathlib.Path, default=DEFAULT_NATIVE_PACKAGE_MACOS_DIR)
    parser.add_argument("--native-package-root", type=pathlib.Path, default=DEFAULT_NATIVE_PACKAGE_ROOT)
    parser.add_argument("--native-gui-startup-log", type=pathlib.Path, default=DEFAULT_NATIVE_GUI_STARTUP_LOG)
    parser.add_argument("--native-gui-startup-plugin-dir", type=pathlib.Path, default=DEFAULT_NATIVE_GUI_STARTUP_PLUGIN_DIR)
    parser.add_argument("--bridge-config-source", type=pathlib.Path, default=DEFAULT_BRIDGE_CONFIG_SOURCE)
    parser.add_argument("--loader-source", type=pathlib.Path, default=DEFAULT_LOADER_SOURCE)
    parser.add_argument("--real-printer-dry-run-report", type=pathlib.Path, default=None)
    parser.add_argument("--authorized-cloud-dry-run-report", type=pathlib.Path, default=None)
    parser.add_argument("--printer-discovery-report", type=pathlib.Path, default=None)
    parser.add_argument("--source-control-parity-report", type=pathlib.Path, default=None)
    parser.add_argument("--real-printer-test-3mf", type=pathlib.Path, default=DEFAULT_REAL_PRINTER_TEST_3MF)
    parser.add_argument(
        "--defer-manual-printer-testing",
        action="store_true",
        help="Mark manual real-printer testing as deferred when dry-run evidence is actionable and every other completion gate is satisfied separately",
    )
    parser.add_argument("--cloud-service-scoped-out", action="store_true")
    parser.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print("macOS native readiness validation checks passed")
        return 0
    if args.native_plugin_report is None:
        parser.error("--native-plugin-report is required unless --self-test is used")
    if args.official_parity_report is None:
        parser.error("--official-parity-report is required unless --self-test is used")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "target": "macos_native",
        "ok": False,
        "blockers": [],
        "gates": {},
    }

    native_gate = native_plugin_gate(args.native_plugin_report)
    add_gate(report, "macos_native_plugin", native_gate)
    native_report = native_gate.get("native_plugin_report") if isinstance(native_gate.get("native_plugin_report"), dict) else None

    smoke_gate = local_smoke_gate(args.local_smoke_report)
    add_gate(report, "local_candidate_smoke", smoke_gate)
    local_smoke_report = smoke_gate.get("local_smoke_report") if isinstance(smoke_gate.get("local_smoke_report"), dict) else None

    official_gate = official_parity_gate(args.official_parity_report, native_report)
    add_gate(report, "official_parity", official_gate)
    official_report = official_gate.get("official_parity_report") if isinstance(official_gate.get("official_parity_report"), dict) else None

    add_gate(report, "source_rtsp_loopback_parity", source_rtsp_loopback_gate(args.source_rtsp_loopback_report, native_report))
    add_gate(report, "source_control_tls_loopback_parity", source_control_tls_loopback_gate(args.source_control_tls_loopback_report, native_report))

    real_printer_report = official_report
    real_printer_inputs_current = official_gate.get("ok") is True
    if args.real_printer_parity_report:
        real_printer_parity_gate = official_parity_gate(args.real_printer_parity_report, native_report)
        add_gate(report, "real_printer_official_parity", real_printer_parity_gate)
        real_printer_report = (
            real_printer_parity_gate.get("official_parity_report")
            if isinstance(real_printer_parity_gate.get("official_parity_report"), dict)
            else None
        )
        real_printer_inputs_current = real_printer_parity_gate.get("ok") is True

    cloud_service_report = official_report
    cloud_service_inputs_current = official_gate.get("ok") is True
    if args.cloud_service_parity_report:
        cloud_service_parity_gate = official_parity_gate(args.cloud_service_parity_report, native_report)
        add_gate(report, "cloud_service_official_parity", cloud_service_parity_gate)
        cloud_service_report = (
            cloud_service_parity_gate.get("official_parity_report")
            if isinstance(cloud_service_parity_gate.get("official_parity_report"), dict)
            else None
        )
        cloud_service_inputs_current = cloud_service_parity_gate.get("ok") is True

    clean_room_artifact_dirs = [
        args.official_parity_report.parent,
        args.source_rtsp_loopback_report.parent,
        args.source_control_tls_loopback_report.parent,
    ]
    if args.real_printer_parity_report:
        clean_room_artifact_dirs.append(args.real_printer_parity_report.parent)
    if args.cloud_service_parity_report:
        clean_room_artifact_dirs.append(args.cloud_service_parity_report.parent)
    if args.source_control_parity_report:
        clean_room_artifact_dirs.append(args.source_control_parity_report.parent)
    clean_room_artifact_dirs = list(dict.fromkeys(clean_room_artifact_dirs))

    add_gate(
        report,
        "clean_room_artifacts",
        clean_room_gate(
            args.official_parity_report,
            clean_room_artifact_dirs,
            [
                ROOT / "build/bambu_network_rust_plugin_release",
                *clean_room_artifact_dirs,
            ],
        ),
    )
    add_gate(
        report,
        "real_printer_parity",
        real_printer_gate(
            real_printer_report,
            args.real_printer_dry_run_report,
            args.printer_discovery_report,
            args.source_control_parity_report,
            args.real_printer_test_3mf,
            real_printer_inputs_current,
            local_smoke_report,
            args.defer_manual_printer_testing,
        ),
    )
    add_gate(
        report,
        "cloud_service_parity",
        cloud_service_gate(
            cloud_service_report,
            cloud_service_inputs_current,
            args.cloud_service_scoped_out,
            local_smoke_report,
            args.authorized_cloud_dry_run_report,
        ),
    )
    add_gate(report, "bridge_fallback_preserved", bridge_fallback_gate(args.bridge_config_source))
    add_gate(report, "native_loader_routing", native_loader_gate(args.loader_source))
    add_gate(report, "native_packaging", native_packaging_gate(args.native_package_macos_dir, native_report, args.native_package_root))
    add_gate(report, "native_gui_startup", native_gui_startup_gate(args.native_gui_startup_log, args.native_gui_startup_plugin_dir))

    report["completion_criteria"] = completion_criteria(report)
    incomplete = [name for name, ok in report["completion_criteria"].items() if not ok]
    if incomplete:
        report["blockers"].extend([f"completion_criteria:{name}" for name in incomplete if f"completion_criteria:{name}" not in report["blockers"]])
    report["ok"] = not report["blockers"]
    report["blocked_actions"] = blocked_actions(report)

    out = args.out_dir / "release_readiness_report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "blockers": report["blockers"], "out": str(out)}, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
