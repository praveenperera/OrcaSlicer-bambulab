#!/usr/bin/env python3
import os
import json
import pathlib
import subprocess
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "tools/bambu_network_contract_tests/run_real_printer_parity.py"


def write_file(path: pathlib.Path, content: bytes = b"fixture\n") -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def run_wrapper(work: pathlib.Path, *extra: str, password: str | None = "dry-run-only") -> subprocess.CompletedProcess:
    official_network = write_file(work / "official/libbambu_networking.dylib")
    official_source = write_file(work / "official/libBambuSource.dylib")
    candidate_network = write_file(work / "candidate/libbambu_networking.dylib")
    candidate_source = write_file(work / "candidate/libBambuSource.dylib")
    linux_report = write_file(work / "linux_bridge_runtime_verify_report.json", b"{}\n")
    print_job = write_file(work / "OrcaCube_v2.3mf")

    env = os.environ.copy()
    if password is None:
        env.pop("BAMBU_NETWORK_PRINTER_PASSWORD", None)
    else:
        env["BAMBU_NETWORK_PRINTER_PASSWORD"] = password

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
            "--printer-dev-id",
            "DRYRUN123",
            "--printer-dev-ip",
            "192.0.2.10",
            "--print-job-file",
            str(print_job),
            "--print-job-remote-name",
            "OrcaCube_v2.3mf",
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


