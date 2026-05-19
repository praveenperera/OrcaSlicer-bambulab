use std::env;
use std::time::Duration;

use serde_json::{json, Value};

use crate::agent::UserSession;
use crate::ERR_CONNECT_FAILED;

const BASE_URL_ENV: &str = "BAMBU_NETWORK_CLOUD_BASE_URL";

#[derive(Clone, Debug)]
pub(crate) struct CloudResponse {
    pub(crate) result: i32,
    pub(crate) http_code: u32,
    pub(crate) body: String,
    pub(crate) int_value: i32,
}

impl CloudResponse {
    pub(crate) fn unsupported() -> Self {
        Self {
            result: ERR_CONNECT_FAILED,
            http_code: 0,
            body: String::new(),
            int_value: 0,
        }
    }
}

pub(crate) fn configured(session: &UserSession) -> bool {
    resolve_base_url(session).is_some()
}

pub(crate) fn call(operation: &str, request: &Value, session: &UserSession) -> CloudResponse {
    let Some(base_url) = resolve_base_url(session) else {
        return CloudResponse::unsupported();
    };

    let url = operation_url(&base_url, operation);
    let method = operation_method(operation);
    let timeout = Duration::from_secs(timeout_seconds());
    let agent = ureq::Agent::config_builder()
        .timeout_global(Some(timeout))
        .http_status_as_error(false)
        .build()
        .new_agent();

    let body = build_request_body(operation, request, session);
    let mut response = if method == "GET" {
        let mut builder = agent.get(&url);
        if !session.access_token.is_empty() {
            let auth = format!("Bearer {}", session.access_token);
            builder = builder.header("Authorization", auth.as_str());
        }
        builder.call()
    } else {
        let mut builder = agent.post(&url).content_type("application/json");
        if !session.access_token.is_empty() {
            let auth = format!("Bearer {}", session.access_token);
            builder = builder.header("Authorization", auth.as_str());
        }
        builder.send(body.to_string())
    };

    match response.as_mut() {
        Ok(response) => {
            let http_code = response.status().as_u16() as u32;
            let raw_body = response.body_mut().read_to_string().unwrap_or_default();
            let result = if (200..300).contains(&http_code) {
                0
            } else {
                ERR_CONNECT_FAILED
            };
            CloudResponse {
                result,
                http_code,
                int_value: extract_int_value(operation, &raw_body),
                body: extract_body(operation, &raw_body),
            }
        }
        Err(_) => CloudResponse::unsupported(),
    }
}

fn base_url() -> Option<String> {
    let value = env::var(BASE_URL_ENV).ok()?;
    sanitize_base_url(&value)
}

fn resolve_base_url(session: &UserSession) -> Option<String> {
    base_url().or_else(|| sanitize_base_url(&session.backend_url))
}

fn sanitize_base_url(value: &str) -> Option<String> {
    let trimmed = value.trim().trim_end_matches('/').to_string();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed)
    }
}

fn operation_url(base_url: &str, operation: &str) -> String {
    let env_name = format!("BAMBU_NETWORK_CLOUD_PATH_{}", env_key(operation));
    let path = env::var(env_name).unwrap_or_else(|_| default_path(operation).to_string());
    if path.starts_with("http://") || path.starts_with("https://") {
        return path;
    }
    if path.starts_with('/') {
        format!("{base_url}{path}")
    } else {
        format!("{base_url}/{path}")
    }
}

fn operation_method(operation: &str) -> String {
    let env_name = format!("BAMBU_NETWORK_CLOUD_METHOD_{}", env_key(operation));
    env::var(env_name)
        .unwrap_or_else(|_| default_method(operation).to_string())
        .to_ascii_uppercase()
}

fn env_key(operation: &str) -> String {
    operation
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() {
                ch.to_ascii_uppercase()
            } else {
                '_'
            }
        })
        .collect()
}

fn default_path(operation: &str) -> &str {
    match operation {
        "connect_server" => "/health",
        "get_user_print_info" => "/v1/user/print-info",
        "get_user_tasks" => "/v1/user/tasks",
        "get_printer_firmware" => "/v1/printer/firmware",
        "get_my_message" => "/v1/user/messages",
        "get_task_plate_index" => "/v1/tasks/plate-index",
        "get_user_info" => "/v1/user/info",
        "request_bind_ticket" => "/v1/user/bind-ticket",
        "query_bind_status" => "/v1/user/bind-status",
        "get_subtask_info" => "/v1/tasks/subtask",
        "get_slice_info" => "/v1/tasks/slice",
        "get_model_publish_url" => "/v1/model/publish-url",
        "get_model_mall_home_url" => "/v1/model/home-url",
        "get_model_mall_detail_url" => "/v1/model/detail-url",
        "get_design_staffpick" => "/v1/model/staffpick",
        "get_my_token" => "/v1/auth/token",
        "get_my_profile" => "/v1/auth/profile",
        "get_oss_config" => "/v1/model/oss-config",
        "put_rating_picture_oss" => "/v1/model/rating-picture",
        "get_model_mall_rating" => "/v1/model/rating",
        "get_mw_user_preference" => "/v1/makerworld/user-preference",
        "get_mw_user_4ulist" => "/v1/makerworld/user-4ulist",
        "get_hms_snapshot" => "/v1/iot/hms-snapshot",
        _ => "/v1/unsupported",
    }
}

fn default_method(operation: &str) -> &str {
    match operation {
        "connect_server" | "get_model_mall_home_url" | "get_model_publish_url" => "GET",
        _ => "POST",
    }
}

fn timeout_seconds() -> u64 {
    env::var("BAMBU_NETWORK_CLOUD_TIMEOUT_SECS")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(10)
}

fn build_request_body(operation: &str, request: &Value, session: &UserSession) -> Value {
    json!({
        "operation": operation,
        "request": request,
        "user": {
            "id": session.user_id,
            "name": session.user_name,
            "nickname": session.user_nickname,
        },
        "backend_url": session.backend_url,
    })
}

fn extract_body(operation: &str, raw_body: &str) -> String {
    let Ok(json) = serde_json::from_str::<Value>(raw_body) else {
        return raw_body.to_string();
    };

    match operation {
        "request_bind_ticket" => read_string(&json, &["ticket"])
            .or_else(|| read_string(&json, &["data", "ticket"]))
            .unwrap_or_else(|| raw_body.to_string()),
        "get_model_publish_url" | "get_model_mall_home_url" | "get_model_mall_detail_url" => {
            read_string(&json, &["url"])
                .or_else(|| read_string(&json, &["data", "url"]))
                .unwrap_or_else(|| raw_body.to_string())
        }
        _ => raw_body.to_string(),
    }
}

fn extract_int_value(operation: &str, raw_body: &str) -> i32 {
    let Ok(json) = serde_json::from_str::<Value>(raw_body) else {
        return 0;
    };

    match operation {
        "get_user_info" => read_i64(&json, &["identifier"])
            .or_else(|| read_i64(&json, &["id"]))
            .or_else(|| read_i64(&json, &["data", "identifier"]))
            .unwrap_or(0) as i32,
        "get_task_plate_index" => read_i64(&json, &["plate_index"])
            .or_else(|| read_i64(&json, &["data", "plate_index"]))
            .unwrap_or(-1) as i32,
        _ => 0,
    }
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

fn read_i64(node: &Value, path: &[&str]) -> Option<i64> {
    let mut current = node;
    for key in path {
        current = current.get(*key)?;
    }
    match current {
        Value::Number(value) => value.as_i64(),
        Value::String(value) => value.parse().ok(),
        _ => None,
    }
}
