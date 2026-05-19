#!/usr/bin/env python3
import argparse
import json
import pathlib
import tempfile
from typing import Any


REQUIRED_GATES = (
    "local_candidate_smoke",
    "official_parity",
    "real_printer_parity_inputs",
    "full_compatibility_feature_parity",
    "linux_bridge_payload",
    "linux_direct_libstdcxx_load",
    "macos_bridge_runtime",
)
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
MACOS_BRIDGE_DYLIB_FIXTURE_KIND = "copy-path-fixture"
SOURCE_CONTROL_TLS_LOOPBACK_CHECKS = (
    "report_ok",
    "no_failed_entries",
    "does_not_copy_binaries",
    "passwords_redacted",
    "official_source_differs_from_candidate",
    "candidate_source_hash_matches_current_build",
    "official_artifact_present",
    "candidate_artifact_present",
    "comparison_artifact_present",
    "comparison_ok",
    "contracts_match",
    "official_validation_ok",
    "candidate_validation_ok",
    "official_login_frame_checked",
    "candidate_login_frame_checked",
    "official_control_frames_checked",
    "candidate_control_frames_checked",
    "artifacts_keep_secret_out",
    "artifacts_use_redacted_url",
)
SOURCE_STREAMING_LOOPBACK_CHECKS = (
    "report_ok",
    "no_failed_entries",
    "does_not_copy_binaries",
    "stores_hashes_and_transcripts",
    "not_self_compare",
    "official_source_differs_from_candidate",
    "candidate_source_hash_matches_current_build",
    "source_streaming_probe",
    "source_streaming_compare",
    "source_streaming_official_artifact",
    "source_streaming_candidate_artifact",
    "source_streaming_artifacts_match",
    "source_streaming_compare_artifact",
    "source_streaming_modes_match",
    "source_streaming_official_success",
    "source_streaming_candidate_success",
)


