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
        require(commands.get("run_macos_native_readiness") is None, "default JSON dry run unexpectedly included native readiness argv")
        require("--expect-cloud-service-success" in capture, "capture command does not require cloud success")
        require("--allow-cloud-network" in capture, "capture command does not enable explicit cloud network access")
        require("--defer-manual-printer-parity" in readiness, "readiness command does not defer manual printer parity")

        real_printer_dry_run = write_file(work / "real_printer_dry_run_missing_inputs.json", b'{"ok":true,"dry_run":true}\n')
        printer_discovery = write_file(work / "bambu_printer_discovery.json", b'{"ok":false,"devices":[]}\n')
        native_json_report = run_wrapper(
            work / "native-json-report",
            "--macos-native-readiness",
            "--real-printer-dry-run-report",
            str(real_printer_dry_run),
            "--printer-discovery-report",
            str(printer_discovery),
            "--json",
        )
        require(native_json_report.returncode == 0, f"native JSON dry run failed: {native_json_report.stderr}\n{native_json_report.stdout}")
        for value in secret_values:
            require(value not in native_json_report.stdout, "native JSON dry-run output leaked a secret value")
        native_payload = json.loads(native_json_report.stdout)
        native_commands = native_payload.get("commands", {})
        native_readiness = native_commands.get("run_macos_native_readiness")
        require(isinstance(native_readiness, list), "native JSON dry run did not include native readiness argv")
        require("run_macos_native_readiness.py" in " ".join(native_readiness), "native readiness argv did not run the native aggregator")
        require("--official-parity-report" in native_readiness, "native readiness argv did not include baseline official parity report")
        require("--cloud-service-parity-report" in native_readiness, "native readiness argv did not include cloud-service parity report")
        require("--real-printer-dry-run-report" in native_readiness, "native readiness argv did not include real-printer dry-run blocker report")
        require("--printer-discovery-report" in native_readiness, "native readiness argv did not include printer discovery blocker report")
        require("--native-package-macos-dir" in native_readiness, "native readiness argv did not include native package directory")
        require("--native-gui-startup-log" in native_readiness, "native readiness argv did not include native GUI startup log")
        native_real_printer_dry_run = native_readiness[native_readiness.index("--real-printer-dry-run-report") + 1]
        native_printer_discovery = native_readiness[native_readiness.index("--printer-discovery-report") + 1]
        require(
            native_real_printer_dry_run.endswith("real_printer_dry_run_missing_inputs.json"),
            "native readiness argv did not preserve real-printer dry-run blocker report",
        )
        require(
            native_printer_discovery.endswith("bambu_printer_discovery.json"),
            "native readiness argv did not preserve printer discovery blocker report",
        )

        native_without_linux_runtime = run_wrapper(
            work / "native-without-linux-runtime",
            "--macos-native-readiness",
            "--json",
            "--linux-runtime-report",
            str(work / "missing-linux-runtime-report.json"),
        )
        require(
            native_without_linux_runtime.returncode == 0,
            f"native dry run required Linux runtime evidence: {native_without_linux_runtime.stderr}\n{native_without_linux_runtime.stdout}",
        )

        legacy_without_linux_runtime = run_wrapper(
            work / "legacy-without-linux-runtime",
            "--json",
            "--linux-runtime-report",
            str(work / "missing-linux-runtime-report.json"),
        )
        require(legacy_without_linux_runtime.returncode != 0, "legacy dry run accepted missing Linux runtime evidence")
        require(
            "Linux runtime report does not exist" in legacy_without_linux_runtime.stderr,
            "legacy missing Linux runtime error was not explicit",
        )

        missing_env = run_wrapper(
            work / "missing-env",
            "--json",
            env={"BAMBU_CLOUD_LOGIN_INFO_JSON": ""},
        )
        require(missing_env.returncode == 0, f"dry run rejected missing login env: {missing_env.stderr}\n{missing_env.stdout}")
        missing_env_payload = json.loads(missing_env.stdout)
        require(
            missing_env_payload.get("cloud", {}).get("user_info_env_present") is False,
            "missing-login dry run did not report missing login env",
        )

        missing_ticket = run_wrapper(
            work / "missing-ticket",
            "--json",
            env={"BAMBU_CLOUD_TICKET": ""},
        )
        require(missing_ticket.returncode == 0, f"dry run rejected missing ticket env: {missing_ticket.stderr}\n{missing_ticket.stdout}")
        missing_ticket_payload = json.loads(missing_ticket.stdout)
        require(
            missing_ticket_payload.get("cloud", {}).get("ticket_env_present") is False,
            "missing-ticket dry run did not report missing ticket env",
        )

        missing_access_token = run_wrapper(
            work / "missing-access-token",
            "--json",
            env={"BAMBU_CLOUD_ACCESS_TOKEN": ""},
        )
        require(
            missing_access_token.returncode == 0,
            f"dry run rejected missing access-token env: {missing_access_token.stderr}\n{missing_access_token.stdout}",
        )
        missing_access_token_payload = json.loads(missing_access_token.stdout)
        require(
            missing_access_token_payload.get("cloud", {}).get("access_token_env_present") is False,
            "missing-access-token dry run did not report missing access-token env",
        )

        missing_native_ticket = run_wrapper(
            work / "missing-native-ticket",
            "--macos-native-readiness",
            "--cloud-ticket-env",
            "",
        )
        require(missing_native_ticket.returncode != 0, "native dry run accepted missing ticket env name")
        require(
            "--macos-native-readiness requires --cloud-ticket-env" in missing_native_ticket.stderr,
            "missing native ticket-env error was not explicit",
        )

        missing_native_access_token = run_wrapper(
            work / "missing-native-access-token",
            "--macos-native-readiness",
            "--cloud-access-token-env",
            "",
        )
        require(missing_native_access_token.returncode != 0, "native dry run accepted missing access-token env name")
        require(
            "--macos-native-readiness requires --cloud-access-token-env" in missing_native_access_token.stderr,
            "missing native access-token-env error was not explicit",
        )

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
