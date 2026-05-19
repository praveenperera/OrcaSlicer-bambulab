# Bambu Network Rust Plugin

This is the clean-room replacement plugin scaffold. It builds a `libbambu_networking` shared library with a C++ ABI facade and a Rust core behind a narrow internal C ABI. It also builds a `libBambuSource` shim with source URL parsing, local TLS control framing, and opt-in synthetic streaming fixtures so the Linux bridge can load both payload libraries without proprietary binaries.

The C++ facade is required because OrcaSlicer loads symbols such as `bambu_network_get_version` with C++ signatures using `std::string`, `std::function`, maps, vectors, and opaque agent pointers. Rust should not try to impersonate that public ABI directly.

## Build

```sh
cmake -S tools/bambu_network_rust_plugin -B build/bambu_network_rust_plugin
cmake --build build/bambu_network_rust_plugin
```

Configure with `-DCMAKE_BUILD_TYPE=Release` for release payloads; the CMake wrapper will build the Rust core with Cargo `--release` and link that static library into the shim.

To cross-build the Linux bridge payload from macOS with Zig:

```sh
cmake -S tools/bambu_network_rust_plugin -B build/bambu_network_rust_plugin_linux_x86_64 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_SYSTEM_NAME=Linux \
  -DCMAKE_CXX_COMPILER="$PWD/tools/bambu_network_rust_plugin/scripts/zig-cxx-x86_64-linux-gnu" \
  -DRUST_TARGET=x86_64-unknown-linux-gnu
cmake --build build/bambu_network_rust_plugin_linux_x86_64 --config Release --parallel
python3 tools/bambu_network_contract_tests/assemble_candidate_linux_payload.py \
  --network-so build/bambu_network_rust_plugin_linux_x86_64/libbambu_networking.so \
  --source-so build/bambu_network_rust_plugin_linux_x86_64/libBambuSource.so \
  --out-dir build/bambu_network_rust_plugin_linux_x86_64/linux-payload \
  --skip-symbol-probes
```

The `--skip-symbol-probes` flag is only needed when assembling Linux ELF files on macOS, because the host process cannot `dlopen` them. The assembler still checks the ELF dynamic export table with `nm -D`; run the non-skipped loader and bridge probes inside a Linux environment.

The Zig cross-build currently qualifies a matched bridge-host-plus-plugin bundle. It does not by itself prove that a direct Linux OrcaSlicer build using GCC/libstdc++ can load the plugin, because Zig's Linux C++ runtime may emit libc++ ABI symbols. Treat direct Linux OrcaSlicer compatibility as a separate Linux-native build and loader gate unless the release only uses the bundled bridge host.

## Verify The First Slice

```sh
build/bambu_network_contract_tests/bambu_network_lifecycle_probe \
  --plugin build/bambu_network_rust_plugin/libbambu_networking.dylib \
  --log-dir /tmp/bambu-rust-plugin-log
```

On Linux the built artifact is `libbambu_networking.so`; on macOS it is `libbambu_networking.dylib`. The final release target for the Linux bridge must be the Linux `.so`.

Probe the source shim:

```sh
build/bambu_network_contract_tests/bambu_network_contract_probe \
  --plugin build/bambu_network_rust_plugin/libBambuSource.dylib \
  --symbols tools/bambu_network_contract_tests/source_symbols.txt \
  --json
```

The current scaffold exports the full required symbol surface. LAN discovery, local MQTT publish/subscribe, implicit FTPS upload, upload-only SD-card transfer, local upload-then-`project_file` print with MD5 fallback, SD-card `project_file` print with an on-demand local MQTT connection, print-specific upload/publish error codes, local print status callbacks, local RTSPS camera URL generation, source URL parsing, local `libBambuSource` TLS control framing, opt-in synthetic `libBambuSource` MJPEG and cloud/service fixtures, callback-style MakerWorld/HMS service exports, an opt-in `BAMBU_NETWORK_CLOUD_BASE_URL` HTTP cloud adapter fixture, session `backend_url` HTTP cloud adapter fallback, and the `ft_*` tunnel/job lifecycle used by Orca's file-transfer wrapper have first-pass implementations. Authorized cloud/service parity and real printer eMMC/port-6000 response behavior still need implementation or parity evidence. Passing the symbol probe means the library can be loaded and inspected; it does not prove official-plugin parity or real printer behavior.
