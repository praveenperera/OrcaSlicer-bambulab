#!/usr/bin/env python3
import argparse
import json
import pathlib
import tempfile
from typing import Any


DEFAULT_REPORT = pathlib.Path("build/bambu_network_release_readiness/release_readiness_report.json")


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

    checklist = completion_checklist(report)
    failed = [item["name"] for item in checklist if item.get("ok") is not True]
    return {
        "ok": not failed,
        "path": str(path),
        "failed": failed,
        "checklist": checklist,
        "blockers": report.get("blockers", []),
    }


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


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="bambu-completion-audit-") as tmp:
        work = pathlib.Path(tmp)
        complete = validate_completion_audit(complete_fixture(work))
        if not complete["ok"]:
            raise RuntimeError(f"complete fixture was rejected: {complete}")

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
    return 0 if result["ok"] or args.allow_incomplete else 1


if __name__ == "__main__":
    raise SystemExit(main())
