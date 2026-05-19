#!/usr/bin/env python3
import argparse
import contextlib
import http.server
import json
import os
import pathlib
import platform
import subprocess
import sys
import threading


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "tools/bambu_network_contract_tests"
PLUGIN_DIR = ROOT / "tools/bambu_network_rust_plugin"
CONTRACT_BUILD = ROOT / "build/bambu_network_contract_tests"
PLUGIN_BUILD = ROOT / "build/bambu_network_rust_plugin"


def run(cmd: list[str], *, capture: bool = False, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    print("+ " + " ".join(cmd), file=sys.stderr)
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture,
        env=env,
    )


def dylib_suffix() -> str:
    system = platform.system()
    if system == "Darwin":
        return ".dylib"
    if system == "Windows":
        return ".dll"
    return ".so"


def load_json_from_command(cmd: list[str], *, env: dict[str, str] | None = None) -> dict:
    completed = run(cmd, capture=True, env=env)
    sys.stderr.write(completed.stderr)
    sys.stderr.write(completed.stdout)
    data = json.loads(completed.stdout)
    if not isinstance(data, dict):
        raise RuntimeError("expected JSON object")
    return data


class MockCloudServiceHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_fixture_response()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        self.send_fixture_response()

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_fixture_response(self) -> None:
        payload = fixture_payload(self.path)
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def fixture_payload(path: str) -> dict:
    if path == "/health":
        return {"ok": True}
    if path.endswith("/bind-ticket"):
        return {"ticket": "mock-bind-ticket"}
    if path.endswith("/info"):
        return {"identifier": 1001}
    if path.endswith("/plate-index"):
        return {"plate_index": 0}
    if path.endswith("/home-url"):
        return {"url": "https://makerworld.com/"}
    if path.endswith("/detail-url"):
        return {"url": "https://makerworld.com/en/models/mock"}
    if path.endswith("/publish-url"):
        return {"url": "https://makerworld.com/en/upload"}
    if path.endswith("/token"):
        return {"access_token": "mock-access-token", "refresh_token": "mock-refresh-token", "expires_in": 3600}
    if path.endswith("/profile"):
        return {"id": "1001", "name": "Praveen"}
    if path.endswith("/print-info"):
        return {"printers": [{"dev_id": "mock-dev"}]}
    if path.endswith("/tasks"):
        return {"tasks": []}
    if path.endswith("/messages"):
        return {"messages": []}
    if path.endswith("/firmware"):
        return {"firmware": []}
    if path.endswith("/bind-status"):
        return {"devices": []}
    if path.endswith("/subtask"):
        return {"subtasks": []}
    if path.endswith("/slice"):
        return {"slices": []}
    if path.endswith("/rating"):
        return {"ratings": []}
    return {"ok": True}


