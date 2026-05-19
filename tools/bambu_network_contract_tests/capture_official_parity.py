#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "tools/bambu_network_contract_tests"
CONTRACT_BUILD = ROOT / "build/bambu_network_contract_tests"
VALID_PRINT_JOB_MODES = ("upload-only", "local-print", "sdcard-print")
TIMEOUT_EXIT_CODE = 124
TIMEOUT_MARKER = "probe timed out"
REDACTED_SOURCE_STREAM_URL = "<redacted-source-stream-url>"


def text_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def sanitized_command(cmd: list[str]) -> list[str]:
    sanitized = list(cmd)
    for index, value in enumerate(sanitized[:-1]):
        if value == "--source-stream-url":
            sanitized[index + 1] = REDACTED_SOURCE_STREAM_URL
    return sanitized


def run(cmd: list[str], *, capture: bool = False, timeout_s: int | None = None) -> subprocess.CompletedProcess:
    print("+ " + " ".join(sanitized_command(cmd)), file=sys.stderr)
    try:
        return subprocess.run(
            cmd,
            cwd=ROOT,
            check=not capture,
            text=True,
            capture_output=capture,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as error:
        stderr = text_output(error.stderr)
        timeout_line = f"{TIMEOUT_MARKER} after {timeout_s} seconds"
        stderr = f"{stderr.rstrip()}\n{timeout_line}\n" if stderr else f"{timeout_line}\n"
        if capture:
            return subprocess.CompletedProcess(
                cmd,
                TIMEOUT_EXIT_CODE,
                stdout=text_output(error.stdout),
                stderr=stderr,
            )
        raise


def ensure_contract_tools(skip_build: bool) -> None:
    if not skip_build:
        run(["cmake", "-S", str(CONTRACT_DIR), "-B", str(CONTRACT_BUILD)])
        run(["cmake", "--build", str(CONTRACT_BUILD)])

    missing = [
        path
        for path in [
            CONTRACT_BUILD / "bambu_network_contract_probe",
            CONTRACT_BUILD / "bambu_network_lifecycle_probe",
            CONTRACT_BUILD / "bambu_network_callback_probe",
            CONTRACT_BUILD / "bambu_network_unsupported_probe",
            CONTRACT_BUILD / "bambu_network_cloud_service_probe",
            CONTRACT_BUILD / "bambu_network_source_behavior_probe",
            CONTRACT_BUILD / "bambu_network_source_streaming_probe",
            CONTRACT_BUILD / "bambu_network_printer_workflow_probe",
            CONTRACT_BUILD / "bambu_network_print_job_probe",
            CONTRACT_BUILD / "bambu_network_event_bridge_probe",
            CONTRACT_BUILD / "bambu_network_discovery_probe",
            CONTRACT_BUILD / "bambu_network_camera_url_probe",
            CONTRACT_BUILD / "bambu_network_ft_behavior_probe",
        ]
        if not path.exists()
    ]
    if missing:
        formatted = "\n".join(str(path) for path in missing)
        raise RuntimeError(f"missing contract tools:\n{formatted}")


def run_json_probe(name: str, side: str, cmd: list[str], output_path: pathlib.Path, timeout_s: int) -> dict:
    completed = run(cmd, capture=True, timeout_s=timeout_s)
    if completed.stderr:
        output_path.with_suffix(output_path.suffix + ".stderr").write_text(completed.stderr, encoding="utf-8")

    stdout = completed.stdout
    timed_out = completed.returncode == TIMEOUT_EXIT_CODE and TIMEOUT_MARKER in (completed.stderr or "")
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as error:
        json_start = stdout.find("{")
        if json_start >= 0:
            try:
                data = json.loads(stdout[json_start:])
            except json.JSONDecodeError:
                data = {
                    "ok": False,
                    "error": f"{side} {name} did not emit JSON: {error}",
                    "stdout_tail": stdout[-4000:],
                    "stderr_tail": completed.stderr[-4000:] if completed.stderr else "",
                }
        else:
            data = {
                "ok": False,
                "error": f"{side} {name} did not emit JSON: {error}",
                "stdout_tail": stdout[-4000:],
                "stderr_tail": completed.stderr[-4000:] if completed.stderr else "",
            }
    if not isinstance(data, dict):
        data = {
            "ok": False,
            "error": f"{side} {name} emitted non-object JSON",
            "stdout_tail": stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:] if completed.stderr else "",
        }
    if timed_out:
        data = {
            "ok": False,
            "error": f"{side} {name} timed out after {timeout_s} seconds",
            "stdout_tail": stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:] if completed.stderr else "",
        }

    output_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "path": str(output_path),
        "exit_code": completed.returncode,
        "timed_out": timed_out,
        "ok": completed.returncode == 0 and data.get("ok") is not False,
    }


