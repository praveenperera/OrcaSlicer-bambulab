use std::fs::File;
use std::io::Read;
use std::path::Path;

use md5::Digest;
use serde_json::{json, Value};

use crate::cloud::{self, CloudResponse};
use crate::event::EventSink;
use crate::lan_mqtt::RumqttcLanTransport;
use crate::protocol::{LocalMqttPublish, OutboundMessage, ProjectFileRequest};
use crate::transport::{FileUploadRequest, LanTransport, PrinterConnectionRequest, TransportError};
use crate::{
    ERR_CONNECT_FAILED, ERR_INVALID_RESULT, ERR_PRINT_LP_PUBLISH_MSG_FAILED,
    ERR_PRINT_LP_UPLOAD_FTP_FAILED, ERR_PRINT_SG_UPLOAD_FTP_FAILED,
};

#[derive(Clone, Debug, Default)]
pub(crate) struct UserSession {
    pub(crate) user_id: String,
    pub(crate) user_name: String,
    pub(crate) user_nickname: String,
    pub(crate) user_avatar: String,
    pub(crate) access_token: String,
    pub(crate) refresh_token: String,
    pub(crate) backend_url: String,
    pub(crate) auth_url: String,
    logged_in: bool,
}

pub(crate) struct Agent {
    _id: u64,
    _log_dir: String,
    config_dir: String,
    country_code: String,
    log_initialized: bool,
    started: bool,
    discovery_enabled: bool,
    discovery_sending: bool,
    server_connected: bool,
    printer: Option<PrinterConnectionRequest>,
    session: UserSession,
    last_cloud_message: Option<OutboundMessage>,
    last_local_message: Option<OutboundMessage>,
    event_sink: EventSink,
    transport: Box<dyn LanTransport>,
}

impl Agent {
    pub(crate) fn new(id: u64, log_dir: String) -> Self {
        Self::with_transport(id, log_dir, Box::new(RumqttcLanTransport::new()))
    }

    pub(crate) fn with_transport(
        id: u64,
        log_dir: String,
        transport: Box<dyn LanTransport>,
    ) -> Self {
        Self {
            _id: id,
            _log_dir: log_dir,
            config_dir: String::new(),
            country_code: String::new(),
            log_initialized: false,
            started: false,
            discovery_enabled: false,
            discovery_sending: false,
            server_connected: false,
            printer: None,
            session: UserSession::default(),
            last_cloud_message: None,
            last_local_message: None,
            event_sink: EventSink::default(),
            transport,
        }
    }

    pub(crate) fn init_log(&mut self) {
        self.log_initialized = true;
    }

    pub(crate) fn set_config_dir(&mut self, config_dir: String) {
        self.config_dir = config_dir;
    }

    pub(crate) fn set_country_code(&mut self, country_code: String) {
        self.country_code = country_code;
    }

    pub(crate) fn start(&mut self) {
        self.started = true;
    }

    pub(crate) fn set_event_sink(&mut self, event_sink: EventSink) {
        self.event_sink = event_sink;
        let _ = self.event_sink.registered_count();
    }

    pub(crate) fn change_user(&mut self, user_info: String) -> i32 {
        let Ok(payload) = serde_json::from_str::<Value>(&user_info) else {
            self.event_sink.emit_user_login(0, false);
            return ERR_INVALID_RESULT;
        };

        let Some(session) = parse_user_session(&payload) else {
            self.event_sink.emit_user_login(0, false);
            return ERR_INVALID_RESULT;
        };

        self.session = session;
        self.event_sink.emit_user_login(1, true);
        0
    }

    pub(crate) fn user_logout(&mut self) -> i32 {
        self.session = UserSession::default();
        self.event_sink.emit_user_login(0, false);
        0
    }

    pub(crate) fn is_user_login(&self) -> bool {
        self.session.logged_in
    }

    pub(crate) fn user_id(&self) -> &str {
        &self.session.user_id
    }

    pub(crate) fn user_name(&self) -> &str {
        &self.session.user_name
    }

    pub(crate) fn user_nickname(&self) -> &str {
        &self.session.user_nickname
    }

    pub(crate) fn user_avatar(&self) -> &str {
        &self.session.user_avatar
    }

    pub(crate) fn build_login_cmd(&self) -> String {
        if !self.session.logged_in {
            return String::new();
        }

        json!({
            "command": "studio_userlogin",
            "data": {
                "name": display_name(&self.session),
                "avatar": self.session.user_avatar,
            },
        })
        .to_string()
    }

    pub(crate) fn build_login_info(&self) -> String {
        json!({
            "user_id": self.session.user_id,
            "user_name": self.session.user_name,
            "nickname": self.session.user_nickname,
            "avatar": self.session.user_avatar,
            "logged_in": self.session.logged_in,
            "access_token": self.session.access_token,
            "refresh_token": self.session.refresh_token,
            "backend_url": self.session.backend_url,
            "auth_url": self.session.auth_url,
        })
        .to_string()
    }

    pub(crate) fn cloud_configured(&self) -> bool {
        cloud::configured(&self.session)
    }

