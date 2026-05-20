# Bambu Network Contract Tests

This directory contains clean-room compatibility tooling for a replacement `libbambu_networking.so`.

The first gate is symbol compatibility: OrcaSlicer and the Linux bridge use `dlopen`/`dlsym`, so a candidate plugin must export every symbol listed in `required_symbols.txt`.

`required_symbols.txt` covers `libbambu_networking`. `source_symbols.txt` covers the separate `libBambuSource` camera/tunnel payload that the Linux bridge also loads during handshake.

## Run Current Candidate Smoke Gates

```sh
python3 tools/bambu_network_contract_tests/run_candidate_smoke.py
```

This builds the standalone contract tools and current replacement plugin scaffold, then verifies the ABI mirror for public structs, callback aliases, and mirrored constants, C++ shim signatures against Orca's loader typedefs, networking symbols, source symbols, lifecycle transcript, callback registration transcript, controlled unsupported behavior, source/tunnel safety behavior, no-printer print-job failure behavior, event bridge, UDP discovery callback bridge, camera URL callback bridge, and transcript comparator. It is a local smoke gate only; it does not prove official-plugin parity or real printer behavior.

The smoke gate also runs `generate_required_symbols.py --check`, which fails if `required_symbols.txt` or `source_symbols.txt` drifts from the public loader sources, `verify_contract_surface_coverage.py`, which fails if any required `libbambu_networking` or `libBambuSource` export is covered only by the raw symbol probe and not referenced by at least one behavior probe, the clean-room artifact verifier self-test, the completion-audit verifier self-test, the readiness validator self-tests for parity/Linux/report artifact semantics, and the authorized-cloud/source-streaming/real-printer wrapper dry-run validators so final manual-gate command generation cannot regress silently.
The final smoke JSON records those prerequisite gates as `preflight_*` checks so release-readiness artifacts show the full pass/fail surface without requiring stderr inspection. Probe transcripts are echoed to stderr; stdout is reserved for the single machine-readable smoke summary.
`run_release_readiness.py` parses that summary and records a `summary_validation` block under the `local_candidate_smoke` gate. Readiness requires `ok: true`, `failed: []`, all preflight checks, symbol checks, lifecycle/callback checks, unsupported/source/print/discovery/camera/FT smoke checks, and the callback transcript comparison.

`verify_cpp_signature_mirror.py` compares every `bambu_network_*` symbol loaded by `BBLNetworkPlugin.cpp` through a `func_*` typedef against the replacement shim's exported C++ function signatures. It also compares the `ft_*` typedefs in `FileTransferUtils.hpp` and every public `Bambu_*` prototype in `BambuTunnel.h` against the replacement shims. This catches drift where a symbol still exists but no longer has the loader-facing argument or return types Orca expects.

Run the same gate against a separate Release build with:

```sh
python3 tools/bambu_network_contract_tests/run_candidate_smoke.py \
  --skip-build \
  --plugin-build-dir build/bambu_network_rust_plugin_release
```

## Run Release Readiness

```sh
python3 tools/bambu_network_contract_tests/run_release_readiness.py \
  --official-network /path/to/official/libbambu_networking.so \
  --official-source /path/to/official/libBambuSource.so \
  --printer-dev-id '<printer-dev-id>' \
  --printer-dev-ip '<printer-ip>' \
  --print-job-file /path/to/test.3mf \
  --print-job-remote-name test.3mf \
  --linux-host /path/to/pjarczak_bambu_linux_host
```

This orchestrates the required evidence gates and writes `release_readiness_report.json`: local candidate smoke, official-vs-candidate parity, real printer parity inputs/workflows, full-compatibility feature parity, Linux payload assembly, Linux bridge probing, and macOS bridge runtime packaging. Real-printer readiness requires upload-only, local-print, and SD-card print modes by default through `--print-job-modes upload-only,local-print,sdcard-print`. Full-compatibility feature parity is intentionally separate from safe-failure checks; it remains red until camera/source streaming, cloud/service feature parity, and non-FTPS tunnel parity have implementation plus evidence, or are explicitly scoped out for a target release. Camera/source streaming can be evidenced with `--source-stream-url` plus `--expect-source-stream-success`. Authorized cloud/service parity can be evidenced with `--include-cloud-service --allow-cloud-network --expect-cloud-service-success` plus a user-provided login context. Both probes redact or normalize credentials and response bodies before writing artifacts. The script exits non-zero when required evidence is missing. Use `--allow-incomplete` to generate the report during development without treating known missing gates as a command failure.

To audit a generated readiness report without rerunning the underlying probes:

```sh
python3 tools/bambu_network_contract_tests/verify_release_readiness_report.py \
  --report build/bambu_network_release_readiness/release_readiness_report.json
```

Add `--require-complete` when the report is supposed to be release-ready. The verifier rejects inconsistent blocker lists, missing required gates, a green local-smoke gate without `summary_validation`, and complete reports that did not check the official parity artifact policy.

To audit the report against the full compatibility objective instead of only its JSON shape:

```sh
python3 tools/bambu_network_contract_tests/verify_completion_audit.py \
  --report build/bambu_network_release_readiness/release_readiness_report.json
```

Use `--allow-incomplete` during development to print the objective checklist without returning a failing exit code. A completed release must pass this command without `--allow-incomplete`.

For macOS release packaging, either stage the assembled runtime into `tools/pjarczak_bambu_linux_host/runtime/linux-x86_64` with:

```sh
python3 tools/bambu_network_contract_tests/assemble_macos_bridge_runtime.py \
  --source-runtime-dir \
  --replace-existing
```

or point `build_release_macos.sh` at an assembled runtime without copying generated binaries into the source tree:

```sh
PJARCZAK_BAMBU_HOST_RUNTIME_DIR="$PWD/build/bambu_network_macos_bridge_runtime" \
./build_release_macos.sh -s
```

The release script fails early if the selected runtime directory lacks `libbambu_networking.so`, `libBambuSource.so`, or `linux_payload_manifest.json`.

The assembled runtime also includes a Linux-side verifier. Run it inside the same Linux guest/container that will execute the bridge host:

```sh
python3 verify_linux_bridge_runtime.py --runtime-dir /path/to/runtime
```

This runs the bridge RPC probe against both `pjarczak_bambu_linux_host_abi1` and `pjarczak_bambu_linux_host_abi0`, including the FT tunnel/job smoke, the opt-in synthetic `libBambuSource` stream/sample smoke, and a loopback `libBambuSource` local control-tunnel smoke that verifies `Bambu_SendMessage` and polled `Bambu_ReadSample` over bridge RPC. Its JSON output is the required Linux loader/RPC evidence for release readiness.

After copying the report back to the macOS build machine, pass it to readiness with:

