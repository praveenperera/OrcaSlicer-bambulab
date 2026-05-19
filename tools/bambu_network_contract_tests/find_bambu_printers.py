#!/usr/bin/env python3
import argparse
import json
import socket
import time
from typing import Any


BAMBU_SSDP_TARGET = "urn:bambulab-com:device:3dprinter:1"
SSDP_MULTICAST = "239.255.255.250"
SSDP_BROADCAST = "255.255.255.255"
DISCOVERY_PORTS = (1990, 2021)


def parse_headers(packet: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in packet.splitlines()[1:]:
        if not line.strip():
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def header(headers: dict[str, str], key: str, default: str = "") -> str:
    value = headers.get(key.lower(), "")
    return value if value else default


def normalize_usn(usn: str) -> str:
    value = usn.removeprefix("uuid:")
    return value.split("::", 1)[0]


def ip_from_location(location: str) -> str:
    value = location.removeprefix("http://").removeprefix("https://")
    host = value.split("/", 1)[0]
    return host.rsplit(":", 1)[0] if ":" in host else host


def is_bambu_packet(headers: dict[str, str]) -> bool:
    target = header(headers, "nt") or header(headers, "st")
    return target == BAMBU_SSDP_TARGET or bool(header(headers, "devmodel.bambu.com"))


def device_from_packet(packet: str, remote_ip: str) -> dict[str, Any] | None:
    headers = parse_headers(packet)
    if not is_bambu_packet(headers):
        return None

    usn = header(headers, "usn")
    dev_id = normalize_usn(usn)
    if not dev_id:
        return None

    location = header(headers, "location")
    dev_ip = ip_from_location(location) if location else remote_ip
    return {
        "bind_state": header(headers, "devbind.bambu.com", "free"),
        "connect_type": header(headers, "devconnect.bambu.com", "lan"),
        "dev_id": dev_id,
        "dev_ip": dev_ip,
        "dev_name": header(headers, "devname.bambu.com", dev_id),
        "dev_signal": header(headers, "devsignal.bambu.com", "0"),
        "dev_type": header(headers, "devmodel.bambu.com"),
        "sec_link": header(headers, "devseclink.bambu.com", "secure"),
    }


def make_msearch_packet() -> bytes:
    return (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {SSDP_MULTICAST}:1990\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 1\r\n"
        f"ST: {BAMBU_SSDP_TARGET}\r\n"
        "\r\n"
    ).encode("utf-8")


def open_search_socket(timeout: float) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(timeout)
    sock.bind(("", 0))
    return sock


def send_search(sock: socket.socket) -> tuple[list[dict[str, Any]], list[str]]:
    packet = make_msearch_packet()
    sent_targets: list[dict[str, Any]] = []
    errors: list[str] = []
    for port in DISCOVERY_PORTS:
        for host in (SSDP_MULTICAST, SSDP_BROADCAST):
            try:
                sock.sendto(packet, (host, port))
                sent_targets.append({"host": host, "port": port})
            except OSError as error:
                errors.append(f"{host}:{port}: {error}")
    return sent_targets, errors


def collect_devices(sock: socket.socket, deadline: float) -> dict[str, dict[str, Any]]:
    devices: dict[str, dict[str, Any]] = {}
    while time.monotonic() < deadline:
        try:
            payload, remote = sock.recvfrom(8192)
        except socket.timeout:
            continue
        except OSError:
            break
        packet = payload.decode("utf-8", errors="replace")
        device = device_from_packet(packet, remote[0])
        if device:
            devices[device["dev_id"]] = device
    return devices


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover Bambu printers on the local LAN")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON only")
    args = parser.parse_args()

    with open_search_socket(timeout=min(max(args.timeout, 0.1), 1.0)) as sock:
        sent_targets, send_errors = send_search(sock)
        devices = collect_devices(sock, time.monotonic() + max(args.timeout, 0.1))

    result = {
        "ok": bool(devices),
        "send_errors": send_errors,
        "sent_targets": sent_targets,
        "devices": sorted(devices.values(), key=lambda item: (item["dev_name"], item["dev_id"])),
    }
    indent = None if args.json else 2
    print(json.dumps(result, indent=indent, sort_keys=True))
    return 0 if devices else 1


if __name__ == "__main__":
    raise SystemExit(main())
