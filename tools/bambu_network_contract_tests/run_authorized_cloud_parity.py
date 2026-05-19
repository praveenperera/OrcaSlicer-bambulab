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
DEFAULT_PARITY_DIR = ROOT / "build/bambu_network_release_readiness/official_parity_authorized_cloud_current"
DEFAULT_READINESS_DIR = ROOT / "build/bambu_network_release_readiness"


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    print("+ " + " ".join(shlex.quote(part) for part in cmd), file=sys.stderr)
    return subprocess.run(cmd, cwd=ROOT, text=True, check=False)


def print_command(label: str, cmd: list[str]) -> None:
    print(f"{label}:")
    print(" ".join(shlex.quote(part) for part in cmd))


def existing_file(path: pathlib.Path, label: str) -> pathlib.Path:
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"{label} does not exist or is not a file: {path}")
    return path


def env_present(name: str) -> bool:
    return bool(name and os.environ.get(name))


def dry_run_report(args: argparse.Namespace, capture_cmd: list[str], readiness_cmd: list[str]) -> dict[str, object]:
    return {
        "ok": True,
        "dry_run": True,
        "will_use_network": True,
        "cloud": {
            "user_info_file_present": bool(args.cloud_user_info_file),
            "user_info_env": args.cloud_user_info_env,
            "user_info_env_present": env_present(args.cloud_user_info_env),
            "ticket_env": args.cloud_ticket_env,
            "ticket_env_present": env_present(args.cloud_ticket_env),
            "access_token_env": args.cloud_access_token_env,
            "access_token_env_present": env_present(args.cloud_access_token_env),
            "detail_id": args.cloud_detail_id,
            "task_id": args.cloud_task_id,
            "subscribe_module": args.cloud_subscribe_module,
        },
        "commands": {
            "capture_official_parity": capture_cmd,
            "run_release_readiness": readiness_cmd,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run authorized Bambu cloud/service official-vs-candidate parity capture and readiness aggregation",
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
    parser.add_argument("--cloud-user-info-file", type=pathlib.Path, default=None)
    parser.add_argument("--cloud-user-info-env", default="")
    parser.add_argument("--cloud-ticket-env", default="")
    parser.add_argument("--cloud-access-token-env", default="")
    parser.add_argument("--cloud-detail-id", default="0")
    parser.add_argument("--cloud-task-id", default="0")
    parser.add_argument("--cloud-subscribe-module", default="app")
    parser.add_argument("--probe-timeout-s", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true", help="validate inputs and print commands without launching plugin probes")
    parser.add_argument("--json", action="store_true", help="with --dry-run, print a machine-readable command report")
    args = parser.parse_args()

    if args.json and not args.dry_run:
        parser.error("--json requires --dry-run")
    if args.cloud_user_info_file and args.cloud_user_info_env:
        parser.error("use only one of --cloud-user-info-file or --cloud-user-info-env")
    if not args.cloud_user_info_file and not args.cloud_user_info_env:
        parser.error("--cloud-user-info-file or --cloud-user-info-env is required")
    if args.cloud_user_info_env and not env_present(args.cloud_user_info_env):
        parser.error(f"{args.cloud_user_info_env} must be set in the environment")
    if args.cloud_ticket_env and not env_present(args.cloud_ticket_env):
        parser.error(f"{args.cloud_ticket_env} must be set in the environment")
    if args.cloud_access_token_env and not env_present(args.cloud_access_token_env):
        parser.error(f"{args.cloud_access_token_env} must be set in the environment")
    if args.probe_timeout_s <= 0:
        parser.error("--probe-timeout-s must be positive")

    candidate_network = args.candidate_network or args.candidate_build_dir / "libbambu_networking.dylib"
    candidate_source = args.candidate_source or args.candidate_build_dir / "libBambuSource.dylib"

    try:
        official_network = existing_file(args.official_network, "official network plugin")
        official_source = existing_file(args.official_source, "official source plugin")
        candidate_network = existing_file(candidate_network, "candidate network plugin")
        candidate_source = existing_file(candidate_source, "candidate source plugin")
        if args.cloud_user_info_file:
            cloud_user_info_file = existing_file(args.cloud_user_info_file, "cloud user-info file")
        else:
            cloud_user_info_file = None
    except argparse.ArgumentTypeError as error:
        parser.error(str(error))

    if args.linux_runtime_report and not args.linux_runtime_report.is_file():
        parser.error(f"Linux runtime report does not exist: {args.linux_runtime_report}")

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
        "--include-cloud-service",
        "--allow-cloud-network",
        "--expect-cloud-service-success",
        "--cloud-detail-id",
        args.cloud_detail_id,
        "--cloud-task-id",
        args.cloud_task_id,
        "--cloud-subscribe-module",
        args.cloud_subscribe_module,
        "--probe-timeout-s",
        str(args.probe_timeout_s),
    ]
    if args.skip_build:
        capture_cmd.append("--skip-build")
    if cloud_user_info_file:
        capture_cmd.extend(["--cloud-user-info-file", str(cloud_user_info_file)])
    if args.cloud_user_info_env:
        capture_cmd.extend(["--cloud-user-info-env", args.cloud_user_info_env])
    if args.cloud_ticket_env:
        capture_cmd.extend(["--cloud-ticket-env", args.cloud_ticket_env])
    if args.cloud_access_token_env:
        capture_cmd.extend(["--cloud-access-token-env", args.cloud_access_token_env])

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
        "--include-cloud-service",
        "--allow-cloud-network",
        "--expect-cloud-service-success",
        "--cloud-detail-id",
        args.cloud_detail_id,
        "--cloud-task-id",
        args.cloud_task_id,
        "--cloud-subscribe-module",
        args.cloud_subscribe_module,
        "--skip-linux-loader-probes",
        "--linux-runtime-report",
        str(args.linux_runtime_report),
        "--defer-manual-printer-parity",
        "--allow-incomplete",
    ]
    if cloud_user_info_file:
        readiness_cmd.extend(["--cloud-user-info-file", str(cloud_user_info_file)])
    if args.cloud_user_info_env:
        readiness_cmd.extend(["--cloud-user-info-env", args.cloud_user_info_env])
    if args.cloud_ticket_env:
        readiness_cmd.extend(["--cloud-ticket-env", args.cloud_ticket_env])
    if args.cloud_access_token_env:
        readiness_cmd.extend(["--cloud-access-token-env", args.cloud_access_token_env])

    if args.dry_run:
        if args.json:
            print(json.dumps(dry_run_report(args, capture_cmd, readiness_cmd), indent=2, sort_keys=True))
        else:
            print("authorized cloud parity dry run ok")
            print_command("capture_official_parity", capture_cmd)
            print_command("run_release_readiness", readiness_cmd)
        return 0

    capture = run(capture_cmd)
    if capture.returncode != 0:
        return capture.returncode

    return run(readiness_cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
