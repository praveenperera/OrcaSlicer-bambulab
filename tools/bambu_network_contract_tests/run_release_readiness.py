#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import platform
import subprocess
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "tools/bambu_network_contract_tests"
DEFAULT_PLUGIN_BUILD = ROOT / "build/bambu_network_rust_plugin_release"
DEFAULT_LINUX_PLUGIN_BUILD = ROOT / "build/bambu_network_rust_plugin_linux_x86_64"
DEFAULT_LINUX_HOST_BUILD = ROOT / "build/pjarczak_bambu_linux_host_linux_x86_64/tools/pjarczak_bambu_linux_host"
DEFAULT_LINUX_LIBSTDCXX_REPORT = (
    ROOT / "build/bambu_network_rust_plugin_linux_x86_64_libstdcxx/linux_libstdcxx_candidate_report.json"
)
DEFAULT_MACOS_RUNTIME_DIR = ROOT / "build/bambu_network_macos_bridge_runtime"
SOURCE_MACOS_RUNTIME_DIR = ROOT / "tools/pjarczak_bambu_linux_host/runtime/linux-x86_64"
BAMBULAB_HOST = "https://bambulab.com"
STUDIO_INFO_URL = "https://api.bambulab.com/v1/iot-service/api/slicer/resource"
MACOS_BRIDGE_DYLIB_FIXTURE_KIND = "copy-path-fixture"
REQUIRED_PRINT_JOB_MODES = ("upload-only", "local-print", "sdcard-print")
REQUIRED_MACOS_COPIED_FILES = (
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
    "libpjarczak_bambu_networking_bridge.dylib",
)
REQUIRED_LOCAL_SMOKE_CHECKS = (
    "preflight_python_sources_compile",
    "preflight_symbol_manifest_sources",
    "preflight_abi_mirror",
    "preflight_cpp_signature_mirror",
    "preflight_contract_surface_coverage",
    "preflight_clean_room_artifact_validation",
    "preflight_completion_audit_validation",
    "preflight_readiness_report_validation",
    "preflight_release_readiness_report_validation",
    "preflight_authorized_cloud_parity_dry_run",
    "preflight_source_streaming_parity_dry_run",
    "preflight_source_control_tunnel_parity_dry_run",
    "preflight_real_printer_parity_dry_run",
    "network_symbols",
    "source_symbols",
    "lifecycle_agent_created",
    "lifecycle_destroy_result",
    "callback_agent_created",
    "callback_no_missing_symbols",
    "callback_transcripts_match",
    "cloud_service_agent_created",
    "cloud_service_destroy_result",
    "cloud_service_network_disabled",
    "cloud_service_no_missing_symbols",
    "cloud_service_offline_ok",
    "cloud_service_login_no_missing_symbols",
    "cloud_service_login_agent_created",
    "cloud_service_login_offline_ok",
    "cloud_service_login_network_disabled",
    "cloud_service_login_change_user",
    "cloud_service_login_is_user_login",
    "cloud_service_login_semantic",
    "cloud_service_login_callback",
    "cloud_service_login_logout",
    "cloud_service_login_destroy_result",
    "cloud_service_fixture_ok",
    "cloud_service_fixture_connect_server",
    "cloud_service_fixture_semantic",
    "cloud_service_fixture_http",
    "cloud_service_fixture_body",
    "cloud_service_fixture_token",
    "cloud_service_fixture_profile",
    "cloud_service_fixture_callback_exports",
    "cloud_service_http_fixture_ok",
    "cloud_service_http_fixture_connect_server",
    "cloud_service_http_fixture_server_connected",
    "cloud_service_http_fixture_semantic",
    "cloud_service_http_fixture_http",
    "cloud_service_http_fixture_body",
    "cloud_service_http_fixture_token",
    "cloud_service_http_fixture_profile",
    "cloud_service_http_fixture_callback_exports",
    "cloud_service_backend_fixture_ok",
    "cloud_service_backend_fixture_connect_server",
    "cloud_service_backend_fixture_server_connected",
    "cloud_service_backend_fixture_semantic",
    "cloud_service_backend_fixture_http",
    "cloud_service_backend_fixture_body",
    "cloud_service_backend_fixture_token",
    "cloud_service_backend_fixture_profile",
    "cloud_service_backend_fixture_callback_exports",
    "unsupported_no_missing_symbols",
    "unsupported_destroy_result",
    "unsupported_bambulab_host",
    "unsupported_studio_info_url",
    "source_behavior_ok",
    "source_streaming_fixture_ok",
    "source_streaming_fixture_info",
    "source_streaming_fixture_sample",
    "source_local_tunnel_ok",
    "source_local_tunnel_opened",
    "source_local_tunnel_started",
    "source_local_tunnel_send",
    "source_local_tunnel_server_received",
    "source_local_tunnel_recv",
    "source_local_tunnel_recv_response",
    "source_local_tunnel_recv_type",
    "source_local_tunnel_sample",
    "source_local_tunnel_response",
    "print_job_ok",
    "event_bridge_payloads",
    "discovery_payload",
    "camera_url_payload",
    "ft_behavior_ok",
)
REQUIRED_FT_SYMBOLS = (
    "ft_abi_version",
    "ft_free",
    "ft_job_result_destroy",
    "ft_job_msg_destroy",
    "ft_tunnel_create",
    "ft_tunnel_retain",
    "ft_tunnel_release",
    "ft_tunnel_start_connect",
    "ft_tunnel_set_status_cb",
    "ft_tunnel_sync_connect",
    "ft_tunnel_shutdown",
    "ft_job_create",
    "ft_job_retain",
    "ft_job_release",
    "ft_job_set_result_cb",
    "ft_job_get_result",
    "ft_tunnel_start_job",
    "ft_job_cancel",
    "ft_job_set_msg_cb",
    "ft_job_try_get_msg",
    "ft_job_get_msg",
)
REQUIRED_AUTH_SYMBOLS = (
    "bambu_network_is_user_login",
    "bambu_network_get_user_id",
    "bambu_network_get_user_name",
    "bambu_network_get_user_avatar",
    "bambu_network_get_user_nickanme",
    "bambu_network_build_login_cmd",
    "bambu_network_build_logout_cmd",
    "bambu_network_build_login_info",
    "bambu_network_change_user",
)
PRINTER_DEFERRED_OFFICIAL_PARITY_FAILURES = frozenset({
    "full_ft_contract_evidence",
})
PRINTER_DEFERRED_FEATURE_FAILURES = frozenset({
    "camera_source_streaming",
    "non_ftps_tunnel_feature_parity",
})
CLOUD_DEFERRED_FEATURE_FAILURES = frozenset({
    "cloud_service_feature_parity",
})
FULL_COMPATIBILITY_GAPS = (
    {
        "name": "camera_source_streaming",
        "implemented": False,
        "reason": "libBambuSource has an opt-in synthetic MJPEG fixture for local plumbing tests, but does not yet produce real printer camera/control samples",
        "current_evidence": [
            "candidate-only source_behavior_probe verifies safe return codes for Bambu_StartStream, Bambu_GetStreamInfo, and Bambu_ReadSample",
            "candidate-only source_streaming_probe verifies an opt-in synthetic MJPEG stream can open, start, report stream info, and return a sample",
            "candidate-only camera_url_probe verifies Orca camera URL construction and callback delivery",
            "official source_behavior parity covers inert camera/local/error behavior only",
            "run_source_streaming_parity.py wraps live official-vs-candidate source streaming parity with URL-redacted dry-run validation",
        ],
        "blocking_probe": "camera_source_streaming_parity",
        "needed_evidence": "official-vs-candidate camera/source streaming parity transcript with successful Bambu_GetStreamInfo and Bambu_ReadSample behavior",
    },
    {
        "name": "cloud_service_feature_parity",
        "implemented": False,
        "reason": "cloud/service exports fail inertly by default and can exercise configurable HTTP plumbing, but authorized official-vs-candidate Bambu service parity is not yet recorded",
        "current_evidence": [
            "unsupported_probe verifies every exported cloud/service call fails safely with inert inputs",
            "official unsupported parity compares those inert failure contracts without using credentials or impersonating service clients",
            "candidate-only cloud_service_probe verifies an opt-in synthetic cloud/service fixture can exercise login, server connection, JSON/http-code outputs, token/profile plumbing, and callback-style MakerWorld/HMS exports",
            "candidate-only cloud_service_probe verifies a configurable BAMBU_NETWORK_CLOUD_BASE_URL HTTP fixture for request/response plumbing, Authorization header state, server-connected callbacks, service JSON/http-code outputs, token/profile calls, and callback-style MakerWorld/HMS exports",
            "candidate-only cloud_service_probe verifies login-payload backend_url fallback uses the same HTTP adapter path without relying on the test override env var",
        ],
        "blocking_probe": "authorized_cloud_service_parity",
        "needed_evidence": "authorized official-vs-candidate cloud/login/service parity transcript or a scoped release decision that these APIs are intentionally out of target",
    },
    {
        "name": "non_ftps_tunnel_feature_parity",
        "implemented": False,
        "reason": "synthetic ft_* lifecycle is implemented, but real tunnel behavior beyond the local FTPS upload path still needs printer-backed evidence",
        "current_evidence": [
            "ft_behavior_probe verifies synthetic local tunnel/job lifecycle, callbacks, ownership, media-ability result, and missing-file upload failure",
            "ft_job_invalid official parity verifies the official-safe ft_job_create invalid-input contract",
            "Linux bridge runtime verifies ft_* capability exposure and synthetic FT smoke through both ABI host variants",
            "source_local_tunnel_probe verifies libBambuSource loopback control-tunnel open/start/send/recv/read behavior through the same Bambu_* API shape Orca uses for port-6000/eMMC browsing",
            "source_control_tls_loopback_parity verifies official-vs-candidate local-control TLS login and message-frame wire contracts without storing credentials",
            "run_source_control_tunnel_parity.py wraps live official-vs-candidate source/control tunnel parity with URL/message-redacted dry-run validation",
        ],
        "blocking_probe": "real_printer_ft_tunnel_parity",
        "needed_evidence": "real-printer FT/tunnel parity transcript covering the tunnel paths Orca uses for the target release",
    },
)
IGNORED_TRANSCRIPT_KEYS = {
    "diagnostics",
    "network_plugin",
    "plugin",
    "source_plugin",
    "log_dir",
}


def run(cmd: list[str], output_path: pathlib.Path) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    output_path.write_text(completed.stdout, encoding="utf-8")
    if completed.stderr:
        output_path.with_suffix(output_path.suffix + ".stderr").write_text(completed.stderr, encoding="utf-8")
    return {
        "command": cmd,
        "exit_code": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout": str(output_path),
        "stderr": str(output_path.with_suffix(output_path.suffix + ".stderr")) if completed.stderr else None,
    }