def load_report(path: pathlib.Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("release readiness report is not a JSON object")
    return payload


def validate_release_readiness_report(path: pathlib.Path, *, require_complete: bool = False) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "path": str(path), "failed": ["report_exists"]}

    try:
        payload = load_report(path)
    except (json.JSONDecodeError, RuntimeError) as error:
        return {"ok": False, "path": str(path), "failed": ["report_json"], "reason": str(error)}

    gates = payload.get("gates", {})
    blockers = payload.get("blockers", [])
    checks: dict[str, bool] = {
        "gates_object": isinstance(gates, dict),
        "blockers_list": isinstance(blockers, list),
    }
    if not checks["gates_object"] or not checks["blockers_list"]:
        failed = [name for name, ok in checks.items() if not ok]
        return {"ok": False, "path": str(path), "checks": checks, "failed": failed}

    for name in REQUIRED_GATES:
        gate = gates.get(name, {})
        checks[f"gate_{name}_present"] = isinstance(gate, dict)
        checks[f"gate_{name}_required"] = isinstance(gate, dict) and gate.get("required") is True
        checks[f"gate_{name}_ok_bool"] = isinstance(gate, dict) and isinstance(gate.get("ok"), bool)

    required_blockers = sorted(
        name
        for name, gate in gates.items()
        if isinstance(gate, dict) and gate.get("required") is True and gate.get("ok") is not True
    )
    checks["blockers_match_failed_required_gates"] = sorted(blockers) == required_blockers
    checks["report_ok_matches_blockers"] = payload.get("ok") is (not blockers)

    deferred = payload.get("deferred")
    if deferred is not None:
        deferred_blockers = deferred.get("deferred_blockers", {}) if isinstance(deferred, dict) else {}
        partially_deferred = deferred.get("partially_deferred_blockers", {}) if isinstance(deferred, dict) else {}
        non_deferred = deferred.get("non_deferred_blockers", []) if isinstance(deferred, dict) else []
        checks["deferred_object"] = isinstance(deferred, dict)
        checks["deferred_manual_printer_bool"] = isinstance(deferred, dict) and isinstance(deferred.get("manual_printer_parity_deferred"), bool)
        checks["deferred_authorized_cloud_bool"] = isinstance(deferred, dict) and isinstance(deferred.get("authorized_cloud_parity_deferred"), bool)
        checks["deferred_blockers_object"] = isinstance(deferred_blockers, dict)
        checks["deferred_partial_object"] = isinstance(partially_deferred, dict)
        checks["deferred_non_deferred_list"] = isinstance(non_deferred, list)
        if isinstance(deferred_blockers, dict) and isinstance(partially_deferred, dict) and isinstance(non_deferred, list):
            blocker_set = set(blockers)
            checks["deferred_blockers_subset"] = set(deferred_blockers) <= blocker_set
            checks["deferred_partial_subset"] = set(partially_deferred) <= blocker_set
            checks["deferred_non_deferred_subset"] = set(non_deferred) <= blocker_set
            checks["deferred_non_deferred_ok_matches"] = deferred.get("non_deferred_ok") is (not non_deferred)

    local_smoke = gates.get("local_candidate_smoke", {})
    local_validation = local_smoke.get("summary_validation", {}) if isinstance(local_smoke, dict) else {}
    checks["local_smoke_summary_validation_present"] = (
        isinstance(local_smoke, dict)
        and local_smoke.get("ok") is not True
    ) or (
        isinstance(local_validation, dict)
        and local_validation.get("ok") is True
    )

    official = gates.get("official_parity", {})
    official_has_report = (
        isinstance(official, dict)
        and isinstance(official.get("path"), str)
        and bool(official.get("path"))
    )
    if official_has_report or (isinstance(official, dict) and official.get("ok") is True):
        artifact_policy = official.get("artifact_policy") if isinstance(official, dict) else None
        checks["official_parity_artifact_policy_checked"] = isinstance(artifact_policy, dict)
        checks["official_parity_artifact_policy_ok"] = (
            isinstance(artifact_policy, dict)
            and artifact_policy.get("ok") is True
        )

    macos_runtime = gates.get("macos_bridge_runtime", {})
    linux_direct = gates.get("linux_direct_libstdcxx_load", {})
    if isinstance(linux_direct, dict) and linux_direct.get("ok") is True:
        direct_checks = linux_direct.get("checks", {})
        checks["linux_direct_libstdcxx_checks_object"] = isinstance(direct_checks, dict)
        if isinstance(direct_checks, dict):
            for name in (
                "report_ok",
                "network_shim_hash_matches_current_source",
                "source_shim_hash_matches_current_source",
                "rust_core_hash_matches_current_input",
                "network_output_hash_matches_file",
                "source_output_hash_matches_file",
                "network_exports",
                "source_exports",
                "network_cxx_abi",
                "source_cxx_abi",
                "network_dlopen",
                "source_dlopen",
            ):
                checks[f"linux_direct_libstdcxx_{name}"] = direct_checks.get(name) is True

    if isinstance(macos_runtime, dict) and macos_runtime.get("ok") is True:
        verify_summary = macos_runtime.get("verify_summary", {})
        metadata_checks = verify_summary.get("checks", {}) if isinstance(verify_summary, dict) else {}
        checks["macos_verify_summary_ok"] = isinstance(verify_summary, dict) and verify_summary.get("ok") is True
        checks["macos_copied_file_metadata_present"] = (
            isinstance(verify_summary, dict)
            and verify_summary.get("copied_file_metadata_present") is True
        )
        checks["macos_bridge_dylib_fixture_declared"] = (
            isinstance(verify_summary, dict)
            and verify_summary.get("bridge_dylib_fixture_declared") is True
            and verify_summary.get("bridge_dylib_fixture_kind") == MACOS_BRIDGE_DYLIB_FIXTURE_KIND
        )
        checks["macos_copied_metadata_checks_object"] = isinstance(metadata_checks, dict)
        if isinstance(metadata_checks, dict):
            for name in REQUIRED_MACOS_COPIED_FILES:
                checks[f"macos_copied_metadata_{name}"] = metadata_checks.get(f"copied_metadata_{name}") is True

    source_control_tls = gates.get("source_control_tls_loopback_parity_report")
    if source_control_tls is not None:
        source_control_checks = source_control_tls.get("checks", {}) if isinstance(source_control_tls, dict) else {}
        checks["source_control_tls_gate_object"] = isinstance(source_control_tls, dict)
        checks["source_control_tls_required_false"] = isinstance(source_control_tls, dict) and source_control_tls.get("required") is False
        checks["source_control_tls_ok"] = isinstance(source_control_tls, dict) and source_control_tls.get("ok") is True
        checks["source_control_tls_failed_empty"] = isinstance(source_control_tls, dict) and source_control_tls.get("failed") == []
        checks["source_control_tls_checks_object"] = isinstance(source_control_checks, dict)
        checks["source_control_tls_parity_flag"] = (
            isinstance(source_control_tls, dict)
            and source_control_tls.get("source_control_tls_loopback_parity_ok") is True
        )
        if isinstance(source_control_checks, dict):
            for name in SOURCE_CONTROL_TLS_LOOPBACK_CHECKS:
                checks[f"source_control_tls_{name}"] = source_control_checks.get(name) is True

    source_streaming = gates.get("source_streaming_parity_report")
    if source_streaming is not None:
        source_streaming_checks = source_streaming.get("checks", {}) if isinstance(source_streaming, dict) else {}
        checks["source_streaming_gate_object"] = isinstance(source_streaming, dict)
        checks["source_streaming_required_false"] = isinstance(source_streaming, dict) and source_streaming.get("required") is False
        checks["source_streaming_ok"] = isinstance(source_streaming, dict) and source_streaming.get("ok") is True
        checks["source_streaming_failed_empty"] = isinstance(source_streaming, dict) and source_streaming.get("failed") == []
        checks["source_streaming_checks_object"] = isinstance(source_streaming_checks, dict)
        checks["source_streaming_parity_flag"] = (
            isinstance(source_streaming, dict)
            and source_streaming.get("source_streaming_parity_ok") is True
        )
        if isinstance(source_streaming_checks, dict):
            for name in SOURCE_STREAMING_LOOPBACK_CHECKS:
                checks[f"source_streaming_{name}"] = source_streaming_checks.get(name) is True

    feature_parity = gates.get("full_compatibility_feature_parity", {})
    feature_checks = feature_parity.get("checks", {}) if isinstance(feature_parity, dict) else {}
    feature_failed = feature_parity.get("failed", []) if isinstance(feature_parity, dict) else []
    feature_gaps = feature_parity.get("gaps", []) if isinstance(feature_parity, dict) else []
    checks["feature_parity_checks_object"] = isinstance(feature_checks, dict)
    checks["feature_parity_failed_list"] = isinstance(feature_failed, list)
    checks["feature_parity_gaps_list"] = isinstance(feature_gaps, list)
    checks["feature_parity_checks_nonempty"] = isinstance(feature_checks, dict) and bool(feature_checks)
    if isinstance(feature_gaps, list):
        for index, gap in enumerate(feature_gaps):
            prefix = f"feature_parity_gap_{index}"
            checks[f"{prefix}_object"] = isinstance(gap, dict)
            if not isinstance(gap, dict):
                continue
            checks[f"{prefix}_name"] = isinstance(gap.get("name"), str) and bool(gap.get("name"))
            checks[f"{prefix}_implemented_bool"] = isinstance(gap.get("implemented"), bool)
            checks[f"{prefix}_reason"] = isinstance(gap.get("reason"), str) and bool(gap.get("reason"))
            checks[f"{prefix}_current_evidence"] = (
                isinstance(gap.get("current_evidence"), list)
                and bool(gap.get("current_evidence"))
                and all(isinstance(item, str) and bool(item) for item in gap.get("current_evidence"))
            )
            checks[f"{prefix}_blocking_probe"] = isinstance(gap.get("blocking_probe"), str) and bool(gap.get("blocking_probe"))
            checks[f"{prefix}_needed_evidence"] = isinstance(gap.get("needed_evidence"), str) and bool(gap.get("needed_evidence"))
    if isinstance(feature_parity, dict) and isinstance(feature_checks, dict) and isinstance(feature_failed, list):
        checks["feature_parity_failed_matches_checks"] = sorted(feature_failed) == sorted(
            name for name, ok in feature_checks.items() if ok is not True
        )
        checks["feature_parity_ok_matches_failed"] = feature_parity.get("ok") is (not feature_failed)

    if require_complete:
        checks["report_complete"] = payload.get("ok") is True and not blockers

    failed = [name for name, ok in checks.items() if not ok]
    return {
        "ok": not failed,
        "path": str(path),
        "require_complete": require_complete,
        "checks": checks,
        "failed": failed,
        "blockers": blockers,
    }


