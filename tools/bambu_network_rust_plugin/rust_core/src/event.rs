use std::ffi::CString;
use std::os::raw::{c_char, c_void};

pub(crate) type StringEvent = Option<extern "C" fn(*mut c_void, *const c_char)>;
pub(crate) type MessageEvent = Option<extern "C" fn(*mut c_void, *const c_char, *const c_char)>;
pub(crate) type LocalConnectEvent =
    Option<extern "C" fn(*mut c_void, i32, *const c_char, *const c_char)>;
pub(crate) type UserLoginEvent = Option<extern "C" fn(*mut c_void, i32, bool)>;
pub(crate) type ServerConnectedEvent = Option<extern "C" fn(*mut c_void, i32, i32)>;
pub(crate) type HttpErrorEvent = Option<extern "C" fn(*mut c_void, u32, *const c_char)>;
pub(crate) type ServerErrorEvent = Option<extern "C" fn(*mut c_void, *const c_char, i32)>;

#[derive(Clone, Copy, Default)]
pub(crate) struct EventSink {
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
}

// callbacks are joined before the owning agent is destroyed
unsafe impl Send for EventSink {}

impl EventSink {
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn new(
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
    ) -> Self {
        Self {
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
        }
    }

    pub(crate) fn registered_count(&self) -> usize {
        [
            self.on_ssdp_msg.is_some(),
            self.on_user_login.is_some(),
            self.on_printer_connected.is_some(),
            self.on_server_connected.is_some(),
            self.on_http_error.is_some(),
            self.on_subscribe_failure.is_some(),
            self.on_message.is_some(),
            self.on_user_message.is_some(),
            self.on_local_connect.is_some(),
            self.on_local_message.is_some(),
            self.on_server_error.is_some(),
        ]
        .into_iter()
        .filter(|registered| *registered)
        .count()
    }

    pub(crate) fn emit_ssdp(&self, dev_info: &str) {
        if let Some(callback) = self.on_ssdp_msg {
            let dev_info = cstring(dev_info);
            callback(self.user, dev_info.as_ptr());
        }
    }

    pub(crate) fn emit_printer_connected(&self, topic: &str) {
        if let Some(callback) = self.on_printer_connected {
            let topic = cstring(topic);
            callback(self.user, topic.as_ptr());
        }
    }

    pub(crate) fn emit_message(&self, dev_id: &str, message: &str) {
        if let Some(callback) = self.on_message {
            let dev_id = cstring(dev_id);
            let message = cstring(message);
            callback(self.user, dev_id.as_ptr(), message.as_ptr());
        }
    }

    pub(crate) fn emit_user_login(&self, online_login: i32, login: bool) {
        if let Some(callback) = self.on_user_login {
            callback(self.user, online_login, login);
        }
    }

    pub(crate) fn emit_server_connected(&self, status: i32, http_code: i32) {
        if let Some(callback) = self.on_server_connected {
            callback(self.user, status, http_code);
        }
    }

    pub(crate) fn emit_local_connect(&self, status: i32, dev_id: &str, message: &str) {
        if let Some(callback) = self.on_local_connect {
            let dev_id = cstring(dev_id);
            let message = cstring(message);
            callback(self.user, status, dev_id.as_ptr(), message.as_ptr());
        }
    }

    pub(crate) fn emit_local_message(&self, dev_id: &str, message: &str) {
        if let Some(callback) = self.on_local_message {
            let dev_id = cstring(dev_id);
            let message = cstring(message);
            callback(self.user, dev_id.as_ptr(), message.as_ptr());
        }
    }

    pub(crate) fn emit_server_error(&self, url: &str, status: i32) {
        if let Some(callback) = self.on_server_error {
            let url = cstring(url);
            callback(self.user, url.as_ptr(), status);
        }
    }
}

fn cstring(value: &str) -> CString {
    CString::new(value.replace('\0', "")).expect("nul bytes were removed")
}