```sh
python3 tools/bambu_network_contract_tests/run_release_readiness.py \
  --linux-runtime-report /path/to/linux_bridge_runtime_verify_report.json \
  ...
```

Readiness compares the report's `libbambu_networking.so` and `libBambuSource.so` hashes against the current assembled payload manifest, so stale Linux reports are rejected.
It also validates the bridge transcript details for both ABI host variants: network/source load state, agent lifecycle RPC calls, the full `ft_*` capability table, FT tunnel/media/upload-missing-file smoke results, source stream/sample forwarding through the bridge RPC binary frame path, and local source control-tunnel send/read forwarding.

To verify an assembled runtime directory without building the whole app:

```sh
python3 tools/bambu_network_contract_tests/verify_macos_release_runtime.py \
  --runtime-dir build/bambu_network_macos_bridge_runtime
```

This checks required files, Linux ELF payloads, manifest hashes, executable bits, and the `build_release_macos.sh` runtime-copy path using a temporary app bundle.

## Build

```sh
cmake -S tools/bambu_network_contract_tests -B build/bambu_network_contract_tests
cmake --build build/bambu_network_contract_tests
```

## Probe a Plugin

```sh
build/bambu_network_contract_tests/bambu_network_contract_probe \
  --plugin /path/to/libbambu_networking.so \
  --symbols tools/bambu_network_contract_tests/required_symbols.txt \
  --json
```

The probe exits `0` only when all required symbols resolve. It does not call plugin functions, so it is safe as the first compatibility check for both official and candidate plugins.

To verify that every required export has at least one behavior probe in the suite:

```sh
python3 tools/bambu_network_contract_tests/verify_contract_surface_coverage.py
```

This does not prove semantic parity by itself. It is a guardrail that prevents new required exports from silently remaining symbol-only coverage.

To verify the release-readiness validators reject stale or self-compare external evidence:

```sh
python3 tools/bambu_network_contract_tests/verify_readiness_report_validation.py
```

Run the probe on the same binary platform as the plugin. Linux ELF `.so` payloads must be probed on Linux, including inside the Lima or WSL guest used by the bridge.

For a host-independent export-table check of a Linux ELF payload:

```sh
python3 tools/bambu_network_contract_tests/verify_elf_exports.py \
  --plugin /path/to/libbambu_networking.so \
  --symbols tools/bambu_network_contract_tests/required_symbols.txt \
  --json
```

This uses `nm -D --defined-only` to confirm exported dynamic symbols. It is useful on macOS while cross-building, but it does not replace the Linux `dlopen`/`dlsym` probe because it cannot prove loader compatibility.

To record or enforce the C++ standard-library ABI visible in a Linux ELF payload:

```sh
python3 tools/bambu_network_contract_tests/verify_elf_cxx_abi.py \
  --plugin /path/to/libbambu_networking.so \
  --expect libstdc++ \
  --json
```

Use `--expect libstdc++` for direct loading by a GCC/libstdc++ Linux OrcaSlicer process. Use `--expect libc++` only for a matched bridge runtime whose host was built with the same C++ ABI. The payload assembler records this probe in `linux_payload_manifest.json`.

## Capture Lifecycle Behavior

```sh
build/bambu_network_contract_tests/bambu_network_lifecycle_probe \
  --plugin /path/to/libbambu_networking.so \
  --log-dir /tmp/bambu-network-contract-log
```

The lifecycle probe emits JSON for a minimal ABI behavior transcript: version, agent creation, init/config/country/start return codes, login state, simple identity strings, login command builders, and destroy result. Use this output as the first official-vs-candidate behavior diff before testing printer or cloud workflows.

Compare two transcripts with:

```sh
python3 tools/bambu_network_contract_tests/compare_transcripts.py \
  official.lifecycle.json \
  candidate.lifecycle.json
```

## Capture Callback Registration Behavior

```sh
build/bambu_network_contract_tests/bambu_network_callback_probe \
  --plugin /path/to/libbambu_networking.so \
  --log-dir /tmp/bambu-network-contract-log
```

This probe registers the callback setters Orca uses and emits return codes plus invocation counters. It verifies registration ABI compatibility only; workflow-specific event timing still needs separate printer/cloud/LAN tests.

## Verify Candidate Event Bridge

```sh
build/bambu_network_contract_tests/bambu_network_event_bridge_probe \
  --plugin /path/to/candidate/libbambu_networking.so \
  --log-dir /tmp/bambu-network-event-bridge
```

This candidate-only probe uses internal `brs_shim_test_emit_*` hooks to verify that Rust-originated events can travel through the C++ shim into the registered Orca callback functions. Official plugins are not expected to expose these internal hooks.

## Verify UDP Discovery

```sh
build/bambu_network_contract_tests/bambu_network_discovery_probe \
  --plugin /path/to/candidate/libbambu_networking.so \
  --log-dir /tmp/bambu-network-discovery
```

This starts candidate discovery, sends a synthetic Bambu-style SSDP packet to the local UDP discovery ports, and verifies that `on_ssdp_msg` receives Orca's expected machine-alive JSON. It proves the local listener and callback path, not that a real printer is discoverable on the current network.

The probe serializes concurrent runs with a `/tmp` lock because Bambu discovery uses fixed UDP ports.

## Verify Candidate Camera URL

```sh
build/bambu_network_contract_tests/bambu_network_camera_url_probe \
  --plugin /path/to/candidate/libbambu_networking.so \
  --log-dir /tmp/bambu-network-camera-url
```

This candidate-only probe seeds a local LAN camera endpoint and verifies that `bambu_network_get_camera_url` emits Orca's `bambu:///rtsps___.../streaming/live/1?proto=rtsps` URL through the callback. It validates URL construction and callback behavior only; actual video streaming still depends on `libBambuSource` and real printer validation.

## Capture Unsupported Behavior Safety

```sh
build/bambu_network_contract_tests/bambu_network_unsupported_probe \
  --network-plugin /path/to/libbambu_networking.so \
  --source-plugin /path/to/libBambuSource.so \
  --log-dir /tmp/bambu-network-contract-log
```

This probe calls every exported cloud/service API with inert inputs, plus unsupported LAN, print, file-transfer, and camera/source paths. It should exit cleanly and emit controlled failure values, proving that unsupported behavior is explicit rather than a crash or accidental external-service call. It also verifies that the candidate validates SD-card print requests, rejects upload requests without a file name, maps missing local upload files to print-specific errors, parses local camera source URLs, and returns a controlled publish failure when a valid `project_file` request is attempted without an active printer session.

## Capture Cloud/Service Parity

