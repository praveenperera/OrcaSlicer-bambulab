#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import pathlib
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_BUILD = ROOT / "build/bambu_network_contract_tests"
DEFAULT_CANDIDATE_SOURCE = ROOT / "build/bambu_network_rust_plugin_release/libBambuSource.dylib"
DEFAULT_OUT_DIR = ROOT / "build/bambu_network_release_readiness/source_rtsp_loopback_parity"


@dataclass
class H264Fixture:
    sps: bytes
    pps: bytes
    frames: list[bytes]


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_annex_b(data: bytes) -> list[bytes]:
    starts: list[tuple[int, int]] = []
    index = 0
    while index < len(data) - 3:
        if data[index : index + 3] == b"\x00\x00\x01":
            starts.append((index, 3))
            index += 3
        elif data[index : index + 4] == b"\x00\x00\x00\x01":
            starts.append((index, 4))
            index += 4
        else:
            index += 1

    nals: list[bytes] = []
    for offset, (position, prefix_len) in enumerate(starts):
        end = starts[offset + 1][0] if offset + 1 < len(starts) else len(data)
        nal = data[position + prefix_len : end]
        if nal:
            nals.append(nal)
    return nals


def build_h264_fixture() -> H264Fixture:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for the RTSP loopback fixture")

    with tempfile.TemporaryDirectory(prefix="bambu-source-rtsp-") as temp_dir:
        output = pathlib.Path(temp_dir) / "fixture.h264"
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=160x120:rate=5",
                "-frames:v",
                "2",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-tune",
                "zerolatency",
                "-pix_fmt",
                "yuv420p",
                "-f",
                "h264",
                str(output),
            ],
            check=True,
        )
        nals = split_annex_b(output.read_bytes())

    sps = next((nal for nal in nals if (nal[0] & 0x1F) == 7), None)
    pps = next((nal for nal in nals if (nal[0] & 0x1F) == 8), None)
    frames = [nal for nal in nals if (nal[0] & 0x1F) in (1, 5, 7, 8)]
    if not sps or not pps or not frames:
        raise RuntimeError("ffmpeg did not produce the required H.264 SPS/PPS/frame data")
    return H264Fixture(sps=sps, pps=pps, frames=frames)


def cseq(request: str) -> str:
    for line in request.split("\r\n"):
        if line.lower().startswith("cseq:"):
            return line.split(":", 1)[1].strip()
    return "1"


def rtsp_response(request: str, port: int, headers: str = "", body: str = "") -> bytes:
    response = f"RTSP/1.0 200 OK\r\nCSeq: {cseq(request)}\r\nServer: loopback\r\nCache-Control: no-cache\r\n{headers}"
    if body:
        response += (
            f"Content-Base: rtsp://127.0.0.1:{port}/live/\r\n"
            "Content-Type: application/sdp\r\n"
            f"Content-Length: {len(body.encode())}\r\n\r\n"
            f"{body}"
        )
    else:
        response += "Content-Length: 0\r\n\r\n"
    return response.encode()


def rtp_packet(sequence: int, nal: bytes, marker: bool) -> bytes:
    header = struct.pack("!BBHII", 0x80, (0x80 if marker else 0) | 96, sequence, sequence * 3600, 0x1234)
    packet = header + nal
    return b"$\x00" + struct.pack("!H", len(packet)) + packet


class RtspFixtureServer:
    def __init__(self, fixture: H264Fixture, port: int = 0) -> None:
        self.fixture = fixture
        self.port = port
        self.error: Exception | None = None
        self.thread: threading.Thread | None = None
        self.ready = threading.Event()

    def start(self) -> int:
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        if not self.ready.wait(timeout=5):
            raise RuntimeError("RTSP loopback server did not start")
        return self.port

    def join(self) -> None:
        if self.thread:
            self.thread.join(timeout=5)
        if self.error:
            raise RuntimeError(f"RTSP loopback server failed: {self.error}")

    def run(self) -> None:
        try:
            with socket.socket() as listener:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind(("127.0.0.1", self.port))
                listener.listen(1)
                self.port = listener.getsockname()[1]
                self.ready.set()
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(5)
                    self.handle_connection(connection)
        except Exception as error:
            self.error = error
            self.ready.set()

    def handle_connection(self, connection: socket.socket) -> None:
        session = "12345678"
        body = (
            "v=0\r\n"
            "o=- 9 2 IN IP4 127.0.0.1\r\n"
            "s=Media Presentation\r\n"
            "c=IN IP4 0.0.0.0\r\n"
            "t=0 0\r\n"
            "a=control:*\r\n"
            "a=range:npt=0-\r\n"
            "m=video 0 RTP/AVP 96\r\n"
            "a=rtpmap:96 H264/90000\r\n"
            "a=fmtp:96 packetization-mode=1;profile-level-id=42C00B;sprop-parameter-sets="
            f"{base64.b64encode(self.fixture.sps).decode()},{base64.b64encode(self.fixture.pps).decode()}\r\n"
            "a=framesize:96 160-120\r\n"
            "a=framerate:5\r\n"
            "a=control:trackID=1\r\n"
        )
        while True:
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = connection.recv(4096)
                if not chunk:
                    return
                data += chunk
            request = data.decode("latin1", "replace")
            if request.startswith("OPTIONS"):
                connection.sendall(
                    rtsp_response(request, self.port, "Public: OPTIONS, DESCRIBE, SETUP, PLAY, TEARDOWN\r\n")
                )
            elif request.startswith("DESCRIBE"):
                connection.sendall(rtsp_response(request, self.port, body=body))
            elif request.startswith("SETUP"):
                connection.sendall(
                    rtsp_response(
                        request,
                        self.port,
                        f"Transport: RTP/AVP/TCP;unicast;interleaved=0-1\r\nSession: {session};timeout=60\r\n",
                    )
                )
            elif request.startswith("PLAY"):
                connection.sendall(
                    rtsp_response(
                        request,
                        self.port,
                        f"Session: {session}\r\nRTP-Info: url=rtsp://127.0.0.1/live/trackID=1;seq=1;rtptime=0\r\n",
                    )
                )
                sequence = 1
                for _ in range(3):
                    for index, nal in enumerate(self.fixture.frames):
                        try:
                            connection.sendall(rtp_packet(sequence, nal, index == len(self.fixture.frames) - 1))
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        sequence += 1
                        time.sleep(0.02)
                time.sleep(0.2)
                return
            else:
                connection.sendall(rtsp_response(request, self.port))