def load_json_file(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def dylib_suffix() -> str:
    if platform.system() == "Darwin":
        return ".dylib"
    if platform.system() == "Windows":
        return ".dll"
    return ".so"


def existing_path(path: pathlib.Path) -> str | None:
    return str(path) if path.exists() else None


def add_gate(report: dict[str, Any], name: str, status: dict[str, Any]) -> None:
    report["gates"][name] = status
    if status.get("required") and not status.get("ok"):
        report["blockers"].append(name)


def merge_supplemental_feature_evidence(
    base: dict[str, Any] | None,
    supplemental: dict[str, Any] | None,
    label: str,
) -> dict[str, Any] | None:
    if base is None:
        return supplemental
    if supplemental is None:
        return base

    merged = dict(base)
    reports = dict(merged.get("supplemental_feature_reports", {}))
    reports[label] = supplemental
    merged["supplemental_feature_reports"] = reports

    for key in (
        "source_streaming_parity_ok",
        "source_control_tunnel_parity_ok",
        "source_control_tls_loopback_parity_ok",
        "cloud_service_parity_ok",
    ):
        merged[key] = bool(base.get(key) or supplemental.get(key))
    for key in (
        "source_streaming_checks",
        "source_control_tls_loopback_checks",
        "cloud_service_checks",
    ):
        if supplemental.get(key):
            merged[key] = supplemental[key]
    return merged


def skipped(required: bool, reason: str) -> dict[str, Any]:
    return {"ok": False, "required": required, "skipped": True, "reason": reason}


def validate_full_compatibility_feature_parity(official_parity_report: dict[str, Any] | None = None) -> dict[str, Any]:
    source_streaming_ok = bool(official_parity_report and official_parity_report.get("source_streaming_parity_ok"))
    source_control_tunnel_ok = bool(official_parity_report and official_parity_report.get("source_control_tunnel_parity_ok"))
    source_control_tls_loopback_ok = bool(
        official_parity_report and official_parity_report.get("source_control_tls_loopback_parity_ok")
    )
    cloud_service_ok = bool(official_parity_report and official_parity_report.get("cloud_service_parity_ok"))
    gaps: list[dict[str, Any]] = []
    for gap in FULL_COMPATIBILITY_GAPS:
        enriched = dict(gap)
        if gap.get("name") == "camera_source_streaming" and source_streaming_ok:
            enriched["implemented"] = True
            enriched["reason"] = "official-vs-candidate libBambuSource streaming parity passed"
            enriched["current_evidence"] = list(gap["current_evidence"]) + [
                "source_streaming parity transcript opened a live source stream, captured stream metadata, and read a sample",
            ]
        if gap.get("name") == "cloud_service_feature_parity" and cloud_service_ok:
            enriched["implemented"] = True
            enriched["reason"] = "authorized official-vs-candidate cloud/service parity passed"
            enriched["current_evidence"] = list(gap["current_evidence"]) + [
                "cloud_service parity transcript proved login state, cloud connection, and non-inert service responses without storing secrets",
            ]
        if gap.get("name") == "non_ftps_tunnel_feature_parity" and source_control_tunnel_ok:
            enriched["implemented"] = True
            enriched["reason"] = "official-vs-candidate libBambuSource control-tunnel parity passed"
            enriched["current_evidence"] = list(gap["current_evidence"]) + [
                "source control-tunnel parity transcript opened a control stream, sent a message, read a control response, and read a sample response",
            ]
        elif gap.get("name") == "non_ftps_tunnel_feature_parity" and source_control_tls_loopback_ok:
            enriched["reason"] = "local-control TLS login and message framing match official, but printer response parity still needs manual validation"
            enriched["current_evidence"] = list(gap["current_evidence"]) + [
                "source control TLS loopback parity matched official login framing, padded credentials, and control message wire frames without storing credentials",
            ]
        gaps.append(enriched)

    checks = {gap["name"]: gap["implemented"] is True for gap in gaps}
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "ok": not failed,
        "required": True,
        "checks": checks,
        "failed": failed,
        "gaps": gaps,
    }


def gate_failure_list(gate: dict[str, Any]) -> list[str]:
    direct_failed = gate.get("failed", [])
    if isinstance(direct_failed, list) and direct_failed:
        return [item for item in direct_failed if isinstance(item, str)]

    validation = gate.get("parity_report_validation", {})
    if isinstance(validation, dict):
        validation_failed = validation.get("failed", [])
        if isinstance(validation_failed, list) and validation_failed:
            return [item for item in validation_failed if isinstance(item, str)]

    if isinstance(direct_failed, list):
        return [item for item in direct_failed if isinstance(item, str)]

    return []


def classify_deferred_blockers(
    report: dict[str, Any],
    *,
    defer_manual_printer_parity: bool,
    defer_authorized_cloud_parity: bool,
) -> dict[str, Any]:
    gates = report.get("gates", {})
    blockers = report.get("blockers", [])
    blockers = blockers if isinstance(blockers, list) else []
    deferred: dict[str, Any] = {}
    partially_deferred: dict[str, Any] = {}
    non_deferred: list[str] = []

    for blocker in blockers:
        if not isinstance(blocker, str):
            continue
        gate = gates.get(blocker, {}) if isinstance(gates, dict) else {}
        gate = gate if isinstance(gate, dict) else {}

        if blocker == "real_printer_parity_inputs" and defer_manual_printer_parity:
            deferred[blocker] = {
                "reason": "manual real-printer parity inputs are intentionally deferred",
                "failed": gate_failure_list(gate),
            }
            continue

        if blocker == "official_parity" and defer_manual_printer_parity:
            failed = set(gate_failure_list(gate))
            if failed and failed <= PRINTER_DEFERRED_OFFICIAL_PARITY_FAILURES:
                deferred[blocker] = {
                    "reason": "official parity is blocked only by printer-backed FT evidence",
                    "failed": sorted(failed),
                }
                continue

        if blocker == "full_compatibility_feature_parity":
            failed = set(gate_failure_list(gate))
            allowed = set()
            if defer_manual_printer_parity:
                allowed.update(PRINTER_DEFERRED_FEATURE_FAILURES)
            if defer_authorized_cloud_parity:
                allowed.update(CLOUD_DEFERRED_FEATURE_FAILURES)
            deferred_failures = sorted(failed & allowed)
            remaining_failures = sorted(failed - allowed)
            if failed and not remaining_failures:
                deferred[blocker] = {
                    "reason": "all remaining feature gaps require explicitly deferred external validation",
                    "failed": sorted(failed),
                }
                continue
            if deferred_failures:
                partially_deferred[blocker] = {
                    "deferred": deferred_failures,
                    "remaining": remaining_failures,
                }

        non_deferred.append(blocker)

    return {
        "manual_printer_parity_deferred": defer_manual_printer_parity,
        "authorized_cloud_parity_deferred": defer_authorized_cloud_parity,
        "deferred_blockers": deferred,
        "partially_deferred_blockers": partially_deferred,
        "non_deferred_blockers": non_deferred,
        "non_deferred_ok": not non_deferred,
    }


def clean_room_artifact_policy_command(
    parity_report: pathlib.Path,
    artifact_dir: pathlib.Path,
    scan_dirs: list[pathlib.Path],
    secret_env_names: list[str],
    secret_files: list[pathlib.Path],
) -> list[str]:
    command = [
        sys.executable,
        str(CONTRACT_DIR / "verify_clean_room_artifacts.py"),
        "--parity-report",
        str(parity_report),
        "--artifact-dir",
        str(artifact_dir),
    ]
    for directory in scan_dirs:
        if directory.is_dir():
            command.extend(["--forbid-official-binary-copies-in", str(directory)])
    for name in secret_env_names:
        if name:
            command.extend(["--forbid-secret-env", name])
    for path in secret_files:
        if path.is_file():
            command.extend(["--forbid-secret-file", str(path)])
    return command


