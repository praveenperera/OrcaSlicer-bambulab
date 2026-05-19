#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import pathlib
import tempfile
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
READINESS = ROOT / "tools/bambu_network_contract_tests/run_release_readiness.py"
REQUIRED_CONTRACT_PROBES = (
    "network_symbols",
    "source_symbols",
    "lifecycle",
    "callback",
    "unsupported",
    "discovery",
    "source_behavior",
)
REQUIRED_CANDIDATE_ONLY_PROBES = (
    "candidate_source_behavior",
    "candidate_event_bridge",
    "candidate_camera_url",
)
FT_BEHAVIOR_PROBE = "ft_behavior"
FT_JOB_INVALID_PROBE = "ft_job_invalid"
SOURCE_STREAMING_PROBE = "source_streaming"
CLOUD_SERVICE_PROBE = "cloud_service"


def load_readiness_module():
    spec = importlib.util.spec_from_file_location("run_release_readiness", READINESS)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {READINESS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: pathlib.Path, payload: dict[str, Any]) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_text(path: pathlib.Path, text: str) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def successful_probe(official_path: str = "/tmp/official.json", candidate_path: str = "/tmp/candidate.json") -> dict[str, Any]:
    return {
        "official": {"ok": True, "exit_code": 0, "path": official_path},
        "candidate": {"ok": True, "exit_code": 0, "path": candidate_path},
    }


def successful_comparison(path: str = "/tmp/compare.txt") -> dict[str, Any]:
    return {"ok": True, "exit_code": 0, "path": path}


def successful_candidate_only_probe(path: str = "/tmp/candidate-only.json") -> dict[str, Any]:
    return {"ok": True, "exit_code": 0, "path": path}


def add_probe_artifacts(report: dict[str, Any], artifact_dir: pathlib.Path, names: tuple[str, ...]) -> None:
    for name in names:
        payload = {"name": name, "ok": True}
        official_path = write_json(artifact_dir / "official" / f"{name}.json", payload)
        candidate_path = write_json(artifact_dir / "candidate" / f"{name}.json", payload)
        comparison_path = write_text(artifact_dir / "compare" / f"{name}.txt", "transcripts match\n")
        report["probes"][name] = successful_probe(str(official_path), str(candidate_path))
        report["comparisons"][name] = successful_comparison(str(comparison_path))


def add_required_artifacts(report: dict[str, Any], artifact_dir: pathlib.Path) -> None:
    add_probe_artifacts(report, artifact_dir, REQUIRED_CONTRACT_PROBES)
    for name in REQUIRED_CANDIDATE_ONLY_PROBES:
        path = write_json(artifact_dir / "candidate" / f"{name}.json", {"name": name, "candidate_only": True})
        report["candidate_only_probes"][name] = successful_candidate_only_probe(str(path))


def printer_workflow_transcript() -> dict[str, Any]:
    return {
        "dev_id": "printer",
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
        "events": [{"name": "local_connect", "status": 0, "dev_id": "printer", "payload": "connected"}],
    }


def print_job_transcript(mode: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "dev_id": "printer",
        "dev_ip": "192.0.2.10",
        "password_present": True,
        "file_present": True,
        "remote_name_present": True,
        "agent_created": True,
        "missing_symbols": [],
        "destroy_result": 0,
        "job_result": 0,
        "ok": True,
        "status_events": [{"status": 6, "code": 0, "message": "finished"}],
        "results": {
            "init_log": 0,
            "set_config_dir": 0,
            "set_country_code": 0,
            "start": 0,
        },
    }


def source_streaming_transcript(mode: str = "video") -> dict[str, Any]:
    payload = {
        "ok": True,
        "mode": mode,
        "missing_symbols": [],
        "results": {},
        "semantic": {
            "opened": True,
            "stream_started": True,
            "stream_info_available": mode == "video",
            "message_sent": mode == "control",
            "message_received": mode == "control",
            "sample_message_sent": mode == "control",
            "sample_read": True,
        },
        "stream_contract": {
            "stream_count_positive": mode == "video",
            "sample_has_buffer": True,
            "sample_size_positive": True,
            "stream_type": 0,
            "stream_sub_type": 0,
            "stream_format_type": 1,
            "stream_format_size_positive": True,
            "stream_max_frame_size_positive": True,
            "stream_width": 1280,
            "stream_height": 720,
            "stream_frame_rate": 30,
        },
    }
    if mode == "control":
        payload["results"] = {
            "Bambu_SendMessage": 0,
            "Bambu_SendMessage_sample": 0,
            "Bambu_RecvMessage": 0,
        }
    return payload


def cloud_service_transcript() -> dict[str, Any]:
    return {
        "ok": True,
        "expect_success": True,
        "allow_network": True,
        "agent_created": True,
        "missing_symbols": [],
        "results": {
            "change_user": 0,
            "is_user_login": True,
            "connect_server": 0,
            "get_user_print_info": 0,
        },
        "contract": {
            "user_info_supplied": True,
            "get_user_print_info_body": {"present": True, "looks_json": True, "length": 100},
        },
        "callbacks": {
            "user_login": 1,
            "server_connected": 1,
            "http_error": 0,
            "message": 0,
            "subscribe_failure": 0,
        },
        "semantic": {
            "login_ok": True,
            "network_ok": True,
            "service_ok": True,
            "non_unsupported_service_results": 2,
        },
    }


def add_real_printer_transcripts(report: dict[str, Any], transcript_dir: pathlib.Path) -> None:
    transcript_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "printer_workflow": printer_workflow_transcript(),
        "print_job_upload_only": print_job_transcript("upload-only"),
        "print_job_local_print": print_job_transcript("local-print"),
        "print_job_sdcard_print": print_job_transcript("sdcard-print"),
    }
    for name, payload in payloads.items():
        official_path = write_json(transcript_dir / "official" / f"{name}.json", payload)
        candidate_path = write_json(transcript_dir / "candidate" / f"{name}.json", payload)
        report["probes"][name] = successful_probe(str(official_path), str(candidate_path))
        comparison_path = write_text(transcript_dir / "compare" / f"{name}.txt", "transcripts match\n")
        report["comparisons"][name] = successful_comparison(str(comparison_path))