def extract_json(stdout: str) -> dict:
    start = stdout.find("{")
    end = stdout.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise RuntimeError(f"probe did not emit JSON: {stdout}")
    payload = json.loads(stdout[start : end + 1])
    if not isinstance(payload, dict):
        raise RuntimeError("probe JSON was not an object")
    return payload


def run_source_probe(plugin: pathlib.Path, url: str, out_path: pathlib.Path, fixture: H264Fixture, port: int) -> dict:
    server = RtspFixtureServer(fixture, port)
    server.start()
    command = [
        str(CONTRACT_BUILD / "bambu_network_source_streaming_probe"),
        "--source-plugin",
        str(plugin),
        "--url",
        url,
        "--mode",
        "video",
        "--timeout-ms",
        "7000",
        "--expect-success",
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    server.join()
    payload = extract_json(completed.stdout)
    payload["ok"] = completed.returncode == 0 and payload.get("ok") is True
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def reserve_loopback_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def compare(official_path: pathlib.Path, candidate_path: pathlib.Path, out_path: pathlib.Path) -> bool:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools/bambu_network_contract_tests/compare_transcripts.py"), str(official_path), str(candidate_path)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    out_path.write_text(completed.stdout, encoding="utf-8")
    return completed.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run official-vs-candidate source streaming parity against a local RTSP fixture")
    parser.add_argument("--official-source", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-source", type=pathlib.Path, default=DEFAULT_CANDIDATE_SOURCE)
    parser.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    source_probe = CONTRACT_BUILD / "bambu_network_source_streaming_probe"
    if not source_probe.is_file():
        parser.error(f"source streaming probe is not built: {source_probe}")
    if not args.official_source.is_file():
        parser.error(f"official source plugin does not exist: {args.official_source}")
    if not args.candidate_source.is_file():
        parser.error(f"candidate source plugin does not exist: {args.candidate_source}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    fixture = build_h264_fixture()

    official_path = args.out_dir / "source_streaming_official.json"
    candidate_path = args.out_dir / "source_streaming_candidate.json"
    comparison_path = args.out_dir / "source_streaming_comparison.txt"

    port = reserve_loopback_port()
    url = f"bambu:///rtsp___user:pass@127.0.0.1:{port}/live"

    official = run_source_probe(args.official_source, url, official_path, fixture, port)
    candidate = run_source_probe(args.candidate_source, url, candidate_path, fixture, port)
    comparison_ok = compare(official_path, candidate_path, comparison_path)

    ok = official.get("ok") is True and candidate.get("ok") is True and comparison_ok
    report = {
        "ok": ok,
        "failed": [] if ok else ["source_streaming"],
        "inputs": {
            "artifact_policy": {
                "copies_input_binaries": False,
                "stores_hashes_and_probe_transcripts_only": True,
            },
            "self_compare_allowed": False,
            "official": {
                "source": {
                    "path": str(args.official_source),
                    "sha256": sha256_file(args.official_source),
                },
            },
            "candidate": {
                "source": {
                    "path": str(args.candidate_source),
                    "sha256": sha256_file(args.candidate_source),
                },
            },
        },
        "probes": {
            "source_streaming": {
                "official": {"ok": official.get("ok") is True, "path": official_path.name},
                "candidate": {"ok": candidate.get("ok") is True, "path": candidate_path.name},
            },
        },
        "comparisons": {
            "source_streaming": {
                "ok": comparison_ok,
                "path": comparison_path.name,
            },
        },
    }
    report_path = args.out_dir / "parity_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": ok, "report": str(report_path)}, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
