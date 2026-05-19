#!/bin/bash
set -euo pipefail

PACKAGE_DIR=""
PLUGIN_DIR=""
PLUGIN_CACHE_DIR=""
ALLOW_MISSING_LINUX_PLUGIN=0
RUN_LINUX_BRIDGE_PROBE=0
LINUX_BRIDGE_REPORT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -PackageDir)
            PACKAGE_DIR="${2:-}"
            shift 2
            ;;
        -PluginDir)
            PLUGIN_DIR="${2:-}"
            shift 2
            ;;
        -PluginCacheDir)
            PLUGIN_CACHE_DIR="${2:-}"
            shift 2
            ;;
        -AllowMissingLinuxPlugin)
            ALLOW_MISSING_LINUX_PLUGIN=1
            shift
            ;;
        -RunLinuxBridgeProbe)
            RUN_LINUX_BRIDGE_PROBE=1
            shift
            ;;
        -LinuxBridgeReport)
            LINUX_BRIDGE_REPORT="${2:-}"
            shift 2
            ;;
        *)
            echo "unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

if [[ -z "$PLUGIN_DIR" ]]; then
    PLUGIN_DIR="$PACKAGE_DIR"
fi
if [[ -z "$PLUGIN_DIR" ]]; then
    echo "PluginDir is required" >&2
    exit 2
fi

APP_SUPPORT_DIR="$HOME/Library/Application Support/OrcaSlicer/macos-bridge"
RUNTIME_DIR="${PJARCZAK_MAC_RUNTIME_DIR:-$APP_SUPPORT_DIR/runtime}"

