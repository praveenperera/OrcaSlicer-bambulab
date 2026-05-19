# Bambu Network Replacement Completion Audit

This audit maps the compatibility goal to concrete artifacts and current evidence. It is intentionally conservative: a green local smoke gate is not treated as full interoperability.

## Success Criteria

| Requirement | Current evidence | Status |
| --- | --- | --- |
| Clean-room Rust reimplementation behind a C++ ABI shim | `tools/bambu_network_rust_plugin/rust_core/`, `tools/bambu_network_rust_plugin/shim/bambu_networking_shim.cpp`, `tools/bambu_network_rust_plugin/shim/bambu_source_shim.cpp` | In progress |
| Mirrored networking ABI types match Orca's public headers | `verify_abi_mirror.py` compares `detectResult`, `PrintParams`, `TaskQueryParams`, `PublishParams`, mirrored callback aliases, and mirrored error constants against Orca's public headers | Locally verified |
| Replacement C++ shim signatures match Orca's loader-facing typedefs | `verify_cpp_signature_mirror.py` maps `BBLNetworkPlugin.cpp` `dlsym`/`get_function` loads to `func_*` typedefs in `BBLNetworkPlugin.hpp`, compares `FileTransferUtils.hpp` `ft_*` typedefs, and compares public `BambuTunnel.h` prototypes against the replacement shims; current run covers 100 loader typedefs, 21 file-transfer typedefs, and 18 BambuSource prototypes | Locally verified |
| OrcaSlicer can load the replacement as `libbambu_networking.so` | Cross-build emits Linux ELF `libbambu_networking.so`; macOS `bambu_network_contract_probe` loads the host `.dylib`; Linux `dlopen` probe still requires a Linux process | Partially verified |
| All required `libbambu_networking` symbols export | `required_symbols.txt`; smoke gate reports 124 present and 0 missing on the host build; `verify_elf_exports.py` reports 124 present and 0 missing on the Linux ELF build, including the `ft_*` symbols loaded by `FileTransferUtils`; unsupported probe verifies `ft_abi_version == 1` | Locally verified |
| All required `libBambuSource` symbols export | `source_symbols.txt`; smoke gate reports 18 present and 0 missing on the host build; `verify_elf_exports.py` reports 18 present and 0 missing on the Linux ELF build | Locally verified |
| Lifecycle contract matches official plugin | `bambu_network_lifecycle_probe`; `capture_official_parity.py` compares official and candidate transcripts and records non-JSON probe failures as JSON artifacts | Verified against official 02.05.02.58 |
| Callback registration contract matches official plugin | `bambu_network_callback_probe`; transcript comparator; failed official probes still leave machine-readable artifacts | Verified against official 02.05.02.58 |
| File-transfer tunnel/job contract can be compared with official plugin | `capture_official_parity.py --include-ft-behavior` records and compares full synthetic `bambu_network_ft_behavior_probe` transcripts; `--include-ft-job-only` records official-safe invalid `ft_job_create` behavior | Invalid `ft_job_create` verified against official 02.05.02.58; full synthetic tunnel parity blocked because official crashes on fake tunnel URLs; real printer FT parity still required |
| Rust-originated events reach Orca callbacks through shim | `bambu_network_event_bridge_probe` candidate-only gate | Locally verified |
| UDP discovery maps Bambu SSDP packets into Orca machine-alive JSON | `bambu_network_discovery_probe` | Locally verified with synthetic packet |
| LAN MQTT connect/send/disconnect behaves like official plugin | `bambu_network_printer_workflow_probe`; `run_release_readiness.py` now loads real-printer parity transcripts and requires both official and candidate runs to show non-empty printer identity, password-present, missing-symbol-free, successful connect/message/disconnect, successful connect callback evidence, and clean destroy before accepting real-printer evidence | Tooling ready, real printer parity missing |
| Upload-only, local print, and SD-card print workflows behave like official plugin | `bambu_network_print_job_probe`; `run_release_readiness.py` now requires `upload-only`, `local-print`, and `sdcard-print` modes, an existing print-job fixture file, a remote name, successful official and candidate print/upload `job_result == 0`, expected print-job mode in each transcript, finished print status callbacks, and no error status callbacks for real-printer readiness; no-printer smoke verifies print-specific upload/publish error codes and status events; Rust unit tests verify SD-card print connects to local MQTT when LAN credentials are provided and local print computes a missing project-file MD5 | Tooling ready; no-printer failure path locally verified; real printer parity missing |
| `ft_*` file-transfer ABI supports Orca's tunnel/job wrapper lifecycle | `bambu_network_ft_behavior_probe` verifies local tunnel creation, status/connect callbacks, media-ability results, result polling, upload progress messages, missing-file failure, and payload destroy functions; `bambu_network_source_local_tunnel_probe` verifies the `libBambuSource` loopback control-tunnel path Orca uses for local eMMC browsing can open, start, send JSON control messages, return a `Bambu_RecvMessage` response, and return a polled sample response; the candidate source shim now uses TLS for `bambu:///local/...` before falling back to raw TCP in candidate-only fixtures, sends the observed local-control login preamble/credential block, and frames `Bambu_SendMessage` payloads with the official `mtype` rewrite; `run_source_control_tls_loopback_parity.py` compares official-vs-candidate TLS login and control-frame wire contracts without storing credentials; `run_source_control_tunnel_parity.py` wraps live official-vs-candidate source/control tunnel parity without starting a print and redacts the control URL/message in dry-run output; `run_release_readiness.py` treats `source_streaming` transcripts in `control` mode separately from video streaming and requires `Bambu_SendMessage`, `Bambu_RecvMessage`, a second control send, and `Bambu_ReadSample` success before `non_ftps_tunnel_feature_parity` can turn green | Local TLS/control framing parity verified against official; real printer eMMC/port-6000 response parity missing |
| Camera URL generation is compatible with Orca expectations | `bambu_network_camera_url_probe` | Locally verified for URL construction only |
| `libBambuSource` camera/tunnel APIs are safe when unsupported | `bambu_network_source_behavior_probe`; source shim and probe use Orca's public `BambuTunnel.h` layouts for `Bambu_StreamInfo` and `Bambu_Sample`; optional `capture_official_parity.py --include-source-behavior` records official-vs-candidate source behavior without weakening the candidate safety gate | Verified against official 02.05.02.58 for non-network camera/local/error behavior |
| Camera/source streaming reaches full feature parity | `bambu_network_source_streaming_probe` opens a user-provided `bambu:///...` source URL, waits through would-block/buffer-limit states, captures stable `Bambu_GetStreamInfo` contract fields, requires positive type/subtype/format metadata, dimensions, frame rate, format sizes, and a non-empty `Bambu_ReadSample` when success is expected, and redacts credentials from artifacts; `run_candidate_smoke.py` now requires an opt-in synthetic MJPEG fixture to prove local source/sample plumbing; `run_source_rtsp_loopback_parity.py` generates a local H.264 RTSP/RTP-over-TCP fixture, compares official and candidate `libBambuSource` transcripts on the same redacted `bambu:///rtsp___...` URL, and feeds readiness through `--source-streaming-parity-report`; `run_source_streaming_parity.py` wraps the live official-vs-candidate source-streaming parity capture, feeds the generated report into readiness with unrelated external gates deferred, and has a dry-run verifier that proves command generation and URL redaction behavior; `run_real_printer_parity.py --include-source-streaming` can include live RTSPS source parity in the final printer-backed report using the same password env; `capture_official_parity.py --source-stream-url ... --expect-source-stream-success` compares official and candidate transcripts; `run_release_readiness.py` marks `camera_source_streaming` green only when source parity evidence is present | Loopback RTSP parity verified against official; real printer camera/source parity remains manual |
| Cloud/service behavior fails safely without crashes or impersonation | `bambu_network_unsupported_probe`; smoke gate now invokes every exported cloud/service API with inert inputs, checks controlled failures, cleared output buffers, quiet callbacks, and non-crashing void APIs; `bambu_network_cloud_service_probe` also verifies the official-matched logged-out host/studio-info contract and redacted offline login/logout behavior without network access | Locally verified for exported surface, offline login state, and logged-out official parity |
| Cloud/service APIs reach full feature parity | `bambu_network_cloud_service_probe` is an opt-in authorized probe for login state, cloud connection, selected URL/service calls, callbacks, and non-inert service responses; it normalizes evidence and avoids storing login JSON, tokens, tickets, access tokens, or raw HTTP bodies; candidate smoke also runs an opt-in synthetic cloud/service fixture plus local HTTP fixtures for both `BAMBU_NETWORK_CLOUD_BASE_URL` and login-payload `backend_url` to prove JSON/http-code/token/profile plumbing, URL extraction, server-connected callbacks, callback-style MakerWorld/HMS exports, service URL extraction, and real request/response flow without touching Bambu services; `run_authorized_cloud_parity.py` wraps `capture_official_parity.py --include-cloud-service --allow-cloud-network --expect-cloud-service-success`, feeds the generated report into readiness with manual printer parity deferred, and has a dry-run verifier that proves command generation and secret redaction behavior; `run_release_readiness.py` marks `cloud_service_feature_parity` green only when authorized parity evidence is present | Candidate synthetic and HTTP plumbing fixtures verified; implementation still needs authorized cloud/service evidence or explicit scope exclusion |
| Required export manifests stay aligned with Orca's public loader sources | `generate_required_symbols.py --check` compares `required_symbols.txt` against `BBLNetworkPlugin.cpp`, `FileTransferUtils.cpp`, and the Linux host source, and compares `source_symbols.txt` against `BambuTunnel.h` | Locally verified |
| Every required export has at least one behavior probe | `verify_contract_surface_coverage.py` scans required symbol lists against all behavior probe sources and fails if a symbol is covered only by `bambu_network_contract_probe` | Locally verified |
| Verification artifacts show pass/fail parity without shipping proprietary binaries | `capture_official_parity.py` writes transcripts, comparisons, SHA-256, size metadata, and `copies_input_binaries=false` policy, including JSON failure artifacts for crashed/non-JSON probes; `verify_clean_room_artifacts.py` checks that parity reports keep official inputs outside the repo, artifact directories contain no ELF, Mach-O, or PE binaries, and scanned release/source directories contain no byte-for-byte copies of the official input binaries; `run_release_readiness.py` runs the artifact-policy verifier for generated and supplied `--official-parity-report` reports even when the report is otherwise red, and validates reports against the current candidate hashes while rejecting stale candidate hashes, self-compare reports, missing required probes/comparisons, missing or unreadable referenced probe artifacts, probe artifacts outside the parity report directory, probe artifact JSON that does not directly match after ignoring path-only fields, comparison artifacts that do not record matching transcripts, missing candidate-only source/event/camera probes, identical official/candidate hashes, missing full FT evidence, weak real-printer reports that do not contain successful workflow transcripts, and weak `--source-control-tls-loopback-parity-report` artifacts with unredacted secrets, stale candidate hashes, copied binaries, or mismatched contracts | Tooling verified; official 02.05.02.58 report is clean-room and passes all non-printer parity but blocks on full FT evidence |
| Release readiness can be judged by one pass/fail artifact | `run_release_readiness.py` writes `release_readiness_report.json` and fails when official parity, real printer inputs, full-compatibility feature parity, Linux bridge loader probes, or macOS bridge runtime packaging evidence are missing; it can now consume `--official-parity-report` as external official/real-printer evidence, `--source-streaming-parity-report` as supplemental source-streaming evidence, `--source-control-tls-loopback-parity-report` as supplemental local-control TLS wire-contract evidence, and `--linux-runtime-report` from `verify_linux_bridge_runtime.py` as external Linux loader/RPC evidence; captured `local_candidate_smoke.json` is a single parseable JSON summary with named `preflight_*` checks rather than concatenated probe transcripts; readiness parses that summary and records `local_candidate_smoke.summary_validation`, requiring smoke `ok`, an empty `failed` list, thirteen preflight checks, and representative symbol/lifecycle/callback/unsupported/source/cloud-fixture/source-local-tunnel/print/discovery/camera/FT checks; deferred-readiness flags classify manual printer and authorized cloud blockers without marking the report complete; `verify_release_readiness_report.py` independently audits generated readiness reports for required gates, blocker consistency, deferred-blocker consistency, macOS copied-file evidence, Linux direct libstdc++ evidence, feature-gap shape, and optional TLS loopback contract/redaction/hash checks; `verify_completion_audit.py` maps the full compatibility objective to concrete readiness evidence and fails until every objective criterion is covered; `verify_real_printer_parity_dry_run.py`, `verify_source_streaming_parity_dry_run.py`, `verify_source_control_tunnel_parity_dry_run.py`, and `verify_authorized_cloud_parity_dry_run.py` cover final wrapper dry-run command generation and secret-safety checks, including control-mode source parity command generation | Linux/local/macOS gates pass; official parity blocks on full FT evidence, and full-compatibility parity blocks on cloud/service feature parity and non-FTPS tunnel parity |
| Linux bridge payload can be assembled without proprietary binaries | `assemble_candidate_linux_payload.py` writes `linux_payload_manifest.json`, rejects non-ELF input, runs host-independent ELF export-table and C++ ABI checks, and can run Linux `dlopen` probes plus `bridge_rpc_probe.py` when executed in Linux; bridge probe now checks auth/session capability exposure, logged-out public host/studio-info URL parity, FT capabilities, tunnel/job RPC smoke, synthetic `libBambuSource` stream/sample forwarding through binary RPC frames, loopback `libBambuSource` local control-tunnel send/read forwarding, and synthetic cloud/service forwarding over RPC; `verify_linux_bridge_runtime.py` is copied into the assembled runtime, records payload hashes, and runs the bridge RPC probe against both ABI host variants from inside Linux; the macOS runtime verifier can now run that Linux-side verifier through Lima with `-RunLinuxBridgeProbe`; `run_release_readiness.py --linux-runtime-report` validates that report, rejects stale payload hashes, and independently checks both ABI transcripts for network/source load state, agent lifecycle RPC results, auth/session/public URL evidence, the full `ft_*` capability table, FT tunnel/media/upload-missing-file smoke details, source stream/sample forwarding, source local control-tunnel forwarding, and cloud/service fixture forwarding before accepting it as Linux bridge evidence | Verified through installed Lima runtime |
| macOS bridge runtime input directory can be assembled from clean-room artifacts | `assemble_macos_bridge_runtime.py --skip-loader-probes` writes `build/bambu_network_macos_bridge_runtime` with Linux host binaries, wrapper/install/verify scripts, Linux-side verifier scripts, certs, clean-room `.so` files, `linux_payload_manifest.json`, and `macos_bridge_runtime_report.json`; `verify_macos_release_runtime.py` checks required files, Linux ELF payloads, manifest hashes, executable bits, and the `build_release_macos.sh` runtime-copy path using a temporary app bundle, including SHA-256 and size metadata for every copied runtime file; `run_release_readiness.py` records that metadata in the macOS gate, and `verify_release_readiness_report.py` rejects reports missing it; the packaged `verify_runtime_macos.sh -RunLinuxBridgeProbe` path can produce the Linux bridge runtime report from the installed Lima runtime; on Apple Silicon, `install_runtime_macos.sh` installs the guest amd64 runtime packages required by Rosetta to launch the x86_64 bridge host; `--source-runtime-dir --replace-existing` stages the same files into `tools/pjarczak_bambu_linux_host/runtime/linux-x86_64` for Orca's macOS packaging; `build_release_macos.sh` can also consume an assembled runtime through `PJARCZAK_BAMBU_HOST_RUNTIME_DIR` and now fails early if the selected runtime is missing the clean-room networking/source `.so` files or manifest; without `--skip-loader-probes` it runs Linux loader checks and bridge RPC probes for both ABI host variants | Locally assembled and copy-verified; Linux loader/bridge run available through installed Lima runtime |
| Direct Linux OrcaSlicer loading uses the expected C++ runtime ABI | `build_linux_libstdcxx_candidate.py` can build `libbambu_networking.so` and `libBambuSource.so` with an x86-64 GCC/libstdc++ cross toolchain from the existing Rust GNU static library, then runs ELF export checks, `verify_elf_cxx_abi.py --expect libstdc++`, and Linux `dlopen`/`dlsym` probes with a Linux `bambu_network_contract_probe`; `verify_elf_exports.py` and `verify_elf_cxx_abi.py` honor `NM`/`OBJDUMP` overrides for cross environments | Locally verified through Lima with `x86_64-linux-gnu-g++`; full real-printer behavior still separate |

