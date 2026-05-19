#!/usr/bin/env python3
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
PUBLIC_PLUGIN_HEADER = ROOT / "src/slic3r/Utils/BBLNetworkPlugin.hpp"
PUBLIC_PLUGIN_LOADER = ROOT / "src/slic3r/Utils/BBLNetworkPlugin.cpp"
PUBLIC_FILE_TRANSFER_HEADER = ROOT / "src/slic3r/Utils/FileTransferUtils.hpp"
PUBLIC_SOURCE_HEADER = ROOT / "src/slic3r/GUI/Printer/BambuTunnel.h"
SHIM_SOURCE = ROOT / "tools/bambu_network_rust_plugin/shim/bambu_networking_shim.cpp"
SOURCE_SHIM_SOURCE = ROOT / "tools/bambu_network_rust_plugin/shim/bambu_source_shim.cpp"

TYPE_ALIASES = {
    "BBL::": "",
    "Slic3r::": "",
    "FtConnectionCallback": "void(*)(void*, int, int, const char*)",
    "FtStatusCallback": "void(*)(void*, int, int, int, const char*)",
    "FtResultCallback": "void(*)(void*, ft_job_result)",
    "FtMsgCallback": "void(*)(void*, ft_job_msg)",
    "FtTunnel": "FT_TunnelHandle",
    "FtJob": "FT_JobHandle",
    "FtJobResult": "ft_job_result",
    "FtJobMsg": "ft_job_msg",
    "std::uint32_t": "uint32_t",
    "ft_err": "int",
}


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//.*", "", text)


def split_top_level(value: str, separator: str) -> list[str]:
    items = []
    start = 0
    angle_depth = 0
    paren_depth = 0
    for index, ch in enumerate(value):
        if ch == "<":
            angle_depth += 1
        elif ch == ">" and angle_depth:
            angle_depth -= 1
        elif ch == "(":
            paren_depth += 1
        elif ch == ")" and paren_depth:
            paren_depth -= 1
        elif ch == separator and angle_depth == 0 and paren_depth == 0:
            items.append(value[start:index].strip())
            start = index + 1
    items.append(value[start:].strip())
    return items


def strip_parameter_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    value = re.sub(r"\s*([*&])\s*", r"\1 ", value).strip()
    if value in {"unsigned int", "unsigned long", "unsigned long long", "long long"}:
        return value
    match = re.match(r"(?P<type>.+?)\s+[A-Za-z_][A-Za-z0-9_]*$", value)
    if not match:
        return value

    candidate = match.group("type").strip()
    return candidate


def normalize_function_pointer_type(value: str) -> str | None:
    value = value.replace("FT_CALL", "")
    value = re.sub(r"\s+", " ", value.strip())
    match = re.match(r"(?P<return_type>.*?)\s*\(\s*\*\s*\)\s*\((?P<params>.*)\)$", value)
    if not match:
        return None

    return_type = normalize_type(match.group("return_type"), strip_name=False)
    params = match.group("params").strip()
    if not params or params == "void":
        normalized_params = []
    else:
        normalized_params = [normalize_type(param) for param in split_top_level(params, ",")]
    return f"{return_type}(*)({', '.join(normalized_params)})"