    pub(crate) fn cloud_call(&mut self, operation: &str, request: &Value) -> CloudResponse {
        let response = cloud::call(operation, request, &self.session);
        if operation == "connect_server" {
            self.server_connected = response.result == 0;
            self.event_sink.emit_server_connected(
                if self.server_connected { 0 } else { -1 },
                response.http_code as i32,
            );
        }
        response
    }

    pub(crate) fn is_server_connected(&self) -> bool {
        self.server_connected
    }

    pub(crate) fn build_logout_cmd(&self) -> String {
        json!({
            "action": "logout",
            "provider": "orca",
        })
        .to_string()
    }

    pub(crate) fn start_discovery(&mut self, start: bool, sending: bool) -> bool {
        self.discovery_enabled = start;
        self.discovery_sending = sending;
        self.transport
            .start_discovery(start, sending, &self.event_sink)
            .unwrap_or(false)
    }

    pub(crate) fn connect_printer(
        &mut self,
        dev_id: String,
        dev_ip: String,
        username: String,
        password: String,
        use_ssl: bool,
    ) -> i32 {
        let request = PrinterConnectionRequest::new(dev_id, dev_ip, username, password, use_ssl);
        self.printer = Some(request.clone());
        match self.transport.connect_printer(request, &self.event_sink) {
            Ok(()) => 0,
            Err(error) => transport_error_code(error),
        }
    }

    pub(crate) fn disconnect_printer(&mut self) -> i32 {
        self.printer = None;
        match self.transport.disconnect_printer(&self.event_sink) {
            Ok(()) => 0,
            Err(error) => transport_error_code(error),
        }
    }

    pub(crate) fn send_message(
        &mut self,
        dev_id: String,
        message: String,
        qos: i32,
        flag: i32,
    ) -> i32 {
        match OutboundMessage::parse(dev_id, message, qos, flag) {
            Ok(message) => {
                let result = self
                    .transport
                    .send_cloud_message(&message, &self.event_sink)
                    .map(|()| 0)
                    .unwrap_or_else(transport_error_code);
                self.last_cloud_message = Some(message);
                result
            }
            Err(_) => ERR_INVALID_RESULT,
        }
    }

