#!/usr/bin/env python3
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
PUBLIC_HEADER = ROOT / "src/slic3r/Utils/bambu_networking.hpp"
PROJECT_TASK_HEADER = ROOT / "src/libslic3r/ProjectTask.hpp"
MIRROR_HEADER = ROOT / "tools/bambu_network_rust_plugin/shim/bambu_networking_abi.hpp"

STRUCTS = [
    "detectResult",
    "PrintParams",
    "TaskQueryParams",
    "PublishParams",
]

ALIASES = [
    "OnUserLoginFn",
    "OnPrinterConnectedFn",
    "OnLocalConnectedFn",
    "OnServerConnectedFn",
    "OnMessageFn",
    "OnHttpErrorFn",
    "GetCountryCodeFn",
    "GetSubscribeFailureFn",
    "OnUpdateStatusFn",
    "WasCancelledFn",
    "OnWaitFn",
    "OnMsgArrivedFn",
    "QueueOnMainFn",
    "ProgressFn",
    "LoginFn",
    "ResultFn",
    "CancelFn",
    "CheckFn",
    "OnServerErrFn",
    "OnGetSubTaskFn",
]

ERROR_CONSTANTS = [
    "BAMBU_NETWORK_ERR_INVALID_HANDLE",
    "BAMBU_NETWORK_ERR_CONNECT_FAILED",
]


def extract_struct(text: str, name: str) -> str:
    match = re.search(rf"struct\s+{re.escape(name)}\s*\{{(?P<body>.*?)\n\}};", text, re.S)
    if not match:
        raise ValueError(f"missing struct {name}")
    return normalize(match.group("body"))


def extract_public_alias(text: str, name: str) -> str:
    match = re.search(rf"typedef\s+(?P<body>[^;]+?)\s+{re.escape(name)}\s*;", text)
    if not match:
        raise ValueError(f"missing typedef {name}")
    return normalize_alias(match.group("body"))


def extract_mirror_alias(text: str, name: str) -> str:
    match = re.search(rf"using\s+{re.escape(name)}\s*=\s*(?P<body>.*?)\s*;", text, re.S)
    if not match:
        raise ValueError(f"missing using alias {name}")
    return normalize_alias(match.group("body"))


def extract_public_define(text: str, name: str) -> str:
    match = re.search(rf"^\s*#define\s+{re.escape(name)}\s+(?P<value>\S+)", text, re.M)
    if not match:
        raise ValueError(f"missing define {name}")
    return match.group("value").strip()


def extract_mirror_constant(text: str, name: str) -> str:
    match = re.search(rf"constexpr\s+int\s+{re.escape(name)}\s*=\s*(?P<value>[^;]+);", text)
    if not match:
        raise ValueError(f"missing mirror constant {name}")
    return match.group("value").strip()


def normalize(body: str) -> str:
    lines = []
    for raw_line in body.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line:
            continue
        line = re.sub(r"\s+", " ", line)
        line = line.replace(" {", "{").replace(" }", "}")
        lines.append(line)
    return "\n".join(lines)


def normalize_alias(body: str) -> str:
    return re.sub(r"\s+", " ", body).strip()


def main() -> int:
    public_text = PUBLIC_HEADER.read_text(encoding="utf-8", errors="ignore")
    project_task_text = PROJECT_TASK_HEADER.read_text(encoding="utf-8", errors="ignore")
    public_alias_text = public_text + "\n" + project_task_text
    mirror_text = MIRROR_HEADER.read_text(encoding="utf-8", errors="ignore")

    failures = []
    for name in STRUCTS:
        public_body = extract_struct(public_text, name)
        mirror_body = extract_struct(mirror_text, name)
        if public_body != mirror_body:
            failures.append((f"struct {name}", public_body, mirror_body))

    for name in ALIASES:
        public_alias = extract_public_alias(public_alias_text, name)
        mirror_alias = extract_mirror_alias(mirror_text, name)
        if public_alias != mirror_alias:
            failures.append((f"alias {name}", public_alias, mirror_alias))

    for name in ERROR_CONSTANTS:
        public_value = extract_public_define(public_text, name)
        mirror_value = extract_mirror_constant(mirror_text, name)
        if public_value != mirror_value:
            failures.append((f"constant {name}", public_value, mirror_value))

    if not failures:
        print("ABI mirror matches public plugin structs, aliases, and constants")
        return 0

    for name, public_body, mirror_body in failures:
        print(f"ABI mirror mismatch: {name}")
        print("public:")
        print(public_body)
        print("mirror:")
        print(mirror_body)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