def normalize_type(value: str, *, strip_name: bool = True) -> str:
    function_pointer = normalize_function_pointer_type(value)
    if function_pointer is not None:
        return function_pointer

    if strip_name:
        value = strip_parameter_name(value)
    for old, new in TYPE_ALIASES.items():
        if old.endswith("::"):
            value = value.replace(old, new)
        else:
            value = re.sub(rf"\b{re.escape(old)}\b", new, value)
    value = re.sub(r"\b((?:unsigned\s+)?[A-Za-z_][A-Za-z0-9_:]*)\s+const\s*([*&])", r"const \1\2", value)
    value = re.sub(r"\bconst\s+", "const ", value)
    value = re.sub(r"\s*([*&])\s*", r"\1", value)
    value = re.sub(r"\s*,\s*", ", ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_signature(return_type: str, params: str) -> str:
    return_type = normalize_type(return_type, strip_name=False)
    params = params.strip()
    if not params or params == "void":
        normalized_params = []
    else:
        normalized_params = [normalize_type(param) for param in split_top_level(params, ",")]
    return f"{return_type}({', '.join(normalized_params)})"


def public_typedef_signatures(text: str) -> dict[str, str]:
    signatures = {}
    typedef_pattern = re.compile(
        r"typedef\s+(?P<return_type>.*?)\s*\(\s*\*\s*(?P<name>func_[A-Za-z0-9_]+)\s*\)\s*"
        r"\((?P<params>.*?)\)\s*;",
        flags=re.S,
    )
    for match in typedef_pattern.finditer(text):
        name = match.group("name")
        signatures[name] = normalize_signature(match.group("return_type"), match.group("params"))
    return signatures


def loaded_symbol_aliases(text: str) -> dict[str, str]:
    aliases = {}
    load_pattern = re.compile(
        r"reinterpret_cast<(?P<alias>func_[A-Za-z0-9_]+)>\s*"
        r"\(\s*get_function\(\"(?P<symbol>bambu_network_[A-Za-z0-9_]+)\"\)\s*\)"
    )
    for match in load_pattern.finditer(text):
        aliases[match.group("symbol")] = match.group("alias")
    return aliases


def shim_signatures(text: str) -> dict[str, str]:
    signatures = {}
    export_pattern = re.compile(
        r'^\s*extern\s+"C"\s+(?P<return_type>[^\n]*?)\s+'
        r"(?P<symbol>bambu_network_[A-Za-z0-9_]+)\s*"
        r"\((?P<params>.*?)\)\s*(?:\{|;)",
        flags=re.S | re.M,
    )
    for match in export_pattern.finditer(text):
        symbol = match.group("symbol")
        signatures[symbol] = normalize_signature(match.group("return_type"), match.group("params"))
    return signatures


def public_ft_signatures(text: str) -> dict[str, str]:
    signatures = {}
    alias_pattern = re.compile(r"^\s*using\s+(?P<name>fn_ft_[A-Za-z0-9_]+)\s*=\s*(?P<body>.*?)\s*;\s*$", flags=re.M)
    signature_pattern = re.compile(r"(?P<return_type>.*?)\(\s*FT_CALL\s*\*\s*\)\s*\((?P<params>.*)\)$")
    for match in alias_pattern.finditer(text):
        name = match.group("name")
        signature = signature_pattern.match(match.group("body").strip())
        if not signature:
            continue
        symbol = name.removeprefix("fn_")
        signatures[symbol] = normalize_signature(signature.group("return_type"), signature.group("params"))
    return signatures


def ft_shim_signatures(text: str) -> dict[str, str]:
    signatures = {}
    export_pattern = re.compile(
        r'^\s*extern\s+"C"\s+(?P<return_type>[^\n]*?)\s+'
        r"(?P<symbol>ft_[A-Za-z0-9_]+)\s*"
        r"\((?P<params>.*?)\)\s*(?:\{|;)",
        flags=re.S | re.M,
    )
    for match in export_pattern.finditer(text):
        signatures[match.group("symbol")] = normalize_signature(match.group("return_type"), match.group("params"))
    return signatures


def public_source_signatures(text: str) -> dict[str, str]:
    signatures = {}
    source_pattern = re.compile(
        r"^\s*BAMBU_EXPORT\s+(?P<return_type>[^\n]*?)\s+BAMBU_FUNC\((?P<symbol>Bambu_[A-Za-z0-9_]+)\)\s*"
        r"\((?P<params>.*?)\)\s*;",
        flags=re.S | re.M,
    )
    for match in source_pattern.finditer(text):
        signatures[match.group("symbol")] = normalize_signature(match.group("return_type"), match.group("params"))
    return signatures


def source_shim_signatures(text: str) -> dict[str, str]:
    signatures = {}
    export_pattern = re.compile(
        r'^\s*extern\s+"C"\s+(?P<return_type>[^\n]*?)\s+'
        r"(?P<symbol>Bambu_[A-Za-z0-9_]+)\s*"
        r"\((?P<params>.*?)\)\s*(?:\{|;)",
        flags=re.S | re.M,
    )
    for match in export_pattern.finditer(text):
        signatures[match.group("symbol")] = normalize_signature(match.group("return_type"), match.group("params"))
    return signatures


def main() -> int:
    public_signatures = public_typedef_signatures(PUBLIC_PLUGIN_HEADER.read_text(encoding="utf-8", errors="ignore"))
    symbol_aliases = loaded_symbol_aliases(PUBLIC_PLUGIN_LOADER.read_text(encoding="utf-8", errors="ignore"))
    replacement_signatures = shim_signatures(SHIM_SOURCE.read_text(encoding="utf-8", errors="ignore"))
    public_ft = public_ft_signatures(PUBLIC_FILE_TRANSFER_HEADER.read_text(encoding="utf-8", errors="ignore"))
    replacement_ft = ft_shim_signatures(SHIM_SOURCE.read_text(encoding="utf-8", errors="ignore"))
    public_source = public_source_signatures(PUBLIC_SOURCE_HEADER.read_text(encoding="utf-8", errors="ignore"))
    replacement_source = source_shim_signatures(SOURCE_SHIM_SOURCE.read_text(encoding="utf-8", errors="ignore"))

    failures = []
    network_checked = 0
    for symbol, alias in sorted(symbol_aliases.items()):
        public_signature = public_signatures.get(alias)
        replacement_signature = replacement_signatures.get(symbol)
        if public_signature is None:
            failures.append(f"{symbol}: loader alias {alias} is missing from {PUBLIC_PLUGIN_HEADER}")
            continue
        if replacement_signature is None:
            failures.append(f"{symbol}: replacement shim does not define an exported function")
            continue
        network_checked += 1
        if public_signature != replacement_signature:
            failures.append(
                f"{symbol}: signature mismatch\n"
                f"  public {alias}: {public_signature}\n"
                f"  shim:          {replacement_signature}"
            )

    ft_checked = 0
    for symbol, public_signature in sorted(public_ft.items()):
        replacement_signature = replacement_ft.get(symbol)
        if replacement_signature is None:
            failures.append(f"{symbol}: replacement shim does not define an exported function")
            continue
        ft_checked += 1
        if public_signature != replacement_signature:
            failures.append(
                f"{symbol}: file-transfer signature mismatch\n"
                f"  public: {public_signature}\n"
                f"  shim:   {replacement_signature}"
            )

    source_checked = 0
    for symbol, public_signature in sorted(public_source.items()):
        replacement_signature = replacement_source.get(symbol)
        if replacement_signature is None:
            failures.append(f"{symbol}: replacement source shim does not define an exported function")
            continue
        source_checked += 1
        if public_signature != replacement_signature:
            failures.append(
                f"{symbol}: source signature mismatch\n"
                f"  public: {public_signature}\n"
                f"  shim:   {replacement_signature}"
            )

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1

    print(
        "C++ shim signatures match "
        f"{network_checked} Orca loader typedefs, {ft_checked} file-transfer typedefs, "
        f"and {source_checked} BambuSource prototypes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
