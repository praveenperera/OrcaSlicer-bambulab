#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "tools/bambu_network_contract_tests/run_source_control_tunnel_parity.py"
SOURCE_URL = "bambu:///local/192.0.2.10?port=6000&user=bblp&passwd=query-secret"
SOURCE_MESSAGE = "{\"sequence\":1,\"command\":\"list\",\"path\":\"/cache/private-project.3mf\"}"


def write_file(path: pathlib.Path, content: bytes = b"fixture\n") -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def run_wrapper(work: pathlib.Path, *extra: str, source_url: str | None = SOURCE_URL, message: str | None = SOURCE_MESSAGE) -> subprocess.CompletedProcess:
    official_network = write_file(work / "official/libbambu_networking.dylib")
    official_source = write_file(work / "official/libBambuSource.dylib")
    candidate_network = write_file(work / "candidate/libbambu_networking.dylib")
    candidate_source = write_file(work / "candidate/libBambuSource.dylib")
    linux_report = write_file(work / "linux_bridge_runtime_verify_report.json", b"{}\n")

    env = os.environ.copy()
    if source_url is None:
        env.pop("BAMBU_SOURCE_CONTROL_URL", None)
    else:
        env["BAMBU_SOURCE_CONTROL_URL"] = source_url
    if message is None:
        env.pop("BAMBU_SOURCE_CONTROL_MESSAGE", None)
    else:
        env["BAMBU_SOURCE_CONTROL_MESSAGE"] = message

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
            "--source-control-url-env",
            "BAMBU_SOURCE_CONTROL_URL",
            "--source-control-message-env",
            "BAMBU_SOURCE_CONTROL_MESSAGE",
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
    for value in [SOURCE_URL, SOURCE_MESSAGE, "query-secret", "private-project.3mf"]:
        require(value not in output, "dry-run output leaked a source control secret")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="bambu-source-control-dry-run-") as tmp:
        work = pathlib.Path(tmp)

        human = run_wrapper(work)
        require(human.returncode == 0, f"human dry run failed: {human.stderr}\n{human.stdout}")
        require("source control-tunnel parity dry run ok" in human.stdout, "dry run did not report success")
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
        require(payload.get("will_open_source_control_tunnel") is True, "JSON dry run did not record control-tunnel behavior")
        control = payload.get("source_control_tunnel", {})
        require(control.get("url_env_present") is True, "JSON dry run did not record source control URL env presence")
        require(control.get("message_env_present") is True, "JSON dry run did not record source control message env presence")
        require(control.get("redacted_url", "").count("<redacted>") == 1, "JSON dry run did not redact URL credentials")
        commands = payload.get("commands", {})
        capture = commands.get("capture_official_parity")
        readiness = commands.get("run_release_readiness")
        require(isinstance(capture, list), "JSON dry run did not include capture argv")
        require(isinstance(readiness, list), "JSON dry run did not include readiness argv")
        require("--expect-source-stream-success" in capture, "capture command does not require control success")
        require("--source-stream-mode" in capture and "control" in capture, "capture command did not force control mode")
        require("--source-stream-message" in capture, "capture command omitted control message")
        require("<redacted-source-control-url>" in capture, "capture command did not redact the source URL")
        require("<redacted-source-control-message>" in capture, "capture command did not redact the source message")
        require("--defer-manual-printer-parity" in readiness, "readiness command does not defer manual printer parity")
        require("--defer-authorized-cloud-parity" in readiness, "readiness command does not defer authorized cloud parity")

        missing_url = run_wrapper(work / "missing-url", source_url=None)
        require(missing_url.returncode != 0, "dry run accepted missing source control URL env")
        require("BAMBU_SOURCE_CONTROL_URL must be set" in missing_url.stderr, "missing source control URL env error was not explicit")

        missing_message = run_wrapper(work / "missing-message", message=None)
        require(missing_message.returncode != 0, "dry run accepted missing source control message env")
        require("BAMBU_SOURCE_CONTROL_MESSAGE must be set" in missing_message.stderr, "missing source control message env error was not explicit")

        json_without_dry_run = subprocess.run(
            [
                sys.executable,
                str(WRAPPER),
                "--official-network",
                str(write_file(work / "json-no-dry-run/official/libbambu_networking.dylib")),
                "--official-source",
                str(write_file(work / "json-no-dry-run/official/libBambuSource.dylib")),
                "--source-control-url-env",
                "BAMBU_SOURCE_CONTROL_URL",
                "--source-control-message-env",
                "BAMBU_SOURCE_CONTROL_MESSAGE",
                "--json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "BAMBU_SOURCE_CONTROL_URL": SOURCE_URL,
                "BAMBU_SOURCE_CONTROL_MESSAGE": SOURCE_MESSAGE,
            },
        )
        require(json_without_dry_run.returncode != 0, "wrapper accepted --json without --dry-run")
        require("--json requires --dry-run" in json_without_dry_run.stderr, "--json misuse error was not explicit")

    print("source control-tunnel parity dry-run validation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