    pub(crate) fn send_message_to_printer(
        &mut self,
        dev_id: String,
        message: String,
        qos: i32,
        flag: i32,
    ) -> i32 {
        match OutboundMessage::parse(dev_id, message, qos, flag) {
            Ok(message) => {
                let Ok(publish) = LocalMqttPublish::from_message(&message) else {
                    return ERR_INVALID_RESULT;
                };
                let result = self
                    .transport
                    .send_local_message(&publish, &self.event_sink)
                    .map(|()| 0)
                    .unwrap_or_else(transport_error_code);
                self.last_local_message = Some(message);
                result
            }
            Err(_) => ERR_INVALID_RESULT,
        }
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn start_sdcard_print(
        &mut self,
        dev_id: String,
        dev_ip: String,
        username: String,
        password: String,
        use_ssl_for_mqtt: bool,
        sequence_id: String,
        plate_index: i32,
        file_path: String,
        file_md5: String,
        bed_type: String,
        bed_leveling: bool,
        flow_cali: bool,
        vibration_cali: bool,
        layer_inspect: bool,
        timelapse: bool,
        use_ams: bool,
        ams_mapping: String,
    ) -> i32 {
        let Ok(message) = ProjectFileRequest::new(
            dev_id,
            sequence_id,
            plate_index,
            file_path,
            file_md5,
            bed_type,
            bed_leveling,
            flow_cali,
            vibration_cali,
            layer_inspect,
            timelapse,
            use_ams,
            ams_mapping,
        )
        .and_then(|request| {
            request
                .into_outbound_message()
                .map_err(|_| crate::protocol::ProtocolError::InvalidProjectFile)
        }) else {
            return ERR_INVALID_RESULT;
        };

        let Ok(publish) = LocalMqttPublish::from_message(&message) else {
            return ERR_INVALID_RESULT;
        };

        if sdcard_connection_requested(&dev_ip, &username, &password) {
            if !sdcard_connection_complete(&dev_ip, &username, &password) {
                return ERR_CONNECT_FAILED;
            }

            let connection = PrinterConnectionRequest::new(
                message.dev_id().to_string(),
                dev_ip,
                username,
                password,
                use_ssl_for_mqtt,
            );
            if let Err(error) = self.transport.connect_printer(connection, &self.event_sink) {
                return transport_error_code(error);
            }
        }

        self.transport
            .send_local_message(&publish, &self.event_sink)
            .map(|()| 0)
            .unwrap_or_else(local_print_publish_error_code)
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn start_local_print(
        &mut self,
        dev_id: String,
        dev_ip: String,
        username: String,
        password: String,
        use_ssl_for_ftp: bool,
        use_ssl_for_mqtt: bool,
        sequence_id: String,
        plate_index: i32,
        local_file: String,
        remote_name: String,
        file_md5: String,
        bed_type: String,
        bed_leveling: bool,
        flow_cali: bool,
        vibration_cali: bool,
        layer_inspect: bool,
        timelapse: bool,
        use_ams: bool,
        ams_mapping: String,
    ) -> i32 {
        let remote_name = normalized_remote_name(&local_file, &remote_name);
        if remote_name.is_empty() {
            return ERR_INVALID_RESULT;
        }

        let upload = FileUploadRequest::new(
            dev_ip.clone(),
            username.clone(),
            password.clone(),
            use_ssl_for_ftp,
            local_file,
            remote_name,
        );
        if let Err(error) = self.transport.upload_file(&upload, &self.event_sink) {
            return local_print_upload_error_code(error);
        }

        let connection = PrinterConnectionRequest::new(
            dev_id.clone(),
            dev_ip,
            username,
            password,
            use_ssl_for_mqtt,
        );
        if let Err(error) = self.transport.connect_printer(connection, &self.event_sink) {
            return transport_error_code(error);
        }

        let project_file_md5 = project_file_md5(&upload, &file_md5);
        self.start_sdcard_print(
            dev_id,
            String::new(),
            String::new(),
            String::new(),
            false,
            sequence_id,
            plate_index,
            upload.remote_url(),
            project_file_md5,
            bed_type,
            bed_leveling,
            flow_cali,
            vibration_cali,
            layer_inspect,
            timelapse,
            use_ams,
            ams_mapping,
        )
    }

    pub(crate) fn upload_file_to_printer(
        &mut self,
        dev_ip: String,
        username: String,
        password: String,
        use_ssl_for_ftp: bool,
        local_file: String,
        remote_name: String,
    ) -> i32 {
        let remote_name = normalized_remote_name(&local_file, &remote_name);
        if remote_name.is_empty() {
            return ERR_INVALID_RESULT;
        }

        let upload = FileUploadRequest::new(
            dev_ip,
            username,
            password,
            use_ssl_for_ftp,
            local_file,
            remote_name,
        );

        self.transport
            .upload_file(&upload, &self.event_sink)
            .map(|()| 0)
            .unwrap_or_else(send_gcode_upload_error_code)
    }

    pub(crate) fn emit_ssdp(&self, dev_info: &str) {
        self.event_sink.emit_ssdp(dev_info);
    }

    pub(crate) fn emit_printer_connected(&self, topic: &str) {
        self.event_sink.emit_printer_connected(topic);
    }

    pub(crate) fn emit_message(&self, dev_id: &str, message: &str) {
        self.event_sink.emit_message(dev_id, message);
    }

    pub(crate) fn emit_local_connect(&self, status: i32, dev_id: &str, message: &str) {
        self.event_sink.emit_local_connect(status, dev_id, message);
    }

    pub(crate) fn emit_local_message(&self, dev_id: &str, message: &str) {
        self.event_sink.emit_local_message(dev_id, message);
    }

    pub(crate) fn emit_server_error(&self, url: &str, status: i32) {
        self.event_sink.emit_server_error(url, status);
    }
}

fn parse_user_session(payload: &Value) -> Option<UserSession> {
    if read_string(payload, &["command"]).as_deref() == Some("user_login") {
        let data = payload.get("data")?;
        if read_string(data, &["code"]).is_some() {
            return None;
        }
        return parse_direct_login(data);
    }

    if let Some(data) = payload.get("data") {
        if let Some(session) = data.get("session").and_then(parse_orca_session) {
            return Some(session);
        }
        if let Some(session) = parse_orca_session(data) {
            return Some(session);
        }
    }

    if let Some(session) = payload.get("session").and_then(parse_orca_session) {
        return Some(session);
    }

    parse_orca_session(payload)
}

fn parse_direct_login(data: &Value) -> Option<UserSession> {
    let access_token =
        read_string(data, &["access_token"]).or_else(|| read_string(data, &["token"]))?;
    let user_id = read_string(data, &["user_id"])
        .or_else(|| read_string(data, &["uidStr"]))
        .or_else(|| read_string(data, &["user", "id"]))
        .or_else(|| read_string(data, &["user", "uid"]))
        .or_else(|| read_string(data, &["user", "uidStr"]))?;

    if access_token.is_empty() || user_id.is_empty() {
        return None;
    }

    let user_name = read_string(data, &["username"])
        .or_else(|| read_string(data, &["name"]))
        .or_else(|| read_string(data, &["user", "name"]))
        .or_else(|| read_string(data, &["user", "account"]))
        .unwrap_or_default();
    let user_nickname = read_string(data, &["nickname"])
        .or_else(|| read_string(data, &["user", "nickname"]))
        .unwrap_or_else(|| display_name_parts(&user_name, &user_name, &user_id));
    let user_avatar = read_string(data, &["avatar"])
        .or_else(|| read_string(data, &["user", "avatar"]))
        .unwrap_or_default();

    Some(UserSession {
        user_id,
        user_name,
        user_nickname,
        user_avatar,
        access_token,
        refresh_token: read_string(data, &["refresh_token"]).unwrap_or_default(),
        backend_url: read_string(data, &["backend_url"])
            .or_else(|| read_string(data, &["bambu_url"]))
            .unwrap_or_default(),
        auth_url: read_string(data, &["auth_url"]).unwrap_or_default(),
        logged_in: true,
    })
}

fn parse_orca_session(node: &Value) -> Option<UserSession> {
    let access_token =
        read_string(node, &["access_token"]).or_else(|| read_string(node, &["token"]))?;
    let user_id = read_string(node, &["user", "id"])?;
    if access_token.is_empty() || user_id.is_empty() {
        return None;
    }

    let email = read_string(node, &["user", "email"]).unwrap_or_default();
    let full_name = read_string(node, &["user", "user_metadata", "full_name"]).unwrap_or_default();
    let preferred_username =
        read_string(node, &["user", "user_metadata", "preferred_username"]).unwrap_or_default();
    let user_name = if !preferred_username.is_empty() {
        preferred_username.clone()
    } else {
        email.clone()
    };
    let name = if !full_name.is_empty() {
        full_name.clone()
    } else {
        display_name_parts(&preferred_username, &email, &user_id)
    };
    let user_nickname = display_name_parts(&preferred_username, &user_name, &name);

    Some(UserSession {
        user_id,
        user_name,
        user_nickname,
        user_avatar: read_string(node, &["user", "user_metadata", "avatar_url"])
            .unwrap_or_default(),
        access_token,
        refresh_token: read_string(node, &["refresh_token"]).unwrap_or_default(),
        backend_url: read_string(node, &["backend_url"]).unwrap_or_default(),
        auth_url: read_string(node, &["auth_url"]).unwrap_or_default(),
        logged_in: true,
    })
}

fn read_string(node: &Value, path: &[&str]) -> Option<String> {
    let mut current = node;
    for key in path {
        current = current.get(*key)?;
    }
    match current {
        Value::String(value) => Some(value.clone()),
        Value::Number(_) | Value::Bool(_) => Some(current.to_string()),
        _ => None,
    }
}

fn display_name(session: &UserSession) -> &str {
    if !session.user_nickname.is_empty() {
        &session.user_nickname
    } else if !session.user_name.is_empty() {
        &session.user_name
    } else {
        &session.user_id
    }
}

fn display_name_parts(first: &str, second: &str, fallback: &str) -> String {
    if !first.is_empty() {
        first.to_string()
    } else if !second.is_empty() {
        second.to_string()
    } else {
        fallback.to_string()
    }
}

fn normalized_remote_name(local_file: &str, remote_name: &str) -> String {
    let remote_name = remote_name.trim().trim_start_matches('/');
    if !remote_name.is_empty() {
        return remote_name.to_string();
    }

    Path::new(local_file)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or_default()
        .to_string()
}

fn sdcard_connection_requested(dev_ip: &str, username: &str, password: &str) -> bool {
    !dev_ip.trim().is_empty() || !username.trim().is_empty() || !password.trim().is_empty()
}

fn sdcard_connection_complete(dev_ip: &str, username: &str, password: &str) -> bool {
    !dev_ip.trim().is_empty() && !username.trim().is_empty() && !password.trim().is_empty()
}

fn project_file_md5(upload: &FileUploadRequest, file_md5: &str) -> String {
    let file_md5 = file_md5.trim();
    if !file_md5.is_empty() {
        return file_md5.to_string();
    }

    calculate_md5(upload.local_path()).unwrap_or_default()
}

fn calculate_md5(path: &Path) -> Option<String> {
    let mut file = File::open(path).ok()?;
    let mut hasher = md5::Md5::new();
    let mut buffer = [0_u8; 32 * 1024];

    loop {
        let bytes_read = file.read(&mut buffer).ok()?;
        if bytes_read == 0 {
            break;
        }
        hasher.update(&buffer[..bytes_read]);
    }

    Some(uppercase_hex(&hasher.finalize()))
}

fn uppercase_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789ABCDEF";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(HEX[(byte >> 4) as usize] as char);
        out.push(HEX[(byte & 0x0f) as usize] as char);
    }
    out
}

