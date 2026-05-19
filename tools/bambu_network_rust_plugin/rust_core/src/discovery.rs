use std::collections::{HashMap, HashSet};
use std::io;
use std::net::{IpAddr, Ipv4Addr, SocketAddr, SocketAddrV4, UdpSocket};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use serde_json::json;

use crate::event::EventSink;

const BAMBU_SSDP_TARGET: &str = "urn:bambulab-com:device:3dprinter:1";
const SSDP_MULTICAST: Ipv4Addr = Ipv4Addr::new(239, 255, 255, 250);
const DISCOVERY_PORTS: [u16; 2] = [1990, 2021];
const READ_TIMEOUT: Duration = Duration::from_millis(250);

pub(crate) struct DiscoverySession {
    running: Arc<AtomicBool>,
    threads: Vec<JoinHandle<()>>,
}

impl DiscoverySession {
    pub(crate) fn start(event_sink: EventSink) -> Option<Self> {
        let sockets = discovery_sockets();
        if sockets.is_empty() {
            return None;
        }

        let running = Arc::new(AtomicBool::new(true));
        let seen_devices = Arc::new(Mutex::new(HashSet::new()));
        let threads = sockets
            .into_iter()
            .map(|socket| {
                let running = Arc::clone(&running);
                let seen_devices = Arc::clone(&seen_devices);
                thread::spawn(move || {
                    listen_for_discovery(socket, running, seen_devices, event_sink)
                })
            })
            .collect();

        Some(Self { running, threads })
    }

    pub(crate) fn stop(&mut self) {
        self.running.store(false, Ordering::Relaxed);
        for thread in self.threads.drain(..) {
            let _ = thread.join();
        }
    }
}

impl Drop for DiscoverySession {
    fn drop(&mut self) {
        self.stop();
    }
}

fn discovery_sockets() -> Vec<UdpSocket> {
    DISCOVERY_PORTS
        .into_iter()
        .filter_map(|port| discovery_socket(port).ok())
        .collect()
}

fn discovery_socket(port: u16) -> io::Result<UdpSocket> {
    let socket = UdpSocket::bind(SocketAddrV4::new(Ipv4Addr::UNSPECIFIED, port))?;
    socket.set_read_timeout(Some(READ_TIMEOUT))?;
    let _ = socket.join_multicast_v4(&SSDP_MULTICAST, &Ipv4Addr::UNSPECIFIED);
    Ok(socket)
}

fn listen_for_discovery(
    socket: UdpSocket,
    running: Arc<AtomicBool>,
    seen_devices: Arc<Mutex<HashSet<String>>>,
    event_sink: EventSink,
) {
    let mut buffer = [0_u8; 4096];

    while running.load(Ordering::Relaxed) {
        match socket.recv_from(&mut buffer) {
            Ok((size, remote)) => {
                let packet = String::from_utf8_lossy(&buffer[..size]);
                if let Some((dev_id, payload)) = discovery_payload(&packet, remote) {
                    if should_emit_device(&seen_devices, &dev_id) {
                        event_sink.emit_ssdp(&payload);
                    }
                }
            }
            Err(error)
                if matches!(
                    error.kind(),
                    io::ErrorKind::WouldBlock
                        | io::ErrorKind::TimedOut
                        | io::ErrorKind::Interrupted
                ) => {}
            Err(_) => break,
        }
    }
}

fn discovery_payload(packet: &str, remote: SocketAddr) -> Option<(String, String)> {
    let headers = parse_headers(packet);
    if !is_bambu_discovery(&headers) {
        return None;
    }

    let dev_id = header(&headers, "usn")?;
    let dev_ip = discovery_ip(header(&headers, "location"), remote.ip())?;
    let dev_name = header(&headers, "devname.bambu.com").unwrap_or(dev_id);
    let dev_type = header(&headers, "devmodel.bambu.com").unwrap_or_default();
    let dev_signal = header(&headers, "devsignal.bambu.com").unwrap_or("0");
    let connect_type = header(&headers, "devconnect.bambu.com").unwrap_or("lan");
    let bind_state = header(&headers, "devbind.bambu.com").unwrap_or("free");
    let sec_link = header(&headers, "devseclink.bambu.com").unwrap_or("secure");

    let normalized_dev_id = normalize_usn(dev_id).to_string();
    let payload = json!({
        "bind_state": bind_state,
        "connect_type": connect_type,
        "connection_name": "",
        "dev_id": normalized_dev_id,
        "dev_ip": dev_ip,
        "dev_name": dev_name,
        "dev_signal": dev_signal,
        "dev_type": dev_type,
        "dev_version": "",
        "sec_link": sec_link,
    });

    serde_json::to_string(&payload)
        .ok()
        .map(|payload| (normalized_dev_id, payload))
}

fn should_emit_device(seen_devices: &Mutex<HashSet<String>>, dev_id: &str) -> bool {
    let Ok(mut seen_devices) = seen_devices.lock() else {
        return false;
    };

    seen_devices.insert(dev_id.to_string())
}