def write_json(path: pathlib.Path, payload: dict[str, Any]) -> pathlib.Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def gate(ok: bool, *, required: bool = True, **extra: Any) -> dict[str, Any]:
    return {"ok": ok, "required": required, **extra}


def macos_gate(ok: bool = True) -> dict[str, Any]:
    return gate(
        ok,
        verify_summary={
            "ok": ok,
            "copied_file_metadata_present": ok,
            "bridge_dylib_fixture_declared": ok,
            "bridge_dylib_fixture_kind": MACOS_BRIDGE_DYLIB_FIXTURE_KIND if ok else None,
            "checks": {f"copied_metadata_{name}": ok for name in REQUIRED_MACOS_COPIED_FILES},
        },
    )


def source_control_tls_gate(ok: bool = True) -> dict[str, Any]:
    checks = {name: ok for name in SOURCE_CONTROL_TLS_LOOPBACK_CHECKS}
    return gate(
        ok,
        required=False,
        failed=[] if ok else ["contracts_match"],
        checks=checks,
        source_control_tls_loopback_parity_ok=ok,
        source_control_tls_loopback_checks=checks,
    )


def source_streaming_gate(ok: bool = True) -> dict[str, Any]:
    checks = {name: ok for name in SOURCE_STREAMING_LOOPBACK_CHECKS}
    return gate(
        ok,
        required=False,
        failed=[] if ok else ["source_streaming_compare"],
        checks=checks,
        source_streaming_parity_ok=ok,
        source_streaming_checks=checks,
    )


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="bambu-release-readiness-report-") as tmp:
        work = pathlib.Path(tmp)
        incomplete = {
            "ok": False,
            "blockers": ["official_parity"],
            "gates": {
                "local_candidate_smoke": gate(True, summary_validation={"ok": True}),
                "official_parity": gate(False),
                "real_printer_parity_inputs": gate(True),
                "full_compatibility_feature_parity": gate(
                    True,
                    checks={"camera_source_streaming": True},
                    failed=[],
                    gaps=[
                        {
                            "name": "camera_source_streaming",
                            "implemented": True,
                            "reason": "covered by test fixture",
                            "current_evidence": ["streaming parity fixture"],
                            "blocking_probe": "camera_source_streaming_parity",
                            "needed_evidence": "streaming parity fixture",
                        },
                    ],
                ),
                "linux_bridge_payload": gate(True),
                "linux_direct_libstdcxx_load": gate(
                    True,
                    checks={
                        "report_ok": True,
                        "network_shim_hash_matches_current_source": True,
                        "source_shim_hash_matches_current_source": True,
                        "rust_core_hash_matches_current_input": True,
                        "network_output_hash_matches_file": True,
                        "source_output_hash_matches_file": True,
                        "network_exports": True,
                        "source_exports": True,
                        "network_cxx_abi": True,
                        "source_cxx_abi": True,
                        "network_dlopen": True,
                        "source_dlopen": True,
                    },
                ),
                "macos_bridge_runtime": macos_gate(),
                "source_streaming_parity_report": source_streaming_gate(),
                "source_control_tls_loopback_parity_report": source_control_tls_gate(),
            },
        }
        result = validate_release_readiness_report(write_json(work / "incomplete.json", incomplete))
        if not result["ok"]:
            raise RuntimeError(f"incomplete-but-consistent report was rejected: {result}")

        complete = {
            "ok": True,
            "blockers": [],
            "deferred": {
                "manual_printer_parity_deferred": False,
                "authorized_cloud_parity_deferred": False,
                "deferred_blockers": {},
                "partially_deferred_blockers": {},
                "non_deferred_blockers": [],
                "non_deferred_ok": True,
            },
            "gates": {
                "local_candidate_smoke": gate(True, summary_validation={"ok": True}),
                "official_parity": gate(True, artifact_policy={"ok": True}),
                "real_printer_parity_inputs": gate(True),
                "full_compatibility_feature_parity": gate(
                    True,
                    checks={"camera_source_streaming": True},
                    failed=[],
                    gaps=[
                        {
                            "name": "camera_source_streaming",
                            "implemented": True,
                            "reason": "covered by test fixture",
                            "current_evidence": ["streaming parity fixture"],
                            "blocking_probe": "camera_source_streaming_parity",
                            "needed_evidence": "streaming parity fixture",
                        },
                    ],
                ),
                "linux_bridge_payload": gate(True),
                "linux_direct_libstdcxx_load": gate(
                    True,
                    checks={
                        "report_ok": True,
                        "network_shim_hash_matches_current_source": True,
                        "source_shim_hash_matches_current_source": True,
                        "rust_core_hash_matches_current_input": True,
                        "network_output_hash_matches_file": True,
                        "source_output_hash_matches_file": True,
                        "network_exports": True,
                        "source_exports": True,
                        "network_cxx_abi": True,
                        "source_cxx_abi": True,
                        "network_dlopen": True,
                        "source_dlopen": True,
                    },
                ),
                "macos_bridge_runtime": macos_gate(),
            },
        }
        result = validate_release_readiness_report(write_json(work / "complete.json", complete), require_complete=True)
        if not result["ok"]:
            raise RuntimeError(f"complete report was rejected: {result}")

        bad_blockers = dict(incomplete)
        bad_blockers["blockers"] = []
        result = validate_release_readiness_report(write_json(work / "bad_blockers.json", bad_blockers))
        if result["ok"] or "blockers_match_failed_required_gates" not in result["failed"]:
            raise RuntimeError(f"inconsistent blockers were accepted: {result}")

        deferred_incomplete = {
            **incomplete,
            "deferred": {
                "manual_printer_parity_deferred": True,
                "authorized_cloud_parity_deferred": False,
                "deferred_blockers": {
                    "official_parity": {
                        "reason": "fixture",
                        "failed": ["full_ft_contract_evidence"],
                    },
                },
                "partially_deferred_blockers": {},
                "non_deferred_blockers": [],
                "non_deferred_ok": True,
            },
        }
        result = validate_release_readiness_report(write_json(work / "deferred_incomplete.json", deferred_incomplete))
        if not result["ok"]:
            raise RuntimeError(f"deferred incomplete report was rejected: {result}")

        bad_deferred = {
            **deferred_incomplete,
            "deferred": {
                **deferred_incomplete["deferred"],
                "non_deferred_blockers": ["not_a_blocker"],
            },
        }
        result = validate_release_readiness_report(write_json(work / "bad_deferred.json", bad_deferred))
        if result["ok"] or "deferred_non_deferred_subset" not in result["failed"]:
            raise RuntimeError(f"inconsistent deferred blocker summary was accepted: {result}")

        weak_local = dict(complete)
        weak_local["gates"] = dict(complete["gates"])
        weak_local["gates"]["local_candidate_smoke"] = gate(True)
        result = validate_release_readiness_report(write_json(work / "weak_local.json", weak_local))
        if result["ok"] or "local_smoke_summary_validation_present" not in result["failed"]:
            raise RuntimeError(f"weak local smoke gate was accepted: {result}")

        weak_artifact_policy = dict(complete)
        weak_artifact_policy["gates"] = dict(complete["gates"])
        weak_artifact_policy["gates"]["official_parity"] = gate(False, path="parity_report.json", artifact_policy=None)
        weak_artifact_policy["blockers"] = ["official_parity"]
        weak_artifact_policy["ok"] = False
        result = validate_release_readiness_report(write_json(work / "weak_artifact_policy.json", weak_artifact_policy))
        if result["ok"] or "official_parity_artifact_policy_checked" not in result["failed"]:
            raise RuntimeError(f"official parity report without artifact policy was accepted: {result}")

        weak_macos = dict(complete)
        weak_macos["gates"] = dict(complete["gates"])
        weak_macos["gates"]["macos_bridge_runtime"] = gate(True)
        result = validate_release_readiness_report(write_json(work / "weak_macos.json", weak_macos))
        if result["ok"] or "macos_verify_summary_ok" not in result["failed"]:
            raise RuntimeError(f"macOS bridge gate without verifier summary was accepted: {result}")

        weak_macos_metadata = dict(complete)
        weak_macos_metadata["gates"] = dict(complete["gates"])
        weak_macos_metadata["gates"]["macos_bridge_runtime"] = macos_gate()
        weak_macos_metadata["gates"]["macos_bridge_runtime"]["verify_summary"]["checks"]["copied_metadata_libBambuSource.so"] = False
        result = validate_release_readiness_report(write_json(work / "weak_macos_metadata.json", weak_macos_metadata))
        if result["ok"] or "macos_copied_metadata_libBambuSource.so" not in result["failed"]:
            raise RuntimeError(f"macOS bridge gate with weak copied-file metadata was accepted: {result}")

        weak_macos_fixture = dict(complete)
        weak_macos_fixture["gates"] = dict(complete["gates"])
        weak_macos_fixture["gates"]["macos_bridge_runtime"] = macos_gate()
        weak_macos_fixture["gates"]["macos_bridge_runtime"]["verify_summary"]["bridge_dylib_fixture_declared"] = False
        result = validate_release_readiness_report(write_json(work / "weak_macos_fixture.json", weak_macos_fixture))
        if result["ok"] or "macos_bridge_dylib_fixture_declared" not in result["failed"]:
            raise RuntimeError(f"macOS bridge gate without fixture disclosure was accepted: {result}")

        weak_feature = dict(complete)
        weak_feature["gates"] = dict(complete["gates"])
        weak_feature["gates"]["full_compatibility_feature_parity"] = gate(
            True,
            checks={"camera_source_streaming": False},
            failed=[],
            gaps=[],
        )
        result = validate_release_readiness_report(write_json(work / "weak_feature.json", weak_feature))
        if result["ok"] or "feature_parity_failed_matches_checks" not in result["failed"]:
            raise RuntimeError(f"weak feature-parity gate was accepted: {result}")

        missing_feature_shape = dict(complete)
        missing_feature_shape["gates"] = dict(complete["gates"])
        missing_feature_shape["gates"]["full_compatibility_feature_parity"] = gate(True)
        result = validate_release_readiness_report(write_json(work / "missing_feature_shape.json", missing_feature_shape))
        if result["ok"] or "feature_parity_checks_nonempty" not in result["failed"]:
            raise RuntimeError(f"feature-parity gate without evidence shape was accepted: {result}")

        weak_feature_gap = dict(complete)
        weak_feature_gap["gates"] = dict(complete["gates"])
        weak_feature_gap["gates"]["full_compatibility_feature_parity"] = gate(
            True,
            checks={"camera_source_streaming": True},
            failed=[],
            gaps=[
                {
                    "name": "camera_source_streaming",
                    "implemented": True,
                    "reason": "covered by test fixture",
                    "current_evidence": [],
                    "blocking_probe": "camera_source_streaming_parity",
                    "needed_evidence": "streaming parity fixture",
                },
            ],
        )
        result = validate_release_readiness_report(write_json(work / "weak_feature_gap.json", weak_feature_gap))
        if result["ok"] or "feature_parity_gap_0_current_evidence" not in result["failed"]:
            raise RuntimeError(f"feature-parity gap without current evidence was accepted: {result}")

        weak_source_control_tls = dict(incomplete)
        weak_source_control_tls["gates"] = dict(incomplete["gates"])
        weak_source_control_tls["gates"]["source_control_tls_loopback_parity_report"] = source_control_tls_gate()
        weak_source_control_tls["gates"]["source_control_tls_loopback_parity_report"]["checks"]["contracts_match"] = False
        result = validate_release_readiness_report(write_json(work / "weak_source_control_tls.json", weak_source_control_tls))
        if result["ok"] or "source_control_tls_contracts_match" not in result["failed"]:
            raise RuntimeError(f"weak source-control TLS loopback gate was accepted: {result}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=pathlib.Path)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print("release readiness report validation checks passed")
        return 0
    if args.report is None:
        parser.error("--report is required unless --self-test is used")

    result = validate_release_readiness_report(args.report, require_complete=args.require_complete)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