```sh
BAMBU_CLOUD_LOGIN_INFO_JSON='<login-info-json>' \
build/bambu_network_contract_tests/bambu_network_cloud_service_probe \
  --plugin /path/to/libbambu_networking.so \
  --user-info-env BAMBU_CLOUD_LOGIN_INFO_JSON \
  --allow-network \
  --expect-success
```

This probe is opt-in because it can call authorized Bambu cloud/service endpoints. It records normalized contract evidence for login state, cloud connection, selected URL/service calls, callbacks, and non-inert service responses. It does not write raw login JSON, tokens, HTTP bodies, tickets, or access tokens to artifacts.

For local no-network verification, omit `--allow-network`. In this mode the probe creates the requested log directory before agent startup, avoids logged-out user-detail calls that the official plugin does not tolerate, and records the public logged-out host/studio-info URL contract. `run_candidate_smoke.py` runs both that logged-out baseline and a redacted login/logout fixture, requiring `bambu_network_change_user`, `bambu_network_is_user_login`, user getters, login-command builders, login callbacks, and `bambu_network_user_logout` to behave consistently without contacting cloud services.

Candidate smoke also runs candidate-only cloud fixtures. `BAMBU_NETWORK_ENABLE_SYNTHETIC_CLOUD_SERVICE=1` returns local synthetic success payloads without opening sockets. `BAMBU_NETWORK_CLOUD_BASE_URL=http://127.0.0.1:<port>` drives the Rust HTTP adapter against a local mock service and verifies request/response plumbing, access-token header state, `bambu_network_connect_server`, `bambu_network_is_server_connected`, server-connected callbacks, service JSON/http-code outputs, URL extraction, token/profile calls, and callback-style MakerWorld/HMS exports. A second local HTTP fixture omits that env override and uses the `backend_url` supplied by the login payload, matching the path used by authorized runtime sessions. These fixtures are local plumbing evidence; they do not replace authorized official-vs-candidate Bambu service parity.

Use the wrapper when authorized cloud credentials are available:

```sh
BAMBU_CLOUD_LOGIN_INFO_JSON='<login-info-json>' \
BAMBU_CLOUD_TICKET='<cloud-ticket>' \
BAMBU_CLOUD_ACCESS_TOKEN='<cloud-access-token>' \
python3 tools/bambu_network_contract_tests/run_authorized_cloud_parity.py \
  --official-network /path/to/official/libbambu_networking.so \
  --official-source /path/to/official/libBambuSource.so \
  --cloud-user-info-env BAMBU_CLOUD_LOGIN_INFO_JSON \
  --cloud-ticket-env BAMBU_CLOUD_TICKET \
  --cloud-access-token-env BAMBU_CLOUD_ACCESS_TOKEN \
  --skip-build
```

`run_authorized_cloud_parity.py` runs `capture_official_parity.py` with `--include-cloud-service --allow-cloud-network --expect-cloud-service-success`, then feeds the generated `parity_report.json` into `run_release_readiness.py` with manual printer parity deferred. It validates required credential inputs up front for live runs, passes those same inputs into the clean-room artifact verifier, and keeps readiness incomplete unless the remaining non-cloud gates are also satisfied. Add `--dry-run` to validate paths and report credential environment presence, then print the exact capture/readiness commands without contacting Bambu services. Add `--json` with `--dry-run` for a sanitized machine-readable report that native readiness can use as missing-input blocker evidence. The dry-run behavior is covered by `verify_authorized_cloud_parity_dry_run.py`.

When a cloud parity report is passed to `run_release_readiness.py --official-parity-report`, an offline cloud-service comparison is accepted as contract evidence but does not turn the feature green. The `cloud_service_feature_parity` full-compatibility gap turns green only if both official and candidate cloud-service transcripts prove login, cloud-network, and service-call success and match on the normalized contract fields.

## Capture File-Transfer Behavior

```sh
build/bambu_network_contract_tests/bambu_network_ft_behavior_probe \
  --plugin /path/to/libbambu_networking.so
```

This candidate probe exercises the `ft_*` ABI used by `FileTransferUtils`: local `bambu:///local/...` tunnel creation, connection and status callbacks, media-ability job result callbacks, result polling, upload-job progress messages, and controlled missing-file failure. It validates shim ownership/free semantics and callback payload lifetimes. It does not prove the printer's port-6000 file-transfer protocol or real eMMC upload behavior; that still needs official parity and real printer validation.

## Verify Source/Tunnel Safety

```sh
build/bambu_network_contract_tests/bambu_network_source_behavior_probe \
  --source-plugin /path/to/candidate/libBambuSource.so
```

This candidate-only probe calls every exported `libBambuSource` symbol using null handles, invalid URLs, local camera URLs, and local tunnel URLs. It verifies that unsupported streaming, message, seek, and sample APIs fail with controlled return values and zero output buffers rather than crashing. It does not prove real camera streaming compatibility.

## Capture Source Streaming Parity

```sh
build/bambu_network_contract_tests/bambu_network_source_streaming_probe \
  --source-plugin /path/to/libBambuSource.so \
  --url 'bambu:///rtsps___bblp:<access-code>@<printer-ip>/streaming/live/1?proto=rtsps' \
  --mode video \
  --expect-success
```

This probe opens a live `libBambuSource` URL, waits through `Bambu_would_block` / `Bambu_buffer_limit`, captures stable stream metadata through `Bambu_GetStreamInfo`, and requires `Bambu_ReadSample` to return a non-empty sample when `--expect-success` is set. It does not write credentials into JSON artifacts. Use it through parity capture to compare official and candidate behavior:

Use the wrapper when a live camera/source URL is available:

```sh
BAMBU_SOURCE_STREAM_URL='bambu:///rtsps___bblp:<access-code>@<printer-ip>/streaming/live/1?proto=rtsps' \
python3 tools/bambu_network_contract_tests/run_source_streaming_parity.py \
  --official-network /path/to/official/libbambu_networking.so \
  --official-source /path/to/official/libBambuSource.so \
  --source-stream-url-env BAMBU_SOURCE_STREAM_URL \
  --skip-build
```

`run_source_streaming_parity.py` runs `capture_official_parity.py` with `--source-stream-url ... --expect-source-stream-success`, then feeds the generated `parity_report.json` into `run_release_readiness.py` while deferring the unrelated manual printer and authorized cloud gates. It redacts source URLs before printing commands or JSON dry-run output. Add `--dry-run` to validate local paths and URL environment presence without opening the stream. Add `--json` with `--dry-run` for a sanitized machine-readable report. The dry-run behavior is covered by `verify_source_streaming_parity_dry_run.py`.