## Latest Local Gates

These commands passed on the current macOS candidate build:

```sh
cmake --build build/bambu_network_contract_tests
python3 tools/bambu_network_contract_tests/run_candidate_smoke.py --skip-build
python3 tools/bambu_network_contract_tests/capture_official_parity.py --skip-build \
  --official-network build/bambu_network_rust_plugin/libbambu_networking.dylib \
  --official-source build/bambu_network_rust_plugin/libBambuSource.dylib \
  --candidate-network build/bambu_network_rust_plugin/libbambu_networking.dylib \
  --candidate-source build/bambu_network_rust_plugin/libBambuSource.dylib \
  --out-dir /tmp/bambu-network-self-parity \
  --include-discovery \
  --include-source-behavior \
  --include-ft-behavior \
  --allow-self-compare
```

These commands passed on the current macOS Release candidate build:

```sh
cmake -S tools/bambu_network_rust_plugin -B build/bambu_network_rust_plugin_release -DCMAKE_BUILD_TYPE=Release
cmake --build build/bambu_network_rust_plugin_release
python3 tools/bambu_network_contract_tests/run_candidate_smoke.py --skip-build \
  --plugin-build-dir build/bambu_network_rust_plugin_release
python3 tools/bambu_network_contract_tests/verify_contract_surface_coverage.py
python3 tools/bambu_network_contract_tests/verify_clean_room_artifacts.py \
  --parity-report /tmp/bambu-network-self-parity/parity_report.json \
  --artifact-dir /tmp/bambu-network-self-parity \
  --allow-official-inside-repo
build/bambu_network_contract_tests/bambu_network_ft_behavior_probe \
  --plugin build/bambu_network_rust_plugin_release/libbambu_networking.dylib
python3 tools/bambu_network_contract_tests/run_release_readiness.py \
  --allow-incomplete \
  --skip-linux-loader-probes \
  --plugin-build-dir build/bambu_network_rust_plugin_release
```

