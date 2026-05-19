use std::io::{ErrorKind, Read, Write};
use std::net::{SocketAddr, TcpStream, ToSocketAddrs};
use std::os::raw::{c_char, c_uchar};
use std::slice;
use std::sync::Arc;
use std::time::{Duration, Instant};

use rustls::pki_types::ServerName;
use rustls::{ClientConnection, StreamOwned};

use crate::{lan_mqtt, read_string};

const BAMBU_SUCCESS: i32 = 0;
const BAMBU_STREAM_END: i32 = 1;
const BAMBU_WOULD_BLOCK: i32 = 2;
const SOURCE_TLS_ERROR: i32 = -1;

struct SourceTlsStream(StreamOwned<ClientConnection, TcpStream>);

fn timeout_duration(timeout_ms: i32) -> Duration {
    Duration::from_millis(timeout_ms.max(1) as u64)
}

fn socket_addr(host: &str, port: &str) -> Option<SocketAddr> {
    format!("{host}:{port}").to_socket_addrs().ok()?.next()
}

fn connect_source_tls(host: String, port: String, timeout_ms: i32) -> Option<SourceTlsStream> {
    if host.is_empty() || port.is_empty() {
        return None;
    }

    let timeout = timeout_duration(timeout_ms);
    let address = socket_addr(&host, &port)?;
    let socket = TcpStream::connect_timeout(&address, timeout).ok()?;
    socket.set_read_timeout(Some(timeout)).ok()?;
    socket.set_write_timeout(Some(timeout)).ok()?;

    let config = Arc::new(lan_mqtt::insecure_rustls_client_config());
    let server_name = ServerName::try_from(host).ok()?;
    let connection = ClientConnection::new(config, server_name).ok()?;
    let mut stream = StreamOwned::new(connection, socket);
    let deadline = Instant::now() + timeout;
    while stream.conn.is_handshaking() {
        if Instant::now() >= deadline {
            return None;
        }
        stream.conn.complete_io(&mut stream.sock).ok()?;
    }

    stream
        .sock
        .set_read_timeout(Some(Duration::from_millis(20)))
        .ok()?;
    stream
        .sock
        .set_write_timeout(Some(Duration::from_secs(2)))
        .ok()?;
    Some(SourceTlsStream(stream))
}

#[no_mangle]
pub extern "C" fn brs_source_tls_connect(
    host: *const c_char,
    port: *const c_char,
    timeout_ms: i32,
) -> usize {
    match connect_source_tls(read_string(host), read_string(port), timeout_ms) {
        Some(stream) => Box::into_raw(Box::new(stream)) as usize,
        None => 0,
    }
}

#[no_mangle]
pub unsafe extern "C" fn brs_source_tls_send(
    handle: usize,
    data: *const c_uchar,
    len: usize,
) -> i32 {
    if handle == 0 || (data.is_null() && len > 0) {
        return SOURCE_TLS_ERROR;
    }

    let stream = &mut *(handle as *mut SourceTlsStream);
    let payload = if len == 0 {
        &[]
    } else {
        slice::from_raw_parts(data, len)
    };
    match stream.0.write_all(payload).and_then(|_| stream.0.flush()) {
        Ok(()) => BAMBU_SUCCESS,
        Err(error) if matches!(error.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => {
            BAMBU_WOULD_BLOCK
        }
        Err(_) => SOURCE_TLS_ERROR,
    }
}

#[no_mangle]
pub unsafe extern "C" fn brs_source_tls_recv(
    handle: usize,
    data: *mut c_uchar,
    capacity: usize,
    bytes_read: *mut usize,
) -> i32 {
    if !bytes_read.is_null() {
        *bytes_read = 0;
    }
    if handle == 0 || data.is_null() || capacity == 0 {
        return SOURCE_TLS_ERROR;
    }

    let stream = &mut *(handle as *mut SourceTlsStream);
    let buffer = slice::from_raw_parts_mut(data, capacity);
    match stream.0.read(buffer) {
        Ok(0) => BAMBU_STREAM_END,
        Ok(count) => {
            if !bytes_read.is_null() {
                *bytes_read = count;
            }
            BAMBU_SUCCESS
        }
        Err(error) if matches!(error.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => {
            BAMBU_WOULD_BLOCK
        }
        Err(_) => SOURCE_TLS_ERROR,
    }
}

#[no_mangle]
pub extern "C" fn brs_source_tls_close(handle: usize) {
    if handle == 0 {
        return;
    }

    unsafe {
        drop(Box::from_raw(handle as *mut SourceTlsStream));
    }
}