For local no-network plumbing checks, the candidate `libBambuSource` also has an opt-in synthetic fixture. Set `BAMBU_SOURCE_ENABLE_SYNTHETIC_STREAM=1` and use `bambu:///rtsps___bblp:redacted@synthetic.local/streaming/live/1?proto=rtsps`; `run_candidate_smoke.py` requires this fixture to open, start, report MJPEG stream info, and return a non-empty sample. This is candidate-only evidence for ABI/sample forwarding and does not satisfy the real camera/source parity gate.

For local official-vs-candidate camera/source parity without a printer, run the RTSP loopback fixture:

```sh
python3 tools/bambu_network_contract_tests/run_source_rtsp_loopback_parity.py \
  --official-source /path/to/official/libBambuSource.dylib \
  --candidate-source build/bambu_network_rust_plugin_release/libBambuSource.dylib
```

The wrapper generates a tiny H.264 stream with `ffmpeg`, serves it over loopback RTSP/RTP-over-TCP, runs `bambu_network_source_streaming_probe` against the official and candidate source plugins on the same redacted `bambu:///rtsp___...` URL, and writes `parity_report.json` under `build/bambu_network_release_readiness/source_rtsp_loopback_parity`. Pass that report to `run_release_readiness.py --source-streaming-parity-report ...` as supplemental source-streaming evidence. H.264 official transcripts may report `max_frame_size == 0`; readiness accepts that when the stream format is AVC byte stream and the sample itself is non-empty.

For local control-tunnel plumbing, `bambu_network_source_local_tunnel_probe` starts a loopback TCP service, opens `bambu:///local/127.0.0.1?port=<loopback>&user=bblp&passwd=<redacted>`, calls `Bambu_StartStreamEx` with Orca's control stream type, sends JSON control messages with `Bambu_SendMessage`, polls `Bambu_RecvMessage` for one JSON response, and polls `Bambu_ReadSample` for a second JSON response. `run_candidate_smoke.py` and release readiness require this loopback probe so the non-FTPS source-tunnel path has local implementation evidence before the final real-printer eMMC/port-6000 parity run.

For local official-vs-candidate control transport parity without a printer, run the TLS loopback fixture:

```sh
python3 tools/bambu_network_contract_tests/run_source_control_tls_loopback_parity.py \
  --official-source /path/to/official/libBambuSource.dylib \
  --candidate-source build/bambu_network_rust_plugin_release/libBambuSource.dylib
```

The wrapper starts a self-signed TLS loopback service, opens the same redacted `bambu:///local/127.0.0.1?...` URL against official and candidate `libBambuSource`, and compares the stable wire contract: login frame shape, padded username/password block metadata, and `Bambu_SendMessage` control framing with the official `{"mtype":<ctrl_type>,...}` payload rewrite. It writes redacted artifacts under `build/bambu_network_release_readiness/source_control_tls_loopback_parity`. Pass that report to `run_release_readiness.py --source-control-tls-loopback-parity-report build/bambu_network_release_readiness/source_control_tls_loopback_parity/parity_report.json` as supplemental source-control evidence. This proves local transport/framing parity without a printer, but it does not replace the final printer-backed port-6000/eMMC response parity because the fake loopback service does not implement the printer-side AV control protocol.

For live source/control tunnel parity without starting a print:

```sh
BAMBU_SOURCE_CONTROL_URL='bambu:///local/<printer-ip>?port=6000&user=bblp&passwd=<access-code>' \
BAMBU_SOURCE_CONTROL_MESSAGE='{"sequence":1,"command":"list","path":"/"}' \
python3 tools/bambu_network_contract_tests/run_source_control_tunnel_parity.py \
  --official-network /path/to/official/libbambu_networking.so \
  --official-source /path/to/official/libBambuSource.so \
  --candidate-network build/bambu_network_rust_plugin_release/libbambu_networking.dylib \
  --candidate-source build/bambu_network_rust_plugin_release/libBambuSource.dylib \
  --source-control-url-env BAMBU_SOURCE_CONTROL_URL \
  --source-control-message-env BAMBU_SOURCE_CONTROL_MESSAGE
```

`run_source_control_tunnel_parity.py` is a focused wrapper around the control-mode `source_streaming` parity probe. It forces `--source-stream-mode control`, redacts the source/control URL and message in dry-run output, and feeds the generated parity report into release readiness. `verify_source_control_tunnel_parity_dry_run.py` covers command generation, URL/message redaction, required env handling, and `--json` misuse checks.

```sh
python3 tools/bambu_network_contract_tests/capture_official_parity.py \
  --official-network /path/to/official/libbambu_networking.so \
  --official-source /path/to/official/libBambuSource.so \
  --candidate-network build/bambu_network_rust_plugin_release/libbambu_networking.dylib \
  --candidate-source build/bambu_network_rust_plugin_release/libBambuSource.dylib \
  --out-dir /tmp/bambu-source-streaming-parity \
  --include-discovery \
  --include-source-behavior \
  --include-ft-job-only \
  --source-stream-url 'bambu:///rtsps___bblp:<access-code>@<printer-ip>/streaming/live/1?proto=rtsps' \
  --expect-source-stream-success
```

When that parity report is passed to `run_release_readiness.py --official-parity-report` or `--source-streaming-parity-report`, the `camera_source_streaming` full-compatibility gap turns green only if both official and candidate source-streaming transcripts are `video` mode, opened the stream, reported stream info with type/subtype/format metadata, positive dimensions/frame rate, positive format buffers, read a sample, and matched on the stable contract fields. Use `--source-stream-mode control --source-stream-message ...` for source/control tunnel parity; that turns the `non_ftps_tunnel_feature_parity` gap green only when both sides also send a control message and read a control response.

## Capture Print Job Behavior

```sh
BAMBU_NETWORK_PRINTER_PASSWORD='<printer-access-code>' \
build/bambu_network_contract_tests/bambu_network_print_job_probe \
  --plugin /path/to/libbambu_networking.so \
  --mode upload-only \
  --dev-id '<printer-dev-id>' \
  --dev-ip '<printer-ip>' \
  --username bblp \
  --file /path/to/test.3mf \
  --remote-name test.3mf \
  --expect-success
```

Use `--mode upload-only` to validate FTP or FTPS transfer without starting a print, `--mode local-print` to validate upload plus local MQTT `project_file`, and `--mode sdcard-print` to validate MQTT print startup for a file already on printer storage. The probe records callback counts, print status events, and return codes suitable for official-vs-candidate comparison.

## Capture Official Parity Artifacts

```sh
python3 tools/bambu_network_contract_tests/capture_official_parity.py \
  --official-network /path/to/official/libbambu_networking.so \
  --official-source /path/to/official/libBambuSource.so \
  --candidate-network /path/to/candidate/libbambu_networking.so \
  --candidate-source /path/to/candidate/libBambuSource.so \
  --out-dir /tmp/bambu-network-parity
```

