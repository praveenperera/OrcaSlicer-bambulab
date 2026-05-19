use crate::event::EventSink;
use std::path::{Path, PathBuf};

use crate::protocol::{LocalMqttPublish, OutboundMessage};

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct PrinterConnectionRequest {
    dev_id: String,
    dev_ip: String,
    username: String,
    password: String,
    use_ssl: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct FileUploadRequest {
    dev_ip: String,
    username: String,
    password: String,
    use_ssl: bool,
    local_path: PathBuf,
    remote_name: String,
}

impl FileUploadRequest {
    pub(crate) fn new(
        dev_ip: String,
        username: String,
        password: String,
        use_ssl: bool,
        local_path: String,
        remote_name: String,
    ) -> Self {
        Self {
            dev_ip,
            username,
            password,
            use_ssl,
            local_path: PathBuf::from(local_path),
            remote_name,
        }
    }

    pub(crate) fn dev_ip(&self) -> &str {
        &self.dev_ip
    }

    pub(crate) fn username(&self) -> &str {
        &self.username
    }

    pub(crate) fn password(&self) -> &str {
        &self.password
    }

    pub(crate) fn use_ssl(&self) -> bool {
        self.use_ssl
    }

    pub(crate) fn local_path(&self) -> &Path {
        &self.local_path
    }

    pub(crate) fn remote_name(&self) -> &str {
        &self.remote_name
    }

    pub(crate) fn remote_url(&self) -> String {
        format!("ftp:///{}", self.remote_name.trim_start_matches('/'))
    }
}

impl PrinterConnectionRequest {
    pub(crate) fn new(
        dev_id: String,
        dev_ip: String,
        username: String,
        password: String,
        use_ssl: bool,
    ) -> Self {
        Self {
            dev_id,
            dev_ip,
            username,
            password,
            use_ssl,
        }
    }

    pub(crate) fn dev_id(&self) -> &str {
        &self.dev_id
    }

    pub(crate) fn dev_ip(&self) -> &str {
        &self.dev_ip
    }

    pub(crate) fn username(&self) -> &str {
        &self.username
    }

    pub(crate) fn password(&self) -> &str {
        &self.password
    }

    pub(crate) fn use_ssl(&self) -> bool {
        self.use_ssl
    }

    pub(crate) fn report_topic(&self) -> Result<String, crate::protocol::ProtocolError> {
        crate::protocol::LocalMqttTopics::new(&self.dev_id)
            .map(|topics| topics.report_topic().to_string())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum TransportError {
    Connect,
    Publish,
    Upload,
}

pub(crate) type TransportResult<T> = Result<T, TransportError>;

pub(crate) trait LanTransport {
    fn start_discovery(
        &mut self,
        start: bool,
        sending: bool,
        event_sink: &EventSink,
    ) -> TransportResult<bool>;

    fn connect_printer(
        &mut self,
        request: PrinterConnectionRequest,
        event_sink: &EventSink,
    ) -> TransportResult<()>;

    fn disconnect_printer(&mut self, event_sink: &EventSink) -> TransportResult<()>;

    fn send_cloud_message(
        &mut self,
        message: &OutboundMessage,
        event_sink: &EventSink,
    ) -> TransportResult<()>;

    fn send_local_message(
        &mut self,
        publish: &LocalMqttPublish,
        event_sink: &EventSink,
    ) -> TransportResult<()>;

    fn upload_file(
        &mut self,
        request: &FileUploadRequest,
        event_sink: &EventSink,
    ) -> TransportResult<()>;
}