fn transport_error_code(error: TransportError) -> i32 {
    match error {
        TransportError::Connect | TransportError::Publish | TransportError::Upload => {
            ERR_CONNECT_FAILED
        }
    }
}

fn local_print_upload_error_code(error: TransportError) -> i32 {
    match error {
        TransportError::Upload => ERR_PRINT_LP_UPLOAD_FTP_FAILED,
        _ => transport_error_code(error),
    }
}

fn local_print_publish_error_code(error: TransportError) -> i32 {
    match error {
        TransportError::Publish => ERR_PRINT_LP_PUBLISH_MSG_FAILED,
        _ => transport_error_code(error),
    }
}

fn send_gcode_upload_error_code(error: TransportError) -> i32 {
    match error {
        TransportError::Upload => ERR_PRINT_SG_UPLOAD_FTP_FAILED,
        _ => transport_error_code(error),
    }
}

#[cfg(test)]
mod tests {
    use std::cell::RefCell;
    use std::env;
    use std::fs;
    use std::process;
    use std::rc::Rc;

    use crate::agent::Agent;
    use crate::event::EventSink;
    use crate::protocol::{LocalMqttPublish, OutboundMessage};
    use crate::transport::{
        FileUploadRequest, LanTransport, PrinterConnectionRequest, TransportError, TransportResult,
    };
    use crate::{ERR_CONNECT_FAILED, ERR_INVALID_RESULT};