def parity_report(
    *,
    self_compare: bool = False,
    candidate_network_sha: str = "candidate-network",
    candidate_source_sha: str = "candidate-source",
    artifact_dir: pathlib.Path | None = None,
    transcript_dir: pathlib.Path | None = None,
    include_ft_behavior: bool = True,
    include_ft_job_invalid: bool = False,
    include_source_streaming: bool = False,
    source_streaming_mode: str = "video",
    include_cloud_service: bool = False,
) -> dict[str, Any]:
    probes = {name: successful_probe() for name in REQUIRED_CONTRACT_PROBES}
    comparisons = {name: successful_comparison() for name in REQUIRED_CONTRACT_PROBES}
    if include_ft_behavior:
        probes[FT_BEHAVIOR_PROBE] = successful_probe()
        comparisons[FT_BEHAVIOR_PROBE] = successful_comparison()
    if include_ft_job_invalid:
        probes[FT_JOB_INVALID_PROBE] = successful_probe()
        comparisons[FT_JOB_INVALID_PROBE] = successful_comparison()
    if include_source_streaming:
        probes[SOURCE_STREAMING_PROBE] = successful_probe()
        comparisons[SOURCE_STREAMING_PROBE] = successful_comparison()
    if include_cloud_service:
        probes[CLOUD_SERVICE_PROBE] = successful_probe()
        comparisons[CLOUD_SERVICE_PROBE] = successful_comparison()
    for name in ("printer_workflow", "print_job_upload_only", "print_job_local_print", "print_job_sdcard_print"):
        probes[name] = successful_probe()
        comparisons[name] = successful_comparison()
    official_network_sha = candidate_network_sha if self_compare else "official-network"
    official_source_sha = candidate_source_sha if self_compare else "official-source"
    report = {
        "ok": True,
        "failed": [],
        "inputs": {
            "artifact_policy": {
                "copies_input_binaries": False,
                "stores_hashes_and_probe_transcripts_only": True,
            },
            "self_compare_allowed": self_compare,
            "print_job_modes": ["upload-only", "local-print", "sdcard-print"],
            "official": {
                "network": {"exists": True, "path": "/outside/libbambu_networking.so", "sha256": official_network_sha, "size": 1},
                "source": {"exists": True, "path": "/outside/libBambuSource.so", "sha256": official_source_sha, "size": 1},
            },
            "candidate": {
                "network": {"exists": True, "path": "/candidate/libbambu_networking.so", "sha256": candidate_network_sha, "size": 1},
                "source": {"exists": True, "path": "/candidate/libBambuSource.so", "sha256": candidate_source_sha, "size": 1},
            },
        },
        "probes": probes,
        "comparisons": comparisons,
        "candidate_only_probes": {
            name: successful_candidate_only_probe() for name in REQUIRED_CANDIDATE_ONLY_PROBES
        },
    }
    if artifact_dir is not None:
        add_required_artifacts(report, artifact_dir)
        if include_ft_behavior:
            add_probe_artifacts(report, artifact_dir, (FT_BEHAVIOR_PROBE,))
        if include_ft_job_invalid:
            add_probe_artifacts(report, artifact_dir, (FT_JOB_INVALID_PROBE,))
        if include_source_streaming:
            payload = source_streaming_transcript(source_streaming_mode)
            official_path = write_json(artifact_dir / "official" / f"{SOURCE_STREAMING_PROBE}.json", payload)
            candidate_path = write_json(artifact_dir / "candidate" / f"{SOURCE_STREAMING_PROBE}.json", payload)
            comparison_path = write_text(artifact_dir / "compare" / f"{SOURCE_STREAMING_PROBE}.txt", "transcripts match\n")
            report["probes"][SOURCE_STREAMING_PROBE] = successful_probe(str(official_path), str(candidate_path))
            report["comparisons"][SOURCE_STREAMING_PROBE] = successful_comparison(str(comparison_path))
        if include_cloud_service:
            payload = cloud_service_transcript()
            official_path = write_json(artifact_dir / "official" / f"{CLOUD_SERVICE_PROBE}.json", payload)
            candidate_path = write_json(artifact_dir / "candidate" / f"{CLOUD_SERVICE_PROBE}.json", payload)
            comparison_path = write_text(artifact_dir / "compare" / f"{CLOUD_SERVICE_PROBE}.txt", "transcripts match\n")
            report["probes"][CLOUD_SERVICE_PROBE] = successful_probe(str(official_path), str(candidate_path))
            report["comparisons"][CLOUD_SERVICE_PROBE] = successful_comparison(str(comparison_path))
    if transcript_dir is not None:
        add_real_printer_transcripts(report, transcript_dir)
    return report


def linux_manifest(network_sha: str = "network", source_sha: str = "source") -> dict[str, Any]:
    return {
        "format": 1,
        "kind": "bambu-network-clean-room-candidate",
        "files": [
            {"name": "libbambu_networking.so", "sha256": network_sha},
            {"name": "libBambuSource.so", "sha256": source_sha},
        ],
    }