def main() -> int:
    password_value = "dry-run-only"
    with tempfile.TemporaryDirectory(prefix="bambu-real-printer-dry-run-") as tmp:
        work = pathlib.Path(tmp)

        upload_only = run_wrapper(work, "--print-job-modes", "upload-only")
        require(upload_only.returncode == 0, f"upload-only dry run failed: {upload_only.stderr}\n{upload_only.stdout}")
        require("real-printer parity dry run ok" in upload_only.stdout, "dry run did not report success")
        require("capture_official_parity:" in upload_only.stdout, "dry run did not print capture command")
        require("run_release_readiness:" in upload_only.stdout, "dry run did not print readiness command")
        require(password_value not in upload_only.stdout, "human dry-run output leaked the printer password value")

        json_report = run_wrapper(work / "json-report", "--print-job-modes", "upload-only", "--json")
        require(json_report.returncode == 0, f"JSON dry run failed: {json_report.stderr}\n{json_report.stdout}")
        require(password_value not in json_report.stdout, "JSON dry-run output leaked the printer password value")
        payload = json.loads(json_report.stdout)
        require(payload.get("ok") is True and payload.get("dry_run") is True, "JSON dry run did not report ok dry-run status")
        require(payload.get("will_start_prints") is False, "upload-only JSON dry run reported print-start behavior")
        require(payload.get("will_open_source_stream") is False, "default JSON dry run reported source-stream behavior")
        require(payload.get("printer", {}).get("password_present") is True, "JSON dry run did not record password presence")
        require(payload.get("print_job", {}).get("modes") == ["upload-only"], "JSON dry run did not preserve print-job modes")
        commands = payload.get("commands", {})
        require(isinstance(commands.get("capture_official_parity"), list), "JSON dry run did not include capture argv")
        require(isinstance(commands.get("run_release_readiness"), list), "JSON dry run did not include readiness argv")

        source_stream = run_wrapper(work / "source-stream", "--print-job-modes", "upload-only", "--include-source-streaming", "--json")
        require(source_stream.returncode == 0, f"source-stream dry run failed: {source_stream.stderr}\n{source_stream.stdout}")
        require(password_value not in source_stream.stdout, "source-stream JSON dry-run output leaked the printer password value")
        require(password_value not in source_stream.stderr, "source-stream JSON dry-run stderr leaked the printer password value")
        source_payload = json.loads(source_stream.stdout)
        require(source_payload.get("will_open_source_stream") is True, "source-stream dry run did not record source-stream behavior")
        require(source_payload.get("will_open_source_control_tunnel") is False, "source-stream dry run reported source-control behavior")
        source_capture = source_payload.get("commands", {}).get("capture_official_parity")
        require(isinstance(source_capture, list), "source-stream dry run did not include capture argv")
        require("--source-stream-url" in source_capture, "source-stream capture command did not include source URL flag")
        require("<redacted-source-stream-url>" in source_capture, "source-stream capture command did not redact the source URL")
        require("--expect-source-stream-success" in source_capture, "source-stream capture command did not require source success")

        source_control_message = '{"sequence":9,"command":"list","path":"/"}'
        source_control = run_wrapper(
            work / "source-control",
            "--print-job-modes",
            "upload-only",
            "--include-source-control-tunnel",
            "--source-control-message",
            source_control_message,
            "--json",
        )
        require(source_control.returncode == 0, f"source-control dry run failed: {source_control.stderr}\n{source_control.stdout}")
        require(password_value not in source_control.stdout, "source-control JSON dry-run output leaked the printer password value")
        require(source_control_message not in source_control.stdout, "source-control JSON dry-run output leaked the control message")
        source_control_payload = json.loads(source_control.stdout)
        require(source_control_payload.get("will_open_source_control_tunnel") is True, "source-control dry run did not record control behavior")
        source_control_capture = source_control_payload.get("commands", {}).get("capture_source_control_tunnel_parity")
        require(isinstance(source_control_capture, list), "source-control dry run did not include control capture argv")
        require("--source-stream-mode" in source_control_capture, "source-control capture command did not include source mode flag")
        require("control" in source_control_capture, "source-control capture command did not request control mode")
        require("<redacted-source-control-url>" in source_control_capture, "source-control capture command did not redact the control URL")
        require("<redacted-source-control-message>" in source_control_capture, "source-control capture command did not redact the control message")
        source_control_readiness = source_control_payload.get("commands", {}).get("run_release_readiness")
        require(isinstance(source_control_readiness, list), "source-control dry run did not include readiness argv")
        require("--source-streaming-parity-report" in source_control_readiness, "source-control readiness command did not include supplemental parity report")

        all_modes = run_wrapper(work / "all-modes", "--confirm-start-prints")
        require(all_modes.returncode == 0, f"all-mode dry run failed: {all_modes.stderr}\n{all_modes.stdout}")

        missing_confirm = run_wrapper(work / "missing-confirm")
        require(missing_confirm.returncode != 0, "dry run accepted print-start modes without confirmation")
        require("--confirm-start-prints is required" in missing_confirm.stderr, "missing confirmation error was not explicit")

        missing_password = run_wrapper(work / "missing-password", "--print-job-modes", "upload-only", password=None)
        require(missing_password.returncode != 0, "dry run accepted missing printer password environment")
        require("BAMBU_NETWORK_PRINTER_PASSWORD must be set" in missing_password.stderr, "missing password error was not explicit")

        invalid_mode = run_wrapper(work / "invalid-mode", "--print-job-modes", "upload-only,bad-mode")
        require(invalid_mode.returncode != 0, "dry run accepted an invalid print-job mode")
        require("invalid print job mode" in invalid_mode.stderr, "invalid print-job mode error was not explicit")

        json_without_dry_run = subprocess.run(
            [
                sys.executable,
                str(WRAPPER),
                "--official-network",
                str(write_file(work / "json-no-dry-run/official/libbambu_networking.dylib")),
                "--official-source",
                str(write_file(work / "json-no-dry-run/official/libBambuSource.dylib")),
                "--printer-dev-id",
                "DRYRUN123",
                "--printer-dev-ip",
                "192.0.2.10",
                "--print-job-file",
                str(write_file(work / "json-no-dry-run/OrcaCube_v2.3mf")),
                "--print-job-remote-name",
                "OrcaCube_v2.3mf",
                "--json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "BAMBU_NETWORK_PRINTER_PASSWORD": password_value},
        )
        require(json_without_dry_run.returncode != 0, "wrapper accepted --json without --dry-run")
        require("--json requires --dry-run" in json_without_dry_run.stderr, "--json misuse error was not explicit")

    print("real-printer parity dry-run validation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