This writes official and candidate JSON transcripts plus comparison output under the artifact directory. The top-level `parity_report.json` records SHA-256 hashes and sizes for each input binary so a report can be tied back to exact official and candidate payloads without copying those binaries. It fails if a probe exits non-zero or if any comparable transcript differs. If a probe crashes, times out, or emits non-JSON output, the artifact is still written as a JSON failure record so readiness can explain the mismatch instead of losing the run. Use `--probe-timeout-s` to adjust the per-probe timeout. Keep the official plugin paths outside the repo; only sanitized transcripts, hashes, and comparison reports should be shared.

Release readiness validates `parity_report.json` whether it is supplied through `--official-parity-report` or generated during the readiness run. The validator rejects stale candidate hashes, self-comparison reports, missing required probe/comparison entries, and artifact directories containing copied binaries.

The script rejects identical official and candidate binaries by default. Use `--allow-self-compare` only when testing the parity harness itself with candidate-as-official inputs.

Readiness can consume an existing parity report instead of re-running official binaries:

```sh
python3 tools/bambu_network_contract_tests/run_release_readiness.py \
  --official-parity-report /tmp/bambu-network-parity/parity_report.json \
  ...
```

The report is accepted only if it passed, is not a self-compare, has different official and candidate hashes, contains the required symbol/lifecycle/callback/unsupported/discovery/source comparisons, contains full FT evidence, contains the candidate-only source safety, event bridge, and camera URL probes, has readable JSON artifacts for every referenced probe under the parity report directory, has official/candidate probe JSON that matches after ignoring path-only fields, has comparison artifacts that record matching transcripts, follows the clean-room artifact policy, keeps official inputs outside the repo, contains no official-binary copies in scanned release payload directories, and its candidate hashes match the current host or Linux candidate payloads. Full FT evidence can come from the synthetic `ft_behavior` comparison or from real-printer upload-only/local-print/SD-card parity plus the official-safe `ft_job_invalid` comparison. If the report also contains real-printer `printer_workflow` plus upload-only, local-print, and SD-card print comparisons, readiness loads those probe transcripts and accepts them as real-printer workflow evidence only when both official and candidate runs show non-empty printer identity, password-present, missing-symbol-free, successful connect/message/disconnect, a successful connect callback, expected print-job mode, successful print/upload results, a finished status callback, and no error status callback. Passing this official parity gate is necessary but not sufficient for full compatibility while `full_compatibility_feature_parity` remains red.
When `run_release_readiness.py` generates the parity report itself, it includes `ft_job_invalid` by default. Add `--include-synthetic-ft-behavior` only when you explicitly want to run the synthetic local FT tunnel probe too.

Verify that a parity artifact directory kept the clean-room boundary:

```sh
python3 tools/bambu_network_contract_tests/verify_clean_room_artifacts.py \
  --parity-report /tmp/bambu-network-parity/parity_report.json \
  --artifact-dir /tmp/bambu-network-parity \
  --forbid-official-binary-copies-in build/bambu_network_rust_plugin_release
```

This checks the report policy, requires official input paths to live outside the repo, fails if the artifact directory contains ELF, Mach-O, or PE binaries, and can hash-scan release/source directories for byte-for-byte copies of the official input binaries. `run_release_readiness.py` runs this automatically for generated and supplied official parity reports, including reports that are otherwise still red because printer-backed FT evidence is missing.

For authorized cloud or printer runs, `run_release_readiness.py` also passes the user-provided credential env names and login-info file path into the artifact verifier. The verifier scans generated text artifacts for those exact secret values and for sensitive JSON field values such as tokens, tickets, passwords, and secrets. It reports only source names, lengths, and SHA-256 fingerprints, never the secret values.

For local non-printer qualification, add `--defer-manual-printer-parity` to classify real-printer, real-camera/source, and printer-backed FT blockers as intentionally deferred without marking the release complete. Add `--defer-authorized-cloud-parity` only when authorized cloud/service parity is also being deferred because credentials or network authorization are not part of the current run. With `--allow-deferred-incomplete`, the command exits 0 only if every remaining blocker is covered by those explicit deferrals; the report still keeps `ok: false` and records the full deferred/non-deferred blocker split.

Add `--include-ft-behavior` to compare the `ft_*` tunnel/job contract. This is intentionally optional because the probe uses a synthetic local tunnel URL; official plugin behavior may depend on the real file-transfer service being reachable. A mismatch is useful evidence, but it should be interpreted alongside a real printer validation run.

The report also includes candidate-only checks for source/tunnel safety behavior, Rust-to-C++ callback forwarding, and local camera URL generation. Readiness requires these candidate-only probes in supplied and generated parity reports. They are not compared with the official plugin because some use internal `brs_shim_test_*` hooks that official binaries should not expose, and the source safety check is a candidate hardening gate rather than an official behavior contract. Add `--include-discovery` to compare synthetic UDP discovery behavior across both plugins. Add `--include-source-behavior` to record detailed `libBambuSource` behavior for both sides and compare it without applying the candidate-only hardening assertions to the official binary.

Candidate smoke also runs opt-in cloud/service fixtures. The synthetic fixture uses `BAMBU_NETWORK_ENABLE_SYNTHETIC_CLOUD_SERVICE=1` and verifies the candidate can carry login state, report a connected service session, return success codes, populate JSON/http-code outputs, exercise token/profile plumbing, and invoke callback-style MakerWorld/HMS service exports without touching Bambu services. The HTTP fixtures use `BAMBU_NETWORK_CLOUD_BASE_URL` and login-payload `backend_url` against a local mock server to verify the same ABI path can perform real HTTP calls and propagate response bodies/status codes/callback state. These are local plumbing evidence only; authorized official-vs-candidate cloud/service parity remains required for full compatibility unless explicitly deferred in a non-final readiness run.

Add a real LAN printer workflow when you are ready to validate printer behavior:

```sh
python3 tools/bambu_network_contract_tests/find_bambu_printers.py
```

Use the reported `dev_id` and `dev_ip` in the final parity command:

```sh
BAMBU_NETWORK_PRINTER_PASSWORD='<printer-access-code>' \
python3 tools/bambu_network_contract_tests/run_real_printer_parity.py \
  --official-network /path/to/official/libbambu_networking.so \
  --official-source /path/to/official/libBambuSource.so \
  --printer-dev-id '<printer-dev-id>' \
  --printer-dev-ip '<printer-ip>' \
  --printer-username bblp \
  --printer-message '{"pushing":{"sequence_id":"0","command":"pushall"}}' \
  --print-job-file /path/to/test.3mf \
  --print-job-modes upload-only,local-print,sdcard-print \
  --print-job-remote-name test.3mf \
  --include-source-streaming \
  --include-source-control-tunnel \
  --confirm-start-prints
```