These commands passed for the current macOS-to-Linux cross-build:

```sh
cmake -S tools/bambu_network_rust_plugin -B build/bambu_network_rust_plugin_linux_x86_64 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_SYSTEM_NAME=Linux \
  -DCMAKE_CXX_COMPILER="$PWD/tools/bambu_network_rust_plugin/scripts/zig-cxx-x86_64-linux-gnu" \
  -DRUST_TARGET=x86_64-unknown-linux-gnu
cmake --build build/bambu_network_rust_plugin_linux_x86_64 --config Release --parallel
python3 tools/bambu_network_contract_tests/verify_elf_exports.py \
  --plugin build/bambu_network_rust_plugin_linux_x86_64/libbambu_networking.so \
  --symbols tools/bambu_network_contract_tests/required_symbols.txt \
  --json
python3 tools/bambu_network_contract_tests/verify_elf_exports.py \
  --plugin build/bambu_network_rust_plugin_linux_x86_64/libBambuSource.so \
  --symbols tools/bambu_network_contract_tests/source_symbols.txt \
  --json
python3 tools/bambu_network_contract_tests/verify_elf_cxx_abi.py \
  --plugin build/bambu_network_rust_plugin_linux_x86_64/libbambu_networking.so \
  --json
python3 tools/bambu_network_contract_tests/assemble_candidate_linux_payload.py \
  --network-so build/bambu_network_rust_plugin_linux_x86_64/libbambu_networking.so \
  --source-so build/bambu_network_rust_plugin_linux_x86_64/libBambuSource.so \
  --out-dir build/bambu_network_rust_plugin_linux_x86_64/linux-payload \
  --skip-symbol-probes
build/bambu_network_macos_bridge_runtime/install_runtime_macos.sh \
  -PluginDir build/bambu_network_macos_bridge_runtime \
  -ReplaceExisting
build/bambu_network_macos_bridge_runtime/verify_runtime_macos.sh \
  -PluginDir build/bambu_network_macos_bridge_runtime \
  -RunLinuxBridgeProbe \
  -LinuxBridgeReport "$PWD/build/bambu_network_release_readiness/linux_bridge_runtime_verify_report.json"
python3 tools/bambu_network_contract_tests/run_release_readiness.py \
  --allow-incomplete \
  --skip-linux-loader-probes \
  --linux-runtime-report build/bambu_network_release_readiness/linux_bridge_runtime_verify_report.json
```

