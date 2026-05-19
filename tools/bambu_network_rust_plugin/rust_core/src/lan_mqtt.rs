use std::fs::File;
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::Duration;

use rumqttc::{
    Client, ConnectReturnCode, Event, MqttOptions, Packet, QoS, RecvTimeoutError, TlsConfiguration,
    Transport,
};
use rustls::client::danger::{HandshakeSignatureValid, ServerCertVerified, ServerCertVerifier};
use rustls::pki_types::{CertificateDer, ServerName, UnixTime};
use rustls::{ClientConfig, DigitallySignedStruct, Error as RustlsError, SignatureScheme};
use suppaftp::{FtpStream, RustlsConnector, RustlsFtpStream};

use crate::discovery::DiscoverySession;
use crate::event::EventSink;
use crate::protocol::LocalMqttPublish;
use crate::transport::{
    FileUploadRequest, LanTransport, PrinterConnectionRequest, TransportError, TransportResult,
};

const MQTT_TLS_PORT: u16 = 8883;
const MQTT_TCP_PORT: u16 = 1883;
const FTPS_IMPLICIT_PORT: u16 = 990;
const FTP_PORT: u16 = 21;
const CONNECT_TIMEOUT: Duration = Duration::from_secs(5);
const KEEP_ALIVE: Duration = Duration::from_secs(15);

#[derive(Default)]
pub(crate) struct RumqttcLanTransport {
    session: Option<MqttSession>,
    discovery: Option<DiscoverySession>,
}

impl RumqttcLanTransport {
    pub(crate) fn new() -> Self {
        Self::default()
    }
}

impl LanTransport for RumqttcLanTransport {
    fn start_discovery(
        &mut self,
        start: bool,
        _sending: bool,
        event_sink: &EventSink,
    ) -> TransportResult<bool> {
        if !start {
            if let Some(mut discovery) = self.discovery.take() {
                discovery.stop();
            }
            return Ok(true);
        }

        if self.discovery.is_some() {
            return Ok(true);
        }

        let Some(discovery) = DiscoverySession::start(*event_sink) else {
            return Ok(false);
        };

        self.discovery = Some(discovery);
        Ok(true)
    }

    fn connect_printer(
        &mut self,
        request: PrinterConnectionRequest,
        event_sink: &EventSink,
    ) -> TransportResult<()> {
        let options = mqtt_options(&request)?;
        let report_topic = request
            .report_topic()
            .map_err(|_| TransportError::Connect)?;
        let (client, mut connection) = Client::new(options, 10);
        client
            .subscribe(report_topic.clone(), QoS::AtLeastOnce)
            .map_err(|_| TransportError::Connect)?;

        wait_for_connect(&mut connection)?;
        event_sink.emit_local_connect(0, request.dev_id(), "0");
        event_sink.emit_printer_connected(request.dev_id());

        let dev_id = request.dev_id().to_string();
        let event_sink = *event_sink;
        let event_thread = thread::spawn(move || {
            for event in connection.iter() {
                let Ok(event) = event else {
                    break;
                };
                if let Event::Incoming(Packet::Publish(publish)) = event {
                    if publish.topic == report_topic {
                        let payload = String::from_utf8_lossy(&publish.payload);
                        event_sink.emit_local_message(&dev_id, &payload);
                    }
                }
            }
        });

        self.session = Some(MqttSession {
            client,
            event_thread: Some(event_thread),
        });
        Ok(())
    }

    fn disconnect_printer(&mut self, _event_sink: &EventSink) -> TransportResult<()> {
        let Some(mut session) = self.session.take() else {
            return Ok(());
        };
        session.disconnect();
        Ok(())
    }

    fn send_cloud_message(
        &mut self,
        _message: &crate::protocol::OutboundMessage,
        _event_sink: &EventSink,
    ) -> TransportResult<()> {
        Err(TransportError::Connect)
    }

    fn send_local_message(
        &mut self,
        publish: &LocalMqttPublish,
        _event_sink: &EventSink,
    ) -> TransportResult<()> {
        let Some(session) = &self.session else {
            return Err(TransportError::Publish);
        };

        session
            .client
            .publish(
                publish.request_topic(),
                qos_from_i32(publish.qos()),
                false,
                publish.payload().as_bytes(),
            )
            .map_err(|_| TransportError::Publish)
    }