trim_file() {
    local path="$1"
    if [[ ! -f "$path" ]]; then
        return 1
    fi
    LC_ALL=C tr -d '' < "$path" | head -n 1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

find_limactl() {
    if [[ -n "${PJARCZAK_LIMACTL:-}" && -x "${PJARCZAK_LIMACTL}" ]]; then
        printf '%s
' "$PJARCZAK_LIMACTL"
        return 0
    fi
    if command -v limactl >/dev/null 2>&1; then
        command -v limactl
        return 0
    fi
    local local_bin="$APP_SUPPORT_DIR/lima/bin/limactl"
    if [[ -x "$local_bin" ]]; then
        printf '%s
' "$local_bin"
        return 0
    fi
    for candidate in /opt/homebrew/bin/limactl /usr/local/bin/limactl; do
        if [[ -x "$candidate" ]]; then
            printf '%s
' "$candidate"
            return 0
        fi
    done
    return 1
}

require_file() {
    local path="$1"
    local label="$2"
    if [[ ! -f "$path" ]]; then
        echo "missing required file: $label" >&2
        exit 1
    fi
}

compare_required_file() {
    local src="$1"
    local dst="$2"
    local label="$3"
    if [[ ! -f "$src" || ! -f "$dst" ]]; then
        echo "runtime payload file missing: $label" >&2
        exit 1
    fi
    if ! cmp -s "$src" "$dst"; then
        echo "runtime payload out of date: $label" >&2
        exit 1
    fi
}

mkdir -p "$APP_SUPPORT_DIR"

require_file "$PLUGIN_DIR/install_runtime_macos.sh" "install_runtime_macos.sh"
require_file "$PLUGIN_DIR/verify_runtime_macos.sh" "verify_runtime_macos.sh"
require_file "$PLUGIN_DIR/pjarczak_lima_instance.txt" "pjarczak_lima_instance.txt"
require_file "$PLUGIN_DIR/pjarczak-bambu-linux-host-wrapper" "pjarczak-bambu-linux-host-wrapper"
require_file "$PLUGIN_DIR/verify_linux_bridge_runtime.py" "verify_linux_bridge_runtime.py"
require_file "$PLUGIN_DIR/bridge_rpc_probe.py" "bridge_rpc_probe.py"

if [[ "$ALLOW_MISSING_LINUX_PLUGIN" -eq 0 ]]; then
    require_file "$PLUGIN_DIR/libbambu_networking.so" "libbambu_networking.so"
    require_file "$PLUGIN_DIR/libBambuSource.so" "libBambuSource.so"
fi
require_file "$PLUGIN_DIR/pjarczak_bambu_linux_host" "pjarczak_bambu_linux_host"
require_file "$PLUGIN_DIR/pjarczak_bambu_linux_host_abi1" "pjarczak_bambu_linux_host_abi1"
require_file "$PLUGIN_DIR/pjarczak_bambu_linux_host_abi0" "pjarczak_bambu_linux_host_abi0"
require_file "$PLUGIN_DIR/ca-certificates.crt" "ca-certificates.crt"
require_file "$PLUGIN_DIR/slicer_base64.cer" "slicer_base64.cer"

require_file "$RUNTIME_DIR/libbambu_networking.so" "runtime/libbambu_networking.so"
require_file "$RUNTIME_DIR/libBambuSource.so" "runtime/libBambuSource.so"
require_file "$RUNTIME_DIR/pjarczak_bambu_linux_host" "runtime/pjarczak_bambu_linux_host"
require_file "$RUNTIME_DIR/pjarczak_bambu_linux_host_abi1" "runtime/pjarczak_bambu_linux_host_abi1"
require_file "$RUNTIME_DIR/pjarczak_bambu_linux_host_abi0" "runtime/pjarczak_bambu_linux_host_abi0"
require_file "$RUNTIME_DIR/verify_linux_bridge_runtime.py" "runtime/verify_linux_bridge_runtime.py"
require_file "$RUNTIME_DIR/bridge_rpc_probe.py" "runtime/bridge_rpc_probe.py"
require_file "$RUNTIME_DIR/linux_payload_manifest.json" "runtime/linux_payload_manifest.json"
require_file "$RUNTIME_DIR/ca-certificates.crt" "runtime/ca-certificates.crt"
require_file "$RUNTIME_DIR/slicer_base64.cer" "runtime/slicer_base64.cer"

compare_required_file "$PLUGIN_DIR/libbambu_networking.so" "$RUNTIME_DIR/libbambu_networking.so" "libbambu_networking.so"
compare_required_file "$PLUGIN_DIR/libBambuSource.so" "$RUNTIME_DIR/libBambuSource.so" "libBambuSource.so"
compare_required_file "$PLUGIN_DIR/pjarczak_bambu_linux_host" "$RUNTIME_DIR/pjarczak_bambu_linux_host" "pjarczak_bambu_linux_host"
compare_required_file "$PLUGIN_DIR/pjarczak_bambu_linux_host_abi1" "$RUNTIME_DIR/pjarczak_bambu_linux_host_abi1" "pjarczak_bambu_linux_host_abi1"
compare_required_file "$PLUGIN_DIR/pjarczak_bambu_linux_host_abi0" "$RUNTIME_DIR/pjarczak_bambu_linux_host_abi0" "pjarczak_bambu_linux_host_abi0"
compare_required_file "$PLUGIN_DIR/verify_linux_bridge_runtime.py" "$RUNTIME_DIR/verify_linux_bridge_runtime.py" "verify_linux_bridge_runtime.py"
compare_required_file "$PLUGIN_DIR/bridge_rpc_probe.py" "$RUNTIME_DIR/bridge_rpc_probe.py" "bridge_rpc_probe.py"
compare_required_file "$PLUGIN_DIR/linux_payload_manifest.json" "$RUNTIME_DIR/linux_payload_manifest.json" "linux_payload_manifest.json"
compare_required_file "$PLUGIN_DIR/ca-certificates.crt" "$RUNTIME_DIR/ca-certificates.crt" "ca-certificates.crt"
compare_required_file "$PLUGIN_DIR/slicer_base64.cer" "$RUNTIME_DIR/slicer_base64.cer" "slicer_base64.cer"

for optional_file in liblive555.so libagora_rtc_sdk.so libagora-fdkaac.so; do
    if [[ -f "$PLUGIN_DIR/$optional_file" ]]; then
        compare_required_file "$PLUGIN_DIR/$optional_file" "$RUNTIME_DIR/$optional_file" "$optional_file"
    fi
done

LIMACTL=$(find_limactl || true)
if [[ -z "$LIMACTL" ]]; then
    echo "limactl not found" >&2
    exit 1
fi

INSTANCE="${PJARCZAK_MAC_LIMA_INSTANCE:-}"
if [[ -z "$INSTANCE" ]]; then
    INSTANCE=$(trim_file "$PLUGIN_DIR/pjarczak_lima_instance.txt" || true)
fi
if [[ -z "$INSTANCE" ]]; then
    echo "Lima instance name is not configured" >&2
    exit 1
fi

if ! "$LIMACTL" shell "$INSTANCE" -- /usr/bin/env true >/dev/null 2>&1; then
    echo "Lima instance '$INSTANCE' is not ready" >&2
    exit 1
fi

if [[ "$RUN_LINUX_BRIDGE_PROBE" -eq 1 ]]; then
    if [[ -z "$LINUX_BRIDGE_REPORT" ]]; then
        LINUX_BRIDGE_REPORT="$RUNTIME_DIR/linux_bridge_runtime_verify_report.json"
    fi
    "$LIMACTL" shell "$INSTANCE" -- /usr/bin/env \
        PJARCZAK_BAMBU_PLUGIN_DIR="$RUNTIME_DIR" \
        PJARCZAK_BAMBU_NETWORK_SO="$RUNTIME_DIR/libbambu_networking.so" \
        PJARCZAK_BAMBU_SOURCE_SO="$RUNTIME_DIR/libBambuSource.so" \
        python3 "$RUNTIME_DIR/verify_linux_bridge_runtime.py" \
            --runtime-dir "$RUNTIME_DIR" \
            --out "$LINUX_BRIDGE_REPORT"
fi

printf 'runtime ok
'
