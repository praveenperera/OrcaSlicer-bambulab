mod agent;
mod cloud;
mod discovery;
mod event;
mod lan_mqtt;
mod protocol;
mod source_tls;
mod transport;

use std::cell::RefCell;
use std::ffi::{CStr, CString};
use std::os::raw::{c_char, c_void};
use std::ptr;
use std::sync::atomic::{AtomicU64, Ordering};

use agent::Agent;
use event::{
    EventSink, HttpErrorEvent, LocalConnectEvent, MessageEvent, ServerConnectedEvent,
    ServerErrorEvent, StringEvent, UserLoginEvent,
};
use serde_json::Value;

const ERR_INVALID_HANDLE: i32 = -1;
const ERR_CONNECT_FAILED: i32 = -2;
const ERR_INVALID_RESULT: i32 = -19;
const ERR_PRINT_LP_UPLOAD_FTP_FAILED: i32 = -4020;
const ERR_PRINT_LP_PUBLISH_MSG_FAILED: i32 = -4030;
const ERR_PRINT_SG_UPLOAD_FTP_FAILED: i32 = -5010;

const VERSION: &[u8] = b"02.05.02.58\0";
static NEXT_AGENT_ID: AtomicU64 = AtomicU64::new(1);

thread_local! {
    static RETURN_STRING: RefCell<CString> = RefCell::new(CString::new("").expect("static string has no nul"));
}

fn read_string(value: *const c_char) -> String {
    if value.is_null() {
        return String::new();
    }

    unsafe { CStr::from_ptr(value) }
        .to_string_lossy()
        .into_owned()
}

fn return_string(value: impl Into<String>) -> *const c_char {
    let value = value.into().replace('\0', "");
    RETURN_STRING.with(|slot| {
        *slot.borrow_mut() = CString::new(value).expect("nul bytes were removed");
        slot.borrow().as_ptr()
    })
}

#[no_mangle]
pub extern "C" fn brs_get_version() -> *const c_char {
    VERSION.as_ptr().cast()
}

#[no_mangle]
pub extern "C" fn brs_create_agent(log_dir: *const c_char) -> usize {
    let id = NEXT_AGENT_ID.fetch_add(1, Ordering::Relaxed);
    Box::into_raw(Box::new(Agent::new(id, read_string(log_dir)))) as usize
}

#[no_mangle]
pub extern "C" fn brs_destroy_agent(agent: usize) -> i32 {
    if agent == 0 {
        return ERR_INVALID_HANDLE;
    }

    unsafe {
        drop(Box::from_raw(agent as *mut Agent));
    }
    0
}

fn agent_ref(agent: usize) -> Option<&'static Agent> {
    if agent == 0 {
        return None;
    }

    unsafe { (agent as *const Agent).as_ref() }
}

fn agent_mut(agent: usize) -> Option<&'static mut Agent> {
    if agent == 0 {
        return None;
    }

    unsafe { (agent as *mut Agent).as_mut() }
}