def sha256(path: pathlib.Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_local_smoke_summary(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "path": str(path), "reason": "local candidate smoke summary does not exist"}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return {"ok": False, "path": str(path), "reason": f"local candidate smoke summary is invalid JSON: {error}"}

    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        return {"ok": False, "path": str(path), "reason": "local candidate smoke summary has no checks object"}

    validation_checks: dict[str, bool] = {
        "summary_ok": payload.get("ok") is True,
        "no_failed_entries": payload.get("failed") == [],
    }
    for name in REQUIRED_LOCAL_SMOKE_CHECKS:
        validation_checks[f"check_{name}"] = checks.get(name) is True

    failed = [name for name, ok in validation_checks.items() if not ok]
    return {
        "ok": not failed,
        "path": str(path),
        "checks": validation_checks,
        "failed": failed,
    }


def probe_ok(report: dict[str, Any], group: str, name: str) -> bool:
    section = report.get(group, {})
    if not isinstance(section, dict):
        return False
    item = section.get(name, {})
    if not isinstance(item, dict):
        return False
    if group == "probes":
        official = item.get("official", {})
        candidate = item.get("candidate", {})
        return isinstance(official, dict) and isinstance(candidate, dict) and official.get("ok") is True and candidate.get("ok") is True
    return item.get("ok") is True


def candidate_only_probe_ok(report: dict[str, Any], name: str) -> bool:
    section = report.get("candidate_only_probes", {})
    if not isinstance(section, dict):
        return False
    item = section.get(name, {})
    return isinstance(item, dict) and item.get("ok") is True


def comparison_artifact_ok(report_path: pathlib.Path, report: dict[str, Any], name: str) -> bool:
    comparisons = report.get("comparisons", {})
    if not isinstance(comparisons, dict):
        return False
    comparison = comparisons.get(name, {})
    if not isinstance(comparison, dict):
        return False
    path = artifact_path(report_path, comparison.get("path"))
    if path is None:
        return False
    try:
        return "transcripts match" in path.read_text(encoding="utf-8")
    except OSError:
        return False


def is_under_directory(path: pathlib.Path, directory: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def artifact_path(report_path: pathlib.Path, value: Any) -> pathlib.Path | None:
    path = transcript_path(report_path, value)
    if path is None:
        return None
    artifact_dir = report_path.parent
    return path if is_under_directory(path, artifact_dir) else None


def transcript_path(report_path: pathlib.Path, value: Any) -> pathlib.Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = pathlib.Path(value)
    candidates = [path] if path.is_absolute() else [report_path.parent / path, ROOT / path, path]
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def load_probe_transcript(report_path: pathlib.Path, report: dict[str, Any], name: str, side: str) -> dict[str, Any] | None:
    probes = report.get("probes", {})
    if not isinstance(probes, dict):
        return None
    probe = probes.get(name, {})
    if not isinstance(probe, dict):
        return None
    side_result = probe.get(side, {})
    if not isinstance(side_result, dict):
        return None
    path = artifact_path(report_path, side_result.get("path"))
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def comparable_transcript(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in sorted(payload.items()) if key not in IGNORED_TRANSCRIPT_KEYS}


def probe_artifacts_match(report_path: pathlib.Path, report: dict[str, Any], name: str) -> bool:
    official = load_probe_transcript(report_path, report, name, "official")
    candidate = load_probe_transcript(report_path, report, name, "candidate")
    if official is None or candidate is None:
        return False
    return comparable_transcript(official) == comparable_transcript(candidate)


def probe_artifact_ok(report_path: pathlib.Path, report: dict[str, Any], name: str, side: str) -> bool:
    return load_probe_transcript(report_path, report, name, side) is not None


def candidate_only_probe_artifact_ok(report_path: pathlib.Path, report: dict[str, Any], name: str) -> bool:
    section = report.get("candidate_only_probes", {})
    if not isinstance(section, dict):
        return False
    item = section.get(name, {})
    if not isinstance(item, dict):
        return False
    path = artifact_path(report_path, item.get("path"))
    if path is None:
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict)


def result_value(transcript: dict[str, Any], key: str) -> Any:
    results = transcript.get("results", {})
    return results.get(key) if isinstance(results, dict) else None


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


def successful_source_streaming_transcript(transcript: dict[str, Any] | None, expected_mode: str) -> bool:
    if transcript is None:
        return False
    semantic = transcript.get("semantic", {})
    contract = transcript.get("stream_contract", {})
    stream_format_type = contract.get("stream_format_type") if isinstance(contract, dict) else None
    max_frame_size_ok = contract.get("stream_max_frame_size_positive") is True or stream_format_type == 1
    return all([
        transcript.get("ok") is True,
        transcript.get("mode") == expected_mode,
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


def successful_cloud_service_transcript(transcript: dict[str, Any] | None) -> bool:
    if transcript is None:
        return False
    semantic = transcript.get("semantic", {})
    return all([
        transcript.get("ok") is True,
        transcript.get("expect_success") is True,
        transcript.get("allow_network") is True,
        transcript.get("agent_created") is True,
        transcript.get("missing_symbols") == [],
        isinstance(semantic, dict),
        semantic.get("login_ok") is True,
        semantic.get("network_ok") is True,
        semantic.get("service_ok") is True,
        isinstance(semantic.get("non_unsupported_service_results"), int),
        semantic.get("non_unsupported_service_results") > 0,
    ])


def validate_official_parity_report(
    path: pathlib.Path,
    candidate_network_hashes: set[str],
    candidate_source_hashes: set[str],
) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "path": str(path), "reason": "official parity report does not exist"}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return {"ok": False, "path": str(path), "reason": f"official parity report is invalid JSON: {error}"}

    inputs = payload.get("inputs", {})
    artifact_policy = inputs.get("artifact_policy", {}) if isinstance(inputs, dict) else {}
    official = inputs.get("official", {}) if isinstance(inputs, dict) else {}
    official_network = official.get("network", {}) if isinstance(official, dict) else {}
    official_source = official.get("source", {}) if isinstance(official, dict) else {}
    official_network_sha = official_network.get("sha256") if isinstance(official_network, dict) else None
    official_source_sha = official_source.get("sha256") if isinstance(official_source, dict) else None
    candidate = inputs.get("candidate", {}) if isinstance(inputs, dict) else {}
    candidate_network = candidate.get("network", {}) if isinstance(candidate, dict) else {}
    candidate_source = candidate.get("source", {}) if isinstance(candidate, dict) else {}
    candidate_network_sha = candidate_network.get("sha256") if isinstance(candidate_network, dict) else None
    candidate_source_sha = candidate_source.get("sha256") if isinstance(candidate_source, dict) else None

    required_contract_probes = [
        "network_symbols",
        "source_symbols",
        "lifecycle",
        "callback",
        "unsupported",
        "discovery",
        "source_behavior",
    ]
    required_candidate_only_probes = [
        "candidate_source_behavior",
        "candidate_event_bridge",
        "candidate_camera_url",
    ]
    checks: dict[str, bool] = {
        "report_ok": payload.get("ok") is True,
        "no_failed_entries": payload.get("failed") == [],
        "does_not_copy_binaries": artifact_policy.get("copies_input_binaries") is False,
        "stores_hashes_and_transcripts": artifact_policy.get("stores_hashes_and_probe_transcripts_only") is True,
        "not_self_compare": inputs.get("self_compare_allowed") is False,
        "official_network_differs_from_candidate": bool(official_network_sha and candidate_network_sha and official_network_sha != candidate_network_sha),
        "official_source_differs_from_candidate": bool(official_source_sha and candidate_source_sha and official_source_sha != candidate_source_sha),
        "candidate_network_hash_matches_current_build": bool(candidate_network_sha and candidate_network_sha in candidate_network_hashes),
        "candidate_source_hash_matches_current_build": bool(candidate_source_sha and candidate_source_sha in candidate_source_hashes),
    }
    for name in required_contract_probes:
        checks[f"probe_{name}"] = probe_ok(payload, "probes", name)
        checks[f"probe_{name}_official_artifact"] = probe_artifact_ok(path, payload, name, "official")
        checks[f"probe_{name}_candidate_artifact"] = probe_artifact_ok(path, payload, name, "candidate")
        checks[f"probe_{name}_artifacts_match"] = probe_artifacts_match(path, payload, name)
        checks[f"compare_{name}"] = probe_ok(payload, "comparisons", name)
        checks[f"compare_{name}_artifact"] = comparison_artifact_ok(path, payload, name)
    for name in required_candidate_only_probes:
        checks[f"candidate_only_{name}"] = candidate_only_probe_ok(payload, name)
        checks[f"candidate_only_{name}_artifact"] = candidate_only_probe_artifact_ok(path, payload, name)

    requested_modes = inputs.get("print_job_modes") if isinstance(inputs, dict) else None
    requested_modes = requested_modes if isinstance(requested_modes, list) else []
    has_required_print_modes = all(mode in requested_modes for mode in REQUIRED_PRINT_JOB_MODES)
    printer_workflow_official = load_probe_transcript(path, payload, "printer_workflow", "official")
    printer_workflow_candidate = load_probe_transcript(path, payload, "printer_workflow", "candidate")
    print_job_transcripts = {
        "upload_only": (
            load_probe_transcript(path, payload, "print_job_upload_only", "official"),
            load_probe_transcript(path, payload, "print_job_upload_only", "candidate"),
        ),
        "local_print": (
            load_probe_transcript(path, payload, "print_job_local_print", "official"),
            load_probe_transcript(path, payload, "print_job_local_print", "candidate"),
        ),
        "sdcard_print": (
            load_probe_transcript(path, payload, "print_job_sdcard_print", "official"),
            load_probe_transcript(path, payload, "print_job_sdcard_print", "candidate"),
        ),
    }
    real_printer_checks = {
        "printer_workflow": probe_ok(payload, "probes", "printer_workflow") and probe_ok(payload, "comparisons", "printer_workflow"),
        "print_job_upload_only": probe_ok(payload, "probes", "print_job_upload_only") and probe_ok(payload, "comparisons", "print_job_upload_only"),
        "print_job_local_print": probe_ok(payload, "probes", "print_job_local_print") and probe_ok(payload, "comparisons", "print_job_local_print"),
        "print_job_sdcard_print": probe_ok(payload, "probes", "print_job_sdcard_print") and probe_ok(payload, "comparisons", "print_job_sdcard_print"),
        "required_print_modes_recorded": has_required_print_modes,
        "printer_workflow_official_success": successful_printer_workflow_transcript(printer_workflow_official),
        "printer_workflow_candidate_success": successful_printer_workflow_transcript(printer_workflow_candidate),
    }
    for name, (official_transcript, candidate_transcript) in print_job_transcripts.items():
        expected_mode = name.replace("_", "-")
        real_printer_checks[f"print_job_{name}_official_success"] = successful_print_job_transcript(official_transcript, expected_mode)
        real_printer_checks[f"print_job_{name}_candidate_success"] = successful_print_job_transcript(candidate_transcript, expected_mode)

    synthetic_ft_behavior_ok = all([
        probe_ok(payload, "probes", "ft_behavior"),
        probe_artifact_ok(path, payload, "ft_behavior", "official"),
        probe_artifact_ok(path, payload, "ft_behavior", "candidate"),
        probe_artifacts_match(path, payload, "ft_behavior"),
        probe_ok(payload, "comparisons", "ft_behavior"),
        comparison_artifact_ok(path, payload, "ft_behavior"),
    ])
    ft_job_invalid_ok = all([
        probe_ok(payload, "probes", "ft_job_invalid"),
        probe_artifact_ok(path, payload, "ft_job_invalid", "official"),
        probe_artifact_ok(path, payload, "ft_job_invalid", "candidate"),
        probe_artifacts_match(path, payload, "ft_job_invalid"),
        probe_ok(payload, "comparisons", "ft_job_invalid"),
        comparison_artifact_ok(path, payload, "ft_job_invalid"),
    ])
    real_printer_workflows_ok = all(real_printer_checks.values())
    checks["full_ft_contract_evidence"] = synthetic_ft_behavior_ok or (ft_job_invalid_ok and real_printer_workflows_ok)

    has_source_streaming_probe = "source_streaming" in payload.get("probes", {}) or "source_streaming" in payload.get("comparisons", {})
    source_streaming_parity_ok = False
    source_control_tunnel_parity_ok = False
    source_streaming_checks: dict[str, bool] = {}
    if has_source_streaming_probe:
        source_streaming_official = load_probe_transcript(path, payload, "source_streaming", "official")
        source_streaming_candidate = load_probe_transcript(path, payload, "source_streaming", "candidate")
        source_streaming_mode = source_streaming_official.get("mode") if isinstance(source_streaming_official, dict) else None
        source_streaming_modes_match = (
            isinstance(source_streaming_official, dict)
            and isinstance(source_streaming_candidate, dict)
            and source_streaming_mode == source_streaming_candidate.get("mode")
        )
        source_streaming_checks = {
            "source_streaming_probe": probe_ok(payload, "probes", "source_streaming"),
            "source_streaming_compare": probe_ok(payload, "comparisons", "source_streaming"),
            "source_streaming_official_artifact": probe_artifact_ok(path, payload, "source_streaming", "official"),
            "source_streaming_candidate_artifact": probe_artifact_ok(path, payload, "source_streaming", "candidate"),
            "source_streaming_artifacts_match": probe_artifacts_match(path, payload, "source_streaming"),
            "source_streaming_compare_artifact": comparison_artifact_ok(path, payload, "source_streaming"),
            "source_streaming_modes_match": source_streaming_modes_match,
            "source_streaming_official_success": successful_source_streaming_transcript(source_streaming_official, "video"),
            "source_streaming_candidate_success": successful_source_streaming_transcript(source_streaming_candidate, "video"),
            "source_control_tunnel_official_success": successful_source_control_tunnel_transcript(source_streaming_official),
            "source_control_tunnel_candidate_success": successful_source_control_tunnel_transcript(source_streaming_candidate),
        }
        source_streaming_artifact_ok = all(
            source_streaming_checks[name]
            for name in (
                "source_streaming_probe",
                "source_streaming_compare",
                "source_streaming_official_artifact",
                "source_streaming_candidate_artifact",
                "source_streaming_artifacts_match",
                "source_streaming_compare_artifact",
                "source_streaming_modes_match",
            )
        )
        source_streaming_success_ok = all(
            source_streaming_checks[name]
            for name in ("source_streaming_official_success", "source_streaming_candidate_success")
        )
        source_control_tunnel_success_ok = all(
            source_streaming_checks[name]
            for name in ("source_control_tunnel_official_success", "source_control_tunnel_candidate_success")
        )
        for name in (
            "source_streaming_probe",
            "source_streaming_compare",
            "source_streaming_official_artifact",
            "source_streaming_candidate_artifact",
            "source_streaming_artifacts_match",
            "source_streaming_compare_artifact",
            "source_streaming_modes_match",
        ):
            checks[name] = source_streaming_checks[name]
        if source_streaming_mode == "control":
            checks["source_control_tunnel_official_success"] = source_streaming_checks["source_control_tunnel_official_success"]
            checks["source_control_tunnel_candidate_success"] = source_streaming_checks["source_control_tunnel_candidate_success"]
        else:
            checks["source_streaming_official_success"] = source_streaming_checks["source_streaming_official_success"]
            checks["source_streaming_candidate_success"] = source_streaming_checks["source_streaming_candidate_success"]
        source_streaming_parity_ok = source_streaming_artifact_ok and source_streaming_success_ok
        source_control_tunnel_parity_ok = source_streaming_artifact_ok and source_control_tunnel_success_ok

    has_cloud_service_probe = "cloud_service" in payload.get("probes", {}) or "cloud_service" in payload.get("comparisons", {})
    cloud_service_parity_ok = False
    cloud_service_checks: dict[str, bool] = {}
    if has_cloud_service_probe:
        cloud_service_official = load_probe_transcript(path, payload, "cloud_service", "official")
        cloud_service_candidate = load_probe_transcript(path, payload, "cloud_service", "candidate")
        cloud_service_feature_requested = bool(
            (cloud_service_official and cloud_service_official.get("expect_success") is True)
            or (cloud_service_candidate and cloud_service_candidate.get("expect_success") is True)
        )
        cloud_service_artifact_checks = {
            "cloud_service_probe": probe_ok(payload, "probes", "cloud_service"),
            "cloud_service_compare": probe_ok(payload, "comparisons", "cloud_service"),
            "cloud_service_official_artifact": probe_artifact_ok(path, payload, "cloud_service", "official"),
            "cloud_service_candidate_artifact": probe_artifact_ok(path, payload, "cloud_service", "candidate"),
            "cloud_service_artifacts_match": probe_artifacts_match(path, payload, "cloud_service"),
            "cloud_service_compare_artifact": comparison_artifact_ok(path, payload, "cloud_service"),
        }
        cloud_service_success_checks = {
            "cloud_service_official_success": successful_cloud_service_transcript(cloud_service_official),
            "cloud_service_candidate_success": successful_cloud_service_transcript(cloud_service_candidate),
        }
        cloud_service_checks = {
            **cloud_service_artifact_checks,
            "cloud_service_feature_requested": cloud_service_feature_requested,
            **cloud_service_success_checks,
        }
        checks.update(cloud_service_artifact_checks)
        if cloud_service_feature_requested:
            checks.update(cloud_service_success_checks)
        cloud_service_parity_ok = cloud_service_feature_requested and all(cloud_service_success_checks.values()) and all(cloud_service_artifact_checks.values())

    failed = [name for name, ok in checks.items() if not ok]
    return {
        "ok": not failed,
        "path": str(path),
        "checks": checks,
        "failed": failed,
        "real_printer_workflows_ok": real_printer_workflows_ok,
        "real_printer_checks": real_printer_checks,
        "source_streaming_parity_ok": source_streaming_parity_ok,
        "source_control_tunnel_parity_ok": source_control_tunnel_parity_ok,
        "source_streaming_checks": source_streaming_checks,
        "cloud_service_parity_ok": cloud_service_parity_ok,
        "cloud_service_checks": cloud_service_checks,
        "ft_contract_checks": {
            "synthetic_ft_behavior": synthetic_ft_behavior_ok,
            "ft_job_invalid": ft_job_invalid_ok,
            "real_printer_workflows_ok": real_printer_workflows_ok,
            "full_ft_contract_evidence": checks["full_ft_contract_evidence"],
        },
    }


def validate_source_streaming_loopback_report(
    path: pathlib.Path,
    candidate_source_hashes: set[str],
) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "path": str(path), "reason": "source streaming loopback report does not exist"}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return {"ok": False, "path": str(path), "reason": f"source streaming loopback report is invalid JSON: {error}"}

    inputs = payload.get("inputs", {})
    artifact_policy = inputs.get("artifact_policy", {}) if isinstance(inputs, dict) else {}
    official = inputs.get("official", {}) if isinstance(inputs, dict) else {}
    official_source = official.get("source", {}) if isinstance(official, dict) else {}
    official_source_sha = official_source.get("sha256") if isinstance(official_source, dict) else None
    candidate = inputs.get("candidate", {}) if isinstance(inputs, dict) else {}
    candidate_source = candidate.get("source", {}) if isinstance(candidate, dict) else {}
    candidate_source_sha = candidate_source.get("sha256") if isinstance(candidate_source, dict) else None

    source_streaming_official = load_probe_transcript(path, payload, "source_streaming", "official")
    source_streaming_candidate = load_probe_transcript(path, payload, "source_streaming", "candidate")
    source_streaming_mode = source_streaming_official.get("mode") if isinstance(source_streaming_official, dict) else None
    source_streaming_modes_match = (
        isinstance(source_streaming_official, dict)
        and isinstance(source_streaming_candidate, dict)
        and source_streaming_mode == source_streaming_candidate.get("mode")
    )
    source_streaming_checks = {
        "report_ok": payload.get("ok") is True,
        "no_failed_entries": payload.get("failed") == [],
        "does_not_copy_binaries": artifact_policy.get("copies_input_binaries") is False,
        "stores_hashes_and_transcripts": artifact_policy.get("stores_hashes_and_probe_transcripts_only") is True,
        "not_self_compare": inputs.get("self_compare_allowed") is False,
        "official_source_differs_from_candidate": bool(official_source_sha and candidate_source_sha and official_source_sha != candidate_source_sha),
        "candidate_source_hash_matches_current_build": bool(candidate_source_sha and candidate_source_sha in candidate_source_hashes),
        "source_streaming_probe": probe_ok(payload, "probes", "source_streaming"),
        "source_streaming_compare": probe_ok(payload, "comparisons", "source_streaming"),
        "source_streaming_official_artifact": probe_artifact_ok(path, payload, "source_streaming", "official"),
        "source_streaming_candidate_artifact": probe_artifact_ok(path, payload, "source_streaming", "candidate"),
        "source_streaming_artifacts_match": probe_artifacts_match(path, payload, "source_streaming"),
        "source_streaming_compare_artifact": comparison_artifact_ok(path, payload, "source_streaming"),
        "source_streaming_modes_match": source_streaming_modes_match,
        "source_streaming_official_success": successful_source_streaming_transcript(source_streaming_official, "video"),
        "source_streaming_candidate_success": successful_source_streaming_transcript(source_streaming_candidate, "video"),
    }
    failed = [name for name, ok in source_streaming_checks.items() if not ok]
    source_streaming_parity_ok = not failed
    return {
        "ok": source_streaming_parity_ok,
        "path": str(path),
        "checks": source_streaming_checks,
        "failed": failed,
        "source_streaming_parity_ok": source_streaming_parity_ok,
        "source_streaming_checks": source_streaming_checks,
    }


def validate_source_control_tls_loopback_report(
    path: pathlib.Path,
    candidate_source_hashes: set[str],
) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "path": str(path), "reason": "source control TLS loopback report does not exist"}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return {"ok": False, "path": str(path), "reason": f"source control TLS loopback report is invalid JSON: {error}"}

    inputs = payload.get("inputs", {})
    inputs = inputs if isinstance(inputs, dict) else {}
    official_source = inputs.get("official_source", {})
    candidate_source = inputs.get("candidate_source", {})
    official_source = official_source if isinstance(official_source, dict) else {}
    candidate_source = candidate_source if isinstance(candidate_source, dict) else {}
    official_source_sha = official_source.get("sha256")
    candidate_source_sha = candidate_source.get("sha256")
    artifacts = payload.get("artifacts", {})
    artifacts = artifacts if isinstance(artifacts, dict) else {}

    official_artifact = artifact_path(path, artifacts.get("official"))
    candidate_artifact = artifact_path(path, artifacts.get("candidate"))
    comparison_artifact = artifact_path(path, artifacts.get("comparison"))
    comparison_payload: dict[str, Any] | None = None
    if comparison_artifact:
        try:
            loaded = json.loads(comparison_artifact.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = None
        comparison_payload = loaded if isinstance(loaded, dict) else None

    official_contract = comparison_payload.get("official_contract", {}) if comparison_payload else {}
    candidate_contract = comparison_payload.get("candidate_contract", {}) if comparison_payload else {}
    official_validation = comparison_payload.get("official_validation", {}) if comparison_payload else {}
    candidate_validation = comparison_payload.get("candidate_validation", {}) if comparison_payload else {}
    official_checks = official_validation.get("checks", {}) if isinstance(official_validation, dict) else {}
    candidate_checks = candidate_validation.get("checks", {}) if isinstance(candidate_validation, dict) else {}

    artifact_text = ""
    for artifact in (official_artifact, candidate_artifact, comparison_artifact):
        if artifact:
            try:
                artifact_text += artifact.read_text(encoding="utf-8")
            except OSError:
                pass

    redacted_url = "bambu:///local/127.0.0.1?port=<loopback>&user=bblp&passwd=<redacted>"
    checks = {
        "report_ok": payload.get("ok") is True,
        "no_failed_entries": payload.get("failed") == [],
        "does_not_copy_binaries": inputs.get("stores_hashes_and_probe_transcripts_only") is True,
        "passwords_redacted": inputs.get("passwords_redacted") is True,
        "official_source_differs_from_candidate": bool(
            official_source_sha and candidate_source_sha and official_source_sha != candidate_source_sha
        ),
        "candidate_source_hash_matches_current_build": bool(candidate_source_sha and candidate_source_sha in candidate_source_hashes),
        "official_artifact_present": official_artifact is not None,
        "candidate_artifact_present": candidate_artifact is not None,
        "comparison_artifact_present": comparison_artifact is not None,
        "comparison_ok": bool(comparison_payload and comparison_payload.get("ok") is True),
        "contracts_match": bool(comparison_payload and official_contract == candidate_contract),
        "official_validation_ok": isinstance(official_validation, dict) and official_validation.get("ok") is True,
        "candidate_validation_ok": isinstance(candidate_validation, dict) and candidate_validation.get("ok") is True,
        "official_login_frame_checked": bool(isinstance(official_checks, dict) and official_checks.get("login_payload_size") is True),
        "candidate_login_frame_checked": bool(isinstance(candidate_checks, dict) and candidate_checks.get("login_payload_size") is True),
        "official_control_frames_checked": bool(isinstance(official_checks, dict) and official_checks.get("control_headers_match_shape") is True),
        "candidate_control_frames_checked": bool(isinstance(candidate_checks, dict) and candidate_checks.get("control_headers_match_shape") is True),
        "artifacts_keep_secret_out": "secret" not in artifact_text and "passwd=secret" not in artifact_text,
        "artifacts_use_redacted_url": redacted_url in artifact_text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "ok": not failed,
        "required": False,
        "path": str(path),
        "checks": checks,
        "failed": failed,
        "source_control_tls_loopback_parity_ok": not failed,
        "source_control_tls_loopback_checks": checks,
    }


def linux_manifest_hashes(path: pathlib.Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    hashes: dict[str, str] = {}
    for entry in payload.get("files", []):
        if isinstance(entry, dict) and isinstance(entry.get("name"), str) and isinstance(entry.get("sha256"), str):
            hashes[entry["name"]] = entry["sha256"]
    return hashes


def response_value(response: dict[str, Any], key: str = "value", default: Any = None) -> Any:
    return response.get(key, default) if isinstance(response, dict) else default


def bridge_ft_smoke_checks(responses: dict[str, Any], prefix: str) -> dict[str, bool]:
    ft_smoke = responses.get("ft_smoke", {}) if isinstance(responses, dict) else {}
    if not isinstance(ft_smoke, dict):
        ft_smoke = {}
    tunnel_create = ft_smoke.get("tunnel_create", {})
    tunnel = tunnel_create.get("tunnel", 0) if isinstance(tunnel_create, dict) else 0
    media_result = ft_smoke.get("media_job_get_result", {})
    upload_msg = ft_smoke.get("upload_job_get_msg", {})
    upload_result = ft_smoke.get("upload_job_get_result", {})
    return {
        f"{prefix}_ft_tunnel_create": response_value(tunnel_create) == 0,
        f"{prefix}_ft_tunnel_handle": isinstance(tunnel, int) and tunnel > 0,
        f"{prefix}_ft_tunnel_sync_connect": response_value(ft_smoke.get("tunnel_sync_connect", {})) == 0,
        f"{prefix}_ft_media_job_create": response_value(ft_smoke.get("media_job_create", {})) == 0,
        f"{prefix}_ft_media_job_start": response_value(ft_smoke.get("media_job_start", {})) == 0,
        f"{prefix}_ft_media_result": response_value(media_result) == 0 and media_result.get("ec") == 0,
        f"{prefix}_ft_media_result_json": "emmc" in str(media_result.get("json", "")),
        f"{prefix}_ft_upload_job_create": response_value(ft_smoke.get("upload_job_create", {})) == 0,
        f"{prefix}_ft_upload_job_start": response_value(ft_smoke.get("upload_job_start", {})) == 0,
        f"{prefix}_ft_upload_progress_message": response_value(upload_msg) == 0 and "progress" in str(upload_msg.get("json", "")),
        f"{prefix}_ft_upload_missing_file_result": response_value(upload_result) == 0 and upload_result.get("ec") == -3,
        f"{prefix}_ft_tunnel_release": response_value(ft_smoke.get("tunnel_release", {})) == 0,
    }


def bridge_source_smoke_checks(responses: dict[str, Any], prefix: str) -> dict[str, bool]:
    source_smoke = responses.get("source_smoke", {}) if isinstance(responses, dict) else {}
    if not isinstance(source_smoke, dict):
        source_smoke = {}
    source_local_tunnel_smoke = responses.get("source_local_tunnel_smoke", {}) if isinstance(responses, dict) else {}
    if not isinstance(source_local_tunnel_smoke, dict):
        source_local_tunnel_smoke = {}
    create = source_smoke.get("create", {})
    tunnel = create.get("tunnel", 0) if isinstance(create, dict) else 0
    stream_info = source_smoke.get("get_stream_info", {})
    info = stream_info.get("info", {}) if isinstance(stream_info, dict) else {}
    read_sample = source_smoke.get("read_sample", {})
    sample = read_sample.get("sample", {}) if isinstance(read_sample, dict) else {}
    local_create = source_local_tunnel_smoke.get("create", {})
    local_tunnel = local_create.get("tunnel", 0) if isinstance(local_create, dict) else 0
    local_recv_message = source_local_tunnel_smoke.get("recv_message", {})
    local_read_sample = source_local_tunnel_smoke.get("read_sample", {})
    local_sample = local_read_sample.get("sample", {}) if isinstance(local_read_sample, dict) else {}
    local_server = source_local_tunnel_smoke.get("server", {})
    return {
        f"{prefix}_source_smoke_present": bool(source_smoke),
        f"{prefix}_source_create": response_value(create) == 0,
        f"{prefix}_source_tunnel_handle": isinstance(tunnel, int) and tunnel > 0,
        f"{prefix}_source_open": response_value(source_smoke.get("open", {})) == 0,
        f"{prefix}_source_start_stream": response_value(source_smoke.get("start_stream", {})) == 0,
        f"{prefix}_source_stream_count": response_value(source_smoke.get("get_stream_count", {})) == 1,
        f"{prefix}_source_stream_info": response_value(stream_info) == 0,
        f"{prefix}_source_stream_info_video": isinstance(info, dict) and info.get("type") == 0 and info.get("sub_type") == 1 and info.get("format_type") == 2,
        f"{prefix}_source_read_sample": response_value(read_sample) == 0,
        f"{prefix}_source_sample_buffer": isinstance(sample, dict) and sample.get("size", 0) > 0 and read_sample.get("__binary_size", 0) > 0,
        f"{prefix}_source_destroy": response_value(source_smoke.get("destroy", {})) == 0,
        f"{prefix}_source_local_tunnel_smoke_present": bool(source_local_tunnel_smoke),
        f"{prefix}_source_local_tunnel_create": response_value(local_create) == 0,
        f"{prefix}_source_local_tunnel_handle": isinstance(local_tunnel, int) and local_tunnel > 0,
        f"{prefix}_source_local_tunnel_open": response_value(source_local_tunnel_smoke.get("open", {})) == 0,
        f"{prefix}_source_local_tunnel_start": response_value(source_local_tunnel_smoke.get("start_stream_ex", {})) == 0,
        f"{prefix}_source_local_tunnel_send": response_value(source_local_tunnel_smoke.get("send_message", {})) == 0,
        f"{prefix}_source_local_tunnel_send_sample": response_value(source_local_tunnel_smoke.get("send_message_sample", {})) == 0,
        f"{prefix}_source_local_tunnel_recv_message": response_value(local_recv_message) == 0,
        f"{prefix}_source_local_tunnel_recv_message_buffer": (
            local_recv_message.get("message_len", 0) > 0
            and local_recv_message.get("__binary_size", 0) > 0
        ),
        f"{prefix}_source_local_tunnel_recv_message_ctrl": local_recv_message.get("ctrl") == 0,
        f"{prefix}_source_local_tunnel_recv_message_response": (
            "bridge-recv-loopback" in str(local_recv_message.get("__binary_text", ""))
        ),
        f"{prefix}_source_local_tunnel_read_sample": response_value(local_read_sample) == 0,
        f"{prefix}_source_local_tunnel_sample_buffer": (
            isinstance(local_sample, dict)
            and local_sample.get("size", 0) > 0
            and local_read_sample.get("__binary_size", 0) > 0
        ),
        f"{prefix}_source_local_tunnel_response": (
            "bridge-sample-loopback" in str(local_read_sample.get("__binary_text", ""))
        ),
        f"{prefix}_source_local_tunnel_server": (
            isinstance(local_server, dict)
            and local_server.get("accepted") is True
            and local_server.get("received_message") is True
            and local_server.get("response_sent") is True
            and local_server.get("error") == ""
        ),
        f"{prefix}_source_local_tunnel_destroy": response_value(source_local_tunnel_smoke.get("destroy", {})) == 0,
    }


def bridge_cloud_smoke_checks(responses: dict[str, Any], prefix: str) -> dict[str, bool]:
    cloud_smoke = responses.get("cloud_smoke", {}) if isinstance(responses, dict) else {}
    if not isinstance(cloud_smoke, dict):
        cloud_smoke = {}
    user_print_info = cloud_smoke.get("get_user_print_info", {})
    user_tasks = cloud_smoke.get("get_user_tasks", {})
    my_token = cloud_smoke.get("get_my_token", {})
    my_profile = cloud_smoke.get("get_my_profile", {})
    bind_ticket = cloud_smoke.get("request_bind_ticket", {})
    user_info = cloud_smoke.get("get_user_info", {})
    plate_index = cloud_smoke.get("get_task_plate_index", {})
    return {
        f"{prefix}_cloud_smoke_present": bool(cloud_smoke),
        f"{prefix}_cloud_change_user": response_value(cloud_smoke.get("change_user", {})) == 0,
        f"{prefix}_cloud_connect_server": response_value(cloud_smoke.get("connect_server", {})) == 0,
        f"{prefix}_cloud_is_server_connected": response_value(cloud_smoke.get("is_server_connected", {})) is True,
        f"{prefix}_cloud_user_print_info": response_value(user_print_info) == 0 and user_print_info.get("http_code") == 200 and bool(user_print_info.get("http_body")),
        f"{prefix}_cloud_user_tasks": response_value(user_tasks) == 0 and bool(user_tasks.get("http_body")),
        f"{prefix}_cloud_token": response_value(my_token) == 0 and my_token.get("http_code") == 200 and bool(my_token.get("http_body")),
        f"{prefix}_cloud_profile": response_value(my_profile) == 0 and my_profile.get("http_code") == 200 and bool(my_profile.get("http_body")),
        f"{prefix}_cloud_bind_ticket": response_value(bind_ticket) == 0 and bool(bind_ticket.get("ticket")),
        f"{prefix}_cloud_user_info": response_value(user_info) == 0 and user_info.get("identifier", 0) > 0,
        f"{prefix}_cloud_task_plate_index": response_value(plate_index) == 0 and plate_index.get("plate_index", -1) >= 0,
        f"{prefix}_cloud_logout": response_value(cloud_smoke.get("user_logout", {})) == 0,
    }


def bridge_ft_capability_checks(responses: dict[str, Any], prefix: str) -> dict[str, bool]:
    capabilities = responses.get("ft_capabilities", {}) if isinstance(responses, dict) else {}
    if not isinstance(capabilities, dict):
        capabilities = {}
    return {
        f"{prefix}_ft_capability_{name}": capabilities.get(name) is True
        for name in REQUIRED_FT_SYMBOLS
    }


def bridge_auth_info_checks(responses: dict[str, Any], prefix: str) -> dict[str, bool]:
    auth_info = responses.get("auth_info", {}) if isinstance(responses, dict) else {}
    if not isinstance(auth_info, dict):
        auth_info = {}
    capabilities = auth_info.get("capabilities", {})
    if not isinstance(capabilities, dict):
        capabilities = {}

    checks = {
        f"{prefix}_auth_info_ok": auth_info.get("ok") is True,
        f"{prefix}_auth_info_logged_out": auth_info.get("logged_in") is False,
        f"{prefix}_auth_info_bambulab_host": auth_info.get("bambulab_host") == BAMBULAB_HOST,
        f"{prefix}_auth_info_studio_info_url": auth_info.get("studio_info_url") == STUDIO_INFO_URL,
    }
    checks.update({
        f"{prefix}_auth_capability_{name}": capabilities.get(name) is True
        for name in REQUIRED_AUTH_SYMBOLS
    })
    return checks


def validate_linux_runtime_report(path: pathlib.Path, expected_manifest: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "path": str(path), "reason": "Linux runtime report does not exist"}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return {"ok": False, "path": str(path), "reason": f"Linux runtime report is invalid JSON: {error}"}

    bridge_probes = payload.get("bridge_probes", {})
    payload_files = payload.get("payload_files", {})
    expected_hashes = linux_manifest_hashes(expected_manifest)
    checks: dict[str, bool] = {
        "report_ok": payload.get("ok") is True,
    }
    for name in ("libbambu_networking.so", "libBambuSource.so"):
        metadata = payload_files.get(name, {}) if isinstance(payload_files, dict) else {}
        checks[f"{name}_hash_matches_current_payload"] = (
            bool(expected_hashes.get(name))
            and metadata.get("sha256") == expected_hashes.get(name)
        )
    for abi in ("abi1", "abi0"):
        probe = bridge_probes.get(abi, {}) if isinstance(bridge_probes, dict) else {}
        transcript = probe.get("stdout_json", {}) if isinstance(probe, dict) else {}
        responses = transcript.get("responses", {}) if isinstance(transcript, dict) else {}
        handshake = responses.get("handshake", {}) if isinstance(responses, dict) else {}
        create_agent = responses.get("create_agent", {}) if isinstance(responses, dict) else {}
        checks[f"{abi}_probe_ok"] = probe.get("ok") is True
        checks[f"{abi}_network_loaded"] = handshake.get("network_loaded") is True
        checks[f"{abi}_source_loaded"] = handshake.get("source_loaded") is True
        checks[f"{abi}_source_present"] = transcript.get("source_so_present") is True
        checks[f"{abi}_network_present"] = transcript.get("network_so_present") is True
        checks[f"{abi}_ft_smoke_present"] = "ft_smoke" in responses
        checks[f"{abi}_create_agent"] = isinstance(create_agent.get("value"), int) and create_agent.get("value") > 0
        checks[f"{abi}_set_config_dir"] = response_value(responses.get("set_config_dir", {})) == 0
        checks[f"{abi}_init_log"] = response_value(responses.get("init_log", {})) == 0
        checks[f"{abi}_set_country_code"] = response_value(responses.get("set_country_code", {})) == 0
        checks[f"{abi}_start"] = response_value(responses.get("start", {})) == 0
        checks[f"{abi}_destroy_agent"] = response_value(responses.get("destroy_agent", {})) == 0
        checks.update(bridge_auth_info_checks(responses, abi))
        checks.update(bridge_ft_capability_checks(responses, abi))
        checks.update(bridge_ft_smoke_checks(responses, abi))
        checks.update(bridge_source_smoke_checks(responses, abi))
        checks.update(bridge_cloud_smoke_checks(responses, abi))

    failed = [name for name, ok in checks.items() if not ok]
    return {
        "ok": not failed,
        "path": str(path),
        "expected_manifest": str(expected_manifest),
        "checks": checks,
        "failed": failed,
        "runtime_dir": payload.get("runtime_dir"),
    }


def report_path(value: Any) -> pathlib.Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = pathlib.Path(value)
    candidates = [path] if path.is_absolute() else [ROOT / path, path]
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def report_sha_matches(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    path = report_path(value.get("path"))
    expected = value.get("sha256")
    return bool(path and isinstance(expected, str) and sha256(path) == expected)


def report_check_payload(payload: dict[str, Any], name: str) -> dict[str, Any]:
    checks = payload.get("checks", {})
    check = checks.get(name, {}) if isinstance(checks, dict) else {}
    report = check.get("payload", {}) if isinstance(check, dict) else {}
    return report if isinstance(report, dict) else {}


def validate_linux_libstdcxx_report(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "path": str(path), "reason": "Linux libstdc++ direct-load report does not exist"}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return {"ok": False, "path": str(path), "reason": f"Linux libstdc++ direct-load report is invalid JSON: {error}"}

    inputs = payload.get("inputs", {})
    outputs = payload.get("outputs", {})
    network_exports = report_check_payload(payload, "network_exports")
    source_exports = report_check_payload(payload, "source_exports")
    network_cxx_abi = report_check_payload(payload, "network_cxx_abi")
    source_cxx_abi = report_check_payload(payload, "source_cxx_abi")
    network_dlopen = report_check_payload(payload, "network_dlopen")
    source_dlopen = report_check_payload(payload, "source_dlopen")
    checks: dict[str, bool] = {
        "report_ok": payload.get("ok") is True,
        "network_shim_hash_matches_current_source": report_sha_matches(inputs.get("network_shim") if isinstance(inputs, dict) else None),
        "source_shim_hash_matches_current_source": report_sha_matches(inputs.get("source_shim") if isinstance(inputs, dict) else None),
        "rust_core_hash_matches_current_input": report_sha_matches(inputs.get("rust_core") if isinstance(inputs, dict) else None),
        "network_output_hash_matches_file": report_sha_matches(outputs.get("network_so") if isinstance(outputs, dict) else None),
        "source_output_hash_matches_file": report_sha_matches(outputs.get("source_so") if isinstance(outputs, dict) else None),
        "network_exports": (
            network_exports.get("ok") is True
            and network_exports.get("present_count") == 124
            and network_exports.get("missing_count") == 0
        ),
        "source_exports": (
            source_exports.get("ok") is True
            and source_exports.get("present_count") == 18
            and source_exports.get("missing_count") == 0
        ),
        "network_cxx_abi": (
            network_cxx_abi.get("ok") is True
            and network_cxx_abi.get("expected") == "libstdc++"
            and network_cxx_abi.get("inferred") == "libstdc++"
            and network_cxx_abi.get("libcxx_symbol_count") == 0
            and "libstdc++.so.6" in network_cxx_abi.get("needed_libraries", [])
        ),
        "source_cxx_abi": (
            source_cxx_abi.get("ok") is True
            and source_cxx_abi.get("expected") == "libstdc++"
            and source_cxx_abi.get("inferred") == "libstdc++"
            and source_cxx_abi.get("libcxx_symbol_count") == 0
            and "libstdc++.so.6" in source_cxx_abi.get("needed_libraries", [])
        ),
        "network_dlopen": (
            network_dlopen.get("ok") is True
            and network_dlopen.get("present_count") == 124
            and network_dlopen.get("missing_count") == 0
        ),
        "source_dlopen": (
            source_dlopen.get("ok") is True
            and source_dlopen.get("present_count") == 18
            and source_dlopen.get("missing_count") == 0
        ),
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "ok": not failed,
        "required": True,
        "path": str(path),
        "checks": checks,
        "failed": failed,
        "network_so": payload.get("network_so"),
        "source_so": payload.get("source_so"),
        "compiler": payload.get("compiler"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=pathlib.Path, default=ROOT / "build/bambu_network_release_readiness")
    parser.add_argument("--plugin-build-dir", type=pathlib.Path, default=DEFAULT_PLUGIN_BUILD)
    parser.add_argument("--candidate-network", type=pathlib.Path, default=None)
    parser.add_argument("--candidate-source", type=pathlib.Path, default=None)
    parser.add_argument("--official-network", type=pathlib.Path, default=None)
    parser.add_argument("--official-source", type=pathlib.Path, default=None)
    parser.add_argument("--official-parity-report", type=pathlib.Path, default=None, help="existing parity_report.json from capture_official_parity.py")
    parser.add_argument("--source-streaming-parity-report", type=pathlib.Path, default=None, help="supplemental source_streaming parity_report.json")
    parser.add_argument("--source-control-tls-loopback-parity-report", type=pathlib.Path, default=None, help="supplemental local-control TLS loopback parity_report.json")
    parser.add_argument("--include-synthetic-ft-behavior", action="store_true", help="include the synthetic ft_* tunnel/job parity probe when generating official parity")
    parser.add_argument("--include-cloud-service", action="store_true", help="include authorized cloud/service parity when generating official parity")
    parser.add_argument("--cloud-user-info-file", default="", help="optional login-info JSON file; contents are not written to artifacts")
    parser.add_argument("--cloud-user-info-env", default="")
    parser.add_argument("--cloud-ticket-env", default="")
    parser.add_argument("--cloud-access-token-env", default="")
    parser.add_argument("--cloud-detail-id", default="0")
    parser.add_argument("--cloud-task-id", default="0")
    parser.add_argument("--cloud-subscribe-module", default="app")
    parser.add_argument("--allow-cloud-network", action="store_true")
    parser.add_argument("--expect-cloud-service-success", action="store_true")
    parser.add_argument("--source-stream-url", default="", help="optional bambu:///... URL for live libBambuSource streaming parity")
    parser.add_argument("--source-stream-mode", default="video", choices=("video", "control"))
    parser.add_argument("--source-stream-timeout-ms", type=int, default=10000)
    parser.add_argument("--source-stream-poll-ms", type=int, default=50)
    parser.add_argument("--source-stream-ctrl-type", type=int, default=0x3001)
    parser.add_argument("--source-stream-message", default="")
    parser.add_argument("--expect-source-stream-success", action="store_true")
    parser.add_argument("--official-probe-timeout-s", type=int, default=30, help="maximum seconds to wait for each generated official parity probe")
    parser.add_argument("--linux-network-so", type=pathlib.Path, default=DEFAULT_LINUX_PLUGIN_BUILD / "libbambu_networking.so")
    parser.add_argument("--linux-source-so", type=pathlib.Path, default=DEFAULT_LINUX_PLUGIN_BUILD / "libBambuSource.so")
    parser.add_argument("--linux-host", type=pathlib.Path, default=None)
    parser.add_argument("--linux-host-abi1", type=pathlib.Path, default=DEFAULT_LINUX_HOST_BUILD / "pjarczak_bambu_linux_host_abi1")
    parser.add_argument("--linux-host-abi0", type=pathlib.Path, default=DEFAULT_LINUX_HOST_BUILD / "pjarczak_bambu_linux_host_abi0")
    parser.add_argument("--linux-runtime-report", type=pathlib.Path, default=None, help="JSON report from verify_linux_bridge_runtime.py")
    parser.add_argument("--linux-libstdcxx-report", type=pathlib.Path, default=DEFAULT_LINUX_LIBSTDCXX_REPORT)
    parser.add_argument("--skip-linux-loader-probes", action="store_true")
    parser.add_argument("--macos-runtime-dir", type=pathlib.Path, default=DEFAULT_MACOS_RUNTIME_DIR)
    parser.add_argument("--run-macos-runtime-loader-probes", action="store_true")
    parser.add_argument("--printer-dev-id", default="")
    parser.add_argument("--printer-dev-ip", default="")
    parser.add_argument("--printer-username", default="bblp")
    parser.add_argument("--printer-password-env", default="BAMBU_NETWORK_PRINTER_PASSWORD")
    parser.add_argument("--printer-message", default='{"pushing":{"sequence_id":"0","command":"pushall"}}')
    parser.add_argument("--printer-wait-ms", type=int, default=1000)
    parser.add_argument("--printer-use-ssl", action="store_true")
    parser.add_argument("--print-job-file", default="")
    parser.add_argument("--print-job-mode", default="", choices=REQUIRED_PRINT_JOB_MODES, help="deprecated single-mode override")
    parser.add_argument("--print-job-modes", default=",".join(REQUIRED_PRINT_JOB_MODES), help="comma-separated real-printer print modes required for readiness")
    parser.add_argument("--print-job-remote-name", default="")
    parser.add_argument("--print-job-use-ssl-for-ftp", action="store_true")
    parser.add_argument("--expect-printer-success", action="store_true")
    parser.add_argument("--defer-manual-printer-parity", action="store_true", help="classify printer-backed parity blockers as intentionally deferred without marking readiness complete")
    parser.add_argument("--defer-authorized-cloud-parity", action="store_true", help="classify authorized cloud/service parity blockers as intentionally deferred without marking readiness complete")
    parser.add_argument("--allow-deferred-incomplete", action="store_true", help="exit 0 when all remaining blockers are explicitly deferred")
    parser.add_argument("--allow-incomplete", action="store_true", help="write the report but exit 0 even when required gates are missing")
    args = parser.parse_args()
    if args.expect_cloud_service_success and not args.include_cloud_service:
        parser.error("--expect-cloud-service-success requires --include-cloud-service")
    if args.expect_cloud_service_success and not args.allow_cloud_network:
        parser.error("--expect-cloud-service-success requires --allow-cloud-network")
    if args.expect_cloud_service_success and not (args.cloud_user_info_file or args.cloud_user_info_env):
        parser.error("--expect-cloud-service-success requires --cloud-user-info-file or --cloud-user-info-env")
    if args.cloud_user_info_file and args.cloud_user_info_env:
        parser.error("use only one of --cloud-user-info-file or --cloud-user-info-env")
    if args.official_probe_timeout_s <= 0:
        parser.error("--official-probe-timeout-s must be positive")

    suffix = dylib_suffix()
    candidate_network = args.candidate_network or args.plugin_build_dir / f"libbambu_networking{suffix}"
    candidate_source = args.candidate_source or args.plugin_build_dir / f"libBambuSource{suffix}"
    candidate_network_hashes = {
        digest for digest in [sha256(candidate_network), sha256(args.linux_network_so)] if digest
    }
    candidate_source_hashes = {
        digest for digest in [sha256(candidate_source), sha256(args.linux_source_so)] if digest
    }
    official_parity_report = (
        validate_official_parity_report(args.official_parity_report, candidate_network_hashes, candidate_source_hashes)
        if args.official_parity_report
        else None
    )
    source_streaming_parity_report = (
        validate_source_streaming_loopback_report(args.source_streaming_parity_report, candidate_source_hashes)
        if args.source_streaming_parity_report
        else None
    )
    source_control_tls_loopback_parity_report = (
        validate_source_control_tls_loopback_report(args.source_control_tls_loopback_parity_report, candidate_source_hashes)
        if args.source_control_tls_loopback_parity_report
        else None
    )
    clean_room_scan_dirs = [
        args.plugin_build_dir,
        args.macos_runtime_dir,
        SOURCE_MACOS_RUNTIME_DIR,
    ]
    forbidden_secret_env_names = [
        args.cloud_user_info_env,
        args.cloud_ticket_env,
        args.cloud_access_token_env,
        args.printer_password_env,
    ]
    forbidden_secret_files = [
        pathlib.Path(args.cloud_user_info_file),
    ] if args.cloud_user_info_file else []

    report: dict[str, Any] = {
        "ok": False,
        "out_dir": str(args.out_dir),
        "inputs": {
            "candidate_network": existing_path(candidate_network),
            "candidate_source": existing_path(candidate_source),
            "official_network": existing_path(args.official_network) if args.official_network else None,
            "official_source": existing_path(args.official_source) if args.official_source else None,
            "official_parity_report": existing_path(args.official_parity_report) if args.official_parity_report else None,
            "source_streaming_parity_report": existing_path(args.source_streaming_parity_report) if args.source_streaming_parity_report else None,
            "source_control_tls_loopback_parity_report": existing_path(args.source_control_tls_loopback_parity_report) if args.source_control_tls_loopback_parity_report else None,
            "cloud_service_requested": bool(args.include_cloud_service),
            "cloud_network_allowed": bool(args.allow_cloud_network),
            "cloud_user_info_present": bool(args.cloud_user_info_file or args.cloud_user_info_env),
            "linux_network_so": existing_path(args.linux_network_so),
            "linux_source_so": existing_path(args.linux_source_so),
            "linux_host": existing_path(args.linux_host) if args.linux_host else None,
            "linux_host_abi1": existing_path(args.linux_host_abi1),
            "linux_host_abi0": existing_path(args.linux_host_abi0),
            "linux_runtime_report": existing_path(args.linux_runtime_report) if args.linux_runtime_report else None,
            "linux_libstdcxx_report": existing_path(args.linux_libstdcxx_report) if args.linux_libstdcxx_report else None,
            "macos_runtime_dir": str(args.macos_runtime_dir),
            "printer_dev_id_present": bool(args.printer_dev_id),
            "printer_dev_ip_present": bool(args.printer_dev_ip),
            "source_stream_url_present": bool(args.source_stream_url),
            "source_stream_mode": args.source_stream_mode,
            "print_job_file": existing_path(pathlib.Path(args.print_job_file)) if args.print_job_file else None,
            "print_job_modes": args.print_job_modes if not args.print_job_mode else args.print_job_mode,
            "defer_manual_printer_parity": bool(args.defer_manual_printer_parity),
            "defer_authorized_cloud_parity": bool(args.defer_authorized_cloud_parity),
        },
        "gates": {},
        "blockers": [],
    }

    if candidate_network.exists() and candidate_source.exists():
        local_smoke_path = args.out_dir / "local_candidate_smoke.json"
        local_smoke_result = run([
            sys.executable,
            str(CONTRACT_DIR / "run_candidate_smoke.py"),
            "--skip-build",
            "--plugin-build-dir",
            str(args.plugin_build_dir),
        ], local_smoke_path)
        local_smoke_validation = validate_local_smoke_summary(local_smoke_path)
        if not local_smoke_validation["ok"]:
            local_smoke_result["ok"] = False
        local_smoke_result["summary_validation"] = local_smoke_validation
        add_gate(report, "local_candidate_smoke", {
            **local_smoke_result,
            "required": True,
        })
    else:
        add_gate(report, "local_candidate_smoke", skipped(True, "candidate build artifacts are missing"))

    if official_parity_report:
        artifact_policy_result = None
        if args.official_parity_report and args.official_parity_report.exists():
            artifact_policy_result = run(
                clean_room_artifact_policy_command(
                    args.official_parity_report,
                    args.official_parity_report.parent,
                    clean_room_scan_dirs,
                    forbidden_secret_env_names,
                    forbidden_secret_files,
                ),
                args.out_dir / "official_parity_artifact_policy.json",
            )
            if not artifact_policy_result["ok"]:
                official_parity_report["ok"] = False
        official_parity_report["artifact_policy"] = artifact_policy_result
        add_gate(report, "official_parity", {**official_parity_report, "required": True})
    elif args.official_network and args.official_source and args.official_network.exists() and args.official_source.exists():
        official_parity_dir = args.out_dir / "official_parity"
        command = [
            sys.executable,
            str(CONTRACT_DIR / "capture_official_parity.py"),
            "--skip-build",
            "--official-network",
            str(args.official_network),
            "--official-source",
            str(args.official_source),
            "--candidate-network",
            str(candidate_network),
            "--candidate-source",
            str(candidate_source),
            "--out-dir",
            str(official_parity_dir),
            "--include-discovery",
            "--include-source-behavior",
            "--include-ft-job-only",
            "--probe-timeout-s",
            str(args.official_probe_timeout_s),
        ]
        if args.include_synthetic_ft_behavior:
            command.append("--include-ft-behavior")
        if args.include_cloud_service:
            command.append("--include-cloud-service")
            command.extend([
                "--cloud-detail-id",
                args.cloud_detail_id,
                "--cloud-task-id",
                args.cloud_task_id,
                "--cloud-subscribe-module",
                args.cloud_subscribe_module,
            ])
            if args.cloud_user_info_file:
                command.extend(["--cloud-user-info-file", args.cloud_user_info_file])
            if args.cloud_user_info_env:
                command.extend(["--cloud-user-info-env", args.cloud_user_info_env])
            if args.cloud_ticket_env:
                command.extend(["--cloud-ticket-env", args.cloud_ticket_env])
            if args.cloud_access_token_env:
                command.extend(["--cloud-access-token-env", args.cloud_access_token_env])
            if args.allow_cloud_network:
                command.append("--allow-cloud-network")
            if args.expect_cloud_service_success:
                command.append("--expect-cloud-service-success")
        if args.source_stream_url:
            command.extend([
                "--source-stream-url",
                args.source_stream_url,
                "--source-stream-mode",
                args.source_stream_mode,
                "--source-stream-timeout-ms",
                str(args.source_stream_timeout_ms),
                "--source-stream-poll-ms",
                str(args.source_stream_poll_ms),
                "--source-stream-ctrl-type",
                str(args.source_stream_ctrl_type),
            ])
            if args.source_stream_message:
                command.extend(["--source-stream-message", args.source_stream_message])
            if args.expect_source_stream_success:
                command.append("--expect-source-stream-success")
        if args.printer_dev_id and args.printer_dev_ip:
            command.extend([
                "--printer-dev-id",
                args.printer_dev_id,
                "--printer-dev-ip",
                args.printer_dev_ip,
                "--printer-username",
                args.printer_username,
                "--printer-password-env",
                args.printer_password_env,
                "--printer-message",
                args.printer_message,
                "--printer-wait-ms",
                str(args.printer_wait_ms),
            ])
            if args.printer_use_ssl:
                command.append("--printer-use-ssl")
        if args.print_job_file:
            print_job_modes = args.print_job_mode if args.print_job_mode else args.print_job_modes
            command.extend([
                "--print-job-file",
                args.print_job_file,
                "--print-job-modes",
                print_job_modes,
            ])
            if args.print_job_remote_name:
                command.extend(["--print-job-remote-name", args.print_job_remote_name])
            if args.print_job_use_ssl_for_ftp:
                command.append("--print-job-use-ssl-for-ftp")
            if args.expect_printer_success:
                command.append("--expect-print-job-success")
        official_result = run(command, args.out_dir / "official_parity.json")
        generated_parity_report = official_parity_dir / "parity_report.json"
        parity_report_validation = validate_official_parity_report(
            generated_parity_report,
            candidate_network_hashes,
            candidate_source_hashes,
        )
        official_parity_report = parity_report_validation
        if not parity_report_validation["ok"]:
            official_result["ok"] = False
        artifact_policy_result = None
        if generated_parity_report.exists():
            artifact_policy_result = run(
                clean_room_artifact_policy_command(
                    generated_parity_report,
                    official_parity_dir,
                    clean_room_scan_dirs,
                    forbidden_secret_env_names,
                    forbidden_secret_files,
                ),
                args.out_dir / "official_parity_artifact_policy.json",
            )
        if artifact_policy_result is not None and not artifact_policy_result["ok"]:
            official_result["ok"] = False
        official_result["artifact_policy"] = artifact_policy_result
        official_result["parity_report_validation"] = parity_report_validation
        add_gate(report, "official_parity", {**official_result, "required": True})
    else:
        add_gate(report, "official_parity", skipped(True, "official plugin paths were not provided or do not exist"))

    feature_parity_report = official_parity_report
    if source_streaming_parity_report:
        add_gate(report, "source_streaming_parity_report", {**source_streaming_parity_report, "required": False})
        feature_parity_report = merge_supplemental_feature_evidence(
            feature_parity_report,
            source_streaming_parity_report,
            "source_streaming_parity_report",
        )
    if source_control_tls_loopback_parity_report:
        add_gate(report, "source_control_tls_loopback_parity_report", {**source_control_tls_loopback_parity_report, "required": False})
        feature_parity_report = merge_supplemental_feature_evidence(
            feature_parity_report,
            source_control_tls_loopback_parity_report,
            "source_control_tls_loopback_parity_report",
        )

    requested_print_job_modes = [mode.strip() for mode in (args.print_job_mode if args.print_job_mode else args.print_job_modes).split(",") if mode.strip()]
    invalid_print_job_modes = [mode for mode in requested_print_job_modes if mode not in REQUIRED_PRINT_JOB_MODES]
    missing_required_print_job_modes = [mode for mode in REQUIRED_PRINT_JOB_MODES if mode not in requested_print_job_modes]
    print_job_file_exists = bool(args.print_job_file and pathlib.Path(args.print_job_file).exists())
    has_external_real_printer_report = bool(
        official_parity_report
        and official_parity_report.get("ok")
        and official_parity_report.get("real_printer_workflows_ok")
    )
    has_real_printer = bool(
        has_external_real_printer_report
        or (
            args.printer_dev_id
            and args.printer_dev_ip
            and print_job_file_exists
            and not invalid_print_job_modes
            and not missing_required_print_job_modes
            and args.print_job_remote_name
        )
    )
    add_gate(report, "real_printer_parity_inputs", {
        "ok": has_real_printer,
        "required": True,
        "external_real_printer_report": has_external_real_printer_report,
        "printer_dev_id_present": bool(args.printer_dev_id),
        "printer_dev_ip_present": bool(args.printer_dev_ip),
        "print_job_file_present": print_job_file_exists,
        "print_job_remote_name_present": bool(args.print_job_remote_name),
        "requested_print_job_modes": requested_print_job_modes,
        "required_print_job_modes": list(REQUIRED_PRINT_JOB_MODES),
    } if has_real_printer else {
        **skipped(
            True,
            "printer dev id, printer ip, print-job file, remote name, and upload-only/local-print/sdcard-print modes are required for real printer parity",
        ),
        "printer_dev_id_present": bool(args.printer_dev_id),
        "printer_dev_ip_present": bool(args.printer_dev_ip),
        "print_job_file_present": print_job_file_exists,
        "print_job_remote_name_present": bool(args.print_job_remote_name),
        "external_real_printer_report": has_external_real_printer_report,
        "external_real_printer_checks": official_parity_report.get("real_printer_checks") if official_parity_report else None,
        "requested_print_job_modes": requested_print_job_modes,
        "required_print_job_modes": list(REQUIRED_PRINT_JOB_MODES),
        "invalid_print_job_modes": invalid_print_job_modes,
        "missing_required_print_job_modes": missing_required_print_job_modes,
    })

    add_gate(report, "full_compatibility_feature_parity", validate_full_compatibility_feature_parity(feature_parity_report))

    if args.linux_network_so.exists() and args.linux_source_so.exists():
        command = [
            sys.executable,
            str(CONTRACT_DIR / "assemble_candidate_linux_payload.py"),
            "--network-so",
            str(args.linux_network_so),
            "--source-so",
            str(args.linux_source_so),
            "--out-dir",
            str(args.out_dir / "linux_payload"),
        ]
        if args.linux_host:
            command.extend(["--host", str(args.linux_host)])
        if args.skip_linux_loader_probes:
            command.append("--skip-symbol-probes")
        linux_required_ok = bool(args.linux_host and not args.skip_linux_loader_probes)
        result = run(command, args.out_dir / "linux_payload.json")
        linux_runtime_report = (
            validate_linux_runtime_report(args.linux_runtime_report, args.out_dir / "linux_payload/linux_payload_manifest.json")
            if args.linux_runtime_report
            else None
        )
        result["required"] = True
        result["has_linux_host"] = bool(args.linux_host)
        result["loader_probes_skipped"] = args.skip_linux_loader_probes
        result["linux_runtime_report"] = linux_runtime_report
        has_external_linux_evidence = bool(linux_runtime_report and linux_runtime_report["ok"])
        if result["ok"] and not (linux_required_ok or has_external_linux_evidence):
            result["ok"] = False
            result["reason"] = "full readiness requires a Linux host with non-skipped loader/bridge probes or an ok verify_linux_bridge_runtime.py report"
        add_gate(report, "linux_bridge_payload", result)
    else:
        add_gate(report, "linux_bridge_payload", skipped(True, "Linux candidate .so artifacts are missing"))

    add_gate(
        report,
        "linux_direct_libstdcxx_load",
        validate_linux_libstdcxx_report(args.linux_libstdcxx_report)
        if args.linux_libstdcxx_report and args.linux_libstdcxx_report.exists()
        else skipped(True, "Linux libstdc++ direct-load report is missing; run build_linux_libstdcxx_candidate.py"),
    )

    if args.linux_network_so.exists() and args.linux_source_so.exists() and args.linux_host_abi1.exists() and args.linux_host_abi0.exists():
        assemble_command = [
            sys.executable,
            str(CONTRACT_DIR / "assemble_macos_bridge_runtime.py"),
            "--network-so",
            str(args.linux_network_so),
            "--source-so",
            str(args.linux_source_so),
            "--host-abi1",
            str(args.linux_host_abi1),
            "--host-abi0",
            str(args.linux_host_abi0),
            "--out-dir",
            str(args.macos_runtime_dir),
        ]
        loader_probes_skipped = not args.run_macos_runtime_loader_probes
        if loader_probes_skipped:
            assemble_command.append("--skip-loader-probes")
        assemble_result = run(assemble_command, args.out_dir / "macos_bridge_runtime_assemble.json")
        verify_result: dict[str, Any] | None = None
        if assemble_result["ok"]:
            verify_result = run([
                sys.executable,
                str(CONTRACT_DIR / "verify_macos_release_runtime.py"),
                "--runtime-dir",
                str(args.macos_runtime_dir),
                "--out-dir",
                str(args.out_dir / "macos_runtime_copy"),
            ], args.out_dir / "macos_bridge_runtime_verify.json")
        verify_payload = load_json_file(pathlib.Path(verify_result["stdout"])) if verify_result else None
        copied_metadata = {}
        bridge_dylib_fixture = {}
        if verify_payload:
            release_copy = verify_payload.get("release_script_copy", {})
            copied_metadata = release_copy.get("copied_file_metadata", {})
            bridge_dylib_fixture = release_copy.get("bridge_dylib_fixture", {})
        metadata_checks = {
            f"copied_metadata_{name}": (
                isinstance(copied_metadata.get(name), dict)
                and bool(copied_metadata[name].get("sha256"))
                and copied_metadata[name].get("size", 0) > 0
            )
            for name in REQUIRED_MACOS_COPIED_FILES
        }
        metadata_ok = bool(metadata_checks) and all(metadata_checks.values())
        bridge_dylib_fixture_ok = (
            isinstance(bridge_dylib_fixture, dict)
            and bridge_dylib_fixture.get("kind") == MACOS_BRIDGE_DYLIB_FIXTURE_KIND
        )
        gate_ok = assemble_result["ok"] and bool(verify_result and verify_result["ok"]) and metadata_ok and bridge_dylib_fixture_ok
        add_gate(report, "macos_bridge_runtime", {
            "ok": gate_ok,
            "required": True,
            "assemble": assemble_result,
            "verify": verify_result,
            "verify_summary": {
                "ok": bool(verify_payload and verify_payload.get("ok") is True),
                "copied_file_metadata_present": metadata_ok,
                "bridge_dylib_fixture_kind": bridge_dylib_fixture.get("kind") if isinstance(bridge_dylib_fixture, dict) else None,
                "bridge_dylib_fixture_declared": bridge_dylib_fixture_ok,
                "checks": metadata_checks,
            },
            "loader_probes_skipped": loader_probes_skipped,
        })
    else:
        add_gate(report, "macos_bridge_runtime", {
            **skipped(True, "Linux candidate .so artifacts or ABI0/ABI1 Linux host binaries are missing"),
            "linux_network_so_present": args.linux_network_so.exists(),
            "linux_source_so_present": args.linux_source_so.exists(),
            "linux_host_abi1_present": args.linux_host_abi1.exists(),
            "linux_host_abi0_present": args.linux_host_abi0.exists(),
        })

    report["ok"] = not report["blockers"]
    report["deferred"] = classify_deferred_blockers(
        report,
        defer_manual_printer_parity=args.defer_manual_printer_parity,
        defer_authorized_cloud_parity=args.defer_authorized_cloud_parity,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.out_dir / "release_readiness_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    deferred_ok = bool(args.allow_deferred_incomplete and report["deferred"].get("non_deferred_ok") is True)
    return 0 if report["ok"] or deferred_ok or args.allow_incomplete else 1


if __name__ == "__main__":
    raise SystemExit(main())