    #[derive(Default)]
    struct RecordingState {
        discovery_calls: Vec<(bool, bool)>,
        connect_requests: Vec<PrinterConnectionRequest>,
        disconnect_calls: usize,
        uploads: Vec<FileUploadRequest>,
        cloud_messages: Vec<OutboundMessage>,
        local_messages: Vec<LocalMqttPublish>,
    }

    #[derive(Clone, Default)]
    struct RecordingTransport {
        state: Rc<RefCell<RecordingState>>,
        connect_error: Option<TransportError>,
        upload_error: Option<TransportError>,
        local_error: Option<TransportError>,
    }

    impl RecordingTransport {
        fn state(&self) -> Rc<RefCell<RecordingState>> {
            Rc::clone(&self.state)
        }
    }

    impl LanTransport for RecordingTransport {
        fn start_discovery(
            &mut self,
            start: bool,
            sending: bool,
            _event_sink: &EventSink,
        ) -> TransportResult<bool> {
            self.state
                .borrow_mut()
                .discovery_calls
                .push((start, sending));
            Ok(true)
        }

        fn connect_printer(
            &mut self,
            request: PrinterConnectionRequest,
            _event_sink: &EventSink,
        ) -> TransportResult<()> {
            self.state.borrow_mut().connect_requests.push(request);
            if let Some(error) = self.connect_error {
                return Err(error);
            }
            Ok(())
        }

        fn disconnect_printer(&mut self, _event_sink: &EventSink) -> TransportResult<()> {
            self.state.borrow_mut().disconnect_calls += 1;
            Ok(())
        }

        fn send_cloud_message(
            &mut self,
            message: &OutboundMessage,
            _event_sink: &EventSink,
        ) -> TransportResult<()> {
            self.state.borrow_mut().cloud_messages.push(message.clone());
            Err(TransportError::Connect)
        }

        fn send_local_message(
            &mut self,
            publish: &LocalMqttPublish,
            _event_sink: &EventSink,
        ) -> TransportResult<()> {
            self.state.borrow_mut().local_messages.push(publish.clone());
            if let Some(error) = self.local_error {
                return Err(error);
            }
            Ok(())
        }

        fn upload_file(
            &mut self,
            request: &FileUploadRequest,
            _event_sink: &EventSink,
        ) -> TransportResult<()> {
            self.state.borrow_mut().uploads.push(request.clone());
            if let Some(error) = self.upload_error {
                return Err(error);
            }
            Ok(())
        }
    }

    fn recording_agent() -> (Agent, Rc<RefCell<RecordingState>>) {
        let transport = RecordingTransport::default();
        let state = transport.state();
        (
            Agent::with_transport(1, "/tmp/bambu-agent-test".to_string(), Box::new(transport)),
            state,
        )
    }

    fn recording_agent_with_transport(
        transport: RecordingTransport,
    ) -> (Agent, Rc<RefCell<RecordingState>>) {
        let state = transport.state();
        (
            Agent::with_transport(1, "/tmp/bambu-agent-test".to_string(), Box::new(transport)),
            state,
        )
    }

    #[test]
    fn change_user_accepts_direct_login_payload() {
        let (mut agent, _) = recording_agent();

        let result = agent.change_user(
            r#"{"command":"user_login","data":{"access_token":"token-redacted","refresh_token":"refresh-redacted","backend_url":"https://api.example.invalid","user_id":"1001","username":"praveen","nickname":"Praveen","avatar":"https://example.invalid/avatar.png"}}"#
                .to_string(),
        );

        assert_eq!(result, 0);
        assert!(agent.is_user_login());
        assert_eq!(agent.user_id(), "1001");
        assert_eq!(agent.user_name(), "praveen");
        assert_eq!(agent.user_nickname(), "Praveen");
        assert_eq!(agent.user_avatar(), "https://example.invalid/avatar.png");

        let login_cmd: serde_json::Value = serde_json::from_str(&agent.build_login_cmd()).unwrap();
        assert_eq!(login_cmd["command"], "studio_userlogin");
        assert_eq!(login_cmd["data"]["name"], "Praveen");

        let login_info: serde_json::Value =
            serde_json::from_str(&agent.build_login_info()).unwrap();
        assert_eq!(login_info["user_id"], "1001");
        assert_eq!(login_info["logged_in"], true);
        assert_eq!(login_info["access_token"], "token-redacted");
        assert_eq!(login_info["refresh_token"], "refresh-redacted");
        assert_eq!(login_info["backend_url"], "https://api.example.invalid");
        assert!(agent.cloud_configured());
    }