The printer password/access code is read from the environment and is reported only as present or absent. `find_bambu_printers.py` sends an SSDP `M-SEARCH` to the Bambu discovery ports and reports any device identity packets it receives; if it does not find the printer, use the device id and IP from Orca/Bambu Studio or the printer UI. `run_real_printer_parity.py` runs `capture_official_parity.py` with source behavior, discovery, official-safe FT job ABI parity, printer workflow, and all requested print-job modes, then immediately feeds the generated `parity_report.json` into readiness. Add `--include-source-streaming` to derive a live RTSPS `libBambuSource` URL from the same printer IP, username, and password env, and to require successful source-streaming parity in the same final printer-backed report. Add `--include-source-control-tunnel` to derive a live `bambu:///local/<printer-ip>?port=6000...` control URL from the same inputs and capture official-vs-candidate `Bambu_SendMessage`/`Bambu_RecvMessage`/`Bambu_ReadSample` parity with a default eMMC list-style message. Legacy readiness receives that control-mode report through `--source-streaming-parity-report`; macOS native readiness receives it through `--source-control-parity-report` so the live port-6000 source-control gate cannot be confused with video streaming evidence. It requires `--confirm-start-prints` when `local-print` or `sdcard-print` is included because those modes can start work on the printer. The optional print-job workflow can capture one or more modes with `--print-job-modes`; release readiness requires upload-only, local-print, and SD-card print behavior with the same printer credentials. To count as final real-printer evidence, the captured transcripts must identify the printer, match the expected print-job mode, include successful connect callback evidence, and include print status callbacks that reach finished status without any error status.

Add `--dry-run` to validate all local paths, report printer identity/password environment presence, validate print-mode inputs, optional source-streaming/control command generation, and print-start confirmation, then print the exact capture/readiness commands without launching the plugin probes or touching the printer. Legacy release-readiness dry-runs also validate Linux runtime report presence; `--macos-native-readiness` intentionally does not require that bridge runtime report. Add `--json` with `--dry-run` to emit a machine-readable report with sanitized printer/password presence, print-job mode details, source-streaming/control intent, and argv command arrays. Source-streaming URLs, source-control URLs, and source-control messages are redacted in dry-run output.

The dry-run behavior itself is covered by:

```sh
python3 tools/bambu_network_contract_tests/verify_real_printer_parity_dry_run.py
```

You can still run `capture_official_parity.py` directly for lower-level debugging, but the wrapper is the preferred final manual gate because it validates required inputs up front and records both parity and readiness artifacts in the expected build directories.

You can also run the printer workflow probe directly:

```sh
BAMBU_NETWORK_PRINTER_PASSWORD='<printer-access-code>' \
build/bambu_network_contract_tests/bambu_network_printer_workflow_probe \
  --plugin /path/to/libbambu_networking.so \
  --dev-id '<printer-dev-id>' \
  --dev-ip '<printer-ip>' \
  --username bblp \
  --message '{"pushing":{"sequence_id":"0","command":"pushall"}}'
```

## Capture Bridge Host Behavior

Assemble a Linux candidate payload directory from Linux-built replacement `.so` files:

```sh
python3 tools/bambu_network_contract_tests/assemble_candidate_linux_payload.py \
  --network-so build/bambu_network_rust_plugin/libbambu_networking.so \
  --source-so build/bambu_network_rust_plugin/libBambuSource.so \
  --out-dir /tmp/bambu-network-linux-payload
```

The assembler refuses non-ELF binaries, runs the host-independent ELF export-table and C++ ABI probes against both copied `.so` files, writes `linux_payload_manifest.json` with SHA-256 hashes and symbol-probe results, and labels the files as clean-room candidate payloads. Run it on Linux or inside the same Linux guest used by the bridge so `dlopen`/`dlsym` checks execute against the real target ABI. Add `--host /path/to/pjarczak_bambu_linux_host` to run the bridge RPC smoke probe as part of assembly. Use `--skip-symbol-probes` only when assembling from macOS or another non-Linux host; the manifest will still include ELF export-table checks, but the loader checks remain a required Linux gate.

```sh
python3 tools/bambu_network_contract_tests/bridge_rpc_probe.py \
  --host /path/to/pjarczak_bambu_linux_host \
  --plugin-dir /path/to/plugin-dir
```

The plugin directory must contain the plugin payload expected by the Linux bridge host, including `libbambu_networking.so` and, when needed, `libBambuSource.so`. This probe speaks the bridge RPC framing protocol over stdio and captures handshake/capability/lifecycle behavior. It also fails if the host cannot see the required auth/session symbols through `net.auth_info`, cannot report the logged-out public Bambu host/studio-info URL contract, or cannot see the required `ft_*` file-transfer symbols through `ft.capabilities`. By default it runs a small FT tunnel/job smoke, a synthetic `libBambuSource` stream/sample smoke, a loopback `libBambuSource` local control-tunnel send/read smoke, and a synthetic cloud/service smoke over RPC. Use `--skip-ft-smoke`, `--skip-source-smoke`, or `--skip-cloud-smoke` only when checking symbol capabilities in an environment where those synthetic calls are expected to differ.

From macOS, the standalone Linux bridge host can be cross-built with Zig:

```sh
cmake -S tools/pjarczak_bambu_linux_host -B build/pjarczak_bambu_linux_host_linux_x86_64 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_SYSTEM_NAME=Linux \
  -DCMAKE_CXX_COMPILER="$PWD/tools/bambu_network_rust_plugin/scripts/zig-cxx-x86_64-linux-gnu"
cmake --build build/pjarczak_bambu_linux_host_linux_x86_64 --target pjarczak_bambu_linux_host --config Release --parallel
```

The resulting host binaries are Linux ELF files. Run `bridge_rpc_probe.py` with those binaries inside Linux, not on macOS.

The Zig cross-build is intended to qualify a matched bridge-host-plus-plugin runtime. It is not enough evidence for direct loading by a Linux OrcaSlicer process built with GCC/libstdc++; that path needs a Linux-native build, or a cross toolchain with a real libstdc++ sysroot, plus the same `dlopen`/`dlsym` probes against that artifact.

When a Linux or Linux-like environment has an x86-64 GCC cross toolchain, build and verify a direct-load libstdc++ candidate from the existing Rust GNU static library:

```sh
python3 tools/bambu_network_contract_tests/build_linux_libstdcxx_candidate.py \
  --run-dlopen-probes \
  --ld-library-path /usr/x86_64-linux-gnu/lib
```