The Linux payload manifest records SHA-256 hashes plus ELF export-table checks for both shared objects. The installed Lima runtime verifies both x86-64 ABI host variants under Rosetta, loads the clean-room network/source `.so` files, runs lifecycle RPCs, validates the full `ft_*` capability table, and runs the FT tunnel/media/upload-missing-file smoke. The release-readiness report currently marks local candidate smoke, Linux bridge payload, and macOS bridge runtime as passing, then blocks on full FT contract evidence, real-printer parity inputs, and explicit full-compatibility feature gaps.

These commands passed for the standalone bridge host:

```sh
cmake -S tools/pjarczak_bambu_linux_host -B build/pjarczak_bambu_linux_host
cmake --build build/pjarczak_bambu_linux_host --target pjarczak_bambu_linux_host --config Release --parallel
cmake -S tools/pjarczak_bambu_linux_host -B build/pjarczak_bambu_linux_host_linux_x86_64 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_SYSTEM_NAME=Linux \
  -DCMAKE_CXX_COMPILER="$PWD/tools/bambu_network_rust_plugin/scripts/zig-cxx-x86_64-linux-gnu"
cmake --build build/pjarczak_bambu_linux_host_linux_x86_64 --target pjarczak_bambu_linux_host --config Release --parallel
python3 tools/bambu_network_contract_tests/assemble_macos_bridge_runtime.py --skip-loader-probes
python3 tools/bambu_network_contract_tests/verify_macos_release_runtime.py \
  --runtime-dir build/bambu_network_macos_bridge_runtime
```