    fn upload_file(
        &mut self,
        request: &FileUploadRequest,
        _event_sink: &EventSink,
    ) -> TransportResult<()> {
        upload_file_to_printer(request)
    }
}

impl Drop for RumqttcLanTransport {
    fn drop(&mut self) {
        if let Some(mut discovery) = self.discovery.take() {
            discovery.stop();
        }
    }
}

struct MqttSession {
    client: Client,
    event_thread: Option<JoinHandle<()>>,
}

impl MqttSession {
    fn disconnect(&mut self) {
        let _ = self.client.disconnect();
        if let Some(event_thread) = self.event_thread.take() {
            let _ = event_thread.join();
        }
    }
}

impl Drop for MqttSession {
    fn drop(&mut self) {
        self.disconnect();
    }
}

fn mqtt_options(request: &PrinterConnectionRequest) -> TransportResult<MqttOptions> {
    if request.dev_ip().is_empty() || request.dev_id().is_empty() || request.password().is_empty() {
        return Err(TransportError::Connect);
    }

    let port = if request.use_ssl() {
        MQTT_TLS_PORT
    } else {
        MQTT_TCP_PORT
    };
    let client_id = format!("orca-rust-{}", request.dev_id());
    let mut options = MqttOptions::new(client_id, request.dev_ip(), port);
    options.set_keep_alive(KEEP_ALIVE);
    options.set_clean_session(true);
    options.set_credentials(request.username(), request.password());
    options.set_max_packet_size(512 * 1024, 512 * 1024);

    if request.use_ssl() {
        options.set_transport(Transport::tls_with_config(TlsConfiguration::Rustls(
            Arc::new(insecure_rustls_client_config()),
        )));
    }

    Ok(options)
}

fn wait_for_connect(connection: &mut rumqttc::Connection) -> TransportResult<()> {
    loop {
        match connection.recv_timeout(CONNECT_TIMEOUT) {
            Ok(Ok(Event::Incoming(Packet::ConnAck(connack)))) => {
                return match connack.code {
                    ConnectReturnCode::Success => Ok(()),
                    _ => Err(TransportError::Connect),
                };
            }
            Ok(Ok(_)) => continue,
            Ok(Err(_)) | Err(RecvTimeoutError::Timeout) | Err(RecvTimeoutError::Disconnected) => {
                return Err(TransportError::Connect);
            }
        }
    }
}

fn qos_from_i32(qos: i32) -> QoS {
    match qos {
        1 => QoS::AtLeastOnce,
        2 => QoS::ExactlyOnce,
        _ => QoS::AtMostOnce,
    }
}

fn upload_file_to_printer(request: &FileUploadRequest) -> TransportResult<()> {
    if request.dev_ip().is_empty()
        || request.username().is_empty()
        || request.password().is_empty()
        || request.remote_name().is_empty()
    {
        return Err(TransportError::Upload);
    }

    let mut file = File::open(request.local_path()).map_err(|_| TransportError::Upload)?;
    if request.use_ssl() {
        let mut stream = implicit_ftps_stream(request)?;
        stream
            .put_file(request.remote_name(), &mut file)
            .map_err(|_| TransportError::Upload)?;
        let _ = stream.quit();
        return Ok(());
    }

    let mut stream = ftp_stream(request)?;
    stream
        .put_file(request.remote_name(), &mut file)
        .map_err(|_| TransportError::Upload)?;
    let _ = stream.quit();
    Ok(())
}

fn implicit_ftps_stream(request: &FileUploadRequest) -> TransportResult<RustlsFtpStream> {
    let mut stream = RustlsFtpStream::connect_secure_implicit(
        (request.dev_ip(), FTPS_IMPLICIT_PORT),
        RustlsConnector::from(Arc::new(insecure_rustls_client_config())),
        request.dev_ip(),
    )
    .map_err(|_| TransportError::Upload)?;
    stream
        .login(request.username(), request.password())
        .map_err(|_| TransportError::Upload)?;
    Ok(stream)
}

pub(crate) fn insecure_rustls_client_config() -> ClientConfig {
    ClientConfig::builder()
        .dangerous()
        .with_custom_certificate_verifier(Arc::new(AcceptAnyServerCert))
        .with_no_client_auth()
}

#[derive(Debug)]
struct AcceptAnyServerCert;