    #[test]
    fn change_user_accepts_orca_session_payload() {
        let (mut agent, _) = recording_agent();

        let result = agent.change_user(
            r#"{"data":{"session":{"access_token":"token-redacted","refresh_token":"refresh-redacted","user":{"id":"user-123","email":"praveen@example.invalid","user_metadata":{"full_name":"Praveen Perera","preferred_username":"praveen","avatar_url":"https://example.invalid/user.png"}}}}}"#
                .to_string(),
        );

        assert_eq!(result, 0);
        assert!(agent.is_user_login());
        assert_eq!(agent.user_id(), "user-123");
        assert_eq!(agent.user_name(), "praveen");
        assert_eq!(agent.user_nickname(), "praveen");
        assert_eq!(agent.user_avatar(), "https://example.invalid/user.png");
    }

    #[test]
    fn change_user_rejects_auth_code_and_malformed_payloads() {
        let (mut agent, _) = recording_agent();

        assert_eq!(agent.change_user("{".to_string()), ERR_INVALID_RESULT);
        assert!(!agent.is_user_login());
        assert_eq!(
            agent.change_user(
                r#"{"command":"user_login","data":{"code":"auth-code-only"}}"#.to_string()
            ),
            ERR_INVALID_RESULT
        );
        assert!(!agent.is_user_login());
        assert!(agent.build_login_cmd().is_empty());
    }

    #[test]
    fn user_logout_clears_login_state() {
        let (mut agent, _) = recording_agent();

        assert_eq!(
            agent.change_user(
                r#"{"command":"user_login","data":{"access_token":"token-redacted","user_id":"1001","name":"Praveen"}}"#
                    .to_string(),
            ),
            0
        );
        assert!(agent.is_user_login());

        assert_eq!(agent.user_logout(), 0);

        let login_info: serde_json::Value =
            serde_json::from_str(&agent.build_login_info()).unwrap();
        assert!(!agent.is_user_login());
        assert_eq!(agent.user_id(), "");
        assert_eq!(agent.user_name(), "");
        assert_eq!(agent.user_nickname(), "");
        assert_eq!(agent.user_avatar(), "");
        assert_eq!(login_info["logged_in"], false);
    }

    #[test]
    fn routes_discovery_and_printer_lifecycle_to_transport() {
        let (mut agent, state) = recording_agent();

        assert!(agent.start_discovery(true, false));
        let connect_result = agent.connect_printer(
            "dev".to_string(),
            "192.0.2.10".to_string(),
            "bblp".to_string(),
            "access-code".to_string(),
            false,
        );
        let disconnect_result = agent.disconnect_printer();

        let state = state.borrow();
        assert_eq!(connect_result, 0);
        assert_eq!(disconnect_result, 0);
        assert_eq!(state.discovery_calls, vec![(true, false)]);
        assert_eq!(state.connect_requests.len(), 1);
        assert_eq!(state.connect_requests[0].dev_id(), "dev");
        assert_eq!(state.connect_requests[0].dev_ip(), "192.0.2.10");
        assert_eq!(state.connect_requests[0].username(), "bblp");
        assert_eq!(state.connect_requests[0].password(), "access-code");
        assert!(!state.connect_requests[0].use_ssl());
        assert_eq!(state.disconnect_calls, 1);
    }

    #[test]
    fn routes_valid_messages_and_preserves_transport_status() {
        let (mut agent, state) = recording_agent();

        let cloud_result = agent.send_message(
            "dev".to_string(),
            r#"{"print":{"command":"x"}}"#.to_string(),
            1,
            2,
        );
        let local_result = agent.send_message_to_printer(
            "dev".to_string(),
            r#"{"pushing":{"sequence_id":"0","command":"pushall"}}"#.to_string(),
            0,
            0,
        );

        let state = state.borrow();
        assert_eq!(cloud_result, ERR_CONNECT_FAILED);
        assert_eq!(local_result, 0);
        assert_eq!(state.cloud_messages.len(), 1);
        assert_eq!(state.cloud_messages[0].dev_id(), "dev");
        assert_eq!(state.cloud_messages[0].qos(), 1);
        assert_eq!(state.cloud_messages[0].flag(), 2);
        assert_eq!(state.local_messages.len(), 1);
        assert!(state.local_messages[0].payload().contains("\"pushing\""));
        assert_eq!(
            state.local_messages[0].request_topic(),
            "device/dev/request"
        );
        assert_eq!(state.local_messages[0].report_topic(), "device/dev/report");
    }

    #[test]
    fn invalid_messages_do_not_reach_transport() {
        let (mut agent, state) = recording_agent();

        let cloud_result = agent.send_message("dev".to_string(), "{".to_string(), 0, 0);
        let local_result = agent.send_message_to_printer("dev".to_string(), "{".to_string(), 0, 0);

        let state = state.borrow();
        assert_eq!(cloud_result, ERR_INVALID_RESULT);
        assert_eq!(local_result, ERR_INVALID_RESULT);
        assert!(state.cloud_messages.is_empty());
        assert!(state.local_messages.is_empty());
    }

    #[test]
    fn invalid_local_device_id_does_not_reach_transport() {
        let (mut agent, state) = recording_agent();

        let result = agent.send_message_to_printer("bad/id".to_string(), "{}".to_string(), 0, 0);

        let state = state.borrow();
        assert_eq!(result, ERR_INVALID_RESULT);
        assert!(state.local_messages.is_empty());
    }