The helper writes `build/bambu_network_rust_plugin_linux_x86_64_libstdcxx/`, verifies both ELF export tables, requires `libstdc++` C++ ABI evidence for `libbambu_networking.so` and `libBambuSource.so`, compiles a Linux `bambu_network_contract_probe`, and runs Linux `dlopen`/`dlsym` checks against both shared objects. It honors `CXX`, `NM`, and `OBJDUMP` when the cross tools have non-default names.

## Verify The macOS Native Plugin Path

The macOS native path is opt-in while it is being qualified:

```sh
PJARCZAK_BAMBU_MACOS_NATIVE_PLUGIN=1 ./build_release_macos.sh -s
```

For copy-only packaging checks, the same flag stages only native dylibs and does not require the Linux bridge runtime:

```sh
PJARCZAK_BAMBU_COPY_RUNTIME_ONLY=1 \
PJARCZAK_BAMBU_MACOS_NATIVE_PLUGIN=1 \
PJARCZAK_BAMBU_COPY_APP_PATH=/path/to/OrcaSlicer.app \
./build_release_macos.sh
```

Verify native Mach-O dylib evidence separately from bridge evidence. The verifier requires `libbambu_networking.dylib` or a versioned `libbambu_networking_<version>.dylib` plus exact `libBambuSource.dylib` source naming:

```sh
python3 tools/bambu_network_contract_tests/verify_macos_native_plugin.py \
  --network-dylib build/bambu_network_rust_plugin_release/libbambu_networking.dylib \
  --source-dylib build/bambu_network_rust_plugin_release/libBambuSource.dylib \
  --out build/bambu_network_release_readiness/macos_native_plugin_report.json
```

Capture the local candidate smoke summary that native readiness consumes:

```sh
python3 tools/bambu_network_contract_tests/run_candidate_smoke.py \
  --skip-build \
  --plugin-build-dir build/bambu_network_rust_plugin_release \
  > build/bambu_network_release_readiness/local_candidate_smoke.json
```

Aggregate native readiness with the current official macOS parity evidence. The official parity report must still point at existing official dylibs outside the repo; rerun `capture_official_parity.py` and pass the new `parity_report.json` if those `/tmp` inputs have been cleaned up or replaced.

```sh
python3 tools/bambu_network_contract_tests/run_macos_native_readiness.py \
  --native-plugin-report build/bambu_network_release_readiness/macos_native_plugin_report.json \
  --local-smoke-report build/bambu_network_release_readiness/local_candidate_smoke.json \
  --official-parity-report build/bambu_network_release_readiness/official_parity_bambu_02.05.02.58_mac_reacquired/parity_report.json \
  --native-package-macos-dir build/bambu_network_release_readiness/native_copy_scratch/OrcaSlicer.app/Contents/MacOS \
  --native-package-root build/bambu_network_release_readiness/native_copy_scratch \
  --native-gui-startup-log build/bambu_network_release_readiness/gui_native_smoke/native_startup_relevant_logs.txt \
  --native-gui-startup-plugin-dir build/bambu_network_release_readiness/gui_native_smoke_datadir/plugins \
  --out-dir build/bambu_network_release_readiness
```

Native readiness rejects the bridge dylib and Linux `.so` payloads as substitutes for native macOS evidence.
The official parity gate requires the official macOS dylibs to be outside the repo, present at the paths recorded in the parity report, and still matching the recorded hashes, so stale parity reports cannot satisfy native readiness after their inputs disappear or change.
The native package gate also verifies that the staged app `Contents/MacOS` directory contains the native Mach-O network/source dylibs matching the verified candidate hashes and no bridge or Linux runtime payloads, and that the package root does not contain generated bridge, Lima, or Linux runtime files.
The bridge fallback gate checks the current bridge config source to confirm macOS bridge mode remains the default and native mode is only enabled by the explicit native-plugin flag.
The loader routing gate checks the current Orca loader source to confirm native mode bypasses bridge preflight, uses macOS dylib loading/fallback paths, logs native mode, and loads `libBambuSource.dylib` separately when bridge mode is disabled.
The GUI startup gate checks a bounded native-mode app launch log and isolated plugin directory to confirm the full app logs native mode, direct network/source dylib loads, `bridge_mode=false`, compatibility success, and network-agent creation without bridge, Linux, or Lima runtime files.
Real-printer readiness requires raw parity evidence for printer workflow, upload-only/local-print/sdcard-print jobs, live source streaming, and a supplemental `--source-control-parity-report` for the live port-6000 source-control tunnel. Summary flags such as `real_printer_workflows_ok` or `source_streaming_parity_ok` are not accepted without successful official and candidate transcript artifacts.
It reports `resources/handy_models/OrcaCube_v2.3mf` as the default available test 3MF for blocker accounting; pass `--real-printer-test-3mf` to point readiness at a different print file. `run_real_printer_parity.py --macos-native-readiness` forwards its `--print-job-file` as that native readiness input.
Cloud/service readiness passes only with authorized `cloud_service` official-vs-candidate parity whose transcripts prove `allow_network=true`, `expect_success=true`, login/network/service success, and non-inert service results, or with `--cloud-service-scoped-out` plus passing unsupported safe-failure parity evidence. Completion audit requires the scoped-out report to carry concrete `safe_failure_checks`; a summary flag alone is not enough.

For the final macOS native external gates, use the real-printer or authorized-cloud wrappers with `--macos-native-readiness` to capture the live parity report and feed it into the native aggregator. The wrapper dry-runs validate command generation and local inputs, but they do not replace the live parity reports. When live inputs are missing, save the dry-run JSON and pass it through `--real-printer-dry-run-report` or `--authorized-cloud-dry-run-report` so the blocked readiness report names the missing inputs. When real-printer and cloud/service evidence are captured in separate runs, rerun the native aggregator with the produced reports through `--real-printer-parity-report` and `--cloud-service-parity-report`:

`run_real_printer_parity.py --macos-native-readiness` rejects incomplete native scope before capture: it requires upload-only, local-print, and sdcard-print modes, `--include-source-streaming`, and `--include-source-control-tunnel`. `run_authorized_cloud_parity.py --macos-native-readiness` requires login info, ticket, and access-token env inputs.
In native-readiness mode, these wrappers do not require the legacy Linux bridge runtime report; that report is still required for the legacy release-readiness path.
When the default blocker artifacts already exist, the wrappers pass them through to native readiness: the real-printer wrapper includes `authorized_cloud_dry_run_missing_inputs.json`, and the authorized-cloud wrapper includes `real_printer_dry_run_missing_inputs.json` plus `bambu_printer_discovery.json`. This keeps single-gate native runs actionable while the other external gate is still unresolved.