#[no_mangle]
pub extern "C" fn brs_init_log(agent: usize) -> i32 {
    let Some(agent) = agent_mut(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.init_log();
    0
}

#[no_mangle]
pub extern "C" fn brs_set_config_dir(agent: usize, config_dir: *const c_char) -> i32 {
    let Some(agent) = agent_mut(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.set_config_dir(read_string(config_dir));
    0
}

#[no_mangle]
pub extern "C" fn brs_set_country_code(agent: usize, country_code: *const c_char) -> i32 {
    let Some(agent) = agent_mut(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.set_country_code(read_string(country_code));
    0
}

#[no_mangle]
pub extern "C" fn brs_start(agent: usize) -> i32 {
    let Some(agent) = agent_mut(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.start();
    0
}

#[no_mangle]
pub extern "C" fn brs_cloud_configured(agent: usize) -> bool {
    agent_ref(agent).is_some_and(Agent::cloud_configured)
}

#[no_mangle]
pub extern "C" fn brs_cloud_is_server_connected(agent: usize) -> bool {
    agent_ref(agent).is_some_and(Agent::is_server_connected)
}

#[no_mangle]
/// Calls the configured cloud-service HTTP adapter
///
/// # Safety
/// Pointer arguments must be null or valid for writes of their pointed type, and input C strings must be valid NUL-terminated strings
pub unsafe extern "C" fn brs_cloud_call(
    agent: usize,
    operation: *const c_char,
    request_json: *const c_char,
    http_code: *mut u32,
    result_code: *mut i32,
    int_value: *mut i32,
) -> *const c_char {
    let Some(agent) = agent_mut(agent) else {
        unsafe {
            if !http_code.is_null() {
                *http_code = 0;
            }
            if !result_code.is_null() {
                *result_code = ERR_INVALID_HANDLE;
            }
            if !int_value.is_null() {
                *int_value = 0;
            }
        }
        return return_string("");
    };

    let request = serde_json::from_str::<Value>(&read_string(request_json))
        .unwrap_or_else(|_| Value::Object(Default::default()));
    let response = agent.cloud_call(&read_string(operation), &request);
    unsafe {
        if !http_code.is_null() {
            *http_code = response.http_code;
        }
        if !result_code.is_null() {
            *result_code = response.result;
        }
        if !int_value.is_null() {
            *int_value = response.int_value;
        }
    }
    return_string(response.body)
}

#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub extern "C" fn brs_set_event_sink(
    agent: usize,
    user: *mut c_void,
    on_ssdp_msg: StringEvent,
    on_user_login: UserLoginEvent,
    on_printer_connected: StringEvent,
    on_server_connected: ServerConnectedEvent,
    on_http_error: HttpErrorEvent,
    on_subscribe_failure: StringEvent,
    on_message: MessageEvent,
    on_user_message: MessageEvent,
    on_local_connect: LocalConnectEvent,
    on_local_message: MessageEvent,
    on_server_error: ServerErrorEvent,
) -> i32 {
    let Some(agent) = agent_mut(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.set_event_sink(EventSink::new(
        user,
        on_ssdp_msg,
        on_user_login,
        on_printer_connected,
        on_server_connected,
        on_http_error,
        on_subscribe_failure,
        on_message,
        on_user_message,
        on_local_connect,
        on_local_message,
        on_server_error,
    ));
    0
}

#[no_mangle]
pub extern "C" fn brs_change_user(agent: usize, user_info: *const c_char) -> i32 {
    let Some(agent) = agent_mut(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.change_user(read_string(user_info))
}

#[no_mangle]
pub extern "C" fn brs_user_logout(agent: usize) -> i32 {
    let Some(agent) = agent_mut(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.user_logout()
}

#[no_mangle]
pub extern "C" fn brs_is_user_login(agent: usize) -> bool {
    agent_ref(agent).is_some_and(Agent::is_user_login)
}

#[no_mangle]
pub extern "C" fn brs_get_user_id(agent: usize) -> *const c_char {
    agent_ref(agent)
        .map(|agent| return_string(agent.user_id()))
        .unwrap_or(ptr::null())
}

#[no_mangle]
pub extern "C" fn brs_get_user_name(agent: usize) -> *const c_char {
    agent_ref(agent)
        .map(|agent| return_string(agent.user_name()))
        .unwrap_or(ptr::null())
}

#[no_mangle]
pub extern "C" fn brs_get_user_nickname(agent: usize) -> *const c_char {
    agent_ref(agent)
        .map(|agent| return_string(agent.user_nickname()))
        .unwrap_or(ptr::null())
}

#[no_mangle]
pub extern "C" fn brs_get_user_avatar(agent: usize) -> *const c_char {
    agent_ref(agent)
        .map(|agent| return_string(agent.user_avatar()))
        .unwrap_or(ptr::null())
}

#[no_mangle]
pub extern "C" fn brs_build_login_cmd(agent: usize) -> *const c_char {
    agent_ref(agent)
        .map(|agent| return_string(agent.build_login_cmd()))
        .unwrap_or(ptr::null())
}

#[no_mangle]
pub extern "C" fn brs_build_login_info(agent: usize) -> *const c_char {
    agent_ref(agent)
        .map(|agent| return_string(agent.build_login_info()))
        .unwrap_or(ptr::null())
}

#[no_mangle]
pub extern "C" fn brs_build_logout_cmd(agent: usize) -> *const c_char {
    agent_ref(agent)
        .map(|agent| return_string(agent.build_logout_cmd()))
        .unwrap_or(ptr::null())
}

#[no_mangle]
pub extern "C" fn brs_start_discovery(agent: usize, start: bool, sending: bool) -> bool {
    let Some(agent) = agent_mut(agent) else {
        return false;
    };
    agent.start_discovery(start, sending)
}

#[no_mangle]
pub extern "C" fn brs_connect_printer(
    agent: usize,
    dev_id: *const c_char,
    dev_ip: *const c_char,
    username: *const c_char,
    password: *const c_char,
    use_ssl: bool,
) -> i32 {
    let Some(agent) = agent_mut(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.connect_printer(
        read_string(dev_id),
        read_string(dev_ip),
        read_string(username),
        read_string(password),
        use_ssl,
    )
}

#[no_mangle]
pub extern "C" fn brs_disconnect_printer(agent: usize) -> i32 {
    let Some(agent) = agent_mut(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.disconnect_printer()
}

#[no_mangle]
pub extern "C" fn brs_send_message(
    agent: usize,
    dev_id: *const c_char,
    message: *const c_char,
    qos: i32,
    flag: i32,
) -> i32 {
    let Some(agent) = agent_mut(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.send_message(read_string(dev_id), read_string(message), qos, flag)
}

#[no_mangle]
pub extern "C" fn brs_send_message_to_printer(
    agent: usize,
    dev_id: *const c_char,
    message: *const c_char,
    qos: i32,
    flag: i32,
) -> i32 {
    let Some(agent) = agent_mut(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.send_message_to_printer(read_string(dev_id), read_string(message), qos, flag)
}

#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub extern "C" fn brs_start_sdcard_print(
    agent: usize,
    dev_id: *const c_char,
    dev_ip: *const c_char,
    username: *const c_char,
    password: *const c_char,
    use_ssl_for_mqtt: bool,
    sequence_id: *const c_char,
    plate_index: i32,
    file_path: *const c_char,
    file_md5: *const c_char,
    bed_type: *const c_char,
    bed_leveling: bool,
    flow_cali: bool,
    vibration_cali: bool,
    layer_inspect: bool,
    timelapse: bool,
    use_ams: bool,
    ams_mapping: *const c_char,
) -> i32 {
    let Some(agent) = agent_mut(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.start_sdcard_print(
        read_string(dev_id),
        read_string(dev_ip),
        read_string(username),
        read_string(password),
        use_ssl_for_mqtt,
        read_string(sequence_id),
        plate_index,
        read_string(file_path),
        read_string(file_md5),
        read_string(bed_type),
        bed_leveling,
        flow_cali,
        vibration_cali,
        layer_inspect,
        timelapse,
        use_ams,
        read_string(ams_mapping),
    )
}

#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub extern "C" fn brs_start_local_print(
    agent: usize,
    dev_id: *const c_char,
    dev_ip: *const c_char,
    username: *const c_char,
    password: *const c_char,
    use_ssl_for_ftp: bool,
    use_ssl_for_mqtt: bool,
    sequence_id: *const c_char,
    plate_index: i32,
    local_file: *const c_char,
    remote_name: *const c_char,
    file_md5: *const c_char,
    bed_type: *const c_char,
    bed_leveling: bool,
    flow_cali: bool,
    vibration_cali: bool,
    layer_inspect: bool,
    timelapse: bool,
    use_ams: bool,
    ams_mapping: *const c_char,
) -> i32 {
    let Some(agent) = agent_mut(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.start_local_print(
        read_string(dev_id),
        read_string(dev_ip),
        read_string(username),
        read_string(password),
        use_ssl_for_ftp,
        use_ssl_for_mqtt,
        read_string(sequence_id),
        plate_index,
        read_string(local_file),
        read_string(remote_name),
        read_string(file_md5),
        read_string(bed_type),
        bed_leveling,
        flow_cali,
        vibration_cali,
        layer_inspect,
        timelapse,
        use_ams,
        read_string(ams_mapping),
    )
}

#[no_mangle]
pub extern "C" fn brs_upload_file_to_printer(
    agent: usize,
    dev_ip: *const c_char,
    username: *const c_char,
    password: *const c_char,
    use_ssl_for_ftp: bool,
    local_file: *const c_char,
    remote_name: *const c_char,
) -> i32 {
    let Some(agent) = agent_mut(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.upload_file_to_printer(
        read_string(dev_ip),
        read_string(username),
        read_string(password),
        use_ssl_for_ftp,
        read_string(local_file),
        read_string(remote_name),
    )
}

#[no_mangle]
pub extern "C" fn brs_internal_emit_ssdp(agent: usize, dev_info: *const c_char) -> i32 {
    let Some(agent) = agent_ref(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.emit_ssdp(&read_string(dev_info));
    0
}

#[no_mangle]
pub extern "C" fn brs_internal_emit_printer_connected(agent: usize, topic: *const c_char) -> i32 {
    let Some(agent) = agent_ref(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.emit_printer_connected(&read_string(topic));
    0
}

#[no_mangle]
pub extern "C" fn brs_internal_emit_message(
    agent: usize,
    dev_id: *const c_char,
    message: *const c_char,
) -> i32 {
    let Some(agent) = agent_ref(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.emit_message(&read_string(dev_id), &read_string(message));
    0
}

#[no_mangle]
pub extern "C" fn brs_internal_emit_local_connect(
    agent: usize,
    status: i32,
    dev_id: *const c_char,
    message: *const c_char,
) -> i32 {
    let Some(agent) = agent_ref(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.emit_local_connect(status, &read_string(dev_id), &read_string(message));
    0
}

#[no_mangle]
pub extern "C" fn brs_internal_emit_local_message(
    agent: usize,
    dev_id: *const c_char,
    message: *const c_char,
) -> i32 {
    let Some(agent) = agent_ref(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.emit_local_message(&read_string(dev_id), &read_string(message));
    0
}

#[no_mangle]
pub extern "C" fn brs_internal_emit_server_error(
    agent: usize,
    url: *const c_char,
    status: i32,
) -> i32 {
    let Some(agent) = agent_ref(agent) else {
        return ERR_INVALID_HANDLE;
    };
    agent.emit_server_error(&read_string(url), status);
    0
}