impl ServerCertVerifier for AcceptAnyServerCert {
    fn verify_server_cert(
        &self,
        _end_entity: &CertificateDer<'_>,
        _intermediates: &[CertificateDer<'_>],
        _server_name: &ServerName<'_>,
        _ocsp_response: &[u8],
        _now: UnixTime,
    ) -> Result<ServerCertVerified, RustlsError> {
        Ok(ServerCertVerified::assertion())
    }

    fn verify_tls12_signature(
        &self,
        _message: &[u8],
        _cert: &CertificateDer<'_>,
        _dss: &DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, RustlsError> {
        Ok(HandshakeSignatureValid::assertion())
    }

    fn verify_tls13_signature(
        &self,
        _message: &[u8],
        _cert: &CertificateDer<'_>,
        _dss: &DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, RustlsError> {
        Ok(HandshakeSignatureValid::assertion())
    }

    fn supported_verify_schemes(&self) -> Vec<SignatureScheme> {
        vec![
            SignatureScheme::ECDSA_NISTP256_SHA256,
            SignatureScheme::ECDSA_NISTP384_SHA384,
            SignatureScheme::ED25519,
            SignatureScheme::RSA_PSS_SHA256,
            SignatureScheme::RSA_PSS_SHA384,
            SignatureScheme::RSA_PSS_SHA512,
            SignatureScheme::RSA_PKCS1_SHA256,
            SignatureScheme::RSA_PKCS1_SHA384,
            SignatureScheme::RSA_PKCS1_SHA512,
        ]
    }
}

fn ftp_stream(request: &FileUploadRequest) -> TransportResult<FtpStream> {
    let mut stream =
        FtpStream::connect((request.dev_ip(), FTP_PORT)).map_err(|_| TransportError::Upload)?;
    stream
        .login(request.username(), request.password())
        .map_err(|_| TransportError::Upload)?;
    Ok(stream)
}

#[cfg(test)]
mod tests {
    use super::{
        mqtt_options, qos_from_i32, FTPS_IMPLICIT_PORT, FTP_PORT, MQTT_TCP_PORT, MQTT_TLS_PORT,
    };
    use crate::transport::{FileUploadRequest, PrinterConnectionRequest};
    use rumqttc::QoS;

    #[test]
    fn builds_tls_mqtt_options_from_printer_request() {
        let request = PrinterConnectionRequest::new(
            "SERIAL123".to_string(),
            "192.0.2.10".to_string(),
            "bblp".to_string(),
            "12345678".to_string(),
            true,
        );

        let options = mqtt_options(&request).unwrap();

        assert_eq!(
            options.broker_address(),
            ("192.0.2.10".to_string(), MQTT_TLS_PORT)
        );
        assert_eq!(options.client_id(), "orca-rust-SERIAL123");
        assert_eq!(options.credentials().unwrap().username, "bblp");
    }

    #[test]
    fn builds_tcp_mqtt_options_when_ssl_is_disabled() {
        let request = PrinterConnectionRequest::new(
            "SERIAL123".to_string(),
            "192.0.2.10".to_string(),
            "bblp".to_string(),
            "12345678".to_string(),
            false,
        );

        let options = mqtt_options(&request).unwrap();

        assert_eq!(
            options.broker_address(),
            ("192.0.2.10".to_string(), MQTT_TCP_PORT)
        );
    }

    #[test]
    fn rejects_missing_connection_secrets() {
        let request = PrinterConnectionRequest::new(
            "SERIAL123".to_string(),
            "192.0.2.10".to_string(),
            "bblp".to_string(),
            String::new(),
            true,
        );

        assert!(mqtt_options(&request).is_err());
    }

    #[test]
    fn maps_qos_values() {
        assert_eq!(qos_from_i32(0), QoS::AtMostOnce);
        assert_eq!(qos_from_i32(1), QoS::AtLeastOnce);
        assert_eq!(qos_from_i32(2), QoS::ExactlyOnce);
        assert_eq!(qos_from_i32(99), QoS::AtMostOnce);
    }

    #[test]
    fn file_upload_request_uses_bambu_ports() {
        let request = FileUploadRequest::new(
            "192.0.2.10".to_string(),
            "bblp".to_string(),
            "12345678".to_string(),
            true,
            "/tmp/model.3mf".to_string(),
            "model.3mf".to_string(),
        );

        assert_eq!(request.dev_ip(), "192.0.2.10");
        assert_eq!(request.remote_url(), "ftp:///model.3mf");
        assert_eq!(FTPS_IMPLICIT_PORT, 990);
        assert_eq!(FTP_PORT, 21);
    }
}