def linux_runtime_report(network_sha: str = "network", source_sha: str = "source") -> dict[str, Any]:
    readiness = load_readiness_module()
    responses = {
        "handshake": {"network_loaded": True, "source_loaded": True},
        "ft_capabilities": {name: True for name in getattr(readiness, "REQUIRED_FT_SYMBOLS")},
        "auth_info": {
            "ok": True,
            "logged_in": False,
            "bambulab_host": getattr(readiness, "BAMBULAB_HOST"),
            "studio_info_url": getattr(readiness, "STUDIO_INFO_URL"),
            "capabilities": {name: True for name in getattr(readiness, "REQUIRED_AUTH_SYMBOLS")},
        },
        "create_agent": {"ok": True, "value": 1},
        "set_config_dir": {"ok": True, "value": 0},
        "init_log": {"ok": True, "value": 0},
        "set_country_code": {"ok": True, "value": 0},
        "start": {"ok": True, "value": 0},
        "destroy_agent": {"ok": True, "value": 0},
        "ft_smoke": {
            "tunnel_create": {"ok": True, "value": 0, "tunnel": 1},
            "tunnel_sync_connect": {"ok": True, "value": 0},
            "media_job_create": {"ok": True, "value": 0, "job": 2},
            "media_job_start": {"ok": True, "value": 0},
            "media_job_get_result": {"ok": True, "value": 0, "ec": 0, "json": "[\"emmc\",\"sdcard\"]"},
            "upload_job_create": {"ok": True, "value": 0, "job": 3},
            "upload_job_start": {"ok": True, "value": 0},
            "upload_job_get_msg": {"ok": True, "value": 0, "json": "{\"progress\":0}"},
            "upload_job_get_result": {"ok": True, "value": 0, "ec": -3},
            "tunnel_release": {"ok": True, "value": 0},
        },
        "source_smoke": {
            "create": {"ok": True, "value": 0, "tunnel": 4},
            "open": {"ok": True, "value": 0},
            "start_stream": {"ok": True, "value": 0},
            "get_stream_count": {"ok": True, "value": 1},
            "get_stream_info": {
                "ok": True,
                "value": 0,
                "info": {"type": 0, "sub_type": 1, "format_type": 2, "width": 1, "height": 1, "frame_rate": 1},
            },
            "read_sample": {
                "ok": True,
                "value": 0,
                "sample": {"itrack": 0, "size": 141, "flags": 1, "decode_time": 0},
                "__binary_size": 141,
            },
            "destroy": {"ok": True, "value": 0},
        },
        "source_local_tunnel_smoke": {
            "create": {"ok": True, "value": 0, "tunnel": 5},
            "open": {"ok": True, "value": 0},
            "start_stream_ex": {"ok": True, "value": 0},
            "send_message": {"ok": True, "value": 0},
            "recv_message": {
                "ok": True,
                "value": 0,
                "ctrl": 0,
                "message_len": 57,
                "__binary_size": 57,
                "__binary_text": "{\"result\":0,\"sequence\":1,\"reply\":\"bridge-recv-loopback\"}\n",
            },
            "send_message_sample": {"ok": True, "value": 0},
            "read_sample": {
                "ok": True,
                "value": 0,
                "sample": {"itrack": 0, "size": 59, "flags": 1, "decode_time": 0},
                "__binary_size": 59,
                "__binary_text": "{\"result\":0,\"sequence\":2,\"reply\":\"bridge-sample-loopback\"}\n",
            },
            "server": {
                "accepted": True,
                "received_message": True,
                "response_sent": True,
                "error": "",
            },
            "destroy": {"ok": True, "value": 0},
        },
        "cloud_smoke": {
            "change_user": {"ok": True, "value": 0},
            "connect_server": {"ok": True, "value": 0},
            "is_server_connected": {"ok": True, "value": True},
            "get_user_print_info": {"ok": True, "value": 0, "http_code": 200, "http_body": "{}"},
            "get_user_tasks": {"ok": True, "value": 0, "http_body": "[]"},
            "get_my_token": {"ok": True, "value": 0, "http_code": 200, "http_body": "{}"},
            "get_my_profile": {"ok": True, "value": 0, "http_code": 200, "http_body": "{}"},
            "request_bind_ticket": {"ok": True, "value": 0, "ticket": "ticket"},
            "get_user_info": {"ok": True, "value": 0, "identifier": 1},
            "get_task_plate_index": {"ok": True, "value": 0, "plate_index": 0},
            "user_logout": {"ok": True, "value": 0},
        },
    }
    probe = {
        "ok": True,
        "stdout_json": {
            "network_so_present": True,
            "source_so_present": True,
            "responses": responses,
        },
    }
    return {
        "ok": True,
        "runtime_dir": "/runtime",
        "payload_files": {
            "libbambu_networking.so": {"sha256": network_sha, "size": 1},
            "libBambuSource.so": {"sha256": source_sha, "size": 1},
        },
        "bridge_probes": {
            "abi1": probe,
            "abi0": probe,
        },
    }


def linux_libstdcxx_report(work: pathlib.Path) -> dict[str, Any]:
    network_shim = write_text(work / "bambu_networking_shim.cpp", "network shim\n")
    source_shim = write_text(work / "bambu_source_shim.cpp", "source shim\n")
    rust_core = write_text(work / "libbambu_network_rust_core.a", "rust core\n")
    network_so = write_text(work / "libbambu_networking.so", "network so\n")
    source_so = write_text(work / "libBambuSource.so", "source so\n")
    return {
        "ok": True,
        "network_so": str(network_so),
        "source_so": str(source_so),
        "inputs": {
            "network_shim": {"path": str(network_shim), "sha256": sha256(network_shim)},
            "source_shim": {"path": str(source_shim), "sha256": sha256(source_shim)},
            "rust_core": {"path": str(rust_core), "sha256": sha256(rust_core)},
        },
        "outputs": {
            "network_so": {"path": str(network_so), "sha256": sha256(network_so)},
            "source_so": {"path": str(source_so), "sha256": sha256(source_so)},
        },
        "checks": {
            "network_exports": {"payload": {"ok": True, "present_count": 124, "missing_count": 0}},
            "source_exports": {"payload": {"ok": True, "present_count": 18, "missing_count": 0}},
            "network_cxx_abi": {
                "payload": {
                    "ok": True,
                    "expected": "libstdc++",
                    "inferred": "libstdc++",
                    "libcxx_symbol_count": 0,
                    "needed_libraries": ["libstdc++.so.6"],
                },
            },
            "source_cxx_abi": {
                "payload": {
                    "ok": True,
                    "expected": "libstdc++",
                    "inferred": "libstdc++",
                    "libcxx_symbol_count": 0,
                    "needed_libraries": ["libstdc++.so.6"],
                },
            },
            "network_dlopen": {"payload": {"ok": True, "present_count": 124, "missing_count": 0}},
            "source_dlopen": {"payload": {"ok": True, "present_count": 18, "missing_count": 0}},
        },
    }


