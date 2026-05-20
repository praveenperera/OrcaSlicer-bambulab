#!/usr/bin/env python3
import argparse
import json
import pathlib
import tempfile
from typing import Any


DEFAULT_REPORT = pathlib.Path("build/bambu_network_release_readiness/release_readiness_report.json")
NATIVE_ALLOWED_INCOMPLETE_FAILURES = {
    "official_native_parity_passes",
    "clean_room_artifact_verification_passes",
    "real_printer_native_parity_passes",
    "cloud_service_native_parity_or_approved_scope_out",
    "all_native_completion_criteria_are_true",
    "single_native_readiness_artifact_is_complete",
}
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
EXPECTED_NATIVE_REAL_PRINTER_RAW_CHECKS = {
    "report_ok",
    "printer_workflow",
    "print_job_upload_only",
    "print_job_local_print",
    "print_job_sdcard_print",
    "source_streaming",
    "source_control_tunnel",
}
EXPECTED_NATIVE_CLOUD_AUTHORIZED_RAW_CHECKS = {
    "probe_ok",
    "comparison_ok",
    "official_authorized_success",
    "candidate_authorized_success",
}


def load_report(path: pathlib.Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("release readiness report is not a JSON object")
    return payload


def gate(report: dict[str, Any], name: str) -> dict[str, Any]:
    gates = report.get("gates", {})
    if not isinstance(gates, dict):
        return {}
    value = gates.get(name, {})
    return value if isinstance(value, dict) else {}


def nested(payload: dict[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def bool_path(payload: dict[str, Any], *keys: str) -> bool:
    return nested(payload, *keys) is True


def non_empty_list(payload: dict[str, Any], name: str) -> bool:
    value = payload.get(name)
    return isinstance(value, list) and bool(value)


def all_true_mapping(payload: dict[str, Any], name: str) -> bool:
    value = payload.get(name)
    return isinstance(value, dict) and bool(value) and all(item is True for item in value.values())


def all_expected_true_mapping(payload: dict[str, Any], name: str, expected: set[str]) -> bool:
    value = payload.get(name)
    return isinstance(value, dict) and set(value) == expected and all(value[item] is True for item in expected)


def load_dry_run_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    report = payload.get("dry_run_report")
    if payload.get("dry_run_loaded") is not True or not isinstance(report, str) or not report:
        return None
    report_path = pathlib.Path(report)
    if not report_path.is_file():
        return None
    try:
        dry_run_payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(dry_run_payload, dict):
        return None
    if dry_run_payload.get("ok") is not True or dry_run_payload.get("dry_run") is not True:
        return None
    return dry_run_payload


def dry_run_evidence_ok(payload: dict[str, Any]) -> bool:
    return load_dry_run_payload(payload) is not None


def real_printer_missing_inputs_match_dry_run(payload: dict[str, Any]) -> bool:
    dry_run_payload = load_dry_run_payload(payload)
    if dry_run_payload is None:
        return False
    printer = dry_run_payload.get("printer")
    if not isinstance(printer, dict):
        return False
    expected = []
    if printer.get("dev_id_present") is not True:
        expected.append("printer dev id")
    if printer.get("dev_ip_present") is not True:
        expected.append("printer IP")
    if printer.get("password_present") is not True:
        expected.append(printer.get("password_env") or "printer password/access-code env")
    return payload.get("missing_inputs") == expected


def cloud_missing_inputs_match_dry_run(payload: dict[str, Any]) -> bool:
    dry_run_payload = load_dry_run_payload(payload)
    if dry_run_payload is None:
        return False
    cloud = dry_run_payload.get("cloud")
    if not isinstance(cloud, dict):
        return False
    expected = []
    if cloud.get("user_info_file_present") is not True and cloud.get("user_info_env_present") is not True:
        expected.append(cloud.get("user_info_env") or "cloud user-info file/env")
    if cloud.get("ticket_env") and cloud.get("ticket_env_present") is not True:
        expected.append(cloud.get("ticket_env"))
    if cloud.get("access_token_env") and cloud.get("access_token_env_present") is not True:
        expected.append(cloud.get("access_token_env"))
    return payload.get("missing_inputs") == expected


def native_completion_criteria_complete(completion: dict[str, Any]) -> bool:
    return (
        native_completion_criteria_shape_ok(completion)
        and all(completion[name] is True for name in EXPECTED_NATIVE_COMPLETION_CRITERIA)
    )


def native_completion_criteria_shape_ok(completion: dict[str, Any]) -> bool:
    return set(completion) == EXPECTED_NATIVE_COMPLETION_CRITERIA


def cloud_safe_failure_evidence_ok(payload: dict[str, Any]) -> bool:
    checks = payload.get("safe_failure_checks")
    if not isinstance(checks, dict):
        return False
    unsupported_compare_ok = (
        checks.get("compare_unsupported") is True
        and checks.get("probe_unsupported_artifacts_match") is True
    )
    unsupported_probe_ok = (
        checks.get("unsupported_probe_ok") is True
        and checks.get("unsupported_comparison_ok") is True
    )
    return checks.get("report_ok") is True and (unsupported_compare_ok or unsupported_probe_ok)


def actionable_blocked_actions(
    report: dict[str, Any],
    gate_names: tuple[str, ...],
    decision_gate_names: tuple[str, ...] = (),
) -> bool:
    actions = report.get("blocked_actions")
    if not isinstance(actions, list):
        return False
    if report.get("ok") is True:
        return actions == []

    gates = report.get("gates", {})
    gates = gates if isinstance(gates, dict) else {}
    expected_action_gates = {
        gate_name
        for gate_name in gate_names
        if isinstance(gates.get(gate_name), dict) and gates[gate_name].get("ok") is not True
    }
    by_gate: dict[str, dict[str, Any]] = {}
    for action in actions:
        if not isinstance(action, dict):
            return False
        gate_name = action.get("gate")
        if not isinstance(gate_name, str) or gate_name in by_gate:
            return False
        by_gate[gate_name] = action
    if set(by_gate) != expected_action_gates:
        return False
    for gate_name in gate_names:
        status = gates.get(gate_name, {})
        if not isinstance(status, dict) or status.get("ok") is True:
            continue
        action = by_gate.get(gate_name)
        if not isinstance(action, dict):
            return False
        if not isinstance(action.get("missing_inputs"), list) or not action["missing_inputs"]:
            return False
        if not isinstance(action.get("needed_action"), list) or not action["needed_action"]:
            return False
        if action["missing_inputs"] != status.get("missing_inputs"):
            return False
        if action["needed_action"] != status.get("needed_action"):
            return False
        if gate_name in decision_gate_names and (
            not isinstance(action.get("needed_decision"), str)
            or action.get("needed_decision") != status.get("needed_decision")
        ):
            return False
    return True


def required_gate_blockers_listed(report: dict[str, Any]) -> bool:
    blockers = report.get("blockers")
    if not isinstance(blockers, list) or any(not isinstance(item, str) for item in blockers):
        return False
    if report.get("ok") is True:
        return blockers == []
    gates = report.get("gates")
    if not isinstance(gates, dict):
        return False
    for name, status in gates.items():
        if (
            isinstance(name, str)
            and isinstance(status, dict)
            and status.get("required") is not False
            and status.get("ok") is not True
            and name not in blockers
        ):
            return False
    return True


def false_completion_criteria_blockers_listed(report: dict[str, Any]) -> bool:
    blockers = report.get("blockers")
    if not isinstance(blockers, list) or any(not isinstance(item, str) for item in blockers):
        return False
    if report.get("ok") is True:
        return blockers == []
    completion = report.get("completion_criteria")
    if not isinstance(completion, dict):
        return False
    for name, ok in completion.items():
        if not isinstance(name, str):
            return False
        if ok is not True and f"completion_criteria:{name}" not in blockers:
            return False
    return True


def top_level_blockers_match_unresolved_state(report: dict[str, Any]) -> bool:
    blockers = report.get("blockers")
    if not isinstance(blockers, list) or any(not isinstance(item, str) for item in blockers):
        return False
    expected: list[str] = []
    if report.get("ok") is True:
        return blockers == []
    gates = report.get("gates")
    completion = report.get("completion_criteria")
    if not isinstance(gates, dict) or not isinstance(completion, dict):
        return False
    for name, status in gates.items():
        if (
            isinstance(name, str)
            and isinstance(status, dict)
            and status.get("required") is not False
            and status.get("ok") is not True
        ):
            expected.append(name)
    for name, ok in completion.items():
        if not isinstance(name, str):
            return False
        if ok is not True:
            expected.append(f"completion_criteria:{name}")
    return set(blockers) == set(expected) and len(blockers) == len(set(blockers))


def report_ok_matches_blockers(report: dict[str, Any]) -> bool:
    blockers = report.get("blockers")
    if not isinstance(blockers, list):
        return False
    return report.get("ok") is (not blockers)


def official_check(official: dict[str, Any], name: str) -> bool:
    return bool_path(official, "parity_report_validation", "checks", name) or bool_path(official, "checks", name)


def official_flag(official: dict[str, Any], name: str) -> bool:
    return nested(official, "parity_report_validation", name) is True or official.get(name) is True


def check_local_smoke(local_smoke: dict[str, Any], *names: str) -> bool:
    checks = nested(local_smoke, "summary_validation", "checks")
    if not isinstance(checks, dict):
        return False
    return all(checks.get(f"check_{name}") is True for name in names)


def artifact_policy_ok(official: dict[str, Any]) -> bool:
    artifact_policy = official.get("artifact_policy")
    if not isinstance(artifact_policy, dict) or artifact_policy.get("ok") is not True:
        return False
    stdout = artifact_policy.get("stdout")
    if not isinstance(stdout, str):
        return False
    policy_path = pathlib.Path(stdout)
    if not policy_path.is_file():
        return False
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return (
        payload.get("ok") is True
        and payload.get("binary_artifacts") == []
        and payload.get("official_binary_copy_findings") == []
        and payload.get("secret_leak_findings", []) == []
        and isinstance(payload.get("official_inputs"), list)
        and bool(payload.get("official_inputs"))
    )


def source_control_tls_loopback_ok(source_control_tls: dict[str, Any]) -> bool:
    if not source_control_tls:
        return True
    checks = source_control_tls.get("checks", {})
    if not isinstance(checks, dict):
        return False
    return (
        source_control_tls.get("ok") is True
        and source_control_tls.get("required") is False
        and source_control_tls.get("failed") == []
        and source_control_tls.get("source_control_tls_loopback_parity_ok") is True
        and checks.get("does_not_copy_binaries") is True
        and checks.get("passwords_redacted") is True
        and checks.get("official_source_differs_from_candidate") is True
        and checks.get("candidate_source_hash_matches_current_build") is True
        and checks.get("contracts_match") is True
        and checks.get("artifacts_keep_secret_out") is True
        and checks.get("artifacts_use_redacted_url") is True
    )


def completion_checklist(report: dict[str, Any]) -> list[dict[str, Any]]:
    local_smoke = gate(report, "local_candidate_smoke")
    official = gate(report, "official_parity")
    real_printer = gate(report, "real_printer_parity_inputs")
    feature_parity = gate(report, "full_compatibility_feature_parity")
    linux_bridge = gate(report, "linux_bridge_payload")
    linux_direct = gate(report, "linux_direct_libstdcxx_load")
    macos_runtime = gate(report, "macos_bridge_runtime")
    source_control_tls = gate(report, "source_control_tls_loopback_parity_report")
    linux_checks = nested(linux_bridge, "linux_runtime_report", "checks")
    linux_checks = linux_checks if isinstance(linux_checks, dict) else {}
    linux_direct_checks = linux_direct.get("checks", {})
    linux_direct_checks = linux_direct_checks if isinstance(linux_direct_checks, dict) else {}

    return [
        {
            "name": "clean_room_rust_candidate_exists",
            "ok": check_local_smoke(local_smoke, "preflight_python_sources_compile", "preflight_clean_room_artifact_validation"),
            "evidence": "local_candidate_smoke preflights compile candidate tooling and run clean-room artifact verifier self-tests",
        },
        {
            "name": "orcaslicer_can_load_libbambu_networking_so",
            "ok": (
                linux_bridge.get("ok") is True
                and macos_runtime.get("ok") is True
                and linux_checks.get("abi0_network_loaded") is True
                and linux_checks.get("abi1_network_loaded") is True
                and linux_checks.get("abi0_source_loaded") is True
                and linux_checks.get("abi1_source_loaded") is True
                and linux_direct.get("ok") is True
                and linux_direct_checks.get("network_exports") is True
                and linux_direct_checks.get("source_exports") is True
                and linux_direct_checks.get("network_cxx_abi") is True
                and linux_direct_checks.get("source_cxx_abi") is True
                and linux_direct_checks.get("network_dlopen") is True
                and linux_direct_checks.get("source_dlopen") is True
            ),
            "evidence": "linux bridge runtime proves bridge loading, and linux_direct_libstdcxx_load proves direct libstdc++ ELF dlopen/dlsym loading",
        },
        {
            "name": "required_exports_and_abi_match",
            "ok": check_local_smoke(
                local_smoke,
                "network_symbols",
                "source_symbols",
                "preflight_symbol_manifest_sources",
                "preflight_abi_mirror",
                "preflight_cpp_signature_mirror",
                "preflight_contract_surface_coverage",
            )
            and official_check(official, "compare_network_symbols")
            and official_check(official, "compare_source_symbols"),
            "evidence": "symbol manifests, ABI mirror, C++ signature mirror, behavior coverage, and official symbol comparisons",
        },
        {
            "name": "lifecycle_and_callbacks_match_official",
            "ok": (
                check_local_smoke(local_smoke, "lifecycle_agent_created", "lifecycle_destroy_result", "callback_agent_created", "callback_transcripts_match")
                and official_check(official, "compare_lifecycle")
                and official_check(official, "compare_callback")
            ),
            "evidence": "official lifecycle and callback transcript comparisons plus local callback determinism",
        },
        {
            "name": "implemented_lan_and_printer_workflows_match_official",
            "ok": real_printer.get("ok") is True and official_flag(official, "real_printer_workflows_ok"),
            "evidence": "real_printer_parity_inputs and official_parity.real_printer_workflows_ok",
        },
        {
            "name": "unsupported_cloud_service_behavior_fails_safely",
            "ok": (
                check_local_smoke(local_smoke, "unsupported_no_missing_symbols", "unsupported_destroy_result")
                and official_check(official, "compare_unsupported")
                and official_check(official, "probe_unsupported_artifacts_match")
            ),
            "evidence": "unsupported probe covers inert cloud/service calls and official unsupported parity matches",
        },
        {
            "name": "full_compatibility_feature_parity",
            "ok": feature_parity.get("ok") is True and feature_parity.get("failed") == [],
            "evidence": "full_compatibility_feature_parity gate for camera/source streaming, cloud/service parity, and non-FTPS tunnel parity",
        },
        {
            "name": "verification_artifacts_are_clean_room_and_actionable",
            "ok": (
                official.get("artifact_policy", {}).get("ok") is True
                and artifact_policy_ok(official)
                and official_check(official, "not_self_compare")
                and official_check(official, "official_network_differs_from_candidate")
                and official_check(official, "official_source_differs_from_candidate")
                and source_control_tls_loopback_ok(source_control_tls)
            ),
            "evidence": "official parity artifact policy, no binary artifact findings, distinct official/candidate hashes, and supplemental TLS loopback artifacts are redacted when present",
        },
        {
            "name": "single_release_readiness_artifact_is_complete",
            "ok": report.get("ok") is True and report.get("blockers") == [],
            "evidence": "release_readiness_report.json ok=true with no blockers",
        },
    ]


def validate_completion_audit(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "path": str(path), "failed": ["report_exists"]}
    try:
        report = load_report(path)
    except (json.JSONDecodeError, RuntimeError) as error:
        return {"ok": False, "path": str(path), "failed": ["report_json"], "reason": str(error)}

    if report.get("target") == "macos_native":
        checklist = native_completion_checklist(report)
    else:
        checklist = completion_checklist(report)
    failed = [item["name"] for item in checklist if item.get("ok") is not True]
    return {
        "ok": not failed,
        "path": str(path),
        "failed": failed,
        "checklist": checklist,
        "blockers": report.get("blockers", []),
        "target": report.get("target"),
    }


def allow_incomplete_result(result: dict[str, Any]) -> bool:
    if result.get("ok") is True:
        return True
    if result.get("target") is None:
        return False
    if result.get("target") != "macos_native":
        return True
    failed = result.get("failed", [])
    if not isinstance(failed, list):
        return False
    return set(failed).issubset(NATIVE_ALLOWED_INCOMPLETE_FAILURES)


def native_completion_checklist(report: dict[str, Any]) -> list[dict[str, Any]]:
    gates = report.get("gates", {})
    gates = gates if isinstance(gates, dict) else {}
    completion = report.get("completion_criteria", {})
    completion = completion if isinstance(completion, dict) else {}
    official = gates.get("official_parity", {})
    official = official if isinstance(official, dict) else {}
    source_rtsp_loopback = gates.get("source_rtsp_loopback_parity", {})
    source_rtsp_loopback = source_rtsp_loopback if isinstance(source_rtsp_loopback, dict) else {}
    source_control_tls_loopback = gates.get("source_control_tls_loopback_parity", {})
    source_control_tls_loopback = source_control_tls_loopback if isinstance(source_control_tls_loopback, dict) else {}
    real_printer = gates.get("real_printer_parity", {})
    real_printer = real_printer if isinstance(real_printer, dict) else {}
    cloud_service = gates.get("cloud_service_parity", {})
    cloud_service = cloud_service if isinstance(cloud_service, dict) else {}
    native_packaging = gates.get("native_packaging", {})
    native_packaging = native_packaging if isinstance(native_packaging, dict) else {}
    cloud_service_evidence_ok = (
        cloud_service.get("authorized_cloud_ok") is True
        and all_expected_true_mapping(cloud_service, "raw_authorized_checks", EXPECTED_NATIVE_CLOUD_AUTHORIZED_RAW_CHECKS)
    ) or (
        cloud_service.get("approved_scope_out") is True
        and cloud_service.get("safe_failure_ok") is True
        and cloud_safe_failure_evidence_ok(cloud_service)
    )
    real_printer_live_evidence_ok = (
        real_printer.get("ok") is True
        and real_printer.get("missing_inputs", []) == []
        and all_expected_true_mapping(real_printer, "raw_checks", EXPECTED_NATIVE_REAL_PRINTER_RAW_CHECKS)
    )
    real_printer_deferred_evidence_ok = (
        real_printer.get("ok") is True
        and real_printer.get("manual_testing_deferred") is True
        and isinstance(real_printer.get("missing_inputs"), list)
        and non_empty_list(real_printer, "needed_action")
        and all_true_mapping(real_printer, "dry_run_validators")
        and dry_run_evidence_ok(real_printer)
        and real_printer_missing_inputs_match_dry_run(real_printer)
        and real_printer.get("test_3mf_available") is True
    )
    real_printer_evidence_ok = real_printer_live_evidence_ok or real_printer_deferred_evidence_ok
    real_printer_blocker_actionable = real_printer.get("ok") is True or (
        non_empty_list(real_printer, "missing_inputs") and non_empty_list(real_printer, "needed_action")
        and all_true_mapping(real_printer, "dry_run_validators")
        and dry_run_evidence_ok(real_printer)
        and real_printer_missing_inputs_match_dry_run(real_printer)
    )
    cloud_service_blocker_actionable = cloud_service.get("ok") is True or (
        non_empty_list(cloud_service, "missing_inputs") and non_empty_list(cloud_service, "needed_action")
        and all_true_mapping(cloud_service, "dry_run_validators")
        and dry_run_evidence_ok(cloud_service)
        and cloud_missing_inputs_match_dry_run(cloud_service)
    )
    blocked_actions_actionable = actionable_blocked_actions(
        report,
        ("official_parity", "real_printer_parity", "cloud_service_parity"),
        decision_gate_names=("cloud_service_parity",),
    )
    required_gate_blockers_ok = required_gate_blockers_listed(report)
    false_completion_criteria_blockers_ok = false_completion_criteria_blockers_listed(report)
    top_level_blockers_ok = top_level_blockers_match_unresolved_state(report)
    report_ok_consistent = report_ok_matches_blockers(report)
    return [
        {
            "name": "native_macos_plugin_verification_passes",
            "ok": (
                gates.get("macos_native_plugin", {}).get("ok") is True
                and gates.get("native_loader_routing", {}).get("ok") is True
                and gates.get("native_gui_startup", {}).get("ok") is True
            ),
            "evidence": "macos_native_plugin, native_loader_routing, and native_gui_startup gates validate Mach-O dylibs, dlopen/dlsym, ABI mirror, C++ signatures, bridge/Linux rejection checks, Orca loader routing, and full app startup logs",
        },
        {
            "name": "local_candidate_smoke_passes",
            "ok": gates.get("local_candidate_smoke", {}).get("ok") is True,
            "evidence": "local_candidate_smoke gate validates the native candidate smoke summary used as local readiness evidence",
        },
        {
            "name": "official_native_parity_passes",
            "ok": (
                official.get("ok") is True
                and official.get("missing_or_stale_inputs", []) == []
                and source_rtsp_loopback.get("ok") is True
                and source_control_tls_loopback.get("ok") is True
            ),
            "evidence": "official_parity plus source_rtsp_loopback_parity and source_control_tls_loopback_parity gates compare current official macOS dylibs outside the repo against current candidate native dylibs and reject missing or stale local/offline inputs",
        },
        {
            "name": "clean_room_artifact_verification_passes",
            "ok": gates.get("clean_room_artifacts", {}).get("ok") is True,
            "evidence": "clean_room_artifacts gate runs verify_clean_room_artifacts.py on native parity artifacts",
        },
        {
            "name": "real_printer_native_parity_passes",
            "ok": real_printer_evidence_ok,
            "evidence": "real_printer_parity gate requires native printer workflow evidence, or an explicit contract deferral with actionable dry-run evidence when manual printer testing is the only remaining gap",
        },
        {
            "name": "real_printer_blocker_is_actionable_when_incomplete",
            "ok": real_printer_blocker_actionable,
            "evidence": "incomplete real_printer_parity gate must name missing live-printer inputs matching the loaded dry-run report, needed actions, passing dry-run validators, and a loaded dry-run report",
        },
        {
            "name": "cloud_service_native_parity_or_approved_scope_out",
            "ok": cloud_service.get("ok") is True and cloud_service_evidence_ok and cloud_service.get("missing_inputs", []) == [],
            "evidence": "cloud_service_parity gate requires authorized cloud/service success evidence or an approved scope-out with concrete safe-failure checks and no missing cloud inputs",
        },
        {
            "name": "cloud_service_blocker_is_actionable_when_incomplete",
            "ok": cloud_service_blocker_actionable,
            "evidence": "incomplete cloud_service_parity gate must name missing authorized cloud inputs matching the loaded dry-run report, needed actions, passing dry-run validators, and a loaded dry-run report",
        },
        {
            "name": "blocked_actions_summary_is_actionable_when_incomplete",
            "ok": blocked_actions_actionable,
            "evidence": "incomplete native readiness reports must carry exact top-level blocked_actions entries with missing inputs and needed actions for unresolved official, printer, and cloud gates, with no stale or duplicate actions",
        },
        {
            "name": "required_gate_blockers_are_listed",
            "ok": required_gate_blockers_ok,
            "evidence": "native readiness reports must list every unresolved required gate in the top-level blockers array",
        },
        {
            "name": "false_completion_criteria_blockers_are_listed",
            "ok": false_completion_criteria_blockers_ok,
            "evidence": "native readiness reports must list every false completion criterion as a completion_criteria entry in the top-level blockers array",
        },
        {
            "name": "top_level_blockers_match_unresolved_state",
            "ok": top_level_blockers_ok,
            "evidence": "native readiness reports must not include stale, duplicate, or unrelated top-level blockers beyond unresolved required gates and false completion criteria",
        },
        {
            "name": "report_ok_matches_blockers",
            "ok": report_ok_consistent,
            "evidence": "native readiness report ok must be true exactly when the top-level blockers array is empty",
        },
        {
            "name": "bridge_fallback_and_native_packaging_preserved",
            "ok": (
                gates.get("bridge_fallback_preserved", {}).get("ok") is True
                and native_packaging.get("ok") is True
                and native_packaging.get("rejected_files", []) == []
                and native_packaging.get("package_root_rejected_files", []) == []
            ),
            "evidence": "bridge_fallback_preserved and native_packaging gates cover opt-in native mode, verified native dylib staging, and absence of bridge/Linux/Lima package artifacts",
        },
        {
            "name": "native_completion_criteria_shape_is_complete",
            "ok": native_completion_criteria_shape_ok(completion),
            "evidence": "completion_criteria object in the native readiness report contains every expected native criterion and no unexpected criteria",
        },
        {
            "name": "all_native_completion_criteria_are_true",
            "ok": native_completion_criteria_complete(completion),
            "evidence": "completion_criteria object in the native readiness report contains every expected native criterion and every value is true",
        },
        {
            "name": "single_native_readiness_artifact_is_complete",
            "ok": report.get("ok") is True and report.get("blockers") == [],
            "evidence": "release_readiness_report.json target=macos_native ok=true with no blockers",
        },
    ]


def write_json(path: pathlib.Path, payload: dict[str, Any]) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def complete_fixture(work: pathlib.Path) -> pathlib.Path:
    artifact_policy = write_json(
        work / "artifact_policy.json",
        {
            "ok": True,
            "binary_artifacts": [],
            "official_binary_copy_findings": [],
            "official_inputs": ["/tmp/official/libbambu_networking.dylib"],
        },
    )
    report = {
        "ok": True,
        "blockers": [],
        "gates": {
            "local_candidate_smoke": {
                "ok": True,
                "required": True,
                "summary_validation": {
                    "ok": True,
                    "checks": {
                        "check_preflight_python_sources_compile": True,
                        "check_preflight_clean_room_artifact_validation": True,
                        "check_network_symbols": True,
                        "check_source_symbols": True,
                        "check_preflight_symbol_manifest_sources": True,
                        "check_preflight_abi_mirror": True,
                        "check_preflight_cpp_signature_mirror": True,
                        "check_preflight_contract_surface_coverage": True,
                        "check_lifecycle_agent_created": True,
                        "check_lifecycle_destroy_result": True,
                        "check_callback_agent_created": True,
                        "check_callback_transcripts_match": True,
                        "check_unsupported_no_missing_symbols": True,
                        "check_unsupported_destroy_result": True,
                    },
                },
            },
            "official_parity": {
                "ok": True,
                "required": True,
                "real_printer_workflows_ok": True,
                "artifact_policy": {"ok": True, "stdout": str(artifact_policy)},
                "checks": {
                    "compare_network_symbols": True,
                    "compare_source_symbols": True,
                    "compare_lifecycle": True,
                    "compare_callback": True,
                    "compare_unsupported": True,
                    "probe_unsupported_artifacts_match": True,
                    "not_self_compare": True,
                    "official_network_differs_from_candidate": True,
                    "official_source_differs_from_candidate": True,
                },
            },
            "real_printer_parity_inputs": {"ok": True, "required": True},
            "full_compatibility_feature_parity": {"ok": True, "required": True, "failed": []},
            "linux_bridge_payload": {
                "ok": True,
                "required": True,
                "linux_runtime_report": {
                    "checks": {
                        "abi0_network_loaded": True,
                        "abi1_network_loaded": True,
                        "abi0_source_loaded": True,
                        "abi1_source_loaded": True,
                    },
                },
            },
            "linux_direct_libstdcxx_load": {
                "ok": True,
                "required": True,
                "checks": {
                    "network_exports": True,
                    "source_exports": True,
                    "network_cxx_abi": True,
                    "source_cxx_abi": True,
                    "network_dlopen": True,
                    "source_dlopen": True,
                },
            },
            "macos_bridge_runtime": {"ok": True, "required": True},
        },
    }
    return write_json(work / "complete_report.json", report)


def native_complete_fixture(work: pathlib.Path) -> pathlib.Path:
    report = {
        "target": "macos_native",
        "ok": True,
        "blockers": [],
        "blocked_actions": [],
        "completion_criteria": {
            "native_macos_mode_loads_native_network_and_source_dylibs_directly": True,
            "native_macos_mode_does_not_require_or_launch_bridge_components": True,
            "bridge_fallback_remains_available": True,
            "native_macos_package_staging_path_can_run_without_lima_or_linux_runtime": True,
            "native_macos_plugin_verification_passes": True,
            "native_macos_gui_startup_smoke_passes": True,
            "local_candidate_smoke_passes": True,
            "native_official_vs_candidate_parity_passes_for_required_local_offline_behavior": True,
            "native_real_printer_parity_completed": True,
            "cloud_service_parity_completed_or_approved_scope_out": True,
            "clean_room_artifact_verification_passes": True,
            "final_readiness_ok": True,
        },
        "gates": {
            "macos_native_plugin": {"ok": True, "required": True},
            "native_loader_routing": {"ok": True, "required": True},
            "native_gui_startup": {"ok": True, "required": True},
            "local_candidate_smoke": {"ok": True, "required": True},
            "official_parity": {"ok": True, "required": True},
            "source_rtsp_loopback_parity": {"ok": True, "required": True},
            "source_control_tls_loopback_parity": {"ok": True, "required": True},
            "clean_room_artifacts": {"ok": True, "required": True},
            "real_printer_parity": {
                "ok": True,
                "required": True,
                "missing_inputs": [],
                "raw_checks": {
                    "report_ok": True,
                    "printer_workflow": True,
                    "print_job_upload_only": True,
                    "print_job_local_print": True,
                    "print_job_sdcard_print": True,
                    "source_streaming": True,
                    "source_control_tunnel": True,
                },
            },
            "cloud_service_parity": {
                "ok": True,
                "required": True,
                "authorized_cloud_ok": True,
                "raw_authorized_checks": {
                    "probe_ok": True,
                    "comparison_ok": True,
                    "official_authorized_success": True,
                    "candidate_authorized_success": True,
                },
                "missing_inputs": [],
            },
            "bridge_fallback_preserved": {"ok": True, "required": True},
            "native_packaging": {"ok": True, "required": True, "rejected_files": [], "package_root_rejected_files": []},
        },
    }
    return write_json(work / "native_complete_report.json", report)


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="bambu-completion-audit-") as tmp:
        work = pathlib.Path(tmp)
        complete = validate_completion_audit(complete_fixture(work))
        if not complete["ok"]:
            raise RuntimeError(f"complete fixture was rejected: {complete}")

        missing_report = validate_completion_audit(work / "missing_report.json")
        if missing_report["ok"] or allow_incomplete_result(missing_report):
            raise RuntimeError(f"missing report fixture was allowed: {missing_report}")

        invalid_report_path = write_json(work / "invalid_report.json", [])
        invalid_report = validate_completion_audit(invalid_report_path)
        if invalid_report["ok"] or allow_incomplete_result(invalid_report):
            raise RuntimeError(f"invalid report fixture was allowed: {invalid_report}")

        incomplete_path = complete_fixture(work / "incomplete")
        incomplete = load_report(incomplete_path)
        incomplete["ok"] = False
        incomplete["blockers"] = ["real_printer_parity_inputs"]
        incomplete["gates"]["real_printer_parity_inputs"]["ok"] = False
        write_json(incomplete_path, incomplete)
        result = validate_completion_audit(incomplete_path)
        if result["ok"] or "implemented_lan_and_printer_workflows_match_official" not in result["failed"]:
            raise RuntimeError(f"incomplete printer fixture was accepted: {result}")

        nested_report_path = complete_fixture(work / "nested")
        nested_report = load_report(nested_report_path)
        official = nested_report["gates"]["official_parity"]
        official["parity_report_validation"] = {
            "checks": official.pop("checks"),
            "real_printer_workflows_ok": official.pop("real_printer_workflows_ok"),
        }
        write_json(nested_report_path, nested_report)
        result = validate_completion_audit(nested_report_path)
        if not result["ok"]:
            raise RuntimeError(f"nested generated-report fixture was rejected: {result}")

        weak_artifacts_path = complete_fixture(work / "weak_artifacts")
        weak_artifacts = load_report(weak_artifacts_path)
        artifact_path = pathlib.Path(weak_artifacts["gates"]["official_parity"]["artifact_policy"]["stdout"])
        write_json(artifact_path, {"ok": True, "binary_artifacts": [], "official_binary_copy_findings": [], "official_inputs": []})
        result = validate_completion_audit(weak_artifacts_path)
        if result["ok"] or "verification_artifacts_are_clean_room_and_actionable" not in result["failed"]:
            raise RuntimeError(f"weak artifact fixture was accepted: {result}")

        weak_source_tls_path = complete_fixture(work / "weak_source_tls")
        weak_source_tls = load_report(weak_source_tls_path)
        weak_source_tls["gates"]["source_control_tls_loopback_parity_report"] = {
            "ok": True,
            "required": False,
            "failed": [],
            "source_control_tls_loopback_parity_ok": True,
            "checks": {
                "does_not_copy_binaries": True,
                "passwords_redacted": True,
                "official_source_differs_from_candidate": True,
                "candidate_source_hash_matches_current_build": True,
                "contracts_match": False,
                "artifacts_keep_secret_out": True,
                "artifacts_use_redacted_url": True,
            },
        }
        write_json(weak_source_tls_path, weak_source_tls)
        result = validate_completion_audit(weak_source_tls_path)
        if result["ok"] or "verification_artifacts_are_clean_room_and_actionable" not in result["failed"]:
            raise RuntimeError(f"weak source-control TLS fixture was accepted: {result}")

        native_complete_path = native_complete_fixture(work / "native_complete")
        native_complete = validate_completion_audit(native_complete_path)
        if not native_complete["ok"]:
            raise RuntimeError(f"native complete fixture was rejected: {native_complete}")

        deferred_printer_complete_path = native_complete_fixture(work / "native_deferred_printer_complete")
        deferred_printer_complete = load_report(deferred_printer_complete_path)
        deferred_printer_dry_run = write_json(
            work / "native_deferred_printer_complete/real_printer_dry_run_missing_inputs.json",
            {
                "ok": True,
                "dry_run": True,
                "printer": {
                    "dev_id_present": False,
                    "dev_ip_present": False,
                    "password_env": "BAMBU_NETWORK_PRINTER_PASSWORD",
                    "password_present": False,
                },
            },
        )
        deferred_printer_complete["gates"]["real_printer_parity"] = {
            "ok": True,
            "required": True,
            "manual_testing_deferred": True,
            "missing_inputs": [
                "printer dev id",
                "printer IP",
                "BAMBU_NETWORK_PRINTER_PASSWORD",
            ],
            "needed_action": [
                "provide printer dev id",
                "provide printer IP",
                "set printer password/access-code env",
                "run run_real_printer_parity.py with --macos-native-readiness, --include-source-streaming, --include-source-control-tunnel, and --confirm-start-prints",
            ],
            "dry_run_validators": {
                "real_printer_wrapper": True,
                "source_streaming_wrapper": True,
                "source_control_tunnel_wrapper": True,
            },
            "dry_run_report": str(deferred_printer_dry_run),
            "dry_run_loaded": True,
            "test_3mf_available": True,
        }
        write_json(deferred_printer_complete_path, deferred_printer_complete)
        result = validate_completion_audit(deferred_printer_complete_path)
        if not result["ok"]:
            raise RuntimeError(f"native deferred-printer complete fixture was rejected: {result}")

        deferred_printer_cloud_missing_path = native_complete_fixture(work / "native_deferred_printer_cloud_missing")
        deferred_printer_cloud_missing = load_report(deferred_printer_cloud_missing_path)
        deferred_printer_cloud_missing["ok"] = False
        deferred_printer_cloud_missing["blockers"] = [
            "cloud_service_parity",
            "completion_criteria:cloud_service_parity_completed_or_approved_scope_out",
            "completion_criteria:final_readiness_ok",
        ]
        deferred_printer_cloud_missing["gates"]["real_printer_parity"] = dict(
            deferred_printer_complete["gates"]["real_printer_parity"]
        )
        deferred_printer_cloud_missing["gates"]["cloud_service_parity"]["ok"] = False
        deferred_printer_cloud_missing["gates"]["cloud_service_parity"].pop("authorized_cloud_ok", None)
        deferred_printer_cloud_missing["gates"]["cloud_service_parity"]["missing_inputs"] = ["authorized cloud login context"]
        deferred_printer_cloud_missing["gates"]["cloud_service_parity"]["needed_action"] = ["provide authorized cloud login context"]
        deferred_printer_cloud_missing["gates"]["cloud_service_parity"][
            "needed_decision"
        ] = "provide authorized cloud parity inputs or approve a cloud/service scope-out with concrete safe-failure checks"
        deferred_printer_cloud_missing["gates"]["cloud_service_parity"]["dry_run_validators"] = {
            "authorized_cloud_wrapper": True,
        }
        deferred_cloud_dry_run = write_json(
            work / "native_deferred_printer_cloud_missing/authorized_cloud_dry_run_missing_inputs.json",
            {
                "ok": True,
                "dry_run": True,
                "cloud": {
                    "user_info_file_present": False,
                    "user_info_env": "authorized cloud login context",
                    "user_info_env_present": False,
                },
            },
        )
        deferred_printer_cloud_missing["gates"]["cloud_service_parity"]["dry_run_report"] = str(deferred_cloud_dry_run)
        deferred_printer_cloud_missing["gates"]["cloud_service_parity"]["dry_run_loaded"] = True
        deferred_printer_cloud_missing["blocked_actions"] = [
            {
                "gate": "cloud_service_parity",
                "missing_inputs": ["authorized cloud login context"],
                "needed_action": ["provide authorized cloud login context"],
                "needed_decision": deferred_printer_cloud_missing["gates"]["cloud_service_parity"]["needed_decision"],
            }
        ]
        deferred_printer_cloud_missing["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        deferred_printer_cloud_missing["completion_criteria"]["final_readiness_ok"] = False
        write_json(deferred_printer_cloud_missing_path, deferred_printer_cloud_missing)
        result = validate_completion_audit(deferred_printer_cloud_missing_path)
        if result["ok"] or "cloud_service_native_parity_or_approved_scope_out" not in result["failed"]:
            raise RuntimeError(f"native deferred-printer missing-cloud fixture was accepted: {result}")

        missing_loader_path = native_complete_fixture(work / "native_missing_loader")
        missing_loader = load_report(missing_loader_path)
        missing_loader["gates"]["native_loader_routing"]["ok"] = False
        missing_loader["completion_criteria"]["native_macos_mode_loads_native_network_and_source_dylibs_directly"] = False
        write_json(missing_loader_path, missing_loader)
        result = validate_completion_audit(missing_loader_path)
        if result["ok"] or "native_macos_plugin_verification_passes" not in result["failed"]:
            raise RuntimeError(f"native missing-loader fixture was accepted: {result}")

        missing_gui_startup_path = native_complete_fixture(work / "native_missing_gui_startup")
        missing_gui_startup = load_report(missing_gui_startup_path)
        missing_gui_startup["gates"]["native_gui_startup"]["ok"] = False
        missing_gui_startup["completion_criteria"]["native_macos_mode_does_not_require_or_launch_bridge_components"] = False
        missing_gui_startup["completion_criteria"]["native_macos_gui_startup_smoke_passes"] = False
        write_json(missing_gui_startup_path, missing_gui_startup)
        result = validate_completion_audit(missing_gui_startup_path)
        if result["ok"] or "native_macos_plugin_verification_passes" not in result["failed"]:
            raise RuntimeError(f"native missing-GUI-startup fixture was accepted: {result}")

        missing_clean_room_path = native_complete_fixture(work / "native_missing_clean_room")
        missing_clean_room = load_report(missing_clean_room_path)
        missing_clean_room["gates"]["clean_room_artifacts"]["ok"] = False
        missing_clean_room["completion_criteria"]["clean_room_artifact_verification_passes"] = False
        write_json(missing_clean_room_path, missing_clean_room)
        result = validate_completion_audit(missing_clean_room_path)
        if result["ok"] or "clean_room_artifact_verification_passes" not in result["failed"]:
            raise RuntimeError(f"native missing-clean-room fixture was accepted: {result}")

        missing_completion_key_path = native_complete_fixture(work / "native_missing_completion_key")
        missing_completion_key = load_report(missing_completion_key_path)
        missing_completion_key["completion_criteria"].pop("native_macos_gui_startup_smoke_passes")
        write_json(missing_completion_key_path, missing_completion_key)
        result = validate_completion_audit(missing_completion_key_path)
        if (
            result["ok"]
            or "native_completion_criteria_shape_is_complete" not in result["failed"]
            or "all_native_completion_criteria_are_true" not in result["failed"]
        ):
            raise RuntimeError(f"native missing-completion-key fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native missing-completion-key fixture was allowed as incomplete: {result}")

        stale_official_path = native_complete_fixture(work / "native_stale_official")
        stale_official = load_report(stale_official_path)
        stale_official["gates"]["official_parity"]["missing_or_stale_inputs"] = ["official_network"]
        write_json(stale_official_path, stale_official)
        result = validate_completion_audit(stale_official_path)
        if result["ok"] or "official_native_parity_passes" not in result["failed"]:
            raise RuntimeError(f"native stale-official fixture was accepted: {result}")

        missing_real_printer_inputs_path = native_complete_fixture(work / "native_missing_real_printer_inputs")
        missing_real_printer_inputs = load_report(missing_real_printer_inputs_path)
        missing_real_printer_inputs["gates"]["real_printer_parity"]["missing_inputs"] = ["printer IP"]
        write_json(missing_real_printer_inputs_path, missing_real_printer_inputs)
        result = validate_completion_audit(missing_real_printer_inputs_path)
        if result["ok"] or "real_printer_native_parity_passes" not in result["failed"]:
            raise RuntimeError(f"native missing-real-printer-inputs fixture was accepted: {result}")

        summary_only_real_printer_path = native_complete_fixture(work / "native_summary_only_real_printer")
        summary_only_real_printer = load_report(summary_only_real_printer_path)
        summary_only_real_printer["gates"]["real_printer_parity"].pop("raw_checks", None)
        write_json(summary_only_real_printer_path, summary_only_real_printer)
        result = validate_completion_audit(summary_only_real_printer_path)
        if result["ok"] or "real_printer_native_parity_passes" not in result["failed"]:
            raise RuntimeError(f"native summary-only-real-printer fixture was accepted: {result}")

        partial_real_printer_raw_checks_path = native_complete_fixture(work / "native_partial_real_printer_raw_checks")
        partial_real_printer_raw_checks = load_report(partial_real_printer_raw_checks_path)
        partial_real_printer_raw_checks["gates"]["real_printer_parity"]["raw_checks"] = {
            "report_ok": True,
        }
        write_json(partial_real_printer_raw_checks_path, partial_real_printer_raw_checks)
        result = validate_completion_audit(partial_real_printer_raw_checks_path)
        if result["ok"] or "real_printer_native_parity_passes" not in result["failed"]:
            raise RuntimeError(f"native partial-real-printer-raw-checks fixture was accepted: {result}")

        missing_real_printer_action_path = native_complete_fixture(work / "native_missing_real_printer_action")
        missing_real_printer_action = load_report(missing_real_printer_action_path)
        missing_real_printer_action["ok"] = False
        missing_real_printer_action["blockers"] = ["real_printer_parity"]
        missing_real_printer_action["gates"]["real_printer_parity"]["ok"] = False
        missing_real_printer_action["gates"]["real_printer_parity"]["missing_inputs"] = ["printer IP"]
        missing_real_printer_action["blocked_actions"] = [
            {"gate": "real_printer_parity", "missing_inputs": ["printer IP"]}
        ]
        missing_real_printer_action["completion_criteria"]["native_real_printer_parity_completed"] = False
        missing_real_printer_action["completion_criteria"]["final_readiness_ok"] = False
        write_json(missing_real_printer_action_path, missing_real_printer_action)
        result = validate_completion_audit(missing_real_printer_action_path)
        if result["ok"] or "real_printer_blocker_is_actionable_when_incomplete" not in result["failed"]:
            raise RuntimeError(f"native missing-real-printer-action fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native missing-real-printer-action fixture was allowed as incomplete: {result}")

        weak_cloud_path = native_complete_fixture(work / "native_weak_cloud")
        weak_cloud = load_report(weak_cloud_path)
        weak_cloud["gates"]["cloud_service_parity"].pop("authorized_cloud_ok", None)
        write_json(weak_cloud_path, weak_cloud)
        result = validate_completion_audit(weak_cloud_path)
        if result["ok"] or "cloud_service_native_parity_or_approved_scope_out" not in result["failed"]:
            raise RuntimeError(f"native weak-cloud fixture was accepted: {result}")

        summary_only_cloud_path = native_complete_fixture(work / "native_summary_only_cloud")
        summary_only_cloud = load_report(summary_only_cloud_path)
        summary_only_cloud["gates"]["cloud_service_parity"].pop("raw_authorized_checks", None)
        write_json(summary_only_cloud_path, summary_only_cloud)
        result = validate_completion_audit(summary_only_cloud_path)
        if result["ok"] or "cloud_service_native_parity_or_approved_scope_out" not in result["failed"]:
            raise RuntimeError(f"native summary-only-cloud fixture was accepted: {result}")

        partial_cloud_raw_checks_path = native_complete_fixture(work / "native_partial_cloud_raw_checks")
        partial_cloud_raw_checks = load_report(partial_cloud_raw_checks_path)
        partial_cloud_raw_checks["gates"]["cloud_service_parity"]["raw_authorized_checks"] = {
            "probe_ok": True,
        }
        write_json(partial_cloud_raw_checks_path, partial_cloud_raw_checks)
        result = validate_completion_audit(partial_cloud_raw_checks_path)
        if result["ok"] or "cloud_service_native_parity_or_approved_scope_out" not in result["failed"]:
            raise RuntimeError(f"native partial-cloud-raw-checks fixture was accepted: {result}")

        scoped_cloud_path = native_complete_fixture(work / "native_scoped_cloud")
        scoped_cloud = load_report(scoped_cloud_path)
        scoped_cloud["gates"]["cloud_service_parity"] = {
            "ok": True,
            "required": True,
            "approved_scope_out": True,
            "safe_failure_ok": True,
            "safe_failure_checks": {
                "report_ok": True,
                "compare_unsupported": True,
                "probe_unsupported_artifacts_match": True,
                "unsupported_probe_ok": False,
                "unsupported_comparison_ok": False,
            },
            "missing_inputs": [],
        }
        write_json(scoped_cloud_path, scoped_cloud)
        result = validate_completion_audit(scoped_cloud_path)
        if not result["ok"]:
            raise RuntimeError(f"native scoped-cloud fixture was rejected: {result}")

        weak_scoped_cloud_path = native_complete_fixture(work / "native_weak_scoped_cloud")
        weak_scoped_cloud = load_report(weak_scoped_cloud_path)
        weak_scoped_cloud["gates"]["cloud_service_parity"] = {
            "ok": True,
            "required": True,
            "approved_scope_out": True,
            "safe_failure_ok": True,
            "missing_inputs": [],
        }
        write_json(weak_scoped_cloud_path, weak_scoped_cloud)
        result = validate_completion_audit(weak_scoped_cloud_path)
        if result["ok"] or "cloud_service_native_parity_or_approved_scope_out" not in result["failed"]:
            raise RuntimeError(f"native weak-scoped-cloud fixture was accepted: {result}")

        missing_cloud_action_path = native_complete_fixture(work / "native_missing_cloud_action")
        missing_cloud_action = load_report(missing_cloud_action_path)
        missing_cloud_action["ok"] = False
        missing_cloud_action["blockers"] = ["cloud_service_parity"]
        missing_cloud_action["gates"]["cloud_service_parity"]["ok"] = False
        missing_cloud_action["gates"]["cloud_service_parity"].pop("authorized_cloud_ok", None)
        missing_cloud_action["gates"]["cloud_service_parity"]["missing_inputs"] = ["authorized cloud login context"]
        missing_cloud_action["blocked_actions"] = [
            {"gate": "cloud_service_parity", "missing_inputs": ["authorized cloud login context"]}
        ]
        missing_cloud_action["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        missing_cloud_action["completion_criteria"]["final_readiness_ok"] = False
        write_json(missing_cloud_action_path, missing_cloud_action)
        result = validate_completion_audit(missing_cloud_action_path)
        if result["ok"] or "cloud_service_blocker_is_actionable_when_incomplete" not in result["failed"]:
            raise RuntimeError(f"native missing-cloud-action fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native missing-cloud-action fixture was allowed as incomplete: {result}")

        rejected_package_path = native_complete_fixture(work / "native_rejected_package")
        rejected_package = load_report(rejected_package_path)
        rejected_package["gates"]["native_packaging"]["package_root_rejected_files"] = ["pjarczak_lima_instance.txt"]
        write_json(rejected_package_path, rejected_package)
        result = validate_completion_audit(rejected_package_path)
        if result["ok"] or "bridge_fallback_and_native_packaging_preserved" not in result["failed"]:
            raise RuntimeError(f"native rejected-package fixture was accepted: {result}")

        missing_external_path = native_complete_fixture(work / "native_missing_external")
        missing_external = load_report(missing_external_path)
        missing_external["ok"] = False
        missing_external["blockers"] = ["official_parity", "real_printer_parity", "cloud_service_parity"]
        for gate_name in ("official_parity", "real_printer_parity", "cloud_service_parity"):
            missing_external["gates"][gate_name]["ok"] = False
        missing_external["completion_criteria"]["native_official_vs_candidate_parity_passes_for_required_local_offline_behavior"] = False
        missing_external["completion_criteria"]["native_real_printer_parity_completed"] = False
        missing_external["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        missing_external["completion_criteria"]["final_readiness_ok"] = False
        write_json(missing_external_path, missing_external)
        result = validate_completion_audit(missing_external_path)
        expected_native_failures = {
            "official_native_parity_passes",
            "real_printer_native_parity_passes",
            "cloud_service_native_parity_or_approved_scope_out",
            "all_native_completion_criteria_are_true",
            "single_native_readiness_artifact_is_complete",
        }
        if result["ok"] or not expected_native_failures.issubset(set(result["failed"])):
            raise RuntimeError(f"native missing-external fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native missing-external fixture was allowed as incomplete: {result}")

        allowed_incomplete_path = native_complete_fixture(work / "native_allowed_incomplete")
        allowed_incomplete = load_report(allowed_incomplete_path)
        real_printer_dry_run = write_json(
            work / "native_allowed_incomplete/real_printer_dry_run_missing_inputs.json",
            {
                "ok": True,
                "dry_run": True,
                "printer": {
                    "dev_id_present": True,
                    "dev_ip_present": False,
                    "password_env": "BAMBU_NETWORK_PRINTER_PASSWORD",
                    "password_present": True,
                },
            },
        )
        cloud_dry_run = write_json(
            work / "native_allowed_incomplete/authorized_cloud_dry_run_missing_inputs.json",
            {
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
            },
        )
        allowed_incomplete["ok"] = False
        allowed_incomplete["blockers"] = ["real_printer_parity", "cloud_service_parity"]
        allowed_incomplete["gates"]["real_printer_parity"]["ok"] = False
        allowed_incomplete["gates"]["real_printer_parity"]["missing_inputs"] = ["printer IP"]
        allowed_incomplete["gates"]["real_printer_parity"]["needed_action"] = ["provide printer IP"]
        allowed_incomplete["gates"]["real_printer_parity"]["dry_run_validators"] = {
            "real_printer_wrapper": True,
            "source_streaming_wrapper": True,
            "source_control_tunnel_wrapper": True,
        }
        allowed_incomplete["gates"]["real_printer_parity"]["dry_run_report"] = str(real_printer_dry_run)
        allowed_incomplete["gates"]["real_printer_parity"]["dry_run_loaded"] = True
        allowed_incomplete["gates"]["cloud_service_parity"]["ok"] = False
        allowed_incomplete["gates"]["cloud_service_parity"].pop("authorized_cloud_ok", None)
        allowed_incomplete["gates"]["cloud_service_parity"]["missing_inputs"] = [
            "BAMBU_CLOUD_LOGIN_INFO_JSON",
            "BAMBU_CLOUD_TICKET",
            "BAMBU_CLOUD_ACCESS_TOKEN",
        ]
        allowed_incomplete["gates"]["cloud_service_parity"]["needed_action"] = ["provide authorized cloud login context"]
        allowed_incomplete["gates"]["cloud_service_parity"][
            "needed_decision"
        ] = "provide authorized cloud parity inputs or approve a cloud/service scope-out with concrete safe-failure checks"
        allowed_incomplete["gates"]["cloud_service_parity"]["dry_run_validators"] = {
            "authorized_cloud_wrapper": True,
        }
        allowed_incomplete["gates"]["cloud_service_parity"]["dry_run_report"] = str(cloud_dry_run)
        allowed_incomplete["gates"]["cloud_service_parity"]["dry_run_loaded"] = True
        allowed_incomplete["blocked_actions"] = [
            {
                "gate": "cloud_service_parity",
                "missing_inputs": [
                    "BAMBU_CLOUD_LOGIN_INFO_JSON",
                    "BAMBU_CLOUD_TICKET",
                    "BAMBU_CLOUD_ACCESS_TOKEN",
                ],
                "needed_action": allowed_incomplete["gates"]["cloud_service_parity"]["needed_action"],
                "needed_decision": allowed_incomplete["gates"]["cloud_service_parity"]["needed_decision"],
            },
            {
                "gate": "real_printer_parity",
                "missing_inputs": ["printer IP"],
                "needed_action": allowed_incomplete["gates"]["real_printer_parity"]["needed_action"],
            },
        ]
        allowed_incomplete["completion_criteria"]["native_real_printer_parity_completed"] = False
        allowed_incomplete["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        allowed_incomplete["completion_criteria"]["final_readiness_ok"] = False
        allowed_incomplete["blockers"].extend([
            "completion_criteria:native_real_printer_parity_completed",
            "completion_criteria:cloud_service_parity_completed_or_approved_scope_out",
            "completion_criteria:final_readiness_ok",
        ])
        write_json(allowed_incomplete_path, allowed_incomplete)
        result = validate_completion_audit(allowed_incomplete_path)
        if result["ok"] or not allow_incomplete_result(result):
            raise RuntimeError(f"native allowed-incomplete fixture was rejected: {result}")

        missing_dry_run_validators_path = native_complete_fixture(work / "native_missing_dry_run_validators")
        missing_dry_run_validators = load_report(missing_dry_run_validators_path)
        missing_dry_run_validators["ok"] = False
        missing_dry_run_validators["blockers"] = ["real_printer_parity", "cloud_service_parity"]
        missing_dry_run_validators["gates"]["real_printer_parity"]["ok"] = False
        missing_dry_run_validators["gates"]["real_printer_parity"]["missing_inputs"] = ["printer IP"]
        missing_dry_run_validators["gates"]["real_printer_parity"]["needed_action"] = ["provide printer IP"]
        missing_dry_run_validators["gates"]["cloud_service_parity"]["ok"] = False
        missing_dry_run_validators["gates"]["cloud_service_parity"].pop("authorized_cloud_ok", None)
        missing_dry_run_validators["gates"]["cloud_service_parity"]["missing_inputs"] = ["authorized cloud login context"]
        missing_dry_run_validators["gates"]["cloud_service_parity"]["needed_action"] = ["provide authorized cloud login context"]
        missing_dry_run_validators["blocked_actions"] = allowed_incomplete["blocked_actions"]
        missing_dry_run_validators["completion_criteria"]["native_real_printer_parity_completed"] = False
        missing_dry_run_validators["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        missing_dry_run_validators["completion_criteria"]["final_readiness_ok"] = False
        write_json(missing_dry_run_validators_path, missing_dry_run_validators)
        result = validate_completion_audit(missing_dry_run_validators_path)
        if (
            result["ok"]
            or "real_printer_blocker_is_actionable_when_incomplete" not in result["failed"]
            or "cloud_service_blocker_is_actionable_when_incomplete" not in result["failed"]
        ):
            raise RuntimeError(f"native missing-dry-run-validators fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native missing-dry-run-validators fixture was allowed as incomplete: {result}")

        missing_dry_run_report_path = native_complete_fixture(work / "native_missing_dry_run_report")
        missing_dry_run_report = load_report(missing_dry_run_report_path)
        missing_dry_run_report["ok"] = False
        missing_dry_run_report["blockers"] = ["real_printer_parity", "cloud_service_parity"]
        missing_dry_run_report["gates"]["real_printer_parity"] = dict(allowed_incomplete["gates"]["real_printer_parity"])
        missing_dry_run_report["gates"]["cloud_service_parity"] = dict(allowed_incomplete["gates"]["cloud_service_parity"])
        missing_dry_run_report["gates"]["real_printer_parity"].pop("dry_run_report", None)
        missing_dry_run_report["gates"]["cloud_service_parity"]["dry_run_loaded"] = False
        missing_dry_run_report["blocked_actions"] = allowed_incomplete["blocked_actions"]
        missing_dry_run_report["completion_criteria"]["native_real_printer_parity_completed"] = False
        missing_dry_run_report["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        missing_dry_run_report["completion_criteria"]["final_readiness_ok"] = False
        write_json(missing_dry_run_report_path, missing_dry_run_report)
        result = validate_completion_audit(missing_dry_run_report_path)
        if (
            result["ok"]
            or "real_printer_blocker_is_actionable_when_incomplete" not in result["failed"]
            or "cloud_service_blocker_is_actionable_when_incomplete" not in result["failed"]
        ):
            raise RuntimeError(f"native missing-dry-run-report fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native missing-dry-run-report fixture was allowed as incomplete: {result}")

        stale_dry_run_report_path = native_complete_fixture(work / "native_stale_dry_run_report")
        stale_dry_run_report = load_report(stale_dry_run_report_path)
        stale_dry_run_report["ok"] = False
        stale_dry_run_report["blockers"] = ["real_printer_parity", "cloud_service_parity"]
        stale_dry_run_report["gates"]["real_printer_parity"] = dict(allowed_incomplete["gates"]["real_printer_parity"])
        stale_dry_run_report["gates"]["cloud_service_parity"] = dict(allowed_incomplete["gates"]["cloud_service_parity"])
        stale_dry_run_report["gates"]["real_printer_parity"]["dry_run_report"] = str(work / "missing-real-printer-dry-run.json")
        stale_dry_run_report["gates"]["cloud_service_parity"]["dry_run_report"] = str(
            write_json(work / "native_stale_dry_run_report/not_a_dry_run.json", {"ok": True, "dry_run": False})
        )
        stale_dry_run_report["blocked_actions"] = allowed_incomplete["blocked_actions"]
        stale_dry_run_report["completion_criteria"]["native_real_printer_parity_completed"] = False
        stale_dry_run_report["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        stale_dry_run_report["completion_criteria"]["final_readiness_ok"] = False
        write_json(stale_dry_run_report_path, stale_dry_run_report)
        result = validate_completion_audit(stale_dry_run_report_path)
        if (
            result["ok"]
            or "real_printer_blocker_is_actionable_when_incomplete" not in result["failed"]
            or "cloud_service_blocker_is_actionable_when_incomplete" not in result["failed"]
        ):
            raise RuntimeError(f"native stale-dry-run-report fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native stale-dry-run-report fixture was allowed as incomplete: {result}")

        mismatched_missing_inputs_path = native_complete_fixture(work / "native_mismatched_missing_inputs")
        mismatched_missing_inputs = load_report(mismatched_missing_inputs_path)
        mismatched_missing_inputs["ok"] = False
        mismatched_missing_inputs["blockers"] = ["real_printer_parity", "cloud_service_parity"]
        mismatched_missing_inputs["gates"]["real_printer_parity"] = dict(allowed_incomplete["gates"]["real_printer_parity"])
        mismatched_missing_inputs["gates"]["cloud_service_parity"] = dict(allowed_incomplete["gates"]["cloud_service_parity"])
        mismatched_missing_inputs["gates"]["real_printer_parity"]["missing_inputs"] = ["printer dev id"]
        mismatched_missing_inputs["gates"]["cloud_service_parity"]["missing_inputs"] = ["BAMBU_CLOUD_TICKET"]
        mismatched_missing_inputs["blocked_actions"] = [
            {
                "gate": "cloud_service_parity",
                "missing_inputs": ["BAMBU_CLOUD_TICKET"],
                "needed_action": ["provide authorized cloud login context"],
                "needed_decision": "provide authorized cloud parity inputs or approve a cloud/service scope-out",
            },
            {
                "gate": "real_printer_parity",
                "missing_inputs": ["printer dev id"],
                "needed_action": ["provide printer IP"],
            },
        ]
        mismatched_missing_inputs["completion_criteria"]["native_real_printer_parity_completed"] = False
        mismatched_missing_inputs["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        mismatched_missing_inputs["completion_criteria"]["final_readiness_ok"] = False
        write_json(mismatched_missing_inputs_path, mismatched_missing_inputs)
        result = validate_completion_audit(mismatched_missing_inputs_path)
        if (
            result["ok"]
            or "real_printer_blocker_is_actionable_when_incomplete" not in result["failed"]
            or "cloud_service_blocker_is_actionable_when_incomplete" not in result["failed"]
        ):
            raise RuntimeError(f"native mismatched-missing-inputs fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native mismatched-missing-inputs fixture was allowed as incomplete: {result}")

        missing_blocked_actions_path = native_complete_fixture(work / "native_missing_blocked_actions")
        missing_blocked_actions = load_report(missing_blocked_actions_path)
        missing_blocked_actions["ok"] = False
        missing_blocked_actions["blockers"] = ["real_printer_parity", "cloud_service_parity"]
        missing_blocked_actions["blocked_actions"] = []
        missing_blocked_actions["gates"]["real_printer_parity"]["ok"] = False
        missing_blocked_actions["gates"]["real_printer_parity"]["missing_inputs"] = ["printer IP"]
        missing_blocked_actions["gates"]["real_printer_parity"]["needed_action"] = ["provide printer IP"]
        missing_blocked_actions["gates"]["cloud_service_parity"]["ok"] = False
        missing_blocked_actions["gates"]["cloud_service_parity"].pop("authorized_cloud_ok", None)
        missing_blocked_actions["gates"]["cloud_service_parity"]["missing_inputs"] = ["authorized cloud login context"]
        missing_blocked_actions["gates"]["cloud_service_parity"]["needed_action"] = ["provide authorized cloud login context"]
        missing_blocked_actions["completion_criteria"]["native_real_printer_parity_completed"] = False
        missing_blocked_actions["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        missing_blocked_actions["completion_criteria"]["final_readiness_ok"] = False
        write_json(missing_blocked_actions_path, missing_blocked_actions)
        result = validate_completion_audit(missing_blocked_actions_path)
        if result["ok"] or "blocked_actions_summary_is_actionable_when_incomplete" not in result["failed"]:
            raise RuntimeError(f"native missing-blocked-actions fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native missing-blocked-actions fixture was allowed as incomplete: {result}")

        mismatched_blocked_actions_path = native_complete_fixture(work / "native_mismatched_blocked_actions")
        mismatched_blocked_actions = load_report(mismatched_blocked_actions_path)
        mismatched_blocked_actions["ok"] = False
        mismatched_blocked_actions["blockers"] = ["real_printer_parity", "cloud_service_parity"]
        mismatched_blocked_actions["gates"]["real_printer_parity"] = dict(allowed_incomplete["gates"]["real_printer_parity"])
        mismatched_blocked_actions["gates"]["cloud_service_parity"] = dict(allowed_incomplete["gates"]["cloud_service_parity"])
        mismatched_blocked_actions["blocked_actions"] = [
            dict(allowed_incomplete["blocked_actions"][0]),
            dict(allowed_incomplete["blocked_actions"][1]),
        ]
        mismatched_blocked_actions["blocked_actions"][0]["missing_inputs"] = ["BAMBU_CLOUD_LOGIN_INFO_JSON"]
        mismatched_blocked_actions["blocked_actions"][1]["needed_action"] = ["provide printer IP"]
        mismatched_blocked_actions["completion_criteria"]["native_real_printer_parity_completed"] = False
        mismatched_blocked_actions["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        mismatched_blocked_actions["completion_criteria"]["final_readiness_ok"] = False
        write_json(mismatched_blocked_actions_path, mismatched_blocked_actions)
        result = validate_completion_audit(mismatched_blocked_actions_path)
        if result["ok"] or "blocked_actions_summary_is_actionable_when_incomplete" not in result["failed"]:
            raise RuntimeError(f"native mismatched-blocked-actions fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native mismatched-blocked-actions fixture was allowed as incomplete: {result}")

        stale_extra_blocked_action_path = native_complete_fixture(work / "native_stale_extra_blocked_action")
        stale_extra_blocked_action = load_report(stale_extra_blocked_action_path)
        stale_extra_blocked_action["ok"] = False
        stale_extra_blocked_action["blockers"] = ["real_printer_parity", "cloud_service_parity"]
        stale_extra_blocked_action["gates"]["real_printer_parity"] = dict(allowed_incomplete["gates"]["real_printer_parity"])
        stale_extra_blocked_action["gates"]["cloud_service_parity"] = dict(allowed_incomplete["gates"]["cloud_service_parity"])
        stale_extra_blocked_action["blocked_actions"] = [
            dict(allowed_incomplete["blocked_actions"][0]),
            dict(allowed_incomplete["blocked_actions"][1]),
            {
                "gate": "stale_gate",
                "missing_inputs": ["stale input"],
                "needed_action": ["remove stale blocked action"],
            },
        ]
        stale_extra_blocked_action["completion_criteria"]["native_real_printer_parity_completed"] = False
        stale_extra_blocked_action["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        stale_extra_blocked_action["completion_criteria"]["final_readiness_ok"] = False
        write_json(stale_extra_blocked_action_path, stale_extra_blocked_action)
        result = validate_completion_audit(stale_extra_blocked_action_path)
        if result["ok"] or "blocked_actions_summary_is_actionable_when_incomplete" not in result["failed"]:
            raise RuntimeError(f"native stale-extra-blocked-action fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native stale-extra-blocked-action fixture was allowed as incomplete: {result}")

        duplicate_blocked_action_path = native_complete_fixture(work / "native_duplicate_blocked_action")
        duplicate_blocked_action = load_report(duplicate_blocked_action_path)
        duplicate_blocked_action["ok"] = False
        duplicate_blocked_action["blockers"] = ["real_printer_parity", "cloud_service_parity"]
        duplicate_blocked_action["gates"]["real_printer_parity"] = dict(allowed_incomplete["gates"]["real_printer_parity"])
        duplicate_blocked_action["gates"]["cloud_service_parity"] = dict(allowed_incomplete["gates"]["cloud_service_parity"])
        duplicate_blocked_action["blocked_actions"] = [
            dict(allowed_incomplete["blocked_actions"][0]),
            dict(allowed_incomplete["blocked_actions"][1]),
            dict(allowed_incomplete["blocked_actions"][1]),
        ]
        duplicate_blocked_action["completion_criteria"]["native_real_printer_parity_completed"] = False
        duplicate_blocked_action["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        duplicate_blocked_action["completion_criteria"]["final_readiness_ok"] = False
        write_json(duplicate_blocked_action_path, duplicate_blocked_action)
        result = validate_completion_audit(duplicate_blocked_action_path)
        if result["ok"] or "blocked_actions_summary_is_actionable_when_incomplete" not in result["failed"]:
            raise RuntimeError(f"native duplicate-blocked-action fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native duplicate-blocked-action fixture was allowed as incomplete: {result}")

        missing_gate_blocker_path = native_complete_fixture(work / "native_missing_gate_blocker")
        missing_gate_blocker = load_report(missing_gate_blocker_path)
        missing_gate_blocker["ok"] = False
        missing_gate_blocker["blockers"] = [
            "completion_criteria:native_real_printer_parity_completed",
            "completion_criteria:cloud_service_parity_completed_or_approved_scope_out",
            "completion_criteria:final_readiness_ok",
        ]
        missing_gate_blocker["gates"]["real_printer_parity"] = dict(allowed_incomplete["gates"]["real_printer_parity"])
        missing_gate_blocker["gates"]["cloud_service_parity"] = dict(allowed_incomplete["gates"]["cloud_service_parity"])
        missing_gate_blocker["blocked_actions"] = allowed_incomplete["blocked_actions"]
        missing_gate_blocker["completion_criteria"]["native_real_printer_parity_completed"] = False
        missing_gate_blocker["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        missing_gate_blocker["completion_criteria"]["final_readiness_ok"] = False
        write_json(missing_gate_blocker_path, missing_gate_blocker)
        result = validate_completion_audit(missing_gate_blocker_path)
        if result["ok"] or "required_gate_blockers_are_listed" not in result["failed"]:
            raise RuntimeError(f"native missing-gate-blocker fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native missing-gate-blocker fixture was allowed as incomplete: {result}")

        missing_criteria_blocker_path = native_complete_fixture(work / "native_missing_criteria_blocker")
        missing_criteria_blocker = load_report(missing_criteria_blocker_path)
        missing_criteria_blocker["ok"] = False
        missing_criteria_blocker["blockers"] = ["real_printer_parity", "cloud_service_parity"]
        missing_criteria_blocker["gates"]["real_printer_parity"] = dict(allowed_incomplete["gates"]["real_printer_parity"])
        missing_criteria_blocker["gates"]["cloud_service_parity"] = dict(allowed_incomplete["gates"]["cloud_service_parity"])
        missing_criteria_blocker["blocked_actions"] = allowed_incomplete["blocked_actions"]
        missing_criteria_blocker["completion_criteria"]["native_real_printer_parity_completed"] = False
        missing_criteria_blocker["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        missing_criteria_blocker["completion_criteria"]["final_readiness_ok"] = False
        write_json(missing_criteria_blocker_path, missing_criteria_blocker)
        result = validate_completion_audit(missing_criteria_blocker_path)
        if result["ok"] or "false_completion_criteria_blockers_are_listed" not in result["failed"]:
            raise RuntimeError(f"native missing-criteria-blocker fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native missing-criteria-blocker fixture was allowed as incomplete: {result}")

        stale_extra_blocker_path = native_complete_fixture(work / "native_stale_extra_blocker")
        stale_extra_blocker = load_report(stale_extra_blocker_path)
        stale_extra_blocker["ok"] = False
        stale_extra_blocker["blockers"] = allowed_incomplete["blockers"] + ["stale_extra_blocker"]
        stale_extra_blocker["gates"]["real_printer_parity"] = dict(allowed_incomplete["gates"]["real_printer_parity"])
        stale_extra_blocker["gates"]["cloud_service_parity"] = dict(allowed_incomplete["gates"]["cloud_service_parity"])
        stale_extra_blocker["blocked_actions"] = allowed_incomplete["blocked_actions"]
        stale_extra_blocker["completion_criteria"]["native_real_printer_parity_completed"] = False
        stale_extra_blocker["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        stale_extra_blocker["completion_criteria"]["final_readiness_ok"] = False
        write_json(stale_extra_blocker_path, stale_extra_blocker)
        result = validate_completion_audit(stale_extra_blocker_path)
        if result["ok"] or "top_level_blockers_match_unresolved_state" not in result["failed"]:
            raise RuntimeError(f"native stale-extra-blocker fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native stale-extra-blocker fixture was allowed as incomplete: {result}")

        stale_ok_with_blockers_path = native_complete_fixture(work / "native_stale_ok_with_blockers")
        stale_ok_with_blockers = load_report(stale_ok_with_blockers_path)
        stale_ok_with_blockers["ok"] = True
        stale_ok_with_blockers["blockers"] = allowed_incomplete["blockers"]
        stale_ok_with_blockers["gates"]["real_printer_parity"] = dict(allowed_incomplete["gates"]["real_printer_parity"])
        stale_ok_with_blockers["gates"]["cloud_service_parity"] = dict(allowed_incomplete["gates"]["cloud_service_parity"])
        stale_ok_with_blockers["blocked_actions"] = allowed_incomplete["blocked_actions"]
        stale_ok_with_blockers["completion_criteria"]["native_real_printer_parity_completed"] = False
        stale_ok_with_blockers["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        stale_ok_with_blockers["completion_criteria"]["final_readiness_ok"] = False
        write_json(stale_ok_with_blockers_path, stale_ok_with_blockers)
        result = validate_completion_audit(stale_ok_with_blockers_path)
        if result["ok"] or "report_ok_matches_blockers" not in result["failed"]:
            raise RuntimeError(f"native stale-ok-with-blockers fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native stale-ok-with-blockers fixture was allowed as incomplete: {result}")

        missing_cloud_decision_path = native_complete_fixture(work / "native_missing_cloud_decision")
        missing_cloud_decision = load_report(missing_cloud_decision_path)
        missing_cloud_decision["ok"] = False
        missing_cloud_decision["blockers"] = ["real_printer_parity", "cloud_service_parity"]
        missing_cloud_decision["gates"]["real_printer_parity"]["ok"] = False
        missing_cloud_decision["gates"]["real_printer_parity"]["missing_inputs"] = ["printer IP"]
        missing_cloud_decision["gates"]["real_printer_parity"]["needed_action"] = ["provide printer IP"]
        missing_cloud_decision["gates"]["cloud_service_parity"]["ok"] = False
        missing_cloud_decision["gates"]["cloud_service_parity"].pop("authorized_cloud_ok", None)
        missing_cloud_decision["gates"]["cloud_service_parity"]["missing_inputs"] = ["authorized cloud login context"]
        missing_cloud_decision["gates"]["cloud_service_parity"]["needed_action"] = ["provide authorized cloud login context"]
        missing_cloud_decision["blocked_actions"] = [
            {
                "gate": "cloud_service_parity",
                "missing_inputs": ["authorized cloud login context"],
                "needed_action": ["provide authorized cloud login context"],
            },
            {
                "gate": "real_printer_parity",
                "missing_inputs": ["printer IP"],
                "needed_action": ["provide printer IP"],
            },
        ]
        missing_cloud_decision["completion_criteria"]["native_real_printer_parity_completed"] = False
        missing_cloud_decision["completion_criteria"]["cloud_service_parity_completed_or_approved_scope_out"] = False
        missing_cloud_decision["completion_criteria"]["final_readiness_ok"] = False
        write_json(missing_cloud_decision_path, missing_cloud_decision)
        result = validate_completion_audit(missing_cloud_decision_path)
        if result["ok"] or "blocked_actions_summary_is_actionable_when_incomplete" not in result["failed"]:
            raise RuntimeError(f"native missing-cloud-decision fixture was accepted: {result}")
        if allow_incomplete_result(result):
            raise RuntimeError(f"native missing-cloud-decision fixture was allowed as incomplete: {result}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=pathlib.Path, default=DEFAULT_REPORT)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print("completion audit validation checks passed")
        return 0

    result = validate_completion_audit(args.report)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] or (args.allow_incomplete and allow_incomplete_result(result)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
