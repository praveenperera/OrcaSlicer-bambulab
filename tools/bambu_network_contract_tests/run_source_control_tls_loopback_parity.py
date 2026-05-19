#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_BUILD = ROOT / "build/bambu_network_contract_tests"
DEFAULT_OUT_DIR = ROOT / "build/bambu_network_release_readiness/source_control_tls_loopback_parity"
LOGIN_RESPONSE = bytes.fromhex("10000000400101010000000000000000")
REDACTED_URL = "bambu:///local/127.0.0.1?port=<loopback>&user=bblp&passwd=<redacted>"


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)


def load_probe_json(stdout: str) -> dict[str, Any]:
    marker = '{\n  "source_plugin"'
    offset = stdout.find(marker)
    if offset < 0:
        return {"parse_error": "probe JSON marker not found", "stdout_prefix": stdout[:400]}
    try:
        payload = json.loads(stdout[offset:])
    except json.JSONDecodeError as error:
        return {"parse_error": str(error), "stdout_prefix": stdout[offset:offset + 400]}
    return payload if isinstance(payload, dict) else {"parse_error": "probe output was not a JSON object"}


def write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_cert(work_dir: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    work_dir.mkdir(parents=True, exist_ok=True)
    cert = work_dir / "cert.pem"
    key = work_dir / "key.pem"
    completed = run([
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(key),
        "-out",
        str(cert),
        "-days",
        "1",
        "-subj",
        "/CN=127.0.0.1",
    ])
    if completed.returncode != 0:
        raise RuntimeError(f"openssl failed: {completed.stderr.strip()}")
    return cert, key


def frame_header(data: bytes) -> dict[str, Any]:
    if len(data) < 16:
        return {"valid": False, "size": len(data)}
    return {
        "valid": True,
        "payload_size": int.from_bytes(data[0:4], "little"),
        "opcode_hex": data[4:6].hex(),
        "channel": data[6],
        "flags": data[7],
        "sequence_present": any(data[8:12]),
        "reserved_zero": data[12:16] == b"\x00\x00\x00\x00",
    }


def credential_contract(data: bytes) -> dict[str, Any]:
    user = data[:8].rstrip(b"\x00").decode("utf-8", errors="replace")
    password = data[8:16].rstrip(b"\x00")
    return {
        "user": user,
        "password_redacted": "<redacted>",
        "password_length": len(password),
        "padded_size": len(data),
    }


def parse_control_frames(data: bytes) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    offset = 0
    while offset + 16 <= len(data):
        header = frame_header(data[offset:offset + 16])
        payload_size = header.get("payload_size", 0)
        if not isinstance(payload_size, int) or payload_size < 0:
            break
        end = offset + 16 + payload_size
        if end > len(data):
            break
        payload = data[offset + 16:end]
        frames.append({
            "header": header,
            "payload_text": payload.decode("utf-8", errors="replace"),
            "payload_size": len(payload),
        })
        offset = end
    return frames


def response_frame(payload: str, sequence: int) -> bytes:
    body = payload.encode("utf-8")
    header = bytearray()
    header.extend(len(body).to_bytes(4, "little"))
    header.extend(bytes.fromhex("3f010201"))
    header.extend(sequence.to_bytes(4, "little"))
    header.extend(b"\x00\x00\x00\x00")
    return bytes(header) + body


def run_side(
    label: str,
    source_plugin: pathlib.Path,
    message: str,
    timeout_ms: int,
    work_dir: pathlib.Path,
) -> dict[str, Any]:
    cert, key = make_cert(work_dir)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = int(server.getsockname()[1])
    capture: dict[str, Any] = {
        "accepted": False,
        "login_header": {},
        "credentials": {},
        "control_frames": [],
        "server_errors": [],
    }

    def serve() -> None:
        try:
            conn, _ = server.accept()
            with context.wrap_socket(conn, server_side=True) as stream:
                capture["accepted"] = True
                stream.settimeout(0.25)
                received = bytearray()
                deadline = time.monotonic() + max(timeout_ms / 1000, 1.0)
                while len(received) < 32 and time.monotonic() < deadline:
                    try:
                        chunk = stream.recv(4096)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    received.extend(chunk)
                capture["login_header"] = frame_header(bytes(received[:16]))
                capture["credentials"] = credential_contract(bytes(received[16:32]))
                stream.sendall(LOGIN_RESPONSE)

                control = bytearray()
                while time.monotonic() < deadline:
                    try:
                        chunk = stream.recv(4096)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    control.extend(chunk)
                    frames = parse_control_frames(bytes(control))
                    if len(frames) >= 1:
                        try:
                            stream.sendall(response_frame('{"result":0,"reply":"loopback"}\n', len(frames) + 1))
                        except OSError:
                            pass
                    if len(frames) >= 2:
                        break
                capture["control_frames"] = parse_control_frames(bytes(control))
        except Exception as error:
            capture["server_errors"].append(repr(error))
        finally:
            server.close()

    thread = threading.Thread(target=serve)
    thread.start()
    url = f"bambu:///local/127.0.0.1?port={port}&user=bblp&passwd=secret"
    probe = CONTRACT_BUILD / "bambu_network_source_streaming_probe"
    completed = run([
        str(probe),
        "--source-plugin",
        str(source_plugin),
        "--url",
        url,
        "--mode",
        "control",
        "--message",
        message,
        "--timeout-ms",
        str(timeout_ms),
        "--poll-ms",
        "50",
    ])
    thread.join(timeout=2)
    transcript = {
        "label": label,
        "source_plugin": str(source_plugin),
        "url": REDACTED_URL,
        "probe_exit_code": completed.returncode,
        "probe": load_probe_json(completed.stdout),
        "probe_stderr": completed.stderr,
        "wire": capture,
    }
    return transcript


def stable_wire_contract(transcript: dict[str, Any]) -> dict[str, Any]:
    wire = transcript.get("wire", {})
    frames = wire.get("control_frames", []) if isinstance(wire, dict) else []
    return {
        "accepted": wire.get("accepted") is True if isinstance(wire, dict) else False,
        "login_header": wire.get("login_header", {}) if isinstance(wire, dict) else {},
        "credentials": wire.get("credentials", {}) if isinstance(wire, dict) else {},
        "control_payloads": [frame.get("payload_text") for frame in frames if isinstance(frame, dict)],
        "control_headers": [frame.get("header") for frame in frames if isinstance(frame, dict)],
    }


def validate_contract(contract: dict[str, Any], expected_payload: str) -> dict[str, Any]:
    login = contract.get("login_header", {})
    credentials = contract.get("credentials", {})
    headers = contract.get("control_headers", [])
    payloads = contract.get("control_payloads", [])
    checks = {
        "accepted": contract.get("accepted") is True,
        "login_payload_size": login.get("payload_size") == 16,
        "login_opcode": login.get("opcode_hex") == "3f01",
        "login_channel": login.get("channel") == 1,
        "login_flags": login.get("flags") == 1,
        "login_reserved_zero": login.get("reserved_zero") is True,
        "credential_user": credentials.get("user") == "bblp",
        "credential_password_length": credentials.get("password_length") == 6,
        "credential_padded_size": credentials.get("padded_size") == 16,
        "two_control_frames": len(payloads) >= 2,
        "control_payloads_match_expected": len(payloads) >= 2 and payloads[:2] == [expected_payload, expected_payload],
        "control_headers_match_shape": all(
            isinstance(header, dict)
            and header.get("opcode_hex") == "3f01"
            and header.get("channel") == 2
            and header.get("flags") == 1
            and header.get("reserved_zero") is True
            for header in headers[:2]
        ) and len(headers) >= 2,
    }
    return {"ok": all(checks.values()), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare official and candidate libBambuSource local-control TLS wire framing")
    parser.add_argument("--official-source", required=True, type=pathlib.Path)
    parser.add_argument("--candidate-source", default=ROOT / "build/bambu_network_rust_plugin_release/libBambuSource.dylib", type=pathlib.Path)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, type=pathlib.Path)
    parser.add_argument("--message", default='{"sequence":1}\n')
    parser.add_argument("--timeout-ms", type=int, default=1200)
    args = parser.parse_args()

    if not (CONTRACT_BUILD / "bambu_network_source_streaming_probe").is_file():
        parser.error("bambu_network_source_streaming_probe is missing; build contract tests first")
    if not args.official_source.is_file():
        parser.error("--official-source does not exist")
    if not args.candidate_source.is_file():
        parser.error("--candidate-source does not exist")
    if args.timeout_ms <= 0:
        parser.error("--timeout-ms must be positive")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    expected_payload = "{\"mtype\":12289," + args.message[1:]
    with tempfile.TemporaryDirectory(prefix="bambu-source-control-tls-") as tmp:
        tmp_dir = pathlib.Path(tmp)
        official = run_side("official", args.official_source, args.message, args.timeout_ms, tmp_dir / "official")
        candidate = run_side("candidate", args.candidate_source, args.message, args.timeout_ms, tmp_dir / "candidate")

    official_contract = stable_wire_contract(official)
    candidate_contract = stable_wire_contract(candidate)
    official_validation = validate_contract(official_contract, expected_payload)
    candidate_validation = validate_contract(candidate_contract, expected_payload)
    parity_ok = official_validation["ok"] and candidate_validation["ok"] and official_contract == candidate_contract

    official_path = args.out_dir / "source_control_tls_official.json"
    candidate_path = args.out_dir / "source_control_tls_candidate.json"
    write_json(official_path, official)
    write_json(candidate_path, candidate)

    comparison = {
        "ok": parity_ok,
        "official_contract": official_contract,
        "candidate_contract": candidate_contract,
        "official_validation": official_validation,
        "candidate_validation": candidate_validation,
    }
    comparison_path = args.out_dir / "source_control_tls_comparison.json"
    write_json(comparison_path, comparison)

    report = {
        "ok": parity_ok,
        "failed": [] if parity_ok else ["source_control_tls_wire_contract"],
        "inputs": {
            "official_source": {
                "path": str(args.official_source),
                "sha256": sha256(args.official_source),
            },
            "candidate_source": {
                "path": str(args.candidate_source),
                "sha256": sha256(args.candidate_source),
            },
            "stores_hashes_and_probe_transcripts_only": True,
            "passwords_redacted": True,
        },
        "artifacts": {
            "official": str(official_path),
            "candidate": str(candidate_path),
            "comparison": str(comparison_path),
        },
    }
    report_path = args.out_dir / "parity_report.json"
    write_json(report_path, report)
    print(json.dumps({"ok": parity_ok, "report": str(report_path)}, indent=2, sort_keys=True))
    return 0 if parity_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