def local_smoke_summary() -> dict[str, Any]:
    checks = {name: True for name in getattr(load_readiness_module(), "REQUIRED_LOCAL_SMOKE_CHECKS")}
    return {
        "ok": True,
        "failed": [],
        "checks": checks,
    }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    readiness = load_readiness_module()
    with tempfile.TemporaryDirectory(prefix="bambu-readiness-validation-") as tmp:
        work = pathlib.Path(tmp)

        good_dir = work / "good_parity"
        good_parity = write_json(good_dir / "parity_report.json", parity_report(
            artifact_dir=good_dir / "artifacts",
            transcript_dir=good_dir / "transcripts",
        ))
        accepted = readiness.validate_official_parity_report(
            good_parity,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(accepted["ok"], f"good parity report was rejected: {accepted}")
        require(accepted["real_printer_workflows_ok"], "good parity report did not satisfy real printer evidence")

        real_ft_job_dir = work / "real_printer_ft_job_parity"
        real_ft_job_parity = write_json(real_ft_job_dir / "parity_report.json", parity_report(
            artifact_dir=real_ft_job_dir / "artifacts",
            transcript_dir=real_ft_job_dir / "transcripts",
            include_ft_behavior=False,
            include_ft_job_invalid=True,
        ))
        accepted = readiness.validate_official_parity_report(
            real_ft_job_parity,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(accepted["ok"], f"real-printer plus ft-job parity report was rejected: {accepted}")
        require(accepted["real_printer_workflows_ok"], "real-printer plus ft-job parity missed printer evidence")
        require(accepted["ft_contract_checks"]["ft_job_invalid"], "real-printer plus ft-job parity missed ft job evidence")
        require(accepted["ft_contract_checks"]["full_ft_contract_evidence"], "real-printer plus ft-job parity missed full FT evidence")

        no_transcript_dir = work / "no_transcript_parity"
        no_transcript_parity = write_json(no_transcript_dir / "parity_report.json", parity_report(
            artifact_dir=no_transcript_dir / "artifacts",
        ))
        accepted = readiness.validate_official_parity_report(
            no_transcript_parity,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(accepted["ok"], f"parity report without real-printer transcripts should still satisfy contract parity: {accepted}")
        require(not accepted["real_printer_workflows_ok"], "parity report without real-printer transcripts satisfied real printer evidence")
        require(
            not accepted["real_printer_checks"]["printer_workflow_official_success"],
            "missing printer workflow transcript was accepted",
        )

        cloud_service_dir = work / "cloud_service_parity"
        cloud_service = write_json(cloud_service_dir / "parity_report.json", parity_report(
            artifact_dir=cloud_service_dir / "artifacts",
            include_cloud_service=True,
        ))
        accepted = readiness.validate_official_parity_report(
            cloud_service,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(accepted["ok"], f"cloud service parity report was rejected: {accepted}")
        require(accepted["cloud_service_parity_ok"], "cloud service parity did not satisfy feature evidence")

        failed_cloud_service_dir = work / "failed_cloud_service_parity"
        failed_cloud_service_payload = parity_report(
            artifact_dir=failed_cloud_service_dir / "artifacts",
            include_cloud_service=True,
        )
        failed_cloud_service_path = pathlib.Path(
            failed_cloud_service_payload["probes"][CLOUD_SERVICE_PROBE]["candidate"]["path"]
        )
        failed_cloud_service = json.loads(failed_cloud_service_path.read_text(encoding="utf-8"))
        failed_cloud_service["semantic"]["service_ok"] = False
        failed_cloud_service["ok"] = False
        write_json(failed_cloud_service_path, failed_cloud_service)
        failed_cloud_service_report = write_json(failed_cloud_service_dir / "parity_report.json", failed_cloud_service_payload)
        rejected = readiness.validate_official_parity_report(
            failed_cloud_service_report,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(not rejected["ok"], "failed cloud service parity report was accepted")
        require("cloud_service_candidate_success" in rejected["failed"], "failed cloud service candidate was not reported")

        source_streaming_dir = work / "source_streaming_parity"
        source_streaming = write_json(source_streaming_dir / "parity_report.json", parity_report(
            artifact_dir=source_streaming_dir / "artifacts",
            include_source_streaming=True,
        ))
        accepted = readiness.validate_official_parity_report(
            source_streaming,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(accepted["ok"], f"source streaming parity report was rejected: {accepted}")
        require(accepted["source_streaming_parity_ok"], "source streaming parity did not satisfy feature evidence")
        require(not accepted["source_control_tunnel_parity_ok"], "video source streaming unexpectedly satisfied control-tunnel evidence")

        source_control_dir = work / "source_control_tunnel_parity"
        source_control = write_json(source_control_dir / "parity_report.json", parity_report(
            artifact_dir=source_control_dir / "artifacts",
            include_source_streaming=True,
            source_streaming_mode="control",
        ))
        accepted = readiness.validate_official_parity_report(
            source_control,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(accepted["ok"], f"source control-tunnel parity report was rejected: {accepted}")
        require(not accepted["source_streaming_parity_ok"], "control-tunnel parity unexpectedly satisfied video source streaming evidence")
        require(accepted["source_control_tunnel_parity_ok"], "source control-tunnel parity did not satisfy feature evidence")

        failed_source_streaming_dir = work / "failed_source_streaming_parity"
        failed_source_streaming_payload = parity_report(
            artifact_dir=failed_source_streaming_dir / "artifacts",
            include_source_streaming=True,
        )
        failed_source_streaming_path = pathlib.Path(
            failed_source_streaming_payload["probes"][SOURCE_STREAMING_PROBE]["candidate"]["path"]
        )
        failed_source_streaming = json.loads(failed_source_streaming_path.read_text(encoding="utf-8"))
        failed_source_streaming["semantic"]["sample_read"] = False
        failed_source_streaming["ok"] = False
        write_json(failed_source_streaming_path, failed_source_streaming)
        failed_source_streaming_report = write_json(failed_source_streaming_dir / "parity_report.json", failed_source_streaming_payload)
        rejected = readiness.validate_official_parity_report(
            failed_source_streaming_report,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(not rejected["ok"], "failed source streaming parity report was accepted")
        require("source_streaming_candidate_success" in rejected["failed"], "failed source streaming candidate was not reported")

        failed_print_job_dir = work / "failed_print_job_parity"
        failed_print_job_payload = parity_report(
            artifact_dir=failed_print_job_dir / "artifacts",
            transcript_dir=failed_print_job_dir / "transcripts",
        )
        failed_print_job_path = pathlib.Path(
            failed_print_job_payload["probes"]["print_job_local_print"]["candidate"]["path"]
        )
        failed_print_job = json.loads(failed_print_job_path.read_text(encoding="utf-8"))
        failed_print_job["job_result"] = -1
        failed_print_job["ok"] = False
        write_json(failed_print_job_path, failed_print_job)
        failed_print_job_report = write_json(failed_print_job_dir / "parity_report.json", failed_print_job_payload)
        accepted = readiness.validate_official_parity_report(
            failed_print_job_report,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(accepted["ok"], f"contract parity unexpectedly failed for failed real-printer transcript fixture: {accepted}")
        require(not accepted["real_printer_workflows_ok"], "failed print-job transcript satisfied real printer evidence")
        require(
            not accepted["real_printer_checks"]["print_job_local_print_candidate_success"],
            "failed local-print candidate transcript was accepted",
        )

        missing_connect_event_dir = work / "missing_connect_event_parity"
        missing_connect_event_payload = parity_report(
            artifact_dir=missing_connect_event_dir / "artifacts",
            transcript_dir=missing_connect_event_dir / "transcripts",
        )
        missing_connect_path = pathlib.Path(
            missing_connect_event_payload["probes"]["printer_workflow"]["candidate"]["path"]
        )
        missing_connect = json.loads(missing_connect_path.read_text(encoding="utf-8"))
        missing_connect["events"] = []
        write_json(missing_connect_path, missing_connect)
        missing_connect_report = write_json(missing_connect_event_dir / "parity_report.json", missing_connect_event_payload)
        accepted = readiness.validate_official_parity_report(
            missing_connect_report,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(accepted["ok"], f"contract parity unexpectedly failed for missing connect event fixture: {accepted}")
        require(not accepted["real_printer_workflows_ok"], "missing connect callback satisfied real printer evidence")
        require(
            not accepted["real_printer_checks"]["printer_workflow_candidate_success"],
            "printer workflow without connect callback was accepted",
        )

        missing_identity_dir = work / "missing_identity_parity"
        missing_identity_payload = parity_report(
            artifact_dir=missing_identity_dir / "artifacts",
            transcript_dir=missing_identity_dir / "transcripts",
        )
        missing_identity_path = pathlib.Path(missing_identity_payload["probes"]["printer_workflow"]["candidate"]["path"])
        missing_identity = json.loads(missing_identity_path.read_text(encoding="utf-8"))
        del missing_identity["dev_ip"]
        write_json(missing_identity_path, missing_identity)
        missing_identity_report = write_json(missing_identity_dir / "parity_report.json", missing_identity_payload)
        accepted = readiness.validate_official_parity_report(
            missing_identity_report,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(accepted["ok"], f"contract parity unexpectedly failed for missing identity fixture: {accepted}")
        require(not accepted["real_printer_workflows_ok"], "missing printer identity satisfied real printer evidence")
        require(
            not accepted["real_printer_checks"]["printer_workflow_candidate_success"],
            "printer workflow without printer identity was accepted",
        )

        missing_finished_status_dir = work / "missing_finished_status_parity"
        missing_finished_status_payload = parity_report(
            artifact_dir=missing_finished_status_dir / "artifacts",
            transcript_dir=missing_finished_status_dir / "transcripts",
        )
        missing_finished_path = pathlib.Path(
            missing_finished_status_payload["probes"]["print_job_sdcard_print"]["candidate"]["path"]
        )
        missing_finished = json.loads(missing_finished_path.read_text(encoding="utf-8"))
        missing_finished["status_events"] = [{"status": 3, "code": 0, "message": "sending"}]
        write_json(missing_finished_path, missing_finished)
        missing_finished_report = write_json(missing_finished_status_dir / "parity_report.json", missing_finished_status_payload)
        accepted = readiness.validate_official_parity_report(
            missing_finished_report,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(accepted["ok"], f"contract parity unexpectedly failed for missing finished status fixture: {accepted}")
        require(not accepted["real_printer_workflows_ok"], "print job without finished status satisfied real printer evidence")
        require(
            not accepted["real_printer_checks"]["print_job_sdcard_print_candidate_success"],
            "sdcard print transcript without finished status was accepted",
        )

        error_status_dir = work / "error_status_parity"
        error_status_payload = parity_report(
            artifact_dir=error_status_dir / "artifacts",
            transcript_dir=error_status_dir / "transcripts",
        )
        error_status_path = pathlib.Path(error_status_payload["probes"]["print_job_upload_only"]["candidate"]["path"])
        error_status = json.loads(error_status_path.read_text(encoding="utf-8"))
        error_status["status_events"] = [
            {"status": 6, "code": 0, "message": "finished"},
            {"status": 7, "code": -1, "message": "error"},
        ]
        write_json(error_status_path, error_status)
        error_status_report = write_json(error_status_dir / "parity_report.json", error_status_payload)
        accepted = readiness.validate_official_parity_report(
            error_status_report,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(accepted["ok"], f"contract parity unexpectedly failed for error status fixture: {accepted}")
        require(not accepted["real_printer_workflows_ok"], "print job with error status satisfied real printer evidence")
        require(
            not accepted["real_printer_checks"]["print_job_upload_only_candidate_success"],
            "upload-only transcript with error status was accepted",
        )

        wrong_mode_dir = work / "wrong_mode_parity"
        wrong_mode_payload = parity_report(
            artifact_dir=wrong_mode_dir / "artifacts",
            transcript_dir=wrong_mode_dir / "transcripts",
        )
        wrong_mode_path = pathlib.Path(wrong_mode_payload["probes"]["print_job_upload_only"]["candidate"]["path"])
        wrong_mode = json.loads(wrong_mode_path.read_text(encoding="utf-8"))
        wrong_mode["mode"] = "local-print"
        write_json(wrong_mode_path, wrong_mode)
        wrong_mode_report = write_json(wrong_mode_dir / "parity_report.json", wrong_mode_payload)
        accepted = readiness.validate_official_parity_report(
            wrong_mode_report,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(accepted["ok"], f"contract parity unexpectedly failed for wrong mode fixture: {accepted}")
        require(not accepted["real_printer_workflows_ok"], "wrong print-job mode satisfied real printer evidence")
        require(
            not accepted["real_printer_checks"]["print_job_upload_only_candidate_success"],
            "upload-only slot accepted a different print-job mode",
        )

        self_compare_dir = work / "self_compare"
        self_compare = write_json(self_compare_dir / "parity_report.json", parity_report(
            self_compare=True,
            artifact_dir=self_compare_dir / "artifacts",
        ))
        rejected = readiness.validate_official_parity_report(
            self_compare,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(not rejected["ok"], "self-compare parity report was accepted")
        require("not_self_compare" in rejected["failed"], "self-compare rejection did not identify not_self_compare")
        require("official_network_differs_from_candidate" in rejected["failed"], "self-compare rejection missed network hash equality")

        stale_candidate_dir = work / "stale_candidate"
        stale_candidate = write_json(stale_candidate_dir / "parity_report.json", parity_report(
            candidate_network_sha="old-network",
            artifact_dir=stale_candidate_dir / "artifacts",
        ))
        rejected = readiness.validate_official_parity_report(
            stale_candidate,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(not rejected["ok"], "stale candidate parity report was accepted")
        require("candidate_network_hash_matches_current_build" in rejected["failed"], "stale parity rejection missed candidate hash")

        missing_ft_dir = work / "missing_ft"
        missing_ft = parity_report(artifact_dir=missing_ft_dir / "artifacts", include_ft_behavior=False)
        missing_ft_path = write_json(missing_ft_dir / "parity_report.json", missing_ft)
        rejected = readiness.validate_official_parity_report(
            missing_ft_path,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(not rejected["ok"], "parity report without FT coverage was accepted")
        require("full_ft_contract_evidence" in rejected["failed"], "missing FT coverage was not reported")

        missing_probe_dir = work / "missing_probe_artifact"
        missing_probe_artifact = parity_report(artifact_dir=missing_probe_dir / "artifacts")
        missing_probe_path = pathlib.Path(missing_probe_artifact["probes"]["lifecycle"]["candidate"]["path"])
        missing_probe_path.unlink()
        missing_probe_artifact_path = write_json(missing_probe_dir / "parity_report.json", missing_probe_artifact)
        rejected = readiness.validate_official_parity_report(
            missing_probe_artifact_path,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(not rejected["ok"], "parity report with missing probe artifact was accepted")
        require(
            "probe_lifecycle_candidate_artifact" in rejected["failed"],
            "missing probe artifact was not reported",
        )

        external_artifact_dir = work / "external_artifact"
        external_artifact = parity_report(artifact_dir=external_artifact_dir / "artifacts")
        external_probe_report_dir = work / "external_probe_report"
        external_artifact_path = write_json(external_probe_report_dir / "parity_report.json", external_artifact)
        rejected = readiness.validate_official_parity_report(
            external_artifact_path,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(not rejected["ok"], "parity report with external probe artifacts was accepted")
        require(
            "probe_lifecycle_candidate_artifact" in rejected["failed"],
            "external probe artifact was not reported",
        )

        invalid_comparison_dir = work / "invalid_comparison_artifact"
        invalid_comparison_artifact = parity_report(artifact_dir=invalid_comparison_dir / "artifacts")
        invalid_comparison_path = pathlib.Path(invalid_comparison_artifact["comparisons"]["callback"]["path"])
        write_text(invalid_comparison_path, "transcripts differ\n")
        invalid_comparison_artifact_path = write_json(invalid_comparison_dir / "parity_report.json", invalid_comparison_artifact)
        rejected = readiness.validate_official_parity_report(
            invalid_comparison_artifact_path,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(not rejected["ok"], "parity report with invalid comparison artifact was accepted")
        require(
            "compare_callback_artifact" in rejected["failed"],
            "invalid comparison artifact was not reported",
        )

        mismatched_probe_dir = work / "mismatched_probe_artifacts"
        mismatched_probe_artifacts = parity_report(artifact_dir=mismatched_probe_dir / "artifacts")
        mismatched_candidate_path = pathlib.Path(mismatched_probe_artifacts["probes"]["unsupported"]["candidate"]["path"])
        candidate_payload = json.loads(mismatched_candidate_path.read_text(encoding="utf-8"))
        candidate_payload["extra"] = "candidate-only-difference"
        write_json(mismatched_candidate_path, candidate_payload)
        mismatched_probe_artifacts_path = write_json(mismatched_probe_dir / "parity_report.json", mismatched_probe_artifacts)
        rejected = readiness.validate_official_parity_report(
            mismatched_probe_artifacts_path,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(not rejected["ok"], "parity report with mismatched probe JSON artifacts was accepted")
        require(
            "probe_unsupported_artifacts_match" in rejected["failed"],
            "mismatched probe JSON artifacts were not reported",
        )

        invalid_candidate_only_dir = work / "invalid_candidate_only_artifact"
        invalid_candidate_only_artifact = parity_report(artifact_dir=invalid_candidate_only_dir / "artifacts")
        invalid_candidate_only_path = pathlib.Path(
            invalid_candidate_only_artifact["candidate_only_probes"]["candidate_event_bridge"]["path"]
        )
        write_text(invalid_candidate_only_path, "not json\n")
        invalid_candidate_only_artifact_path = write_json(
            invalid_candidate_only_dir / "parity_report.json",
            invalid_candidate_only_artifact,
        )
        rejected = readiness.validate_official_parity_report(
            invalid_candidate_only_artifact_path,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(not rejected["ok"], "parity report with invalid candidate-only artifact was accepted")
        require(
            "candidate_only_candidate_event_bridge_artifact" in rejected["failed"],
            "invalid candidate-only artifact was not reported",
        )

        missing_candidate_only_dir = work / "missing_candidate_only"
        missing_candidate_only = parity_report(artifact_dir=missing_candidate_only_dir / "artifacts")
        del missing_candidate_only["candidate_only_probes"]["candidate_camera_url"]
        missing_candidate_only_path = write_json(missing_candidate_only_dir / "parity_report.json", missing_candidate_only)
        rejected = readiness.validate_official_parity_report(
            missing_candidate_only_path,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(not rejected["ok"], "parity report without candidate-only coverage was accepted")
        require(
            "candidate_only_candidate_camera_url" in rejected["failed"],
            "missing candidate-only coverage was not reported",
        )

        failed_candidate_only_dir = work / "failed_candidate_only"
        failed_candidate_only = parity_report(artifact_dir=failed_candidate_only_dir / "artifacts")
        failed_candidate_only["candidate_only_probes"]["candidate_event_bridge"]["ok"] = False
        failed_candidate_only_path = write_json(failed_candidate_only_dir / "parity_report.json", failed_candidate_only)
        rejected = readiness.validate_official_parity_report(
            failed_candidate_only_path,
            {"candidate-network"},
            {"candidate-source"},
        )
        require(not rejected["ok"], "parity report with failed candidate-only coverage was accepted")
        require(
            "candidate_only_candidate_event_bridge" in rejected["failed"],
            "failed candidate-only coverage was not reported",
        )

        manifest = write_json(work / "linux_payload_manifest.json", linux_manifest())
        good_linux = write_json(work / "good_linux.json", linux_runtime_report())
        accepted = readiness.validate_linux_runtime_report(good_linux, manifest)
        require(accepted["ok"], f"good Linux runtime report was rejected: {accepted}")

        stale_linux = write_json(work / "stale_linux.json", linux_runtime_report(network_sha="old-network"))
        rejected = readiness.validate_linux_runtime_report(stale_linux, manifest)
        require(not rejected["ok"], "stale Linux runtime report was accepted")
        require("libbambu_networking.so_hash_matches_current_payload" in rejected["failed"], "stale Linux report did not identify network hash mismatch")

        weak_linux = linux_runtime_report()
        weak_linux["bridge_probes"]["abi1"]["stdout_json"]["responses"]["ft_smoke"]["upload_job_get_result"]["ec"] = 0
        weak_linux_path = write_json(work / "weak_linux.json", weak_linux)
        rejected = readiness.validate_linux_runtime_report(weak_linux_path, manifest)
        require(not rejected["ok"], "Linux runtime report with weak FT smoke was accepted")
        require("abi1_ft_upload_missing_file_result" in rejected["failed"], "weak Linux report did not identify FT upload result mismatch")

        missing_ft_capability = linux_runtime_report()
        missing_ft_capability["bridge_probes"]["abi0"]["stdout_json"]["responses"]["ft_capabilities"]["ft_job_get_msg"] = False
        missing_ft_capability_path = write_json(work / "missing_ft_capability.json", missing_ft_capability)
        rejected = readiness.validate_linux_runtime_report(missing_ft_capability_path, manifest)
        require(not rejected["ok"], "Linux runtime report with missing FT capability was accepted")
        require(
            "abi0_ft_capability_ft_job_get_msg" in rejected["failed"],
            "missing Linux FT capability was not reported",
        )

        missing_auth_info = linux_runtime_report()
        del missing_auth_info["bridge_probes"]["abi0"]["stdout_json"]["responses"]["auth_info"]
        missing_auth_info_path = write_json(work / "missing_auth_info_linux.json", missing_auth_info)
        rejected = readiness.validate_linux_runtime_report(missing_auth_info_path, manifest)
        require(not rejected["ok"], "Linux runtime report without auth-info evidence was accepted")
        require("abi0_auth_info_ok" in rejected["failed"], "missing auth-info evidence was not reported")

        missing_source_smoke = linux_runtime_report()
        del missing_source_smoke["bridge_probes"]["abi1"]["stdout_json"]["responses"]["source_smoke"]
        missing_source_smoke_path = write_json(work / "missing_source_smoke_linux.json", missing_source_smoke)
        rejected = readiness.validate_linux_runtime_report(missing_source_smoke_path, manifest)
        require(not rejected["ok"], "Linux runtime report without source-smoke evidence was accepted")
        require("abi1_source_smoke_present" in rejected["failed"], "missing source-smoke evidence was not reported")

        missing_source_local_tunnel_smoke = linux_runtime_report()
        del missing_source_local_tunnel_smoke["bridge_probes"]["abi1"]["stdout_json"]["responses"]["source_local_tunnel_smoke"]
        missing_source_local_tunnel_smoke_path = write_json(
            work / "missing_source_local_tunnel_smoke_linux.json",
            missing_source_local_tunnel_smoke,
        )
        rejected = readiness.validate_linux_runtime_report(missing_source_local_tunnel_smoke_path, manifest)
        require(not rejected["ok"], "Linux runtime report without source local tunnel evidence was accepted")
        require(
            "abi1_source_local_tunnel_smoke_present" in rejected["failed"],
            "missing source local tunnel evidence was not reported",
        )

        wrong_source_local_tunnel_recv = linux_runtime_report()
        wrong_source_local_tunnel_recv["bridge_probes"]["abi1"]["stdout_json"]["responses"]["source_local_tunnel_smoke"][
            "recv_message"
        ]["__binary_text"] = "{\"result\":0,\"sequence\":1,\"reply\":\"wrong\"}\n"
        wrong_source_local_tunnel_recv_path = write_json(
            work / "wrong_source_local_tunnel_recv_linux.json",
            wrong_source_local_tunnel_recv,
        )
        rejected = readiness.validate_linux_runtime_report(wrong_source_local_tunnel_recv_path, manifest)
        require(not rejected["ok"], "Linux runtime report with wrong source local tunnel recv response was accepted")
        require(
            "abi1_source_local_tunnel_recv_message_response" in rejected["failed"],
            "wrong source local tunnel recv response was not reported",
        )

        missing_cloud_smoke = linux_runtime_report()
        del missing_cloud_smoke["bridge_probes"]["abi1"]["stdout_json"]["responses"]["cloud_smoke"]
        missing_cloud_smoke_path = write_json(work / "missing_cloud_smoke_linux.json", missing_cloud_smoke)
        rejected = readiness.validate_linux_runtime_report(missing_cloud_smoke_path, manifest)
        require(not rejected["ok"], "Linux runtime report without cloud-smoke evidence was accepted")
        require("abi1_cloud_smoke_present" in rejected["failed"], "missing cloud-smoke evidence was not reported")

        linux_direct_dir = work / "linux_libstdcxx"
        linux_direct_path = write_json(linux_direct_dir / "linux_libstdcxx_candidate_report.json", linux_libstdcxx_report(linux_direct_dir))
        accepted = readiness.validate_linux_libstdcxx_report(linux_direct_path)
        require(accepted["ok"], f"good Linux libstdc++ direct-load report was rejected: {accepted}")

        stale_linux_direct = linux_libstdcxx_report(work / "stale_linux_libstdcxx")
        stale_linux_direct["inputs"]["network_shim"]["sha256"] = "old-network-shim"
        stale_linux_direct_path = write_json(work / "stale_linux_libstdcxx_report.json", stale_linux_direct)
        rejected = readiness.validate_linux_libstdcxx_report(stale_linux_direct_path)
        require(not rejected["ok"], "Linux libstdc++ report with stale source hash was accepted")
        require(
            "network_shim_hash_matches_current_source" in rejected["failed"],
            "stale Linux libstdc++ source hash was not reported",
        )

        weak_linux_direct = linux_libstdcxx_report(work / "weak_linux_libstdcxx")
        weak_linux_direct["checks"]["network_cxx_abi"]["payload"]["inferred"] = "libc++"
        weak_linux_direct_path = write_json(work / "weak_linux_libstdcxx_report.json", weak_linux_direct)
        rejected = readiness.validate_linux_libstdcxx_report(weak_linux_direct_path)
        require(not rejected["ok"], "Linux libstdc++ report with libc++ ABI was accepted")
        require("network_cxx_abi" in rejected["failed"], "weak Linux libstdc++ ABI was not reported")

        smoke = write_json(work / "local_smoke.json", local_smoke_summary())
        accepted = readiness.validate_local_smoke_summary(smoke)
        require(accepted["ok"], f"good local smoke summary was rejected: {accepted}")

        missing_preflight = local_smoke_summary()
        missing_preflight["checks"]["preflight_cpp_signature_mirror"] = False
        missing_preflight_path = write_json(work / "missing_preflight_smoke.json", missing_preflight)
        rejected = readiness.validate_local_smoke_summary(missing_preflight_path)
        require(not rejected["ok"], "local smoke summary without signature preflight was accepted")
        require("check_preflight_cpp_signature_mirror" in rejected["failed"], "local smoke rejection missed signature preflight")

        invalid_smoke = work / "invalid_smoke.json"
        invalid_smoke.write_text("transcripts match\n{}\n", encoding="utf-8")
        rejected = readiness.validate_local_smoke_summary(invalid_smoke)
        require(not rejected["ok"], "invalid local smoke JSON was accepted")

        feature_parity = readiness.validate_full_compatibility_feature_parity()
        require(not feature_parity["ok"], "default full-compatibility feature parity unexpectedly passed")
        require(feature_parity["required"], "full-compatibility feature parity is not marked required")
        require(
            feature_parity["failed"] == [
                "camera_source_streaming",
                "cloud_service_feature_parity",
                "non_ftps_tunnel_feature_parity",
            ],
            f"full-compatibility feature failures drifted: {feature_parity}",
        )
        require(
            all(gap.get("current_evidence") and gap.get("blocking_probe") and gap.get("needed_evidence") for gap in feature_parity["gaps"]),
            "full-compatibility feature gaps are missing actionable evidence fields",
        )

        source_streaming_feature = readiness.validate_full_compatibility_feature_parity({
            "source_streaming_parity_ok": True,
        })
        require(not source_streaming_feature["ok"], "source streaming evidence unexpectedly satisfied all feature parity")
        require(
            source_streaming_feature["checks"]["camera_source_streaming"],
            f"source streaming evidence did not satisfy camera/source feature parity: {source_streaming_feature}",
        )
        require(
            source_streaming_feature["failed"] == [
                "cloud_service_feature_parity",
                "non_ftps_tunnel_feature_parity",
            ],
            f"source streaming evidence reported unexpected feature failures: {source_streaming_feature}",
        )

        source_control_tunnel_feature = readiness.validate_full_compatibility_feature_parity({
            "source_control_tunnel_parity_ok": True,
        })
        require(not source_control_tunnel_feature["ok"], "source control-tunnel evidence unexpectedly satisfied all feature parity")
        require(
            source_control_tunnel_feature["checks"]["non_ftps_tunnel_feature_parity"],
            f"source control-tunnel evidence did not satisfy non-FTPS tunnel feature parity: {source_control_tunnel_feature}",
        )
        require(
            source_control_tunnel_feature["failed"] == [
                "camera_source_streaming",
                "cloud_service_feature_parity",
            ],
            f"source control-tunnel evidence reported unexpected feature failures: {source_control_tunnel_feature}",
        )

        cloud_service_feature = readiness.validate_full_compatibility_feature_parity({
            "cloud_service_parity_ok": True,
        })
        require(not cloud_service_feature["ok"], "cloud service evidence unexpectedly satisfied all feature parity")
        require(
            cloud_service_feature["checks"]["cloud_service_feature_parity"],
            f"cloud service evidence did not satisfy cloud/service feature parity: {cloud_service_feature}",
        )
        require(
            cloud_service_feature["failed"] == [
                "camera_source_streaming",
                "non_ftps_tunnel_feature_parity",
            ],
            f"cloud service evidence reported unexpected feature failures: {cloud_service_feature}",
        )

        deferred_report = {
            "blockers": [
                "official_parity",
                "real_printer_parity_inputs",
                "full_compatibility_feature_parity",
            ],
            "gates": {
                "official_parity": {"failed": ["full_ft_contract_evidence"]},
                "real_printer_parity_inputs": {"failed": []},
                "full_compatibility_feature_parity": {
                    "failed": [
                        "camera_source_streaming",
                        "cloud_service_feature_parity",
                        "non_ftps_tunnel_feature_parity",
                    ],
                },
            },
        }
        deferred = readiness.classify_deferred_blockers(
            deferred_report,
            defer_manual_printer_parity=True,
            defer_authorized_cloud_parity=False,
        )
        require(
            deferred["non_deferred_blockers"] == ["full_compatibility_feature_parity"],
            f"manual deferral hid non-manual blockers: {deferred}",
        )
        require(
            deferred["partially_deferred_blockers"]["full_compatibility_feature_parity"]["remaining"] == ["cloud_service_feature_parity"],
            f"manual deferral did not isolate cloud blocker: {deferred}",
        )
        deferred_all = readiness.classify_deferred_blockers(
            deferred_report,
            defer_manual_printer_parity=True,
            defer_authorized_cloud_parity=True,
        )
        require(deferred_all["non_deferred_ok"], f"explicit external deferrals left blockers: {deferred_all}")

        original_gaps = readiness.FULL_COMPATIBILITY_GAPS
        try:
            readiness.FULL_COMPATIBILITY_GAPS = tuple(
                {**gap, "implemented": True}
                for gap in original_gaps
            )
            accepted_feature_parity = readiness.validate_full_compatibility_feature_parity()
            require(accepted_feature_parity["ok"], f"implemented feature parity fixture was rejected: {accepted_feature_parity}")
            require(accepted_feature_parity["failed"] == [], "implemented feature parity fixture reported failures")
            require(
                all(accepted_feature_parity["checks"].values()),
                "implemented feature parity fixture did not mark every check true",
            )
        finally:
            readiness.FULL_COMPATIBILITY_GAPS = original_gaps

    print("readiness report validation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