The cross-built host outputs are Linux x86-64 ELF executables for both ABI variants. The installed macOS Lima runtime now provides the Linux runtime loading evidence for that matched bridge-host-plus-plugin bundle.

The current Zig-built Linux plugin and host should be treated as one matched runtime bundle. It is not proof that an unrelated Linux OrcaSlicer process built against GCC/libstdc++ can load the plugin directly, because the produced shared object contains libc++ ABI symbols. If direct Linux loading is a target, add a Linux-native GCC build gate or provide a cross sysroot with libstdc++, then rerun the same ELF export, `dlopen`, and contract probes against that artifact.

This direct Linux libstdc++ build passed inside the configured Lima guest using the installed x86-64 GCC cross toolchain:

```sh
python3 tools/bambu_network_contract_tests/build_linux_libstdcxx_candidate.py \
  --run-dlopen-probes \
  --ld-library-path /usr/x86_64-linux-gnu/lib
```

The generated report is `build/bambu_network_rust_plugin_linux_x86_64_libstdcxx/linux_libstdcxx_candidate_report.json`. It shows `libbambu_networking.so` and `libBambuSource.so` are x86-64 ELF shared objects, export 124/124 and 18/18 required symbols, infer `libstdc++` for both C++ ABI checks, and pass Linux `dlopen`/`dlsym` probes for both symbol manifests.