```sh
BAMBU_NETWORK_PRINTER_PASSWORD='<printer-access-code>' \
python3 tools/bambu_network_contract_tests/run_real_printer_parity.py \
  --skip-build \
  --official-network /tmp/bambu-official-plugin-02.05.02.58-reacquire/extracted/libbambu_networking.dylib \
  --official-source /tmp/bambu-official-plugin-02.05.02.58-reacquire/extracted/libBambuSource.dylib \
  --printer-dev-id '<printer-dev-id>' \
  --printer-dev-ip '<printer-ip>' \
  --printer-username bblp \
  --print-job-file '<path-to-test.3mf>' \
  --print-job-modes upload-only,local-print,sdcard-print \
  --print-job-remote-name test.3mf \
  --include-source-streaming \
  --include-source-control-tunnel \
  --macos-native-readiness \
  --confirm-start-prints

python3 tools/bambu_network_contract_tests/run_macos_native_readiness.py \
  --native-plugin-report build/bambu_network_release_readiness/macos_native_plugin_report.json \
  --local-smoke-report build/bambu_network_release_readiness/local_candidate_smoke.json \
  --official-parity-report build/bambu_network_release_readiness/official_parity_real_printer_current/parity_report.json \
  --real-printer-parity-report build/bambu_network_release_readiness/official_parity_real_printer_current/parity_report.json \
  --real-printer-dry-run-report build/bambu_network_release_readiness/real_printer_dry_run_missing_inputs.json \
  --printer-discovery-report build/bambu_network_release_readiness/bambu_printer_discovery.json \
  --source-control-parity-report build/bambu_network_release_readiness/official_parity_real_printer_current_source_control_tunnel/parity_report.json \
  --real-printer-test-3mf resources/handy_models/OrcaCube_v2.3mf \
  --native-package-macos-dir build/arm64/OrcaSlicer/OrcaSlicer.app/Contents/MacOS \
  --native-package-root build/arm64/OrcaSlicer \
  --native-gui-startup-log build/bambu_network_release_readiness/gui_native_smoke/native_startup_relevant_logs.txt \
  --native-gui-startup-plugin-dir build/bambu_network_release_readiness/gui_native_smoke_datadir/plugins \
  --out-dir build/bambu_network_release_readiness
```

```sh
BAMBU_CLOUD_LOGIN_INFO_JSON='<login-info-json>' \
BAMBU_CLOUD_TICKET='<cloud-ticket>' \
BAMBU_CLOUD_ACCESS_TOKEN='<cloud-access-token>' \
python3 tools/bambu_network_contract_tests/run_authorized_cloud_parity.py \
  --skip-build \
  --official-network /tmp/bambu-official-plugin-02.05.02.58-reacquire/extracted/libbambu_networking.dylib \
  --official-source /tmp/bambu-official-plugin-02.05.02.58-reacquire/extracted/libBambuSource.dylib \
  --cloud-user-info-env BAMBU_CLOUD_LOGIN_INFO_JSON \
  --cloud-ticket-env BAMBU_CLOUD_TICKET \
  --cloud-access-token-env BAMBU_CLOUD_ACCESS_TOKEN \
  --macos-native-readiness

python3 tools/bambu_network_contract_tests/run_macos_native_readiness.py \
  --native-plugin-report build/bambu_network_release_readiness/macos_native_plugin_report.json \
  --local-smoke-report build/bambu_network_release_readiness/local_candidate_smoke.json \
  --official-parity-report build/bambu_network_release_readiness/official_parity_authorized_cloud_current/parity_report.json \
  --cloud-service-parity-report build/bambu_network_release_readiness/official_parity_authorized_cloud_current/parity_report.json \
  --authorized-cloud-dry-run-report build/bambu_network_release_readiness/authorized_cloud_dry_run_missing_inputs.json \
  --native-package-macos-dir build/arm64/OrcaSlicer/OrcaSlicer.app/Contents/MacOS \
  --native-package-root build/arm64/OrcaSlicer \
  --native-gui-startup-log build/bambu_network_release_readiness/gui_native_smoke/native_startup_relevant_logs.txt \
  --native-gui-startup-plugin-dir build/bambu_network_release_readiness/gui_native_smoke_datadir/plugins \
  --out-dir build/bambu_network_release_readiness
```

Assemble the macOS bridge runtime input directory from the cross-built host and clean-room plugin payload:

```sh
python3 tools/bambu_network_contract_tests/assemble_macos_bridge_runtime.py \
  --skip-loader-probes
```

This writes `build/bambu_network_macos_bridge_runtime` with the Linux host binaries, macOS wrapper/install/verify scripts, certs, `libbambu_networking.so`, `libBambuSource.so`, `linux_payload_manifest.json`, and `macos_bridge_runtime_report.json`. Use `--skip-loader-probes` only on non-Linux hosts; a Linux release gate should omit it so `dlopen` checks and bridge RPC probes for both ABI host variants run.

After installing the runtime on macOS, the packaged verifier can run the Linux-side bridge probe through the configured Lima instance and write the report that release readiness consumes:

```sh
build/bambu_network_macos_bridge_runtime/verify_runtime_macos.sh \
  -PluginDir build/bambu_network_macos_bridge_runtime \
  -RunLinuxBridgeProbe \
  -LinuxBridgeReport "$PWD/build/bambu_network_release_readiness/linux_bridge_runtime_verify_report.json"
```

Pass that report back into release readiness with `--linux-runtime-report`. The verifier still requires the runtime payload copied into the user's OrcaSlicer application support directory and a ready Lima instance; run `install_runtime_macos.sh` first when validating on a fresh machine. On Apple Silicon, the installer enables Rosetta and installs the guest amd64 runtime packages needed to launch the x86_64 Linux bridge host.

To stage the same clean-room runtime into the source directory consumed by Orca's macOS packaging:

```sh
python3 tools/bambu_network_contract_tests/assemble_macos_bridge_runtime.py \
  --source-runtime-dir \
  --replace-existing \
  --skip-loader-probes
```

Do not use `--skip-loader-probes` for final release qualification inside Linux.

## Verify The Local ABI Mirror

The Rust plugin shim uses a small local ABI mirror header so it can build without OrcaSlicer's full dependency tree. Check that the mirror still matches the public plugin structs:

```sh
python3 tools/bambu_network_contract_tests/verify_abi_mirror.py
```

## Regenerate the Symbol Manifest

```sh
python3 tools/bambu_network_contract_tests/generate_required_symbols.py \
  > tools/bambu_network_contract_tests/required_symbols.txt
```

To regenerate the `libBambuSource` manifest:

```sh
python3 tools/bambu_network_contract_tests/generate_required_symbols.py --kind source \
  > tools/bambu_network_contract_tests/source_symbols.txt
```

To check both manifests without rewriting them:

```sh
python3 tools/bambu_network_contract_tests/generate_required_symbols.py --check
```

Only regenerate from public repo source files. Do not add symbols or notes copied from decompiled proprietary code.
