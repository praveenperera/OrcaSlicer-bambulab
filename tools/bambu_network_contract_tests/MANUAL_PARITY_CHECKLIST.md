# Manual Parity Checklist

Use this checklist after local non-manual readiness passes with `deferred.non_deferred_ok: true`.

## Real-printer parity

1. Set the printer access code:

```sh
export BAMBU_NETWORK_PRINTER_PASSWORD='your-printer-access-code'
```

2. Choose a small known-good `.3mf` file and a remote filename.

3. Run real-printer parity:

```sh
python3 tools/bambu_network_contract_tests/run_real_printer_parity.py \
  --skip-build \
  --official-network /tmp/bambu-official-plugin-02.05.02.58/extracted/libbambu_networking.dylib \
  --official-source /tmp/bambu-official-plugin-02.05.02.58/extracted/libBambuSource.dylib \
  --printer-dev-id '<printer-dev-id>' \
  --printer-dev-ip '<printer-ip>' \
  --print-job-file '<path-to-test.3mf>' \
  --print-job-remote-name '<remote-test-name.3mf>' \
  --print-job-modes upload-only,local-print,sdcard-print \
  --include-source-streaming \
  --include-source-control-tunnel \
  --confirm-start-prints
```

4. Confirm the generated readiness report has no printer or tunnel blockers:

```sh
python3 tools/bambu_network_contract_tests/verify_completion_audit.py \
  --report build/bambu_network_release_readiness/release_readiness_report.json
```

## Cloud parity

Either run authorized cloud parity:

```sh
python3 tools/bambu_network_contract_tests/run_authorized_cloud_parity.py \
  --skip-build \
  --official-network /tmp/bambu-official-plugin-02.05.02.58/extracted/libbambu_networking.dylib \
  --official-source /tmp/bambu-official-plugin-02.05.02.58/extracted/libBambuSource.dylib \
  --cloud-user-info-env BAMBU_CLOUD_LOGIN_INFO_JSON \
  --cloud-ticket-env BAMBU_CLOUD_TICKET \
  --cloud-access-token-env BAMBU_CLOUD_ACCESS_TOKEN
```

Or explicitly decide cloud/service APIs are out of scope for this release.

## Final pass condition

Run:

```sh
python3 tools/bambu_network_contract_tests/verify_completion_audit.py \
  --report build/bambu_network_release_readiness/release_readiness_report.json
```

The final report should return `ok: true` with no failed checklist items.