@contextlib.contextmanager
def run_mock_cloud_service():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockCloudServiceHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_preflight(checks: dict[str, bool], name: str, cmd: list[str]) -> None:
    completed = run(cmd, capture=True)
    sys.stderr.write(completed.stderr)
    sys.stderr.write(completed.stdout)
    checks[name] = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--plugin-build-dir", type=pathlib.Path, default=PLUGIN_BUILD)
    args = parser.parse_args()

    if not args.skip_build:
        run(["cmake", "-S", str(CONTRACT_DIR), "-B", str(CONTRACT_BUILD)])
        run(["cmake", "--build", str(CONTRACT_BUILD)])
        run(["cmake", "-S", str(PLUGIN_DIR), "-B", str(PLUGIN_BUILD)])
        run(["cmake", "--build", str(PLUGIN_BUILD)])

    preflight_checks = {}

    run_preflight(preflight_checks, "preflight_python_sources_compile", [
        "python3",
        "-m",
        "py_compile",
        str(CONTRACT_DIR / "bridge_rpc_probe.py"),
        str(CONTRACT_DIR / "assemble_macos_bridge_runtime.py"),
        str(CONTRACT_DIR / "assemble_candidate_linux_payload.py"),
        str(CONTRACT_DIR / "build_linux_libstdcxx_candidate.py"),
        str(CONTRACT_DIR / "capture_official_parity.py"),
        str(CONTRACT_DIR / "compare_transcripts.py"),
        str(CONTRACT_DIR / "generate_required_symbols.py"),
        str(CONTRACT_DIR / "find_bambu_printers.py"),
        str(CONTRACT_DIR / "run_authorized_cloud_parity.py"),
        str(CONTRACT_DIR / "run_candidate_smoke.py"),
        str(CONTRACT_DIR / "run_real_printer_parity.py"),
        str(CONTRACT_DIR / "run_release_readiness.py"),
        str(CONTRACT_DIR / "run_source_control_tls_loopback_parity.py"),
        str(CONTRACT_DIR / "run_source_control_tunnel_parity.py"),
        str(CONTRACT_DIR / "run_source_rtsp_loopback_parity.py"),
        str(CONTRACT_DIR / "run_source_streaming_parity.py"),
        str(CONTRACT_DIR / "verify_abi_mirror.py"),
        str(CONTRACT_DIR / "verify_clean_room_artifacts.py"),
        str(CONTRACT_DIR / "verify_completion_audit.py"),
        str(CONTRACT_DIR / "verify_contract_surface_coverage.py"),
        str(CONTRACT_DIR / "verify_cpp_signature_mirror.py"),
        str(CONTRACT_DIR / "verify_elf_cxx_abi.py"),
        str(CONTRACT_DIR / "verify_elf_exports.py"),
        str(CONTRACT_DIR / "verify_linux_bridge_runtime.py"),
        str(CONTRACT_DIR / "verify_macos_release_runtime.py"),
        str(CONTRACT_DIR / "verify_readiness_report_validation.py"),
        str(CONTRACT_DIR / "verify_authorized_cloud_parity_dry_run.py"),
        str(CONTRACT_DIR / "verify_real_printer_parity_dry_run.py"),
        str(CONTRACT_DIR / "verify_release_readiness_report.py"),
        str(CONTRACT_DIR / "verify_source_control_tunnel_parity_dry_run.py"),
        str(CONTRACT_DIR / "verify_source_streaming_parity_dry_run.py"),
    ])
    run_preflight(preflight_checks, "preflight_symbol_manifest_sources", [
        "python3",
        str(CONTRACT_DIR / "generate_required_symbols.py"),
        "--check",
    ])
    run_preflight(preflight_checks, "preflight_abi_mirror", ["python3", str(CONTRACT_DIR / "verify_abi_mirror.py")])
    run_preflight(preflight_checks, "preflight_cpp_signature_mirror", [
        "python3",
        str(CONTRACT_DIR / "verify_cpp_signature_mirror.py"),
    ])
    run_preflight(preflight_checks, "preflight_contract_surface_coverage", [
        "python3",
        str(CONTRACT_DIR / "verify_contract_surface_coverage.py"),
    ])
    run_preflight(preflight_checks, "preflight_clean_room_artifact_validation", [
        "python3",
        str(CONTRACT_DIR / "verify_clean_room_artifacts.py"),
        "--self-test",
    ])
    run_preflight(preflight_checks, "preflight_completion_audit_validation", [
        "python3",
        str(CONTRACT_DIR / "verify_completion_audit.py"),
        "--self-test",
    ])
    run_preflight(preflight_checks, "preflight_readiness_report_validation", [
        "python3",
        str(CONTRACT_DIR / "verify_readiness_report_validation.py"),
    ])
    run_preflight(preflight_checks, "preflight_release_readiness_report_validation", [
        "python3",
        str(CONTRACT_DIR / "verify_release_readiness_report.py"),
        "--self-test",
    ])
    run_preflight(preflight_checks, "preflight_authorized_cloud_parity_dry_run", [
        "python3",
        str(CONTRACT_DIR / "verify_authorized_cloud_parity_dry_run.py"),
    ])
    run_preflight(preflight_checks, "preflight_source_streaming_parity_dry_run", [
        "python3",
        str(CONTRACT_DIR / "verify_source_streaming_parity_dry_run.py"),
    ])
    run_preflight(preflight_checks, "preflight_source_control_tunnel_parity_dry_run", [
        "python3",
        str(CONTRACT_DIR / "verify_source_control_tunnel_parity_dry_run.py"),
    ])
    run_preflight(preflight_checks, "preflight_real_printer_parity_dry_run", [
        "python3",
        str(CONTRACT_DIR / "verify_real_printer_parity_dry_run.py"),
    ])

    suffix = dylib_suffix()
    plugin_build = args.plugin_build_dir
    network_lib = plugin_build / f"libbambu_networking{suffix}"
    source_lib = plugin_build / f"libBambuSource{suffix}"
    contract_probe = CONTRACT_BUILD / "bambu_network_contract_probe"
    lifecycle_probe = CONTRACT_BUILD / "bambu_network_lifecycle_probe"
    callback_probe = CONTRACT_BUILD / "bambu_network_callback_probe"
    unsupported_probe = CONTRACT_BUILD / "bambu_network_unsupported_probe"
    cloud_service_probe = CONTRACT_BUILD / "bambu_network_cloud_service_probe"
    source_behavior_probe = CONTRACT_BUILD / "bambu_network_source_behavior_probe"
    source_streaming_probe = CONTRACT_BUILD / "bambu_network_source_streaming_probe"
    source_local_tunnel_probe = CONTRACT_BUILD / "bambu_network_source_local_tunnel_probe"
    print_job_probe = CONTRACT_BUILD / "bambu_network_print_job_probe"
    event_bridge_probe = CONTRACT_BUILD / "bambu_network_event_bridge_probe"
    discovery_probe = CONTRACT_BUILD / "bambu_network_discovery_probe"
    camera_url_probe = CONTRACT_BUILD / "bambu_network_camera_url_probe"
    ft_behavior_probe = CONTRACT_BUILD / "bambu_network_ft_behavior_probe"

    network_symbols = load_json_from_command([
        str(contract_probe),
        "--plugin",
        str(network_lib),
        "--symbols",
        str(CONTRACT_DIR / "required_symbols.txt"),
        "--json",
    ])
    source_symbols = load_json_from_command([
        str(contract_probe),
        "--plugin",
        str(source_lib),
        "--symbols",
        str(CONTRACT_DIR / "source_symbols.txt"),
        "--json",
    ])
    lifecycle = load_json_from_command([
        str(lifecycle_probe),
        "--plugin",
        str(network_lib),
        "--log-dir",
        "/tmp/bambu-rust-plugin-smoke-lifecycle",
    ])
    callback_a = load_json_from_command([
        str(callback_probe),
        "--plugin",
        str(network_lib),
        "--log-dir",
        "/tmp/bambu-rust-plugin-smoke-callback-a",
    ])
    callback_b_path = pathlib.Path("/tmp/bambu-rust-plugin-smoke-callback-b.json")
    callback_b = load_json_from_command([
        str(callback_probe),
        "--plugin",
        str(network_lib),
        "--log-dir",
        "/tmp/bambu-rust-plugin-smoke-callback-b",
    ])
    callback_a_path = pathlib.Path("/tmp/bambu-rust-plugin-smoke-callback-a.json")
    callback_a_path.write_text(json.dumps(callback_a, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    callback_b_path.write_text(json.dumps(callback_b, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    callback_compare = run([
        "python3",
        str(CONTRACT_DIR / "compare_transcripts.py"),
        str(callback_a_path),
        str(callback_b_path),
    ], capture=True)
    sys.stderr.write(callback_compare.stderr)
    sys.stderr.write(callback_compare.stdout)
    unsupported = load_json_from_command([
        str(unsupported_probe),
        "--network-plugin",
        str(network_lib),
        "--source-plugin",
        str(source_lib),
        "--log-dir",
        "/tmp/bambu-rust-plugin-smoke-unsupported",
    ])
    cloud_service = load_json_from_command([
        str(cloud_service_probe),
        "--plugin",
        str(network_lib),
        "--log-dir",
        "/tmp/bambu-rust-plugin-smoke-cloud-service",
    ])
    cloud_user_info_path = pathlib.Path("/tmp/bambu-rust-plugin-smoke-cloud-user-info.json")
    cloud_user_info_path.write_text(
        json.dumps({
            "command": "user_login",
            "data": {
                "access_token": "token-redacted",
                "refresh_token": "refresh-redacted",
                "user_id": "1001",
                "username": "praveen",
                "nickname": "Praveen",
                "avatar": "https://example.invalid/avatar.png",
            },
        }, sort_keys=True),
        encoding="utf-8",
    )
    cloud_service_login = load_json_from_command([
        str(cloud_service_probe),
        "--plugin",
        str(network_lib),
        "--log-dir",
        "/tmp/bambu-rust-plugin-smoke-cloud-service-login",
        "--user-info-file",
        str(cloud_user_info_path),
    ])
    cloud_service_fixture_env = os.environ.copy()
    cloud_service_fixture_env["BAMBU_NETWORK_ENABLE_SYNTHETIC_CLOUD_SERVICE"] = "1"
    cloud_service_fixture_env["BAMBU_NETWORK_SYNTHETIC_TICKET"] = "synthetic-ticket"
    cloud_service_fixture_env["BAMBU_NETWORK_SYNTHETIC_ACCESS_TOKEN"] = "synthetic-access-token"
    cloud_service_fixture = load_json_from_command([
        str(cloud_service_probe),
        "--plugin",
        str(network_lib),
        "--log-dir",
        "/tmp/bambu-rust-plugin-smoke-cloud-service-fixture",
        "--user-info-file",
        str(cloud_user_info_path),
        "--allow-network",
        "--expect-success",
        "--ticket-env",
        "BAMBU_NETWORK_SYNTHETIC_TICKET",
        "--access-token-env",
        "BAMBU_NETWORK_SYNTHETIC_ACCESS_TOKEN",
    ], env=cloud_service_fixture_env)
    cloud_service_http_fixture_env = os.environ.copy()
    cloud_service_http_fixture_env["BAMBU_NETWORK_CLOUD_TIMEOUT_SECS"] = "2"
    cloud_service_http_fixture_env["BAMBU_NETWORK_HTTP_TICKET"] = "mock-ticket"
    cloud_service_http_fixture_env["BAMBU_NETWORK_HTTP_ACCESS_TOKEN"] = "mock-access-token"
    with run_mock_cloud_service() as mock_cloud_service:
        cloud_service_http_fixture_env["BAMBU_NETWORK_CLOUD_BASE_URL"] = mock_cloud_service
        cloud_service_http_fixture = load_json_from_command([
            str(cloud_service_probe),
            "--plugin",
            str(network_lib),
            "--log-dir",
            "/tmp/bambu-rust-plugin-smoke-cloud-service-http-fixture",
            "--user-info-file",
            str(cloud_user_info_path),
            "--allow-network",
            "--expect-success",
            "--ticket-env",
            "BAMBU_NETWORK_HTTP_TICKET",
            "--access-token-env",
            "BAMBU_NETWORK_HTTP_ACCESS_TOKEN",
        ], env=cloud_service_http_fixture_env)
    cloud_service_backend_fixture_env = os.environ.copy()
    cloud_service_backend_fixture_env.pop("BAMBU_NETWORK_CLOUD_BASE_URL", None)
    cloud_service_backend_fixture_env.pop("BAMBU_NETWORK_ENABLE_SYNTHETIC_CLOUD_SERVICE", None)
    cloud_service_backend_fixture_env["BAMBU_NETWORK_CLOUD_TIMEOUT_SECS"] = "2"
    cloud_service_backend_fixture_env["BAMBU_NETWORK_BACKEND_TICKET"] = "mock-ticket"
    cloud_service_backend_fixture_env["BAMBU_NETWORK_BACKEND_ACCESS_TOKEN"] = "mock-access-token"
    with run_mock_cloud_service() as mock_cloud_service:
        cloud_user_info_backend_path = pathlib.Path("/tmp/bambu-rust-plugin-smoke-cloud-user-info-backend.json")
        cloud_user_info_backend_path.write_text(
            json.dumps({
                "command": "user_login",
                "data": {
                    "access_token": "token-redacted",
                    "refresh_token": "refresh-redacted",
                    "backend_url": mock_cloud_service,
                    "user_id": "1001",
                    "username": "praveen",
                    "nickname": "Praveen",
                    "avatar": "https://example.invalid/avatar.png",
                },
            }, sort_keys=True),
            encoding="utf-8",
        )
        cloud_service_backend_fixture = load_json_from_command([
            str(cloud_service_probe),
            "--plugin",
            str(network_lib),
            "--log-dir",
            "/tmp/bambu-rust-plugin-smoke-cloud-service-backend-fixture",
            "--user-info-file",
            str(cloud_user_info_backend_path),
            "--allow-network",
            "--expect-success",
            "--ticket-env",
            "BAMBU_NETWORK_BACKEND_TICKET",
            "--access-token-env",
            "BAMBU_NETWORK_BACKEND_ACCESS_TOKEN",
        ], env=cloud_service_backend_fixture_env)
    source_behavior = load_json_from_command([
        str(source_behavior_probe),
        "--source-plugin",
        str(source_lib),
    ])
    source_streaming_env = os.environ.copy()
    source_streaming_env["BAMBU_SOURCE_ENABLE_SYNTHETIC_STREAM"] = "1"
    source_streaming = load_json_from_command([
        str(source_streaming_probe),
        "--source-plugin",
        str(source_lib),
        "--url",
        "bambu:///rtsps___bblp:redacted@synthetic.local/streaming/live/1?proto=rtsps",
        "--expect-success",
    ], env=source_streaming_env)
    source_local_tunnel = load_json_from_command([
        str(source_local_tunnel_probe),
        "--source-plugin",
        str(source_lib),
    ])
    print_job = load_json_from_command([
        str(print_job_probe),
        "--plugin",
        str(network_lib),
        "--mode",
        "upload-only",
        "--dev-id",
        "dev",
        "--dev-ip",
        "127.0.0.1",
        "--file",
        "/tmp/bambu-rust-plugin-smoke-missing-file.3mf",
        "--use-ssl-for-ftp",
        "false",
    ])
    event_bridge = load_json_from_command([
        str(event_bridge_probe),
        "--plugin",
        str(network_lib),
        "--log-dir",
        "/tmp/bambu-rust-plugin-smoke-event-bridge",
    ])
    discovery = load_json_from_command([
        str(discovery_probe),
        "--plugin",
        str(network_lib),
        "--log-dir",
        "/tmp/bambu-rust-plugin-smoke-discovery",
    ])
    camera_url = load_json_from_command([
        str(camera_url_probe),
        "--plugin",
        str(network_lib),
        "--log-dir",
        "/tmp/bambu-rust-plugin-smoke-camera-url",
    ])
    ft_behavior = load_json_from_command([
        str(ft_behavior_probe),
        "--plugin",
        str(network_lib),
    ])

    checks = {
        **preflight_checks,
        "network_symbols": network_symbols.get("ok") is True,
        "source_symbols": source_symbols.get("ok") is True,
        "lifecycle_agent_created": lifecycle.get("agent_created") is True,
        "lifecycle_init_log_result": lifecycle.get("init_log_result") == 0,
        "lifecycle_set_config_dir_result": lifecycle.get("set_config_dir_result") == 0,
        "lifecycle_set_country_code_result": lifecycle.get("set_country_code_result") == 0,
        "lifecycle_start_result": lifecycle.get("start_result") == 0,
        "lifecycle_destroy_result": lifecycle.get("destroy_result") == 0,
        "callback_agent_created": callback_a.get("agent_created") is True,
        "callback_no_missing_symbols": callback_a.get("missing_symbols") == [],
        "callback_transcripts_match": True,
        "unsupported_no_missing_symbols": unsupported.get("missing_symbols") == [],
        "unsupported_destroy_result": unsupported.get("destroy_result") == 0,
        "cloud_service_no_missing_symbols": cloud_service.get("missing_symbols") == [],
        "cloud_service_agent_created": cloud_service.get("agent_created") is True,
        "cloud_service_offline_ok": cloud_service.get("ok") is True,
        "cloud_service_network_disabled": cloud_service.get("allow_network") is False,
        "cloud_service_destroy_result": cloud_service.get("destroy_result") == 0,
        "cloud_service_login_no_missing_symbols": cloud_service_login.get("missing_symbols") == [],
        "cloud_service_login_agent_created": cloud_service_login.get("agent_created") is True,
        "cloud_service_login_offline_ok": cloud_service_login.get("ok") is True,
        "cloud_service_login_network_disabled": cloud_service_login.get("allow_network") is False,
        "cloud_service_login_change_user": cloud_service_login.get("results", {}).get("change_user") == 0,
        "cloud_service_login_is_user_login": cloud_service_login.get("results", {}).get("is_user_login") is True,
        "cloud_service_login_semantic": cloud_service_login.get("semantic", {}).get("login_ok") is True,
        "cloud_service_login_callback": cloud_service_login.get("callbacks", {}).get("user_login", 0) >= 2,
        "cloud_service_login_logout": cloud_service_login.get("results", {}).get("user_logout") == 0,
        "cloud_service_login_destroy_result": cloud_service_login.get("destroy_result") == 0,
        "cloud_service_fixture_ok": cloud_service_fixture.get("ok") is True,
        "cloud_service_fixture_network_allowed": cloud_service_fixture.get("allow_network") is True,
        "cloud_service_fixture_expect_success": cloud_service_fixture.get("expect_success") is True,
        "cloud_service_fixture_connect_server": cloud_service_fixture.get("results", {}).get("connect_server") == 0,
        "cloud_service_fixture_semantic": cloud_service_fixture.get("semantic", {}).get("service_ok") is True,
        "cloud_service_fixture_http": cloud_service_fixture.get("contract", {}).get("get_user_print_info_http_code") == 200,
        "cloud_service_fixture_body": cloud_service_fixture.get("contract", {}).get("get_user_print_info_body", {}).get("looks_json") is True,
        "cloud_service_fixture_token": cloud_service_fixture.get("contract", {}).get("get_my_token_body", {}).get("looks_json") is True,
        "cloud_service_fixture_profile": cloud_service_fixture.get("contract", {}).get("get_my_profile_body", {}).get("looks_json") is True,
        "cloud_service_fixture_callback_exports": (
            cloud_service_fixture.get("contract", {}).get("get_design_staffpick_callback_count") == 1
            and cloud_service_fixture.get("contract", {}).get("get_mw_user_preference_callback_count") == 1
            and cloud_service_fixture.get("contract", {}).get("get_mw_user_4ulist_callback_count") == 1
            and cloud_service_fixture.get("contract", {}).get("get_hms_snapshot_callback_count") == 1
            and cloud_service_fixture.get("contract", {}).get("get_hms_snapshot_http_code") == 200
        ),
        "cloud_service_http_fixture_ok": cloud_service_http_fixture.get("ok") is True,
        "cloud_service_http_fixture_network_allowed": cloud_service_http_fixture.get("allow_network") is True,
        "cloud_service_http_fixture_expect_success": cloud_service_http_fixture.get("expect_success") is True,
        "cloud_service_http_fixture_connect_server": cloud_service_http_fixture.get("results", {}).get("connect_server") == 0,
        "cloud_service_http_fixture_server_connected": cloud_service_http_fixture.get("results", {}).get("is_server_connected") is True,
        "cloud_service_http_fixture_callback": cloud_service_http_fixture.get("callbacks", {}).get("server_connected", 0) >= 1,
        "cloud_service_http_fixture_semantic": cloud_service_http_fixture.get("semantic", {}).get("service_ok") is True,
        "cloud_service_http_fixture_http": cloud_service_http_fixture.get("contract", {}).get("get_user_print_info_http_code") == 200,
        "cloud_service_http_fixture_body": cloud_service_http_fixture.get("contract", {}).get("get_user_print_info_body", {}).get("looks_json") is True,
        "cloud_service_http_fixture_token": cloud_service_http_fixture.get("contract", {}).get("get_my_token_body", {}).get("looks_json") is True,
        "cloud_service_http_fixture_profile": cloud_service_http_fixture.get("contract", {}).get("get_my_profile_body", {}).get("looks_json") is True,
        "cloud_service_http_fixture_callback_exports": (
            cloud_service_http_fixture.get("contract", {}).get("get_design_staffpick_callback_count") == 1
            and cloud_service_http_fixture.get("contract", {}).get("get_mw_user_preference_callback_count") == 1
            and cloud_service_http_fixture.get("contract", {}).get("get_mw_user_4ulist_callback_count") == 1
            and cloud_service_http_fixture.get("contract", {}).get("get_hms_snapshot_callback_count") == 1
            and cloud_service_http_fixture.get("contract", {}).get("get_hms_snapshot_http_code") == 200
        ),
        "cloud_service_backend_fixture_ok": cloud_service_backend_fixture.get("ok") is True,
        "cloud_service_backend_fixture_network_allowed": cloud_service_backend_fixture.get("allow_network") is True,
        "cloud_service_backend_fixture_expect_success": cloud_service_backend_fixture.get("expect_success") is True,
        "cloud_service_backend_fixture_connect_server": cloud_service_backend_fixture.get("results", {}).get("connect_server") == 0,
        "cloud_service_backend_fixture_server_connected": cloud_service_backend_fixture.get("results", {}).get("is_server_connected") is True,
        "cloud_service_backend_fixture_callback": cloud_service_backend_fixture.get("callbacks", {}).get("server_connected", 0) >= 1,
        "cloud_service_backend_fixture_semantic": cloud_service_backend_fixture.get("semantic", {}).get("service_ok") is True,
        "cloud_service_backend_fixture_http": cloud_service_backend_fixture.get("contract", {}).get("get_user_print_info_http_code") == 200,
        "cloud_service_backend_fixture_body": cloud_service_backend_fixture.get("contract", {}).get("get_user_print_info_body", {}).get("looks_json") is True,
        "cloud_service_backend_fixture_token": cloud_service_backend_fixture.get("contract", {}).get("get_my_token_body", {}).get("looks_json") is True,
        "cloud_service_backend_fixture_profile": cloud_service_backend_fixture.get("contract", {}).get("get_my_profile_body", {}).get("looks_json") is True,
        "cloud_service_backend_fixture_callback_exports": (
            cloud_service_backend_fixture.get("contract", {}).get("get_design_staffpick_callback_count") == 1
            and cloud_service_backend_fixture.get("contract", {}).get("get_mw_user_preference_callback_count") == 1
            and cloud_service_backend_fixture.get("contract", {}).get("get_mw_user_4ulist_callback_count") == 1
            and cloud_service_backend_fixture.get("contract", {}).get("get_hms_snapshot_callback_count") == 1
            and cloud_service_backend_fixture.get("contract", {}).get("get_hms_snapshot_http_code") == 200
        ),
        "unsupported_invalid_cloud_json": unsupported.get("results", {}).get("send_message_invalid_json") == -19,
        "unsupported_invalid_local_json": unsupported.get("results", {}).get("send_message_to_printer_invalid_json") == -19,
        "unsupported_invalid_local_dev_id": unsupported.get("results", {}).get("send_message_to_printer_invalid_dev_id") == -19,
        "unsupported_sdcard_print_without_session": unsupported.get("results", {}).get("start_sdcard_print_without_session") == -4030,
        "unsupported_invalid_sdcard_print": unsupported.get("results", {}).get("start_sdcard_print_invalid_dev_id") == -19,
        "unsupported_start_send_gcode_missing_file_name": unsupported.get("results", {}).get("start_send_gcode_missing_file_name") == -19,
        "unsupported_start_send_gcode_nonexistent_file": unsupported.get("results", {}).get("start_send_gcode_nonexistent_file") == -5010,
        "unsupported_start_local_print_nonexistent_file": unsupported.get("results", {}).get("start_local_print_nonexistent_file") == -4020,
        "unsupported_source_valid_camera_create": unsupported.get("results", {}).get("Bambu_Create_valid_camera") == 0,
        "unsupported_source_valid_camera_open": unsupported.get("results", {}).get("Bambu_Open_valid_camera") == 0,
        "unsupported_source_valid_camera_error": unsupported.get("results", {}).get("Bambu_GetLastErrorMsg_valid_camera") == "Unknown error!",
        "unsupported_ft_abi_version": unsupported.get("results", {}).get("ft_abi_version") == 1,
        "unsupported_ft_job_create": unsupported.get("results", {}).get("ft_job_create") == -6,
        "unsupported_ft_job_created_handle": unsupported.get("results", {}).get("ft_job_created_handle") is False,
        "unsupported_ft_tunnel_start_connect": unsupported.get("results", {}).get("ft_tunnel_start_connect_null") == -1,
        "unsupported_ft_tunnel_set_status": unsupported.get("results", {}).get("ft_tunnel_set_status_cb_null") == -1,
        "source_behavior_no_missing_symbols": source_behavior.get("missing_symbols") == [],
        "source_behavior_ok": source_behavior.get("ok") is True,
        "source_behavior_open_camera": source_behavior.get("results", {}).get("Bambu_Open_camera") == 0,
        "source_behavior_read_sample": source_behavior.get("results", {}).get("Bambu_ReadSample_camera") == 2,
        "source_behavior_recv_zeroed": source_behavior.get("results", {}).get("Bambu_RecvMessage_camera_zeroed") is False,
        "source_streaming_fixture_ok": source_streaming.get("ok") is True,
        "source_streaming_fixture_opened": source_streaming.get("semantic", {}).get("opened") is True,
        "source_streaming_fixture_started": source_streaming.get("semantic", {}).get("stream_started") is True,
        "source_streaming_fixture_info": source_streaming.get("semantic", {}).get("stream_info_available") is True,
        "source_streaming_fixture_sample": source_streaming.get("semantic", {}).get("sample_read") is True,
        "source_streaming_fixture_sample_size": source_streaming.get("stream_contract", {}).get("sample_size_positive") is True,
        "source_local_tunnel_ok": source_local_tunnel.get("ok") is True,
        "source_local_tunnel_opened": source_local_tunnel.get("semantic", {}).get("opened") is True,
        "source_local_tunnel_started": source_local_tunnel.get("semantic", {}).get("stream_started") is True,
        "source_local_tunnel_send": source_local_tunnel.get("semantic", {}).get("send_ok") is True,
        "source_local_tunnel_server_received": source_local_tunnel.get("semantic", {}).get("server_received_message") is True,
        "source_local_tunnel_recv": source_local_tunnel.get("semantic", {}).get("recv_message_read") is True,
        "source_local_tunnel_recv_response": source_local_tunnel.get("semantic", {}).get("recv_message_contains_response") is True,
        "source_local_tunnel_recv_type": source_local_tunnel.get("semantic", {}).get("recv_message_type") is True,
        "source_local_tunnel_sample": source_local_tunnel.get("semantic", {}).get("sample_read") is True,
        "source_local_tunnel_response": source_local_tunnel.get("semantic", {}).get("sample_contains_response") is True,
        "print_job_no_missing_symbols": print_job.get("missing_symbols") == [],
        "print_job_agent_created": print_job.get("agent_created") is True,
        "print_job_missing_file_failure": print_job.get("job_result") == -5010,
        "print_job_status_events": [event.get("status") for event in print_job.get("status_events", [])] == [0, 1, 7],
        "print_job_error_status_code": (
            len(print_job.get("status_events", [])) == 3
            and print_job.get("status_events", [])[2].get("code") == -5010
        ),
        "print_job_cancel_checked": print_job.get("cancel_calls") == 1,
        "print_job_destroy_result": print_job.get("destroy_result") == 0,
        "print_job_ok": print_job.get("ok") is True,
        "event_bridge_no_missing_symbols": event_bridge.get("missing_symbols") == [],
        "event_bridge_payloads": event_bridge.get("payloads_ok") is True,
        "event_bridge_counters": event_bridge.get("counters_ok") is True,
        "event_bridge_destroy_result": event_bridge.get("destroy_result") == 0,
        "discovery_no_missing_symbols": discovery.get("missing_symbols") == [],
        "discovery_start_result": discovery.get("start_result") is True,
        "discovery_callback_received": discovery.get("callback_received") is True,
        "discovery_payload": discovery.get("payload_ok") is True,
        "discovery_destroy_result": discovery.get("destroy_result") == 0,
        "camera_url_no_missing_symbols": camera_url.get("missing_symbols") == [],
        "camera_url_empty_result": camera_url.get("empty_result") == -2,
        "camera_url_result": camera_url.get("camera_result") == 0,
        "camera_url_callback": camera_url.get("callback_calls") == 1,
        "camera_url_payload": camera_url.get("url_ok") is True,
        "camera_url_destroy_result": camera_url.get("destroy_result") == 0,
        "ft_behavior_ok": ft_behavior.get("ok") is True,
        "ft_behavior_no_missing_symbols": ft_behavior.get("missing_symbols") == [],
        "ft_behavior_connect_callback": ft_behavior.get("connection_success") is True,
        "ft_behavior_media_result": ft_behavior.get("media_result_ec") == 0,
        "ft_behavior_upload_missing_file_result": ft_behavior.get("upload_result_ec") == -3,
        "ft_behavior_upload_progress": ft_behavior.get("upload_msg_calls", 0) >= 1,
    }
    unsupported_results = unsupported.get("results", {})
    expected_unsupported_failures = [
        "refresh_connection",
        "start_subscribe",
        "stop_subscribe",
        "add_subscribe",
        "del_subscribe",
        "update_cert",
        "ping_bind",
        "bind_detect",
        "report_consent",
        "bind",
        "unbind",
        "set_user_selected_machine",
        "start_print",
        "get_user_presets",
        "put_setting",
        "get_setting_list",
        "get_setting_list2",
        "delete_setting",
        "set_extra_http_header",
        "get_my_message",
        "check_user_task_report",
        "get_user_print_info",
        "get_user_tasks",
        "get_printer_firmware",
        "get_task_plate_index",
        "get_user_info",
        "request_bind_ticket",
        "get_subtask_info",
        "get_slice_info",
        "query_bind_status",
        "modify_printer_name",
        "get_camera_url_for_golive",
        "get_design_staffpick",
        "start_publish",
        "get_model_publish_url",
        "get_subtask",
        "get_model_mall_home_url",
        "get_model_mall_detail_url",
        "get_my_token",
        "get_my_profile",
        "track_enable",
        "track_remove_files",
        "track_event",
        "track_header",
        "track_update_property",
        "track_get_property",
        "put_model_mall_rating",
        "get_oss_config",
        "put_rating_picture_oss",
        "get_model_mall_rating",
        "get_mw_user_preference",
        "get_mw_user_4ulist",
        "get_hms_snapshot",
    ]
    checks.update({
        f"unsupported_safe_failure_{name}": unsupported_results.get(name) == -2
        for name in expected_unsupported_failures
    })
    expected_empty_outputs = [
        "bind_detect_result_msg",
        "get_user_avatar",
        "get_user_selected_machine",
        "request_setting_id",
        "get_my_message_body",
        "get_user_print_info_body",
        "get_user_tasks_body",
        "get_printer_firmware_body",
        "request_bind_ticket_value",
        "get_subtask_info_task_json",
        "get_subtask_info_body",
        "get_slice_info_json",
        "query_bind_status_body",
        "start_publish_out",
        "get_model_publish_url_value",
        "get_model_mall_home_url_value",
        "get_model_mall_detail_url_value",
        "get_my_token_body",
        "get_my_profile_body",
        "track_get_property_value",
        "put_model_mall_rating_http_error",
        "get_oss_config_config",
        "get_oss_config_http_error",
        "put_rating_picture_oss_config",
        "put_rating_picture_oss_path",
        "put_rating_picture_oss_http_error",
        "get_model_mall_rating_value",
        "get_model_mall_rating_http_error",
    ]
    checks.update({
        f"unsupported_empty_output_{name}": unsupported_results.get(name) == ""
        for name in expected_empty_outputs
    })
    expected_zero_outputs = [
        "get_user_presets_size",
        "request_setting_id_http_code",
        "put_setting_http_code",
        "get_my_message_http_code",
        "check_user_task_report_task_id",
        "get_user_print_info_http_code",
        "get_printer_firmware_http_code",
        "get_user_info_identifier",
        "get_subtask_info_http_code",
        "query_bind_status_http_code",
        "get_my_token_http_code",
        "get_my_profile_http_code",
        "put_model_mall_rating_http_code",
        "get_oss_config_http_code",
        "put_rating_picture_oss_http_code",
        "get_model_mall_rating_http_code",
    ]
    checks.update({
        f"unsupported_zero_output_{name}": unsupported_results.get(name) == 0
        for name in expected_zero_outputs
    })
    checks.update({
        "unsupported_enable_multi_machine_called": unsupported_results.get("enable_multi_machine_called") is True,
        "unsupported_install_device_cert_called": unsupported_results.get("install_device_cert_called") is True,
        "unsupported_check_user_task_report_printable": unsupported_results.get("check_user_task_report_printable") is False,
        "unsupported_get_task_plate_index_value": unsupported_results.get("get_task_plate_index_value") == -1,
        "unsupported_camera_callbacks_quiet": unsupported.get("camera_callbacks") == 0,
        "unsupported_string_callbacks_quiet": unsupported.get("string_callbacks") == 0,
        "unsupported_hms_callbacks_quiet": unsupported.get("hms_callbacks") == 0,
        "unsupported_invalid_tunnel_rejected": unsupported_results.get("ft_tunnel_create") == -1,
        "unsupported_invalid_tunnel_no_handle": unsupported_results.get("ft_tunnel_created_handle") is False,
        "unsupported_check_debug_consistent": unsupported_results.get("check_debug_consistent") is True,
        "unsupported_set_cert_file": unsupported_results.get("set_cert_file") == 0,
        "unsupported_invalid_change_user": unsupported_results.get("change_user") == -19,
        "unsupported_user_logout_result": unsupported_results.get("user_logout") == 0,
        "unsupported_bambulab_host": unsupported_results.get("get_bambulab_host") == "https://bambulab.com",
        "unsupported_studio_info_url": (
            unsupported_results.get("get_studio_info_url")
            == "https://api.bambulab.com/v1/iot-service/api/slicer/resource"
        ),
    })
    failed = [name for name, ok in checks.items() if not ok]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
