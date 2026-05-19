#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "tools/bambu_network_contract_tests/run_source_streaming_parity.py"
SOURCE_URL = "bambu:///rtsps___bblp:dry-run-secret@192.0.2.10/streaming/live/1?proto=rtsps&passwd=query-secret"


def write_file(path: pathlib.Path, content: bytes = b"fixture\n") -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def run_wrapper(work: pathlib.Path, *extra: str, source_url: str | None = SOURCE_URL) -> subprocess.CompletedProcess:
    official_network = write_file(work / "official/libbambu_networking.dylib")
    official_source = write_file(work / "official/libBambuSource.dylib")
    candidate_network = write_file(work / "candidate/libbambu_networking.dylib")
    candidate_source = write_file(work / "candidate/libBambuSource.dylib")
    linux_report = write_file(work / "linux_bridge_runtime_verify_report.json", b"{}\n")

    env = os.environ.copy()
    if source_url is None:
        env.pop("BAMBU_SOURCE_STREAM_URL", None)
    else:
        env["BAMBU_SOURCE_STREAM_URL"] = source_url

    return subprocess.run(
        [
            sys.executable,
            str(WRAPPER),
            "--official-network",
            str(official_network),
            "--official-source",
            str(official_source),
            "--candidate-network",
            str(candidate_network),
            "--candidate-source",
            str(candidate_source),
            "--linux-runtime-report",
            str(linux_report),
            "--source-stream-url-env",
            "BAMBU_SOURCE_STREAM_URL",
            "--skip-build",
            "--dry-run",
            *extra,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def require_no_secret_leak(output: str) -> None:
    for value in [SOURCE_URL, "dry-run-secret", "query-secret"]:
        require(value not in output, "dry-run output leaked a source-stream secret")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="bambu-source-streaming-dry-run-") as tmp:
        work = pathlib.Path(tmp)

        human = run_wrapper(work)
        require(human.returncode == 0, f"human dry run failed: {human.stderr}\n{human.stdout}")
        require("source-streaming parity dry run ok" in human.stdout, "dry run did not report success")
        require("capture_official_parity:" in human.stdout, "dry run did not print capture command")
        require("run_release_readiness:" in human.stdout, "dry run did not print readiness command")
        require_no_secret_leak(human.stdout)
        require_no_secret_leak(human.stderr)

        json_report = run_wrapper(work / "json-report", "--json")
        require(json_report.returncode == 0, f"JSON dry run failed: {json_report.stderr}\n{json_report.stdout}")
        require_no_secret_leak(json_report.stdout)
        require_no_secret_leak(json_report.stderr)
        payload = json.loads(json_report.stdout)
        require(payload.get("ok") is True and payload.get("dry_run") is True, "JSON dry run did not report ok dry-run status")
        require(payload.get("will_open_source_stream") is True, "JSON dry run did not record stream-opening behavior")
        source = payload.get("source_stream", {})
        require(source.get("url_env_present") is True, "JSON dry run did not record source URL env presence")
        require(source.get("redacted_url", "").count("<redacted>") == 2, "JSON dry run did not redact URL credentials")
        commands = payload.get("commands", {})
        capture = commands.get("capture_official_parity")
        readiness = commands.get("run_release_readiness")
        require(isinstance(capture, list), "JSON dry run did not include capture argv")
        require(isinstance(readiness, list), "JSON dry run did not include readiness argv")
        require("--expect-source-stream-success" in capture, "capture command does not require stream success")
        require("--defer-manual-printer-parity" in readiness, "readiness command does not defer manual printer parity")
        require("--defer-authorized-cloud-parity" in readiness, "readiness command does not defer authorized cloud parity")
        require("<redacted-source-stream-url>" in capture, "capture command did not redact the source URL")

        control_report = run_wrapper(
            work / "control-report",
            "--json",
            "--source-stream-mode",
            "control",
            "--source-stream-message",
            "{\"sequence\":1,\"command\":\"list\"}",
        )
        require(control_report.returncode == 0, f"control JSON dry run failed: {control_report.stderr}\n{control_report.stdout}")
        require_no_secret_leak(control_report.stdout)
        control_payload = json.loads(control_report.stdout)
        control_source = control_payload.get("source_stream", {})
        require(control_source.get("mode") == "control", "control dry run did not preserve source stream mode")
        require(control_source.get("message_present") is True, "control dry run did not record control message presence")
        control_capture = control_payload.get("commands", {}).get("capture_official_parity", [])
        require("--source-stream-mode" in control_capture, "control capture command omitted source mode")
        require("control" in control_capture, "control capture command omitted control mode value")
        require("--source-stream-message" in control_capture, "control capture command omitted source message")

        missing_env = run_wrapper(work / "missing-env", source_url=None)
        require(missing_env.returncode != 0, "dry run accepted missing source URL env")
        require("BAMBU_SOURCE_STREAM_URL must be set" in missing_env.stderr, "missing source URL env error was not explicit")

        json_without_dry_run = subprocess.run(
            [
                sys.executable,
                str(WRAPPER),
                "--official-network",
                str(write_file(work / "json-no-dry-run/official/libbambu_networking.dylib")),
                "--official-source",
                str(write_file(work / "json-no-dry-run/official/libBambuSource.dylib")),
                "--source-stream-url-env",
                "BAMBU_SOURCE_STREAM_URL",
                "--json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "BAMBU_SOURCE_STREAM_URL": SOURCE_URL},
        )
        require(json_without_dry_run.returncode != 0, "wrapper accepted --json without --dry-run")
        require("--json requires --dry-run" in json_without_dry_run.stderr, "--json misuse error was not explicit")

    print("source-streaming parity dry-run validation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