    #[test]
    fn start_sdcard_print_sends_project_file_message() {
        let (mut agent, state) = recording_agent();

        let result = agent.start_sdcard_print(
            "SERIAL123".to_string(),
            String::new(),
            String::new(),
            String::new(),
            false,
            "0".to_string(),
            3,
            "ftp:///already-uploaded.3mf".to_string(),
            "md5-value".to_string(),
            "auto".to_string(),
            true,
            true,
            false,
            true,
            false,
            true,
            "[-1,-1,-1,0]".to_string(),
        );

        let state = state.borrow();
        assert_eq!(result, 0);
        assert_eq!(state.local_messages.len(), 1);
        assert_eq!(
            state.local_messages[0].request_topic(),
            "device/SERIAL123/request"
        );
        assert!(state.local_messages[0]
            .payload()
            .contains("\"command\":\"project_file\""));
        assert!(state.local_messages[0]
            .payload()
            .contains("\"url\":\"ftp:///already-uploaded.3mf\""));
        assert!(state.local_messages[0]
            .payload()
            .contains("\"param\":\"Metadata/plate_3.gcode\""));
    }

    #[test]
    fn start_sdcard_print_connects_when_printer_credentials_are_supplied() {
        let (mut agent, state) = recording_agent();

        let result = agent.start_sdcard_print(
            "SERIAL123".to_string(),
            "192.0.2.10".to_string(),
            "bblp".to_string(),
            "12345678".to_string(),
            true,
            "0".to_string(),
            3,
            "ftp:///already-uploaded.3mf".to_string(),
            "md5-value".to_string(),
            "auto".to_string(),
            true,
            true,
            false,
            true,
            false,
            true,
            "[-1,-1,-1,0]".to_string(),
        );

        let state = state.borrow();
        assert_eq!(result, 0);
        assert_eq!(state.connect_requests.len(), 1);
        assert_eq!(state.connect_requests[0].dev_id(), "SERIAL123");
        assert_eq!(state.connect_requests[0].dev_ip(), "192.0.2.10");
        assert_eq!(state.connect_requests[0].username(), "bblp");
        assert_eq!(state.connect_requests[0].password(), "12345678");
        assert!(state.connect_requests[0].use_ssl());
        assert_eq!(state.local_messages.len(), 1);
    }

    #[test]
    fn start_sdcard_print_rejects_partial_printer_credentials() {
        let (mut agent, state) = recording_agent();

        let result = agent.start_sdcard_print(
            "SERIAL123".to_string(),
            "192.0.2.10".to_string(),
            "bblp".to_string(),
            String::new(),
            true,
            "0".to_string(),
            3,
            "ftp:///already-uploaded.3mf".to_string(),
            "md5-value".to_string(),
            "auto".to_string(),
            true,
            true,
            false,
            true,
            false,
            true,
            "[-1,-1,-1,0]".to_string(),
        );

        let state = state.borrow();
        assert_eq!(result, ERR_CONNECT_FAILED);
        assert!(state.connect_requests.is_empty());
        assert!(state.local_messages.is_empty());
    }

    #[test]
    fn invalid_sdcard_print_request_does_not_reach_transport() {
        let (mut agent, state) = recording_agent();

        let result = agent.start_sdcard_print(
            "bad/id".to_string(),
            String::new(),
            String::new(),
            String::new(),
            false,
            "0".to_string(),
            1,
            String::new(),
            String::new(),
            String::new(),
            false,
            false,
            false,
            false,
            false,
            false,
            String::new(),
        );

        let state = state.borrow();
        assert_eq!(result, ERR_INVALID_RESULT);
        assert!(state.local_messages.is_empty());
    }

    #[test]
    fn start_local_print_uploads_connects_and_sends_project_file() {
        let (mut agent, state) = recording_agent();

        let result = agent.start_local_print(
            "SERIAL123".to_string(),
            "192.0.2.10".to_string(),
            "bblp".to_string(),
            "12345678".to_string(),
            true,
            true,
            "0".to_string(),
            1,
            "/tmp/project.gcode.3mf".to_string(),
            String::new(),
            "md5-value".to_string(),
            "auto".to_string(),
            true,
            false,
            false,
            true,
            false,
            false,
            String::new(),
        );

        let state = state.borrow();
        assert_eq!(result, 0);
        assert_eq!(state.uploads.len(), 1);
        assert_eq!(state.uploads[0].dev_ip(), "192.0.2.10");
        assert_eq!(state.uploads[0].username(), "bblp");
        assert_eq!(state.uploads[0].password(), "12345678");
        assert_eq!(state.uploads[0].remote_name(), "project.gcode.3mf");
        assert_eq!(state.uploads[0].remote_url(), "ftp:///project.gcode.3mf");
        assert_eq!(state.connect_requests.len(), 1);
        assert_eq!(state.connect_requests[0].dev_id(), "SERIAL123");
        assert_eq!(state.local_messages.len(), 1);
        assert!(state.local_messages[0]
            .payload()
            .contains("\"url\":\"ftp:///project.gcode.3mf\""));
    }

