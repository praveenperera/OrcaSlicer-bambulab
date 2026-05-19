#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import shlex
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "tools/bambu_network_contract_tests"
DEFAULT_PLUGIN_BUILD = ROOT / "build/bambu_network_rust_plugin_release"
DEFAULT_LINUX_RUNTIME_REPORT = ROOT / "build/bambu_network_release_readiness/linux_bridge_runtime_verify_report.json"
DEFAULT_PARITY_DIR = ROOT / "build/bambu_network_release_readiness/official_parity_real_printer_current"
DEFAULT_READINESS_DIR = ROOT / "build/bambu_network_release_readiness"
REQUIRED_PRINT_JOB_MODES = ("upload-only", "local-print", "sdcard-print")
REDACTED_SOURCE_STREAM_URL = "<redacted-source-stream-url>"
REDACTED_SOURCE_CONTROL_URL = "<redacted-source-control-url>"
REDACTED_SOURCE_CONTROL_MESSAGE = "<redacted-source-control-message>"


def sanitized_command(cmd: list[str], source_stream_url: str = "", source_control_url: str = "", source_control_message: str = "") -> list[str]:
    sanitized: list[str] = []
    for part in cmd:
        if source_stream_url and part == source_stream_url:
            sanitized.append(REDACTED_SOURCE_STREAM_URL)
        elif source_control_url and part == source_control_url:
            sanitized.append(REDACTED_SOURCE_CONTROL_URL)
        elif source_control_message and part == source_control_message:
            sanitized.append(REDACTED_SOURCE_CONTROL_MESSAGE)
        else:
            sanitized.append(part)
    return sanitized


def run(cmd: list[str], source_stream_url: str = "", source_control_url: str = "", source_control_message: str = "") -> subprocess.CompletedProcess:
    print(
        "+ " + " ".join(shlex.quote(part) for part in sanitized_command(cmd, source_stream_url, source_control_url, source_control_message)),
        file=sys.stderr,
    )
    return subprocess.run(cmd, cwd=ROOT, text=True, check=False)


def print_command(label: str, cmd: list[str], source_stream_url: str = "", source_control_url: str = "", source_control_message: str = "") -> None:
    print(f"{label}:")
    print(" ".join(shlex.quote(part) for part in sanitized_command(cmd, source_stream_url, source_control_url, source_control_message)))


def source_stream_url(args: argparse.Namespace, password: str) -> str:
    return (
        f"bambu:///rtsps___{args.printer_username}:{password}"
        f"@{args.printer_dev_ip}/streaming/live/1?proto=rtsps"
    )


def source_control_url(args: argparse.Namespace, password: str) -> str:
    return (
        f"bambu:///local/{args.printer_dev_ip}"
        f"?port=6000&user={args.printer_username}&passwd={password}"
    )


def dry_run_report(
    args: argparse.Namespace,
    capture_cmd: list[str],
    source_control_capture_cmd: list[str] | None,
    readiness_cmd: list[str],
    source_url: str = "",
    control_url: str = "",
) -> dict[str, object]:
    return {
        "ok": True,
        "dry_run": True,
        "will_start_prints": any(mode != "upload-only" for mode in args.print_job_modes),
        "will_open_source_stream": bool(args.include_source_streaming),
        "will_open_source_control_tunnel": bool(args.include_source_control_tunnel),
        "printer": {
            "dev_id_present": bool(args.printer_dev_id),
            "dev_ip_present": bool(args.printer_dev_ip),
            "username": args.printer_username,
            "password_env": args.printer_password_env,
            "password_present": bool(os.environ.get(args.printer_password_env)),
        },
        "print_job": {
            "file": str(args.print_job_file),
            "remote_name": args.print_job_remote_name,
            "modes": args.print_job_modes,
            "confirm_start_prints": args.confirm_start_prints,
        },
        "source_control_tunnel": {
            "message_present": bool(args.source_control_message),
            "timeout_ms": args.source_control_timeout_ms,
            "poll_ms": args.source_control_poll_ms,
            "ctrl_type": args.source_control_ctrl_type,
        },
        "commands": {
            "capture_official_parity": sanitized_command(capture_cmd, source_url, control_url, args.source_control_message),
            "capture_source_control_tunnel_parity": sanitized_command(source_control_capture_cmd, source_url, control_url, args.source_control_message)
            if source_control_capture_cmd
            else None,
            "run_release_readiness": sanitized_command(readiness_cmd, source_url, control_url, args.source_control_message),
        },
    }


