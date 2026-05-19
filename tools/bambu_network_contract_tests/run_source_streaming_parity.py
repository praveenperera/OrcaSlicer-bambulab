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
DEFAULT_PARITY_DIR = ROOT / "build/bambu_network_release_readiness/official_parity_source_streaming_current"
DEFAULT_READINESS_DIR = ROOT / "build/bambu_network_release_readiness"
REDACTED_URL = "<redacted-source-stream-url>"


def redact_url(url: str) -> str:
    marker = "___"
    marker_pos = url.find(marker)
    at_pos = url.find("@", marker_pos + len(marker) if marker_pos != -1 else 0)
    if marker_pos != -1 and at_pos != -1:
        userinfo_start = marker_pos + len(marker)
        colon_pos = url.find(":", userinfo_start)
        if colon_pos != -1 and colon_pos < at_pos:
            url = url[: colon_pos + 1] + "<redacted>" + url[at_pos:]

    passwd_key = "passwd="
    search_pos = 0
    while True:
        search_pos = url.find(passwd_key, search_pos)
        if search_pos == -1:
            return url
        value_start = search_pos + len(passwd_key)
        value_end = url.find("&", value_start)
        if value_end == -1:
            value_end = len(url)
        url = url[:value_start] + "<redacted>" + url[value_end:]
        search_pos = value_start + len("<redacted>")


def sanitized_command(cmd: list[str], source_url: str) -> list[str]:
    return [REDACTED_URL if part == source_url else part for part in cmd]


def run(cmd: list[str], source_url: str) -> subprocess.CompletedProcess:
    printable = sanitized_command(cmd, source_url)
    print("+ " + " ".join(shlex.quote(part) for part in printable), file=sys.stderr)
    return subprocess.run(cmd, cwd=ROOT, text=True, check=False)


def print_command(label: str, cmd: list[str], source_url: str) -> None:
    print(f"{label}:")
    print(" ".join(shlex.quote(part) for part in sanitized_command(cmd, source_url)))


def existing_file(path: pathlib.Path, label: str) -> pathlib.Path:
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"{label} does not exist or is not a file: {path}")
    return path


def resolve_source_url(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str:
    if args.source_stream_url and args.source_stream_url_env:
        parser.error("use only one of --source-stream-url or --source-stream-url-env")
    if args.source_stream_url_env:
        value = os.environ.get(args.source_stream_url_env)
        if not value:
            parser.error(f"{args.source_stream_url_env} must be set in the environment")
        return value
    if not args.source_stream_url:
        parser.error("--source-stream-url or --source-stream-url-env is required")
    return args.source_stream_url


def dry_run_report(args: argparse.Namespace, source_url: str, capture_cmd: list[str], readiness_cmd: list[str]) -> dict[str, object]:
    return {
        "ok": True,
        "dry_run": True,
        "will_open_source_stream": True,
        "source_stream": {
            "url_present": True,
            "url_env": args.source_stream_url_env,
            "url_env_present": bool(args.source_stream_url_env and os.environ.get(args.source_stream_url_env)),
            "redacted_url": redact_url(source_url),
            "mode": args.source_stream_mode,
            "timeout_ms": args.source_stream_timeout_ms,
            "poll_ms": args.source_stream_poll_ms,
            "ctrl_type": args.source_stream_ctrl_type,
            "message_present": bool(args.source_stream_message),
        },
        "commands": {
            "capture_official_parity": sanitized_command(capture_cmd, source_url),
            "run_release_readiness": sanitized_command(readiness_cmd, source_url),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run live libBambuSource official-vs-candidate streaming parity capture and readiness aggregation",
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
    parser.add_argument("--source-stream-url", default="")
    parser.add_argument("--source-stream-url-env", default="")
    parser.add_argument("--source-stream-mode", default="video", choices=("video", "control"))
    parser.add_argument("--source-stream-timeout-ms", type=int, default=10000)
    parser.add_argument("--source-stream-poll-ms", type=int, default=50)
    parser.add_argument("--source-stream-ctrl-type", type=int, default=0x3001)
    parser.add_argument("--source-stream-message", default="")
    parser.add_argument("--probe-timeout-s", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true", help="validate inputs and print commands without launching plugin probes")
    parser.add_argument("--json", action="store_true", help="with --dry-run, print a machine-readable command report")
    args = parser.parse_args()

    if args.json and not args.dry_run:
        parser.error("--json requires --dry-run")
    if args.source_stream_timeout_ms <= 0:
        parser.error("--source-stream-timeout-ms must be positive")
    if args.source_stream_poll_ms <= 0:
        parser.error("--source-stream-poll-ms must be positive")
    if args.probe_timeout_s <= 0:
        parser.error("--probe-timeout-s must be positive")

    source_url = resolve_source_url(args, parser)
    candidate_network = args.candidate_network or args.candidate_build_dir / "libbambu_networking.dylib"
    candidate_source = args.candidate_source or args.candidate_build_dir / "libBambuSource.dylib"

    try:
        official_network = existing_file(args.official_network, "official network plugin")
        official_source = existing_file(args.official_source, "official source plugin")
        candidate_network = existing_file(candidate_network, "candidate network plugin")
        candidate_source = existing_file(candidate_source, "candidate source plugin")
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
        "--source-stream-url",
        source_url,
        "--source-stream-mode",
        args.source_stream_mode,
        "--source-stream-timeout-ms",
        str(args.source_stream_timeout_ms),
        "--source-stream-poll-ms",
        str(args.source_stream_poll_ms),
        "--source-stream-ctrl-type",
        str(args.source_stream_ctrl_type),
        "--expect-source-stream-success",
        "--probe-timeout-s",
        str(args.probe_timeout_s),
    ]
    if args.skip_build:
        capture_cmd.append("--skip-build")
    if args.source_stream_message:
        capture_cmd.extend(["--source-stream-message", args.source_stream_message])

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
        "--skip-linux-loader-probes",
        "--linux-runtime-report",
        str(args.linux_runtime_report),
        "--defer-manual-printer-parity",
        "--defer-authorized-cloud-parity",
        "--allow-incomplete",
    ]

    if args.dry_run:
        if args.json:
            print(json.dumps(dry_run_report(args, source_url, capture_cmd, readiness_cmd), indent=2, sort_keys=True))
        else:
            print("source-streaming parity dry run ok")
            print_command("capture_official_parity", capture_cmd, source_url)
            print_command("run_release_readiness", readiness_cmd, source_url)
        return 0

    capture = run(capture_cmd, source_url)
    if capture.returncode != 0:
        return capture.returncode

    return run(readiness_cmd, source_url).returncode


if __name__ == "__main__":
    raise SystemExit(main())