    #[test]
    fn start_local_print_computes_missing_project_file_md5() {
        let (mut agent, state) = recording_agent();
        let file_path = env::temp_dir().join(format!(
            "bambu-rust-md5-{}-{}.3mf",
            process::id(),
            "local-print"
        ));
        fs::write(&file_path, b"hello").unwrap();

        let result = agent.start_local_print(
            "SERIAL123".to_string(),
            "192.0.2.10".to_string(),
            "bblp".to_string(),
            "12345678".to_string(),
            true,
            true,
            "0".to_string(),
            1,
            file_path.to_string_lossy().into_owned(),
            String::new(),
            String::new(),
            "auto".to_string(),
            true,
            false,
            false,
            true,
            false,
            false,
            String::new(),
        );

        let _ = fs::remove_file(&file_path);
        let state = state.borrow();
        assert_eq!(result, 0);
        assert_eq!(state.local_messages.len(), 1);
        assert!(state.local_messages[0]
            .payload()
            .contains("\"md5\":\"5D41402ABC4B2A76B9719D911017C592\""));
    }

    #[test]
    fn start_local_print_rejects_missing_file_name() {
        let (mut agent, state) = recording_agent();

        let result = agent.start_local_print(
            "SERIAL123".to_string(),
            "192.0.2.10".to_string(),
            "bblp".to_string(),
            "12345678".to_string(),
            true,
            true,
            "0".to_string(),
            1,
            String::new(),
            String::new(),
            String::new(),
            String::new(),
            false,
            false,
            false,
            false,
            false,
            false,
            String::new(),
        );

        let state = state.borrow();
        assert_eq!(result, ERR_INVALID_RESULT);
        assert!(state.uploads.is_empty());
        assert!(state.local_messages.is_empty());
    }

    #[test]
    fn upload_file_to_printer_does_not_send_print_command() {
        let (mut agent, state) = recording_agent();

        let result = agent.upload_file_to_printer(
            "192.0.2.10".to_string(),
            "bblp".to_string(),
            "12345678".to_string(),
            true,
            "/tmp/check_access_code.txt".to_string(),
            String::new(),
        );

        let state = state.borrow();
        assert_eq!(result, 0);
        assert_eq!(state.uploads.len(), 1);
        assert_eq!(state.uploads[0].remote_name(), "check_access_code.txt");
        assert!(state.connect_requests.is_empty());
        assert!(state.local_messages.is_empty());
    }

    #[test]
    fn upload_file_to_printer_maps_upload_failure_to_send_gcode_error() {
        let transport = RecordingTransport {
            upload_error: Some(TransportError::Upload),
            ..RecordingTransport::default()
        };
        let (mut agent, state) = recording_agent_with_transport(transport);

        let result = agent.upload_file_to_printer(
            "192.0.2.10".to_string(),
            "bblp".to_string(),
            "12345678".to_string(),
            true,
            "/tmp/project.gcode.3mf".to_string(),
            String::new(),
        );

        let state = state.borrow();
        assert_eq!(result, crate::ERR_PRINT_SG_UPLOAD_FTP_FAILED);
        assert_eq!(state.uploads.len(), 1);
        assert!(state.connect_requests.is_empty());
        assert!(state.local_messages.is_empty());
    }

    #[test]
    fn start_local_print_maps_upload_failure_to_local_print_error() {
        let transport = RecordingTransport {
            upload_error: Some(TransportError::Upload),
            ..RecordingTransport::default()
        };
        let (mut agent, state) = recording_agent_with_transport(transport);

        let result = agent.start_local_print(
            "SERIAL123".to_string(),
            "192.0.2.10".to_string(),
            "bblp".to_string(),
            "12345678".to_string(),
            true,
            true,
            "0".to_string(),
            1,
            "/tmp/project.gcode.3mf".to_string(),
            String::new(),
            "md5-value".to_string(),
            "auto".to_string(),
            true,
            false,
            false,
            true,
            false,
            false,
            String::new(),
        );

        let state = state.borrow();
        assert_eq!(result, crate::ERR_PRINT_LP_UPLOAD_FTP_FAILED);
        assert_eq!(state.uploads.len(), 1);
        assert!(state.connect_requests.is_empty());
        assert!(state.local_messages.is_empty());
    }

    #[test]
    fn start_sdcard_print_maps_publish_failure_to_local_print_error() {
        let transport = RecordingTransport {
            local_error: Some(TransportError::Publish),
            ..RecordingTransport::default()
        };
        let (mut agent, state) = recording_agent_with_transport(transport);

        let result = agent.start_sdcard_print(
            "SERIAL123".to_string(),
            String::new(),
            String::new(),
            String::new(),
            false,
            "0".to_string(),
            3,
            "ftp:///already-uploaded.3mf".to_string(),
            "md5-value".to_string(),
            "auto".to_string(),
            true,
            true,
            false,
            true,
            false,
            true,
            "[-1,-1,-1,0]".to_string(),
        );

        let state = state.borrow();
        assert_eq!(result, crate::ERR_PRINT_LP_PUBLISH_MSG_FAILED);
        assert_eq!(state.local_messages.len(), 1);
    }
}
