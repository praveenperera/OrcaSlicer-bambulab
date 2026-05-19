#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "tools/bambu_network_contract_tests/run_authorized_cloud_parity.py"


def write_file(path: pathlib.Path, content: bytes = b"fixture\n") -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def run_wrapper(work: pathlib.Path, *extra: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    official_network = write_file(work / "official/libbambu_networking.dylib")
    official_source = write_file(work / "official/libBambuSource.dylib")
    candidate_network = write_file(work / "candidate/libbambu_networking.dylib")
    candidate_source = write_file(work / "candidate/libBambuSource.dylib")
    linux_report = write_file(work / "linux_bridge_runtime_verify_report.json", b"{}\n")

    merged_env = os.environ.copy()
    merged_env.update({
        "BAMBU_CLOUD_LOGIN_INFO_JSON": '{"access_token":"dry-run-secret-token","user":{"id":"dry-run"}}',
        "BAMBU_CLOUD_TICKET": "dry-run-secret-ticket",
        "BAMBU_CLOUD_ACCESS_TOKEN": "dry-run-secret-access-token",
    })
    if env is not None:
        merged_env.update(env)

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
            "--cloud-user-info-env",
            "BAMBU_CLOUD_LOGIN_INFO_JSON",
            "--cloud-ticket-env",
            "BAMBU_CLOUD_TICKET",
            "--cloud-access-token-env",
            "BAMBU_CLOUD_ACCESS_TOKEN",
            "--skip-build",
            "--dry-run",
            *extra,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=merged_env,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    secret_values = [
        '{"access_token":"dry-run-secret-token","user":{"id":"dry-run"}}',
        "dry-run-secret-ticket",
        "dry-run-secret-access-token",
    ]

    with tempfile.TemporaryDirectory(prefix="bambu-authorized-cloud-dry-run-") as tmp:
        work = pathlib.Path(tmp)

        human = run_wrapper(work)
        require(human.returncode == 0, f"human dry run failed: {human.stderr}\n{human.stdout}")
        require("authorized cloud parity dry run ok" in human.stdout, "dry run did not report success")
        require("capture_official_parity:" in human.stdout, "dry run did not print capture command")
        require("run_release_readiness:" in human.stdout, "dry run did not print readiness command")
        for value in secret_values:
            require(value not in human.stdout, "human dry-run output leaked a secret value")

        json_report = run_wrapper(work / "json-report", "--json")
        require(json_report.returncode == 0, f"JSON dry run failed: {json_report.stderr}\n{json_report.stdout}")
        for value in secret_values:
            require(value not in json_report.stdout, "JSON dry-run output leaked a secret value")
        payload = json.loads(json_report.stdout)
        require(payload.get("ok") is True and payload.get("dry_run") is True, "JSON dry run did not report ok dry-run status")
        require(payload.get("will_use_network") is True, "JSON dry run did not record network use")
        cloud = payload.get("cloud", {})
        require(cloud.get("user_info_env_present") is True, "JSON dry run did not record user-info env presence")
        require(cloud.get("ticket_env_present") is True, "JSON dry run did not record ticket env presence")
        require(cloud.get("access_token_env_present") is True, "JSON dry run did not record access-token env presence")
        commands = payload.get("commands", {})
        capture = commands.get("capture_official_parity")
        readiness = commands.get("run_release_readiness")
        require(isinstance(capture, list), "JSON dry run did not include capture argv")
        require(isinstance(readiness, list), "JSON dry run did not include readiness argv")
        require("--expect-cloud-service-success" in capture, "capture command does not require cloud success")
        require("--allow-cloud-network" in capture, "capture command does not enable explicit cloud network access")
        require("--defer-manual-printer-parity" in readiness, "readiness command does not defer manual printer parity")

        missing_env = run_wrapper(
            work / "missing-env",
            env={"BAMBU_CLOUD_LOGIN_INFO_JSON": ""},
        )
        require(missing_env.returncode != 0, "dry run accepted missing login env")
        require("BAMBU_CLOUD_LOGIN_INFO_JSON must be set" in missing_env.stderr, "missing login env error was not explicit")

        json_without_dry_run = subprocess.run(
            [
                sys.executable,
                str(WRAPPER),
                "--official-network",
                str(write_file(work / "json-no-dry-run/official/libbambu_networking.dylib")),
                "--official-source",
                str(write_file(work / "json-no-dry-run/official/libBambuSource.dylib")),
                "--cloud-user-info-env",
                "BAMBU_CLOUD_LOGIN_INFO_JSON",
                "--json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "BAMBU_CLOUD_LOGIN_INFO_JSON": '{"access_token":"dry-run-secret-token"}',
            },
        )
        require(json_without_dry_run.returncode != 0, "wrapper accepted --json without --dry-run")
        require("--json requires --dry-run" in json_without_dry_run.stderr, "--json misuse error was not explicit")

    print("authorized cloud parity dry-run validation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