def parse_modes(value: str) -> list[str]:
    modes = [mode.strip() for mode in value.split(",") if mode.strip()]
    invalid = [mode for mode in modes if mode not in REQUIRED_PRINT_JOB_MODES]
    if invalid:
        raise argparse.ArgumentTypeError(f"invalid print job mode(s): {', '.join(invalid)}")
    return modes


def existing_file(path: pathlib.Path, label: str) -> pathlib.Path:
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"{label} does not exist or is not a file: {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the final real-printer official-vs-candidate parity capture and readiness aggregation",
    )
    parser.add_argument("--official-network", type=pathlib.Path, required=True)
    parser.add_argument("--official-source", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-build-dir", type=pathlib.Path, default=DEFAULT_PLUGIN_BUILD)
    parser.add_argument("--candidate-network", type=pathlib.Path, default=None)
    parser.add_argument("--candidate-source", type=pathlib.Path, default=None)
    parser.add_argument("--parity-out-dir", type=pathlib.Path, default=DEFAULT_PARITY_DIR)
    parser.add_argument("--readiness-out-dir", type=pathlib.Path, default=DEFAULT_READINESS_DIR)
    parser.add_argument("--linux-runtime-report", type=pathlib.Path, default=DEFAULT_LINUX_RUNTIME_REPORT)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--printer-dev-id", required=True)
    parser.add_argument("--printer-dev-ip", required=True)
    parser.add_argument("--printer-username", default="bblp")
    parser.add_argument("--printer-password-env", default="BAMBU_NETWORK_PRINTER_PASSWORD")
    parser.add_argument("--printer-country-code", default="US")
    parser.add_argument("--printer-message", default='{"pushing":{"sequence_id":"0","command":"pushall"}}')
    parser.add_argument("--printer-wait-ms", type=int, default=1000)
    parser.add_argument("--printer-use-ssl", action="store_true")
    parser.add_argument("--print-job-file", type=pathlib.Path, required=True)
    parser.add_argument("--print-job-modes", type=parse_modes, default=list(REQUIRED_PRINT_JOB_MODES))
    parser.add_argument("--print-job-remote-name", required=True)
    parser.add_argument("--print-job-file-md5", default="")
    parser.add_argument("--print-job-use-ssl-for-ftp", action="store_true")
    parser.add_argument("--include-synthetic-ft-behavior", action="store_true")
    parser.add_argument("--include-source-streaming", action="store_true", help="also capture live RTSPS libBambuSource parity using the printer access-code env")
    parser.add_argument("--source-stream-timeout-ms", type=int, default=10000)
    parser.add_argument("--source-stream-poll-ms", type=int, default=50)
    parser.add_argument("--source-stream-ctrl-type", type=int, default=0x3001)
    parser.add_argument("--include-source-control-tunnel", action="store_true", help="also capture live port-6000 libBambuSource control-tunnel parity")
    parser.add_argument("--source-control-parity-out-dir", type=pathlib.Path, default=None)
    parser.add_argument("--source-control-message", default='{"sequence":1,"command":"list","path":"/"}')
    parser.add_argument("--source-control-timeout-ms", type=int, default=10000)
    parser.add_argument("--source-control-poll-ms", type=int, default=50)
    parser.add_argument("--source-control-ctrl-type", type=int, default=0x3001)
    parser.add_argument("--confirm-start-prints", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="validate inputs and print commands without launching plugin probes")
    parser.add_argument("--json", action="store_true", help="with --dry-run, print a machine-readable command report")
    args = parser.parse_args()

    if args.json and not args.dry_run:
        parser.error("--json requires --dry-run")
    if args.source_stream_timeout_ms <= 0:
        parser.error("--source-stream-timeout-ms must be positive")
    if args.source_stream_poll_ms <= 0:
        parser.error("--source-stream-poll-ms must be positive")
    if args.source_control_timeout_ms <= 0:
        parser.error("--source-control-timeout-ms must be positive")
    if args.source_control_poll_ms <= 0:
        parser.error("--source-control-poll-ms must be positive")

    candidate_network = args.candidate_network or args.candidate_build_dir / "libbambu_networking.dylib"
    candidate_source = args.candidate_source or args.candidate_build_dir / "libBambuSource.dylib"

    try:
        official_network = existing_file(args.official_network, "official network plugin")
        official_source = existing_file(args.official_source, "official source plugin")
        candidate_network = existing_file(candidate_network, "candidate network plugin")
        candidate_source = existing_file(candidate_source, "candidate source plugin")
        print_job_file = existing_file(args.print_job_file, "print job file")
    except argparse.ArgumentTypeError as error:
        parser.error(str(error))

    printer_password = os.environ.get(args.printer_password_env)
    if not printer_password:
        parser.error(f"{args.printer_password_env} must be set in the environment")
    if args.linux_runtime_report and not args.linux_runtime_report.is_file():
        parser.error(f"Linux runtime report does not exist: {args.linux_runtime_report}")
    if any(mode != "upload-only" for mode in args.print_job_modes) and not args.confirm_start_prints:
        parser.error("--confirm-start-prints is required when local-print or sdcard-print is included")
    live_source_url = source_stream_url(args, printer_password) if args.include_source_streaming else ""
    live_control_url = source_control_url(args, printer_password) if args.include_source_control_tunnel else ""
    source_control_parity_out_dir = args.source_control_parity_out_dir or args.parity_out_dir.parent / f"{args.parity_out_dir.name}_source_control_tunnel"

    capture_cmd = [
        sys.executable,
        str(CONTRACT_DIR / "capture_official_parity.py"),
        "--official-network",
        str(official_network),
        "--official-source",
        str(official_source),
        "--candidate-network",
        str(candidate_network),
        "--candidate-source",
        str(candidate_source),
        "--out-dir",
        str(args.parity_out_dir),
        "--include-source-behavior",
        "--include-discovery",
        "--include-ft-job-only",
        "--printer-dev-id",
        args.printer_dev_id,
        "--printer-dev-ip",
        args.printer_dev_ip,
        "--printer-username",
        args.printer_username,
        "--printer-password-env",
        args.printer_password_env,
        "--printer-country-code",
        args.printer_country_code,
        "--printer-message",
        args.printer_message,
        "--printer-wait-ms",
        str(args.printer_wait_ms),
        "--expect-printer-connect-success",
        "--print-job-file",
        str(print_job_file),
        "--print-job-modes",
        ",".join(args.print_job_modes),
        "--print-job-remote-name",
        args.print_job_remote_name,
        "--expect-print-job-success",
    ]
    if args.skip_build:
        capture_cmd.append("--skip-build")
    if args.printer_use_ssl:
        capture_cmd.append("--printer-use-ssl")
    if args.print_job_file_md5:
        capture_cmd.extend(["--print-job-file-md5", args.print_job_file_md5])
    if args.print_job_use_ssl_for_ftp:
        capture_cmd.append("--print-job-use-ssl-for-ftp")
    if args.include_synthetic_ft_behavior:
        capture_cmd.append("--include-ft-behavior")
    if args.include_source_streaming:
        capture_cmd.extend([
            "--source-stream-url",
            live_source_url,
            "--source-stream-mode",
            "video",
            "--source-stream-timeout-ms",
            str(args.source_stream_timeout_ms),
            "--source-stream-poll-ms",
            str(args.source_stream_poll_ms),
            "--source-stream-ctrl-type",
            str(args.source_stream_ctrl_type),
            "--expect-source-stream-success",
        ])

    source_control_capture_cmd = None
    if args.include_source_control_tunnel:
        source_control_capture_cmd = [
            sys.executable,
            str(CONTRACT_DIR / "capture_official_parity.py"),
            "--official-network",
            str(official_network),
            "--official-source",
            str(official_source),
            "--candidate-network",
            str(candidate_network),
            "--candidate-source",
            str(candidate_source),
            "--out-dir",
            str(source_control_parity_out_dir),
            "--include-source-behavior",
            "--include-discovery",
            "--include-ft-job-only",
            "--source-stream-url",
            live_control_url,
            "--source-stream-mode",
            "control",
            "--source-stream-timeout-ms",
            str(args.source_control_timeout_ms),
            "--source-stream-poll-ms",
            str(args.source_control_poll_ms),
            "--source-stream-ctrl-type",
            str(args.source_control_ctrl_type),
            "--source-stream-message",
            args.source_control_message,
            "--expect-source-stream-success",
        ]
        if args.skip_build:
            source_control_capture_cmd.append("--skip-build")

    readiness_cmd = [
        sys.executable,
        str(CONTRACT_DIR / "run_release_readiness.py"),
        "--out-dir",
        str(args.readiness_out_dir),
        "--plugin-build-dir",
        str(args.candidate_build_dir),
        "--candidate-network",
        str(candidate_network),
        "--candidate-source",
        str(candidate_source),
        "--official-parity-report",
        str(args.parity_out_dir / "parity_report.json"),
        "--printer-dev-id",
        args.printer_dev_id,
        "--printer-dev-ip",
        args.printer_dev_ip,
        "--printer-username",
        args.printer_username,
        "--printer-password-env",
        args.printer_password_env,
        "--printer-message",
        args.printer_message,
        "--printer-wait-ms",
        str(args.printer_wait_ms),
        "--print-job-file",
        str(print_job_file),
        "--print-job-modes",
        ",".join(args.print_job_modes),
        "--print-job-remote-name",
        args.print_job_remote_name,
        "--skip-linux-loader-probes",
        "--linux-runtime-report",
        str(args.linux_runtime_report),
    ]
    if args.printer_use_ssl:
        readiness_cmd.append("--printer-use-ssl")
    if args.print_job_use_ssl_for_ftp:
        readiness_cmd.append("--print-job-use-ssl-for-ftp")
    if args.include_source_control_tunnel:
        readiness_cmd.extend([
            "--source-streaming-parity-report",
            str(source_control_parity_out_dir / "parity_report.json"),
        ])
    readiness_cmd.append("--expect-printer-success")

    if args.dry_run:
        if args.json:
            print(json.dumps(dry_run_report(args, capture_cmd, source_control_capture_cmd, readiness_cmd, live_source_url, live_control_url), indent=2, sort_keys=True))
        else:
            print("real-printer parity dry run ok")
            print_command("capture_official_parity", capture_cmd, live_source_url, live_control_url, args.source_control_message)
            if source_control_capture_cmd:
                print_command("capture_source_control_tunnel_parity", source_control_capture_cmd, live_source_url, live_control_url, args.source_control_message)
            print_command("run_release_readiness", readiness_cmd, live_source_url, live_control_url, args.source_control_message)
        return 0

    capture = run(capture_cmd, live_source_url, live_control_url, args.source_control_message)
    if capture.returncode != 0:
        return capture.returncode

    if source_control_capture_cmd:
        source_control_capture = run(source_control_capture_cmd, live_source_url, live_control_url, args.source_control_message)
        if source_control_capture.returncode != 0:
            return source_control_capture.returncode

    return run(readiness_cmd, live_source_url, live_control_url, args.source_control_message).returncode


if __name__ == "__main__":
    raise SystemExit(main())
