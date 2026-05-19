#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import socket
import struct
import subprocess
import sys
import threading
import time
from typing import Any


MAGIC = 0x52424A50
JSON_REQUEST = 1
JSON_RESPONSE = 2
BINARY_DATA = 3


def write_frame(stream, frame_type: int, request_id: int, payload: bytes) -> None:
    stream.write(struct.pack("<IIII", MAGIC, frame_type, request_id, len(payload)))
    stream.write(payload)
    stream.flush()


def read_frame(stream) -> tuple[int, int, bytes]:
    header = stream.read(16)
    if len(header) != 16:
        raise RuntimeError("failed to read frame header")
    magic, frame_type, request_id, size = struct.unpack("<IIII", header)
    if magic != MAGIC:
        raise RuntimeError(f"invalid frame magic: {magic:#x}")
    payload = stream.read(size)
    if len(payload) != size:
        raise RuntimeError("failed to read frame payload")
    return frame_type, request_id, payload


def request(
    proc: subprocess.Popen,
    request_id: int,
    method: str,
    payload: dict[str, Any] | None = None,
    *,
    capture_binary_text: bool = False,
) -> dict[str, Any]:
    body = json.dumps({"method": method, "payload": payload or {}}).encode("utf-8")
    assert proc.stdin is not None
    assert proc.stdout is not None
    write_frame(proc.stdin, JSON_REQUEST, request_id, body)
    frame_type, response_id, response = read_frame(proc.stdout)
    if frame_type != JSON_RESPONSE:
        raise RuntimeError(f"unexpected frame type: {frame_type}")
    if response_id != request_id:
        raise RuntimeError(f"unexpected response id: {response_id}, wanted {request_id}")
    decoded = json.loads(response.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError("response was not a JSON object")
    if decoded.get("__binary_pending") is True:
        binary_type, binary_id, binary_payload = read_frame(proc.stdout)
        if binary_type != BINARY_DATA:
            raise RuntimeError(f"unexpected binary frame type: {binary_type}")
        if binary_id != request_id:
            raise RuntimeError(f"unexpected binary response id: {binary_id}, wanted {request_id}")
        decoded["__binary_size"] = len(binary_payload)
        if capture_binary_text:
            decoded["__binary_text"] = binary_payload.decode("utf-8", errors="replace")
    return decoded


def response_value(response: dict[str, Any], key: str = "value", default: Any = None) -> Any:
    return response.get(key, default)


def run_ft_smoke(proc: subprocess.Popen, start_request_id: int) -> tuple[dict[str, Any], int]:
    request_id = start_request_id
    responses: dict[str, Any] = {}

    def call(name: str, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        nonlocal request_id
        response = request(proc, request_id, method, payload)
        request_id += 1
        responses[name] = response
        return response

    tunnel_create = call("tunnel_create", "ft.tunnel_create", {
        "url": "bambu:///local/127.0.0.1?port=6000&user=bblp&passwd=secret"
    })
    tunnel = tunnel_create.get("tunnel", 0)
    if isinstance(tunnel, int) and tunnel > 0:
        call("tunnel_sync_connect", "ft.tunnel_sync_connect", {"tunnel": tunnel})

        media_create = call("media_job_create", "ft.job_create", {"params_json": '{"cmd_type":7}'})
        media_job = media_create.get("job", 0)
        if isinstance(media_job, int) and media_job > 0:
            call("media_job_start", "ft.job_start", {"tunnel": tunnel, "job": media_job})
            call("media_job_get_result", "ft.job_get_result", {"job": media_job, "timeout_ms": 1000})
            call("media_job_release", "ft.job_release", {"job": media_job})

        upload_create = call("upload_job_create", "ft.job_create", {
            "params_json": (
                '{"cmd_type":5,"dest_storage":"emmc","dest_name":"missing.3mf",'
                '"file_path":"/tmp/bambu-network-bridge-ft-missing.3mf"}'
            )
        })
        upload_job = upload_create.get("job", 0)
        if isinstance(upload_job, int) and upload_job > 0:
            call("upload_job_start", "ft.job_start", {"tunnel": tunnel, "job": upload_job})
            call("upload_job_get_msg", "ft.job_get_msg", {"job": upload_job, "timeout_ms": 1000})
            call("upload_job_get_result", "ft.job_get_result", {"job": upload_job, "timeout_ms": 1000})
            call("upload_job_release", "ft.job_release", {"job": upload_job})

        call("tunnel_shutdown", "ft.tunnel_shutdown", {"tunnel": tunnel})
        call("tunnel_release", "ft.tunnel_release", {"tunnel": tunnel})

    return responses, request_id


def ft_smoke_ok(responses: dict[str, Any]) -> bool:
    if response_value(responses.get("tunnel_create", {})) != 0:
        return False
    tunnel = responses.get("tunnel_create", {}).get("tunnel", 0)
    if not isinstance(tunnel, int) or tunnel <= 0:
        return False
    if response_value(responses.get("tunnel_sync_connect", {})) != 0:
        return False
    if response_value(responses.get("media_job_create", {})) != 0:
        return False
    if response_value(responses.get("media_job_start", {})) != 0:
        return False
    media_result = responses.get("media_job_get_result", {})
    if response_value(media_result) != 0 or media_result.get("ec") != 0:
        return False
    if "emmc" not in str(media_result.get("json", "")):
        return False
    if response_value(responses.get("upload_job_create", {})) != 0:
        return False
    if response_value(responses.get("upload_job_start", {})) != 0:
        return False
    upload_msg = responses.get("upload_job_get_msg", {})
    if response_value(upload_msg) != 0 or "progress" not in str(upload_msg.get("json", "")):
        return False
    upload_result = responses.get("upload_job_get_result", {})
    if response_value(upload_result) != 0 or upload_result.get("ec") != -3:
        return False
    return response_value(responses.get("tunnel_release", {})) == 0


def run_source_smoke(proc: subprocess.Popen, start_request_id: int) -> tuple[dict[str, Any], int]:
    request_id = start_request_id
    responses: dict[str, Any] = {}

    def call(name: str, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        nonlocal request_id
        response = request(proc, request_id, method, payload)
        request_id += 1
        responses[name] = response
        return response

    created = call("create", "src.create", {
        "path": "bambu:///rtsps___bblp:redacted@synthetic.local/streaming/live/1?proto=rtsps"
    })
    tunnel = created.get("tunnel", 0)
    if isinstance(tunnel, int) and tunnel > 0:
        call("open", "src.open", {"tunnel": tunnel})
        call("start_stream", "src.start_stream", {"tunnel": tunnel, "video": True})
        call("get_stream_count", "src.get_stream_count", {"tunnel": tunnel})
        call("get_stream_info", "src.get_stream_info", {"tunnel": tunnel, "index": 0})
        call("read_sample", "src.read_sample", {"tunnel": tunnel})
        call("close", "src.close", {"tunnel": tunnel})
        call("destroy", "src.destroy", {"tunnel": tunnel})

    return responses, request_id


def source_smoke_ok(responses: dict[str, Any]) -> bool:
    if response_value(responses.get("create", {})) != 0:
        return False
    tunnel = responses.get("create", {}).get("tunnel", 0)
    if not isinstance(tunnel, int) or tunnel <= 0:
        return False
    if response_value(responses.get("open", {})) != 0:
        return False
    if response_value(responses.get("start_stream", {})) != 0:
        return False
    if response_value(responses.get("get_stream_count", {})) != 1:
        return False
    stream_info = responses.get("get_stream_info", {})
    info = stream_info.get("info", {}) if isinstance(stream_info, dict) else {}
    if response_value(stream_info) != 0 or not isinstance(info, dict):
        return False
    if info.get("type") != 0 or info.get("sub_type") != 1 or info.get("format_type") != 2:
        return False
    if info.get("width") != 1 or info.get("height") != 1 or info.get("frame_rate") != 1:
        return False
    sample = responses.get("read_sample", {})
    sample_info = sample.get("sample", {}) if isinstance(sample, dict) else {}
    if response_value(sample) != 0 or not isinstance(sample_info, dict):
        return False
    if sample_info.get("size", 0) <= 0 or sample.get("__binary_size", 0) <= 0:
        return False
    return response_value(responses.get("destroy", {})) == 0


def run_loopback_source_server() -> tuple[socket.socket, threading.Thread, dict[str, Any]]:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(5)
    state: dict[str, Any] = {
        "port": server.getsockname()[1],
        "accepted": False,
        "received": "",
        "responses_sent": 0,
        "error": "",
    }

    def serve() -> None:
        try:
            client, _ = server.accept()
            state["accepted"] = True
            with client:
                client.settimeout(5)
                responses = [
                    b'{"result":0,"sequence":1,"reply":"bridge-recv-loopback"}\n',
                    b'{"result":0,"sequence":2,"reply":"bridge-sample-loopback"}\n',
                ]
                for response in responses:
                    data = client.recv(4096)
                    state["received"] += data.decode("utf-8", errors="replace")
                    client.sendall(response)
                    state["responses_sent"] += 1
        except Exception as error:
            state["error"] = str(error)
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return server, thread, state


def run_source_local_tunnel_smoke(proc: subprocess.Popen, start_request_id: int) -> tuple[dict[str, Any], int]:
    request_id = start_request_id
    responses: dict[str, Any] = {}
    _, server_thread, server_state = run_loopback_source_server()

    def call(
        name: str,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        capture_binary_text: bool = False,
    ) -> dict[str, Any]:
        nonlocal request_id
        response = request(proc, request_id, method, payload, capture_binary_text=capture_binary_text)
        request_id += 1
        responses[name] = response
        return response

    try:
        created = call("create", "src.create", {
            "path": f"bambu:///local/127.0.0.1?port={server_state['port']}&user=bblp&passwd=redacted"
        })
        tunnel = created.get("tunnel", 0)
        if isinstance(tunnel, int) and tunnel > 0:
            call("open", "src.open", {"tunnel": tunnel})
            call("start_stream_ex", "src.start_stream_ex", {"tunnel": tunnel, "type": 0x3001})
            call("send_message", "src.send_message", {
                "tunnel": tunnel,
                "ctrl": 0x3001,
                "data": '{"sequence":1,"command":"bridge-recv-loopback"}\n',
            })
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                recv_message = call(
                    "recv_message",
                    "src.recv_message",
                    {"tunnel": tunnel, "buffer_size": 4096},
                    capture_binary_text=True,
                )
                if response_value(recv_message) == 0:
                    break
                if response_value(recv_message) != 2:
                    break
                time.sleep(0.025)

            call("send_message_sample", "src.send_message", {
                "tunnel": tunnel,
                "ctrl": 0x3001,
                "data": '{"sequence":2,"command":"bridge-sample-loopback"}\n',
            })

            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                read_sample = call(
                    "read_sample",
                    "src.read_sample",
                    {"tunnel": tunnel},
                    capture_binary_text=True,
                )
                if response_value(read_sample) == 0:
                    break
                if response_value(read_sample) != 2:
                    break
                time.sleep(0.025)

            call("close", "src.close", {"tunnel": tunnel})
            call("destroy", "src.destroy", {"tunnel": tunnel})
    finally:
        server_thread.join(timeout=5)

    responses["server"] = {
        "accepted": server_state.get("accepted") is True,
        "received_message": (
            "bridge-recv-loopback" in str(server_state.get("received", ""))
            and "bridge-sample-loopback" in str(server_state.get("received", ""))
        ),
        "response_sent": server_state.get("responses_sent") == 2,
        "error": server_state.get("error", ""),
    }
    return responses, request_id


def source_local_tunnel_smoke_ok(responses: dict[str, Any]) -> bool:
    if response_value(responses.get("create", {})) != 0:
        return False
    tunnel = responses.get("create", {}).get("tunnel", 0)
    if not isinstance(tunnel, int) or tunnel <= 0:
        return False
    if response_value(responses.get("open", {})) != 0:
        return False
    if response_value(responses.get("start_stream_ex", {})) != 0:
        return False
    if response_value(responses.get("send_message", {})) != 0:
        return False
    if response_value(responses.get("send_message_sample", {})) != 0:
        return False
    recv_message = responses.get("recv_message", {})
    read_sample = responses.get("read_sample", {})
    sample = read_sample.get("sample", {}) if isinstance(read_sample, dict) else {}
    server = responses.get("server", {})
    return all([
        response_value(recv_message) == 0,
        recv_message.get("message_len", 0) > 0,
        recv_message.get("__binary_size", 0) > 0,
        recv_message.get("ctrl") == 0,
        "bridge-recv-loopback" in str(recv_message.get("__binary_text", "")),
        response_value(read_sample) == 0,
        isinstance(sample, dict) and sample.get("size", 0) > 0,
        read_sample.get("__binary_size", 0) > 0,
        "bridge-sample-loopback" in str(read_sample.get("__binary_text", "")),
        isinstance(server, dict) and server.get("accepted") is True,
        isinstance(server, dict) and server.get("received_message") is True,
        isinstance(server, dict) and server.get("response_sent") is True,
        isinstance(server, dict) and server.get("error") == "",
        response_value(responses.get("destroy", {})) == 0,
    ])


def run_cloud_smoke(proc: subprocess.Popen, start_request_id: int, agent: int) -> tuple[dict[str, Any], int]:
    request_id = start_request_id
    responses: dict[str, Any] = {}

    def call(name: str, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        nonlocal request_id
        response = request(proc, request_id, method, payload)
        request_id += 1
        responses[name] = response
        return response

    login_payload = {
        "command": "user_login",
        "data": {
            "access_token": "token-redacted",
            "refresh_token": "refresh-redacted",
            "user_id": "1001",
            "username": "praveen",
            "nickname": "Praveen",
            "avatar": "https://example.invalid/avatar.png",
        },
    }
    call("change_user", "net.change_user", {"agent": agent, "user_info": json.dumps(login_payload, sort_keys=True)})
    call("connect_server", "net.connect_server", {"agent": agent})
    call("is_server_connected", "net.is_server_connected", {"agent": agent})
    call("get_user_print_info", "net.get_user_print_info", {"agent": agent})
    call("get_user_tasks", "net.get_user_tasks", {"agent": agent, "params": {"limit": 20}})
    call("get_my_message", "net.get_my_message", {"agent": agent, "type": 0, "after": 0, "limit": 20})
    call("request_bind_ticket", "net.request_bind_ticket", {"agent": agent})
    call("query_bind_status", "net.query_bind_status", {"agent": agent, "query_list": []})
    call("get_user_info", "net.get_user_info", {"agent": agent})
    call("get_task_plate_index", "net.get_task_plate_index", {"agent": agent, "task_id": "synthetic-task"})
    call("get_model_mall_home_url", "net.get_model_mall_home_url", {"agent": agent})
    call("get_model_mall_detail_url", "net.get_model_mall_detail_url", {"agent": agent, "id": "synthetic"})
    call("get_model_publish_url", "net.get_model_publish_url", {"agent": agent})
    call("get_model_mall_rating", "net.get_model_mall_rating", {"agent": agent, "job_id": 1})
    call("get_my_token", "net.get_my_token", {"agent": agent, "ticket": "synthetic-ticket"})
    call("get_my_profile", "net.get_my_profile", {"agent": agent, "token": "synthetic-access-token"})
    call("user_logout", "net.user_logout", {"agent": agent, "request": False})

    return responses, request_id


def json_payload_present(response: dict[str, Any], key: str) -> bool:
    value = response.get(key)
    if not isinstance(value, str) or not value:
        return False
    try:
        json.loads(value)
    except json.JSONDecodeError:
        return False
    return True


def cloud_smoke_ok(responses: dict[str, Any]) -> bool:
    if response_value(responses.get("change_user", {})) != 0:
        return False
    if response_value(responses.get("connect_server", {})) != 0:
        return False
    if response_value(responses.get("is_server_connected", {})) is not True:
        return False

    json_checks = [
        ("get_user_print_info", "http_body"),
        ("get_user_tasks", "http_body"),
        ("get_my_message", "http_body"),
        ("query_bind_status", "http_body"),
        ("get_model_mall_rating", "rating_result"),
        ("get_my_token", "http_body"),
        ("get_my_profile", "http_body"),
    ]
    for name, key in json_checks:
        response = responses.get(name, {})
        if response_value(response) != 0 or not json_payload_present(response, key):
            return False

    if response_value(responses.get("request_bind_ticket", {})) != 0 or not responses.get("request_bind_ticket", {}).get("ticket"):
        return False
    if response_value(responses.get("get_user_info", {})) != 0 or responses.get("get_user_info", {}).get("identifier", 0) <= 0:
        return False
    if response_value(responses.get("get_task_plate_index", {})) != 0 or responses.get("get_task_plate_index", {}).get("plate_index", -1) < 0:
        return False
    for name in ("get_model_mall_home_url", "get_model_mall_detail_url", "get_model_publish_url"):
        response = responses.get(name, {})
        if response_value(response) != 0 or not str(response.get("url", "")).startswith("https://"):
            return False
    return response_value(responses.get("user_logout", {})) == 0


def auth_info_ok(auth_info: dict[str, Any]) -> bool:
    capabilities = auth_info.get("capabilities", {})
    if not auth_info.get("ok"):
        return False
    if auth_info.get("logged_in") is not False:
        return False
    if auth_info.get("bambulab_host") != "https://bambulab.com":
        return False
    if auth_info.get("studio_info_url") != "https://api.bambulab.com/v1/iot-service/api/slicer/resource":
        return False
    required_symbols = [
        "bambu_network_is_user_login",
        "bambu_network_get_user_id",
        "bambu_network_get_user_name",
        "bambu_network_get_user_avatar",
        "bambu_network_get_user_nickanme",
        "bambu_network_build_login_cmd",
        "bambu_network_build_logout_cmd",
        "bambu_network_build_login_info",
        "bambu_network_change_user",
    ]
    return all(capabilities.get(name) is True for name in required_symbols)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True, help="path to pjarczak_bambu_linux_host")
    parser.add_argument("--plugin-dir", required=True, help="directory containing libbambu_networking.so")
    parser.add_argument("--source-so", default=None, help="optional explicit libBambuSource path")
    parser.add_argument("--country-code", default="US")
    parser.add_argument("--skip-ft-smoke", action="store_true", help="only check FT symbol capabilities, not bridge FT calls")
    parser.add_argument("--skip-source-smoke", action="store_true", help="skip synthetic libBambuSource stream probe over bridge RPC")
    parser.add_argument("--skip-cloud-smoke", action="store_true", help="skip synthetic cloud/service probe over bridge RPC")
    args = parser.parse_args()

    host = pathlib.Path(args.host)
    plugin_dir = pathlib.Path(args.plugin_dir)
    network_so = plugin_dir / "libbambu_networking.so"
    source_so = pathlib.Path(args.source_so) if args.source_so else plugin_dir / "libBambuSource.so"

    env = os.environ.copy()
    env["PJARCZAK_BAMBU_PLUGIN_DIR"] = str(plugin_dir)
    env["PJARCZAK_BAMBU_NETWORK_SO"] = str(network_so)
    env["PJARCZAK_BAMBU_SOURCE_SO"] = str(source_so)
    env["BAMBU_SOURCE_ENABLE_SYNTHETIC_STREAM"] = "1"
    env["BAMBU_SOURCE_DISABLE_LOCAL_TLS"] = "1"
    env["BAMBU_NETWORK_ENABLE_SYNTHETIC_CLOUD_SERVICE"] = "1"

    proc = subprocess.Popen(
        [str(host)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    transcript: dict[str, Any] = {
        "host": str(host),
        "plugin_dir": str(plugin_dir),
        "network_so_present": network_so.exists(),
        "source_so_present": source_so.exists(),
        "responses": {},
    }

    try:
        transcript["responses"]["handshake"] = request(proc, 1, "bridge.handshake")
        transcript["responses"]["capabilities"] = request(proc, 2, "bridge.capabilities")
        transcript["responses"]["ft_capabilities"] = request(proc, 3, "ft.capabilities")
        create = request(proc, 4, "net.create_agent", {"log_dir": str(plugin_dir), "country_code": args.country_code})
        transcript["responses"]["create_agent"] = create
        agent = create.get("value", 0)
        if isinstance(agent, int) and agent > 0:
            transcript["responses"]["set_config_dir"] = request(proc, 5, "net.set_config_dir", {"agent": agent, "config_dir": str(plugin_dir)})
            transcript["responses"]["init_log"] = request(proc, 6, "net.init_log", {"agent": agent})
            transcript["responses"]["set_country_code"] = request(proc, 7, "net.set_country_code", {"agent": agent, "country_code": args.country_code})
            transcript["responses"]["start"] = request(proc, 8, "net.start", {"agent": agent})
            transcript["responses"]["auth_info"] = request(proc, 9, "net.auth_info", {"agent": agent})
            next_request_id = 10
            if not args.skip_ft_smoke:
                ft_smoke, next_request_id = run_ft_smoke(proc, next_request_id)
                transcript["responses"]["ft_smoke"] = ft_smoke
            if not args.skip_source_smoke:
                source_smoke, next_request_id = run_source_smoke(proc, next_request_id)
                transcript["responses"]["source_smoke"] = source_smoke
                source_local_tunnel_smoke, next_request_id = run_source_local_tunnel_smoke(proc, next_request_id)
                transcript["responses"]["source_local_tunnel_smoke"] = source_local_tunnel_smoke
            if not args.skip_cloud_smoke:
                cloud_smoke, next_request_id = run_cloud_smoke(proc, next_request_id, agent)
                transcript["responses"]["cloud_smoke"] = cloud_smoke
            transcript["responses"]["destroy_agent"] = request(proc, next_request_id, "net.destroy_agent", {"agent": agent})
    finally:
        proc.kill()
        _, stderr = proc.communicate(timeout=5)
        if stderr:
            transcript["stderr"] = stderr.decode("utf-8", errors="replace")[-4000:]

    print(json.dumps(transcript, indent=2, sort_keys=True))
    handshake = transcript["responses"].get("handshake", {})
    ft_capabilities = transcript["responses"].get("ft_capabilities", {})
    required_ft_symbols = [
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
    ]
    missing_ft_symbols = [name for name in required_ft_symbols if not ft_capabilities.get(name)]
    if missing_ft_symbols:
        transcript["missing_ft_symbols"] = missing_ft_symbols
        print(json.dumps(transcript, indent=2, sort_keys=True), file=sys.stderr)
    ft_ok = args.skip_ft_smoke or ft_smoke_ok(transcript["responses"].get("ft_smoke", {}))
    if not ft_ok:
        print(json.dumps({"error": "ft smoke failed", "responses": transcript["responses"].get("ft_smoke", {})}, indent=2, sort_keys=True), file=sys.stderr)
    source_ok = args.skip_source_smoke or source_smoke_ok(transcript["responses"].get("source_smoke", {}))
    if not source_ok:
        print(json.dumps({"error": "source smoke failed", "responses": transcript["responses"].get("source_smoke", {})}, indent=2, sort_keys=True), file=sys.stderr)
    source_local_tunnel_ok = args.skip_source_smoke or source_local_tunnel_smoke_ok(
        transcript["responses"].get("source_local_tunnel_smoke", {})
    )
    if not source_local_tunnel_ok:
        print(json.dumps(
            {"error": "source local tunnel smoke failed", "responses": transcript["responses"].get("source_local_tunnel_smoke", {})},
            indent=2,
            sort_keys=True,
        ), file=sys.stderr)
    cloud_ok = args.skip_cloud_smoke or cloud_smoke_ok(transcript["responses"].get("cloud_smoke", {}))
    if not cloud_ok:
        print(json.dumps({"error": "cloud smoke failed", "responses": transcript["responses"].get("cloud_smoke", {})}, indent=2, sort_keys=True), file=sys.stderr)
    auth_ok = auth_info_ok(transcript["responses"].get("auth_info", {}))
    if not auth_ok:
        print(json.dumps({"error": "auth info failed", "response": transcript["responses"].get("auth_info", {})}, indent=2, sort_keys=True), file=sys.stderr)
    return 0 if (
        handshake.get("network_loaded")
        and not missing_ft_symbols
        and ft_ok
        and source_ok
        and source_local_tunnel_ok
        and cloud_ok
        and auth_ok
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
