use std::path::Path;

use serde_json::json;

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct OutboundMessage {
    dev_id: String,
    payload: String,
    qos: i32,
    flag: i32,
}

impl OutboundMessage {
    pub(crate) fn parse(
        dev_id: String,
        payload: String,
        qos: i32,
        flag: i32,
    ) -> Result<Self, serde_json::Error> {
        Ok(Self {
            dev_id,
            payload: normalize_json_payload(&payload)?,
            qos,
            flag,
        })
    }

    pub(crate) fn dev_id(&self) -> &str {
        &self.dev_id
    }

    pub(crate) fn payload(&self) -> &str {
        &self.payload
    }

    pub(crate) fn qos(&self) -> i32 {
        self.qos
    }

    pub(crate) fn flag(&self) -> i32 {
        self.flag
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct ProjectFileRequest {
    dev_id: String,
    sequence_id: String,
    plate_index: i32,
    file_url: String,
    file_md5: String,
    bed_type: String,
    bed_leveling: bool,
    flow_cali: bool,
    vibration_cali: bool,
    layer_inspect: bool,
    timelapse: bool,
    use_ams: bool,
    ams_mapping: String,
}

impl ProjectFileRequest {
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn new(
        dev_id: String,
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
    ) -> Result<Self, ProtocolError> {
        validate_dev_id(&dev_id)?;
        let file_url = normalize_project_file_url(&file_path)?;
        Ok(Self {
            dev_id,
            sequence_id,
            plate_index: plate_index.max(1),
            file_url,
            file_md5,
            bed_type: normalize_bed_type(&bed_type),
            bed_leveling,
            flow_cali,
            vibration_cali,
            layer_inspect,
            timelapse,
            use_ams,
            ams_mapping,
        })
    }

    pub(crate) fn into_outbound_message(self) -> Result<OutboundMessage, serde_json::Error> {
        let payload = json!({
            "print": {
                "sequence_id": self.sequence_id,
                "command": "project_file",
                "param": format!("Metadata/plate_{}.gcode", self.plate_index),
                "project_id": "0",
                "profile_id": "0",
                "task_id": "0",
                "subtask_id": "0",
                "subtask_name": "",
                "file": "",
                "url": self.file_url,
                "md5": self.file_md5,
                "timelapse": self.timelapse,
                "bed_type": self.bed_type,
                "bed_levelling": self.bed_leveling,
                "flow_cali": self.flow_cali,
                "vibration_cali": self.vibration_cali,
                "layer_inspect": self.layer_inspect,
                "ams_mapping": self.ams_mapping,
                "use_ams": self.use_ams,
            }
        });

        OutboundMessage::parse(self.dev_id, serde_json::to_string(&payload)?, 1, 0)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct LocalMqttPublish {
    request_topic: String,
    report_topic: String,
    payload: String,
    qos: i32,
    flag: i32,
}

impl LocalMqttPublish {
    pub(crate) fn from_message(message: &OutboundMessage) -> Result<Self, ProtocolError> {
        let topics = LocalMqttTopics::new(message.dev_id())?;
        Ok(Self {
            request_topic: topics.request_topic,
            report_topic: topics.report_topic,
            payload: message.payload().to_string(),
            qos: message.qos(),
            flag: message.flag(),
        })
    }

    pub(crate) fn request_topic(&self) -> &str {
        &self.request_topic
    }

    #[cfg(test)]
    pub(crate) fn report_topic(&self) -> &str {
        &self.report_topic
    }

    pub(crate) fn payload(&self) -> &str {
        &self.payload
    }

    pub(crate) fn qos(&self) -> i32 {
        self.qos
    }

    #[cfg(test)]
    pub(crate) fn flag(&self) -> i32 {
        self.flag
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct LocalMqttTopics {
    request_topic: String,
    report_topic: String,
}

impl LocalMqttTopics {
    pub(crate) fn new(dev_id: &str) -> Result<Self, ProtocolError> {
        validate_dev_id(dev_id)?;
        Ok(Self {
            request_topic: format!("device/{dev_id}/request"),
            report_topic: format!("device/{dev_id}/report"),
        })
    }

    pub(crate) fn report_topic(&self) -> &str {
        &self.report_topic
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ProtocolError {
    InvalidDeviceId,
    InvalidProjectFile,
}

pub(crate) fn normalize_json_payload(payload: &str) -> Result<String, serde_json::Error> {
    let value: serde_json::Value = serde_json::from_str(payload)?;
    serde_json::to_string(&value)
}

fn validate_dev_id(dev_id: &str) -> Result<(), ProtocolError> {
    if dev_id.is_empty() || dev_id.contains('/') || dev_id.contains('#') || dev_id.contains('+') {
        return Err(ProtocolError::InvalidDeviceId);
    }
    Ok(())
}

fn normalize_project_file_url(file_path: &str) -> Result<String, ProtocolError> {
    let file_path = file_path.trim();
    if file_path.is_empty() {
        return Err(ProtocolError::InvalidProjectFile);
    }

    if file_path.contains("://") {
        return Ok(file_path.to_string());
    }

    let filename = Path::new(file_path)
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|name| !name.is_empty())
        .unwrap_or(file_path.trim_start_matches('/'));

    Ok(format!("ftp:///{filename}"))
}

fn normalize_bed_type(bed_type: &str) -> String {
    let bed_type = bed_type.trim();
    if bed_type.is_empty() {
        return "auto".to_string();
    }
    bed_type.to_string()
}

#[cfg(test)]
mod tests {
    use super::{
        normalize_json_payload, LocalMqttPublish, LocalMqttTopics, OutboundMessage,
        ProjectFileRequest,
    };

    #[test]
    fn normalizes_valid_json() {
        let normalized =
            normalize_json_payload(r#"{"pushing":{"command":"pushall","sequence_id":"0"}}"#)
                .unwrap();
        assert!(normalized.contains("\"pushing\""));
        assert!(normalized.contains("\"pushall\""));
    }

    #[test]
    fn rejects_invalid_json() {
        assert!(normalize_json_payload("{").is_err());
    }

    #[test]
    fn parses_outbound_message() {
        let message = OutboundMessage::parse("dev".to_string(), "{}".to_string(), 0, 0);
        assert!(message.is_ok());
    }

    #[test]
    fn derives_local_mqtt_topics() {
        let topics = LocalMqttTopics::new("SERIAL123").unwrap();
        assert_eq!(topics.request_topic, "device/SERIAL123/request");
        assert_eq!(topics.report_topic, "device/SERIAL123/report");
    }

    #[test]
    fn rejects_mqtt_wildcards_in_device_id() {
        assert!(LocalMqttTopics::new("").is_err());
        assert!(LocalMqttTopics::new("bad/id").is_err());
        assert!(LocalMqttTopics::new("bad+id").is_err());
        assert!(LocalMqttTopics::new("bad#id").is_err());
    }

    #[test]
    fn builds_local_mqtt_publish_packet() {
        let message = OutboundMessage::parse(
            "SERIAL123".to_string(),
            r#"{"print":{"command":"x"}}"#.to_string(),
            1,
            2,
        )
        .unwrap();

        let publish = LocalMqttPublish::from_message(&message).unwrap();

        assert_eq!(publish.request_topic(), "device/SERIAL123/request");
        assert_eq!(publish.report_topic(), "device/SERIAL123/report");
        assert!(publish.payload().contains("\"print\""));
        assert_eq!(publish.qos(), 1);
        assert_eq!(publish.flag(), 2);
    }

    #[test]
    fn builds_project_file_message_for_sdcard_prints() {
        let message = ProjectFileRequest::new(
            "SERIAL123".to_string(),
            "0".to_string(),
            2,
            "/tmp/model.gcode.3mf".to_string(),
            "abc123".to_string(),
            String::new(),
            true,
            false,
            true,
            false,
            true,
            true,
            "[0,-1,-1,-1]".to_string(),
        )
        .unwrap()
        .into_outbound_message()
        .unwrap();

        let payload: serde_json::Value = serde_json::from_str(message.payload()).unwrap();
        assert_eq!(message.dev_id(), "SERIAL123");
        assert_eq!(message.qos(), 1);
        assert_eq!(payload["print"]["command"], "project_file");
        assert_eq!(payload["print"]["param"], "Metadata/plate_2.gcode");
        assert_eq!(payload["print"]["url"], "ftp:///model.gcode.3mf");
        assert_eq!(payload["print"]["md5"], "abc123");
        assert_eq!(payload["print"]["bed_type"], "auto");
        assert_eq!(payload["print"]["bed_levelling"], true);
        assert_eq!(payload["print"]["flow_cali"], false);
        assert_eq!(payload["print"]["vibration_cali"], true);
        assert_eq!(payload["print"]["layer_inspect"], false);
        assert_eq!(payload["print"]["timelapse"], true);
        assert_eq!(payload["print"]["use_ams"], true);
        assert_eq!(payload["print"]["ams_mapping"], "[0,-1,-1,-1]");
    }

    #[test]
    fn preserves_explicit_project_file_url() {
        let message = ProjectFileRequest::new(
            "SERIAL123".to_string(),
            "0".to_string(),
            0,
            "file:///sdcard/existing.3mf".to_string(),
            String::new(),
            "textured_plate".to_string(),
            false,
            false,
            false,
            false,
            false,
            false,
            String::new(),
        )
        .unwrap()
        .into_outbound_message()
        .unwrap();

        let payload: serde_json::Value = serde_json::from_str(message.payload()).unwrap();
        assert_eq!(payload["print"]["param"], "Metadata/plate_1.gcode");
        assert_eq!(payload["print"]["url"], "file:///sdcard/existing.3mf");
        assert_eq!(payload["print"]["bed_type"], "textured_plate");
    }

    #[test]
    fn rejects_project_file_message_without_file() {
        let message = ProjectFileRequest::new(
            "SERIAL123".to_string(),
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

        assert!(message.is_err());
    }
}