fn parse_headers(packet: &str) -> HashMap<String, String> {
    packet
        .lines()
        .skip(1)
        .take_while(|line| !line.trim().is_empty())
        .filter_map(|line| line.split_once(':'))
        .map(|(key, value)| (key.trim().to_ascii_lowercase(), value.trim().to_string()))
        .collect()
}

fn is_bambu_discovery(headers: &HashMap<String, String>) -> bool {
    header(headers, "nt")
        .or_else(|| header(headers, "st"))
        .is_some_and(|target| target == BAMBU_SSDP_TARGET)
        || headers.contains_key("devmodel.bambu.com")
}

fn header<'a>(headers: &'a HashMap<String, String>, key: &str) -> Option<&'a str> {
    headers
        .get(key)
        .map(String::as_str)
        .filter(|value| !value.is_empty())
}

fn discovery_ip(location: Option<&str>, fallback: IpAddr) -> Option<String> {
    location
        .and_then(ip_from_location)
        .or_else(|| match fallback {
            IpAddr::V4(ip) if !ip.is_unspecified() => Some(ip.to_string()),
            IpAddr::V6(ip) if !ip.is_unspecified() => Some(ip.to_string()),
            _ => None,
        })
}

fn ip_from_location(location: &str) -> Option<String> {
    let without_scheme = location
        .strip_prefix("http://")
        .or_else(|| location.strip_prefix("https://"))
        .unwrap_or(location);
    let host = without_scheme.split('/').next().unwrap_or(without_scheme);
    let host = host.rsplit_once(':').map(|(host, _)| host).unwrap_or(host);

    if host.is_empty() {
        return None;
    }

    Some(host.to_string())
}

fn normalize_usn(usn: &str) -> &str {
    usn.strip_prefix("uuid:")
        .unwrap_or(usn)
        .split("::")
        .next()
        .unwrap_or(usn)
}

#[cfg(test)]
mod tests {
    use std::net::{IpAddr, Ipv4Addr, SocketAddr};

    use serde_json::Value;

    use super::{discovery_payload, ip_from_location};

    #[test]
    fn converts_bambu_ssdp_headers_to_orca_payload() {
        let packet = concat!(
            "NOTIFY * HTTP/1.1\r\n",
            "Host: 239.255.255.250:1990\r\n",
            "NT: urn:bambulab-com:device:3dprinter:1\r\n",
            "NTS: ssdp:alive\r\n",
            "USN: 0123456789ABCDEF\r\n",
            "Location: 192.0.2.10\r\n",
            "DevModel.bambu.com: 3DPrinter-X1-Carbon\r\n",
            "DevName.bambu.com: Lab Printer\r\n",
            "DevSignal.bambu.com: -61\r\n",
            "DevConnect.bambu.com: lan\r\n",
            "DevBind.bambu.com: free\r\n",
            "Devseclink.bambu.com: secure\r\n",
            "\r\n",
        );

        let (_, payload) = discovery_payload(packet, socket_addr()).unwrap();
        let payload: Value = serde_json::from_str(&payload).unwrap();

        assert_eq!(payload["dev_id"], "0123456789ABCDEF");
        assert_eq!(payload["dev_ip"], "192.0.2.10");
        assert_eq!(payload["dev_name"], "Lab Printer");
        assert_eq!(payload["dev_type"], "3DPrinter-X1-Carbon");
        assert_eq!(payload["dev_signal"], "-61");
        assert_eq!(payload["connect_type"], "lan");
        assert_eq!(payload["bind_state"], "free");
        assert_eq!(payload["connection_name"], "");
        assert_eq!(payload["dev_version"], "");
        assert_eq!(payload["sec_link"], "secure");
        assert!(payload.get("ssdp_version").is_none());
    }

    #[test]
    fn ignores_unrelated_ssdp_packets() {
        let packet = concat!(
            "NOTIFY * HTTP/1.1\r\n",
            "NT: urn:schemas-upnp-org:device:MediaServer:1\r\n",
            "USN: media\r\n",
            "\r\n",
        );

        assert!(discovery_payload(packet, socket_addr()).is_none());
    }

    #[test]
    fn uses_remote_ip_when_location_is_missing() {
        let packet = concat!(
            "NOTIFY * HTTP/1.1\r\n",
            "NT: urn:bambulab-com:device:3dprinter:1\r\n",
            "USN: SERIAL\r\n",
            "DevModel.bambu.com: A1\r\n",
            "\r\n",
        );

        let (_, payload) = discovery_payload(packet, socket_addr()).unwrap();
        let payload: Value = serde_json::from_str(&payload).unwrap();

        assert_eq!(payload["dev_ip"], "198.51.100.25");
        assert_eq!(payload["dev_name"], "SERIAL");
    }

    #[test]
    fn strips_url_parts_from_location() {
        assert_eq!(
            ip_from_location("http://192.0.2.20:8080/rootDesc.xml").unwrap(),
            "192.0.2.20",
        );
        assert_eq!(ip_from_location("192.0.2.21").unwrap(), "192.0.2.21");
    }

    fn socket_addr() -> SocketAddr {
        SocketAddr::new(IpAddr::V4(Ipv4Addr::new(198, 51, 100, 25)), 49152)
    }
}