def compare_transcripts(name: str, official_path: pathlib.Path, candidate_path: pathlib.Path, output_path: pathlib.Path) -> dict:
    completed = run(
        [
            "python3",
            str(CONTRACT_DIR / "compare_transcripts.py"),
            str(official_path),
            str(candidate_path),
        ],
        capture=True,
    )
    output = completed.stdout
    if completed.stderr:
        output += "\n[stderr]\n" + completed.stderr
    output_path.write_text(output, encoding="utf-8")

    return {
        "path": str(output_path),
        "exit_code": completed.returncode,
        "ok": completed.returncode == 0,
    }


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def binary_metadata(path: pathlib.Path) -> dict[str, object]:
    resolved = path.resolve()
    return {
        "path": str(resolved),
        "exists": resolved.exists(),
        "size": resolved.stat().st_size if resolved.exists() else None,
        "sha256": sha256_file(resolved) if resolved.exists() else None,
    }


def make_input_manifest(args: argparse.Namespace) -> dict[str, object]:
    return {
        "official": {
            "network": binary_metadata(pathlib.Path(args.official_network)),
            "source": binary_metadata(pathlib.Path(args.official_source)),
        },
        "candidate": {
            "network": binary_metadata(pathlib.Path(args.candidate_network)),
            "source": binary_metadata(pathlib.Path(args.candidate_source)),
        },
        "print_job_modes": args.resolved_print_job_modes,
        "artifact_policy": {
            "copies_input_binaries": False,
            "stores_hashes_and_probe_transcripts_only": True,
        },
        "self_compare_allowed": args.allow_self_compare,
    }


def same_existing_binary(left: pathlib.Path, right: pathlib.Path) -> bool:
    left_resolved = left.resolve()
    right_resolved = right.resolve()
    if not left_resolved.exists() or not right_resolved.exists():
        return False
    if left_resolved == right_resolved:
        return True
    return left_resolved.stat().st_size == right_resolved.stat().st_size and sha256_file(left_resolved) == sha256_file(right_resolved)


def parse_print_job_modes(value: str) -> list[str]:
    modes = [mode.strip() for mode in value.split(",") if mode.strip()]
    invalid = [mode for mode in modes if mode not in VALID_PRINT_JOB_MODES]
    if invalid:
        joined = ", ".join(invalid)
        valid = ", ".join(VALID_PRINT_JOB_MODES)
        raise ValueError(f"invalid print job mode(s): {joined}; expected comma-separated values from: {valid}")
    return modes