The self-parity run verifies the artifact pipeline only. It does not prove parity with the official Bambu plugin.

This bridge host build passed on macOS to verify the host-side RPC/capability changes compile:

```sh
cmake -S tools/pjarczak_bambu_linux_host -B build/pjarczak_bambu_linux_host
cmake --build build/pjarczak_bambu_linux_host --target pjarczak_bambu_linux_host
```

## Remaining Completion Blockers

1. Run real LAN printer validation for connect, publish/subscribe, upload-only transfer, local-print, SD-card print, live RTSPS source streaming, and live port-6000 source-control/eMMC parity using `run_real_printer_parity.py --include-source-streaming --include-source-control-tunnel`. This is the remaining path to satisfy `full_ft_contract_evidence`, real-printer workflow evidence, camera/source feature parity, and non-FTPS tunnel feature parity without relying on the synthetic fake-tunnel official probe that currently crashes official 02.05.02.58.
2. Capture authorized cloud/service parity with `run_authorized_cloud_parity.py` or explicitly scope cloud/service APIs out of the target release. Cloud/service must stay red until the candidate produces successful authorized parity evidence or the target release contract excludes those APIs.
3. Capture final readiness with the real-printer parity report, source-control supplemental report, and cloud/service decision so `release_readiness_report.json` has no blockers.
4. Re-run the Linux-native GCC/libstdc++ direct load gate when the final candidate payload changes.