def reject_accidental_self_compare(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.allow_self_compare:
        return

    same_inputs = []
    if same_existing_binary(pathlib.Path(args.official_network), pathlib.Path(args.candidate_network)):
        same_inputs.append("network")
    if same_existing_binary(pathlib.Path(args.official_source), pathlib.Path(args.candidate_source)):
        same_inputs.append("source")
    if same_inputs:
        joined = ", ".join(same_inputs)
        parser.error(
            f"official and candidate {joined} payloads are identical; use --allow-self-compare only for harness self-tests"
        )


def make_probe_commands(args: argparse.Namespace, side: str, base_dir: pathlib.Path) -> dict[str, list[str]]:
    network = pathlib.Path(getattr(args, f"{side}_network"))
    source = pathlib.Path(getattr(args, f"{side}_source"))
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    commands = {
        "network_symbols": [
            str(CONTRACT_BUILD / "bambu_network_contract_probe"),
            "--plugin",
            str(network),
            "--symbols",
            str(CONTRACT_DIR / "required_symbols.txt"),
            "--json",
        ],
        "source_symbols": [
            str(CONTRACT_BUILD / "bambu_network_contract_probe"),
            "--plugin",
            str(source),
            "--symbols",
            str(CONTRACT_DIR / "source_symbols.txt"),
            "--json",
        ],
        "lifecycle": [
            str(CONTRACT_BUILD / "bambu_network_lifecycle_probe"),
            "--plugin",
            str(network),
            "--log-dir",
            str(log_dir / "lifecycle"),
        ],
        "callback": [
            str(CONTRACT_BUILD / "bambu_network_callback_probe"),
            "--plugin",
            str(network),
            "--log-dir",
            str(log_dir / "callback"),
        ],
        "unsupported": [
            str(CONTRACT_BUILD / "bambu_network_unsupported_probe"),
            "--network-plugin",
            str(network),
            "--source-plugin",
            str(source),
            "--log-dir",
            str(log_dir / "unsupported"),
            "--official-compatible",
        ],
    }

    if args.include_source_behavior:
        commands["source_behavior"] = [
            str(CONTRACT_BUILD / "bambu_network_source_behavior_probe"),
            "--source-plugin",
            str(source),
            "--record-only",
        ]

    if args.include_discovery:
        commands["discovery"] = [
            str(CONTRACT_BUILD / "bambu_network_discovery_probe"),
            "--plugin",
            str(network),
            "--log-dir",
            str(log_dir / "discovery"),
        ]

    if args.include_ft_behavior:
        commands["ft_behavior"] = [
            str(CONTRACT_BUILD / "bambu_network_ft_behavior_probe"),
            "--plugin",
            str(network),
            "--log-dir",
            str(log_dir / "ft_behavior"),
        ]

    if args.include_ft_job_only:
        commands["ft_job_invalid"] = [
            str(CONTRACT_BUILD / "bambu_network_ft_behavior_probe"),
            "--plugin",
            str(network),
            "--log-dir",
            str(log_dir / "ft_job_invalid"),
            "--skip-agent-bootstrap",
            "--job-only",
        ]

    if args.include_cloud_service:
        cloud_service = [
            str(CONTRACT_BUILD / "bambu_network_cloud_service_probe"),
            "--plugin",
            str(network),
            "--log-dir",
            str(log_dir / "cloud_service"),
            "--detail-id",
            args.cloud_detail_id,
            "--task-id",
            args.cloud_task_id,
            "--subscribe-module",
            args.cloud_subscribe_module,
        ]
        if args.cloud_user_info_file:
            cloud_service += ["--user-info-file", args.cloud_user_info_file]
        if args.cloud_user_info_env:
            cloud_service += ["--user-info-env", args.cloud_user_info_env]
        if args.cloud_ticket_env:
            cloud_service += ["--ticket-env", args.cloud_ticket_env]
        if args.cloud_access_token_env:
            cloud_service += ["--access-token-env", args.cloud_access_token_env]
        if args.allow_cloud_network:
            cloud_service.append("--allow-network")
        if args.expect_cloud_service_success:
            cloud_service.append("--expect-success")
        commands["cloud_service"] = cloud_service

    if args.source_stream_url:
        source_streaming = [
            str(CONTRACT_BUILD / "bambu_network_source_streaming_probe"),
            "--source-plugin",
            str(source),
            "--url",
            args.source_stream_url,
            "--mode",
            args.source_stream_mode,
            "--timeout-ms",
            str(args.source_stream_timeout_ms),
            "--poll-ms",
            str(args.source_stream_poll_ms),
            "--ctrl-type",
            str(args.source_stream_ctrl_type),
        ]
        if args.source_stream_message:
            source_streaming += ["--message", args.source_stream_message]
        if args.expect_source_stream_success:
            source_streaming.append("--expect-success")
        commands["source_streaming"] = source_streaming

    if args.printer_dev_id and args.printer_dev_ip:
        printer = [
            str(CONTRACT_BUILD / "bambu_network_printer_workflow_probe"),
            "--plugin",
            str(network),
            "--log-dir",
            str(log_dir / "printer_workflow"),
            "--dev-id",
            args.printer_dev_id,
            "--dev-ip",
            args.printer_dev_ip,
            "--username",
            args.printer_username,
            "--password-env",
            args.printer_password_env,
            "--country-code",
            args.printer_country_code,
            "--wait-ms",
            str(args.printer_wait_ms),
            "--use-ssl",
            "true" if args.printer_use_ssl else "false",
        ]
        if args.printer_message:
            printer += ["--message", args.printer_message]
        if args.expect_printer_connect_success:
            printer.append("--expect-connect-success")
        commands["printer_workflow"] = printer

    if args.print_job_file and args.printer_dev_id and args.printer_dev_ip:
        modes = args.resolved_print_job_modes
        for mode in modes:
            probe_name = "print_job" if len(modes) == 1 else f"print_job_{mode.replace('-', '_')}"
            print_job = [
                str(CONTRACT_BUILD / "bambu_network_print_job_probe"),
                "--plugin",
                str(network),
                "--log-dir",
                str(log_dir / probe_name),
                "--mode",
                mode,
                "--dev-id",
                args.printer_dev_id,
                "--dev-ip",
                args.printer_dev_ip,
                "--username",
                args.printer_username,
                "--password-env",
                args.printer_password_env,
                "--country-code",
                args.printer_country_code,
                "--file",
                args.print_job_file,
                "--wait-ms",
                str(args.printer_wait_ms),
                "--use-ssl-for-ftp",
                "true" if args.print_job_use_ssl_for_ftp else "false",
                "--use-ssl-for-mqtt",
                "true" if args.printer_use_ssl else "false",
            ]
            if args.print_job_remote_name:
                print_job += ["--remote-name", args.print_job_remote_name]
            if args.print_job_file_md5:
                print_job += ["--file-md5", args.print_job_file_md5]
            if args.expect_print_job_success:
                print_job.append("--expect-success")
            commands[probe_name] = print_job

    for command in commands.values():
        for index, value in enumerate(command):
            if value == "--log-dir" and index + 1 < len(command):
                pathlib.Path(command[index + 1]).mkdir(parents=True, exist_ok=True)

    return commands


def make_candidate_only_commands(args: argparse.Namespace, base_dir: pathlib.Path) -> dict[str, list[str]]:
    network = pathlib.Path(args.candidate_network)
    source = pathlib.Path(args.candidate_source)
    log_dir = base_dir / "candidate_only_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    commands = {
        "candidate_source_behavior": [
            str(CONTRACT_BUILD / "bambu_network_source_behavior_probe"),
            "--source-plugin",
            str(source),
        ],
        "candidate_event_bridge": [
            str(CONTRACT_BUILD / "bambu_network_event_bridge_probe"),
            "--plugin",
            str(network),
            "--log-dir",
            str(log_dir / "event_bridge"),
        ],
        "candidate_camera_url": [
            str(CONTRACT_BUILD / "bambu_network_camera_url_probe"),
            "--plugin",
            str(network),
            "--log-dir",
            str(log_dir / "camera_url"),
        ],
        "candidate_unsupported_hardening": [
            str(CONTRACT_BUILD / "bambu_network_unsupported_probe"),
            "--network-plugin",
            str(network),
            "--source-plugin",
            str(source),
            "--log-dir",
            str(log_dir / "unsupported_hardening"),
        ],
    }

    for command in commands.values():
        for index, value in enumerate(command):
            if value == "--log-dir" and index + 1 < len(command):
                pathlib.Path(command[index + 1]).mkdir(parents=True, exist_ok=True)

    return commands


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-network", required=True, help="path to the official libbambu_networking payload")
    parser.add_argument("--official-source", required=True, help="path to the official libBambuSource payload")
    parser.add_argument("--candidate-network", required=True, help="path to the candidate libbambu_networking payload")
    parser.add_argument("--candidate-source", required=True, help="path to the candidate libBambuSource payload")
    parser.add_argument("--out-dir", required=True, help="directory where parity artifacts will be written")
    parser.add_argument("--skip-build", action="store_true", help="reuse existing contract test binaries")
    parser.add_argument("--printer-dev-id", default="", help="optional real printer device id for LAN workflow parity")
    parser.add_argument("--printer-dev-ip", default="", help="optional real printer IP address for LAN workflow parity")
    parser.add_argument("--printer-username", default="bblp")
    parser.add_argument("--printer-password-env", default="BAMBU_NETWORK_PRINTER_PASSWORD")
    parser.add_argument("--printer-country-code", default="US")
    parser.add_argument("--printer-message", default="", help="optional JSON command to send after connect")
    parser.add_argument("--printer-wait-ms", type=int, default=1000)
    parser.add_argument("--printer-use-ssl", action="store_true")
    parser.add_argument("--expect-printer-connect-success", action="store_true")
    parser.add_argument("--include-discovery", action="store_true", help="also run synthetic UDP discovery parity against both plugins")
    parser.add_argument("--include-source-behavior", action="store_true", help="also record and compare detailed libBambuSource behavior")
    parser.add_argument("--include-ft-behavior", action="store_true", help="also record and compare ft_* tunnel/job behavior")
    parser.add_argument("--include-ft-job-only", action="store_true", help="also record and compare official-safe invalid ft_job_create behavior")
    parser.add_argument("--include-cloud-service", action="store_true", help="also record and compare authorized cloud/service behavior")
    parser.add_argument("--cloud-user-info-file", default="", help="optional login-info JSON file for cloud/service parity; contents are not written to artifacts")
    parser.add_argument("--cloud-user-info-env", default="", help="optional env var containing login-info JSON for cloud/service parity")
    parser.add_argument("--cloud-ticket-env", default="", help="optional env var containing a login ticket for get_my_token parity")
    parser.add_argument("--cloud-access-token-env", default="", help="optional env var containing an access token for get_my_profile parity")
    parser.add_argument("--cloud-detail-id", default="0")
    parser.add_argument("--cloud-task-id", default="0")
    parser.add_argument("--cloud-subscribe-module", default="app")
    parser.add_argument("--allow-cloud-network", action="store_true")
    parser.add_argument("--expect-cloud-service-success", action="store_true")
    parser.add_argument("--source-stream-url", default="", help="optional bambu:///... URL for live libBambuSource streaming parity")
    parser.add_argument("--source-stream-mode", default="video", choices=("video", "control"))
    parser.add_argument("--source-stream-timeout-ms", type=int, default=10000)
    parser.add_argument("--source-stream-poll-ms", type=int, default=50)
    parser.add_argument("--source-stream-ctrl-type", type=int, default=0x3001)
    parser.add_argument("--source-stream-message", default="")
    parser.add_argument("--expect-source-stream-success", action="store_true")
    parser.add_argument("--probe-timeout-s", type=int, default=30, help="maximum seconds to wait for each captured probe")
    parser.add_argument("--print-job-file", default="", help="optional local 3MF/G-code file for LAN print/upload job parity")
    parser.add_argument("--print-job-mode", default="", choices=VALID_PRINT_JOB_MODES, help="single print-job mode; kept for one-off parity runs")
    parser.add_argument("--print-job-modes", default="", help="comma-separated print-job modes to run")
    parser.add_argument("--print-job-remote-name", default="")
    parser.add_argument("--print-job-file-md5", default="")
    parser.add_argument("--print-job-use-ssl-for-ftp", action="store_true")
    parser.add_argument("--expect-print-job-success", action="store_true")
    parser.add_argument("--allow-self-compare", action="store_true", help="allow official and candidate inputs to be the same binary for harness self-tests")
    args = parser.parse_args()

    if bool(args.printer_dev_id) != bool(args.printer_dev_ip):
        parser.error("--printer-dev-id and --printer-dev-ip must be provided together")
    if args.expect_cloud_service_success and not args.include_cloud_service:
        parser.error("--expect-cloud-service-success requires --include-cloud-service")
    if args.expect_cloud_service_success and not args.allow_cloud_network:
        parser.error("--expect-cloud-service-success requires --allow-cloud-network")
    if args.expect_cloud_service_success and not (args.cloud_user_info_file or args.cloud_user_info_env):
        parser.error("--expect-cloud-service-success requires --cloud-user-info-file or --cloud-user-info-env")
    if args.cloud_user_info_file and args.cloud_user_info_env:
        parser.error("use only one of --cloud-user-info-file or --cloud-user-info-env")
    if args.expect_source_stream_success and not args.source_stream_url:
        parser.error("--expect-source-stream-success requires --source-stream-url")
    if args.source_stream_timeout_ms <= 0:
        parser.error("--source-stream-timeout-ms must be positive")
    if args.source_stream_poll_ms <= 0:
        parser.error("--source-stream-poll-ms must be positive")
    if args.probe_timeout_s <= 0:
        parser.error("--probe-timeout-s must be positive")
    if args.print_job_file and not (args.printer_dev_id and args.printer_dev_ip):
        parser.error("--print-job-file requires --printer-dev-id and --printer-dev-ip")
    try:
        if args.print_job_modes:
            args.resolved_print_job_modes = parse_print_job_modes(args.print_job_modes)
        elif args.print_job_mode:
            args.resolved_print_job_modes = [args.print_job_mode]
        else:
            args.resolved_print_job_modes = ["upload-only"]
    except ValueError as error:
        parser.error(str(error))
    if args.print_job_file and not args.resolved_print_job_modes:
        parser.error("--print-job-file requires at least one print-job mode")
    if args.print_job_file and not args.print_job_remote_name and any(mode != "upload-only" for mode in args.resolved_print_job_modes):
        parser.error("--print-job-remote-name is required for local-print and sdcard-print parity")
    reject_accidental_self_compare(args, parser)

    ensure_contract_tools(args.skip_build)

    out_dir = pathlib.Path(args.out_dir)
    official_dir = out_dir / "official"
    candidate_dir = out_dir / "candidate"
    compare_dir = out_dir / "compare"
    for path in [official_dir, candidate_dir, compare_dir]:
        path.mkdir(parents=True, exist_ok=True)

    official_commands = make_probe_commands(args, "official", official_dir)
    candidate_commands = make_probe_commands(args, "candidate", candidate_dir)

    report: dict[str, object] = {
        "out_dir": str(out_dir),
        "inputs": make_input_manifest(args),
        "probes": {},
        "candidate_only_probes": {},
        "comparisons": {},
        "failed": [],
    }

    probe_report: dict[str, object] = {}
    for name in official_commands:
        official_path = official_dir / f"{name}.json"
        candidate_path = candidate_dir / f"{name}.json"
        probe_report[name] = {
            "official": run_json_probe(name, "official", official_commands[name], official_path, args.probe_timeout_s),
            "candidate": run_json_probe(name, "candidate", candidate_commands[name], candidate_path, args.probe_timeout_s),
        }

    comparison_report: dict[str, object] = {}
    for name in official_commands:
        comparison_report[name] = compare_transcripts(
            name,
            official_dir / f"{name}.json",
            candidate_dir / f"{name}.json",
            compare_dir / f"{name}.txt",
        )

    candidate_only_report: dict[str, object] = {}
    for name, command in make_candidate_only_commands(args, candidate_dir).items():
        candidate_only_report[name] = run_json_probe(name, "candidate", command, candidate_dir / f"{name}.json", args.probe_timeout_s)

    failed: list[str] = []
    for name, result in probe_report.items():
        assert isinstance(result, dict)
        official = result["official"]
        candidate = result["candidate"]
        if isinstance(official, dict) and not official["ok"]:
            failed.append(f"official {name}")
        if isinstance(candidate, dict) and not candidate["ok"]:
            failed.append(f"candidate {name}")

    for name, result in comparison_report.items():
        if isinstance(result, dict) and not result["ok"]:
            failed.append(f"compare {name}")

    for name, result in candidate_only_report.items():
        if isinstance(result, dict) and not result["ok"]:
            failed.append(name)

    report["probes"] = probe_report
    report["candidate_only_probes"] = candidate_only_report
    report["comparisons"] = comparison_report
    report["failed"] = failed
    report["ok"] = not failed

    report_path = out_dir / "parity_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
