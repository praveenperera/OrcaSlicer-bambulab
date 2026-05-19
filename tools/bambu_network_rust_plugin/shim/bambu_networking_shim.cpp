#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include "bambu_networking_abi.hpp"

extern "C" const char* brs_get_version();
extern "C" std::uintptr_t brs_create_agent(const char* log_dir);
extern "C" int brs_destroy_agent(std::uintptr_t agent);
extern "C" bool brs_is_user_login(std::uintptr_t agent);
extern "C" const char* brs_get_user_id(std::uintptr_t agent);
extern "C" const char* brs_get_user_name(std::uintptr_t agent);
extern "C" const char* brs_get_user_nickname(std::uintptr_t agent);
extern "C" const char* brs_get_user_avatar(std::uintptr_t agent);
extern "C" const char* brs_build_login_cmd(std::uintptr_t agent);
extern "C" const char* brs_build_login_info(std::uintptr_t agent);
extern "C" const char* brs_build_logout_cmd(std::uintptr_t agent);
extern "C" int brs_change_user(std::uintptr_t agent, const char* user_info);
extern "C" int brs_user_logout(std::uintptr_t agent);
extern "C" int brs_init_log(std::uintptr_t agent);
extern "C" int brs_set_config_dir(std::uintptr_t agent, const char* config_dir);
extern "C" int brs_set_country_code(std::uintptr_t agent, const char* country_code);
extern "C" int brs_start(std::uintptr_t agent);
extern "C" bool brs_cloud_configured(std::uintptr_t agent);
extern "C" bool brs_cloud_is_server_connected(std::uintptr_t agent);
extern "C" const char* brs_cloud_call(std::uintptr_t agent,
                                      const char* operation,
                                      const char* request_json,
                                      unsigned int* http_code,
                                      int* result_code,
                                      int* int_value);
extern "C" bool brs_start_discovery(std::uintptr_t agent, bool start, bool sending);
extern "C" int brs_connect_printer(std::uintptr_t agent, const char* dev_id, const char* dev_ip, const char* username, const char* password, bool use_ssl);
extern "C" int brs_disconnect_printer(std::uintptr_t agent);
extern "C" int brs_send_message(std::uintptr_t agent, const char* dev_id, const char* message, int qos, int flag);
extern "C" int brs_send_message_to_printer(std::uintptr_t agent, const char* dev_id, const char* message, int qos, int flag);
extern "C" int brs_start_sdcard_print(std::uintptr_t agent,
                                      const char* dev_id,
                                      const char* dev_ip,
                                      const char* username,
                                      const char* password,
                                      bool use_ssl_for_mqtt,
                                      const char* sequence_id,
                                      int plate_index,
                                      const char* file_path,
                                      const char* file_md5,
                                      const char* bed_type,
                                      bool bed_leveling,
                                      bool flow_cali,
                                      bool vibration_cali,
                                      bool layer_inspect,
                                      bool timelapse,
                                      bool use_ams,
                                      const char* ams_mapping);
extern "C" int brs_start_local_print(std::uintptr_t agent,
                                     const char* dev_id,
                                     const char* dev_ip,
                                     const char* username,
                                     const char* password,
                                     bool use_ssl_for_ftp,
                                     bool use_ssl_for_mqtt,
                                     const char* sequence_id,
                                     int plate_index,
                                     const char* local_file,
                                     const char* remote_name,
                                     const char* file_md5,
                                     const char* bed_type,
                                     bool bed_leveling,
                                     bool flow_cali,
                                     bool vibration_cali,
                                     bool layer_inspect,
                                     bool timelapse,
                                     bool use_ams,
                                     const char* ams_mapping);
extern "C" int brs_upload_file_to_printer(std::uintptr_t agent,
                                          const char* dev_ip,
                                          const char* username,
                                          const char* password,
                                          bool use_ssl_for_ftp,
                                          const char* local_file,
                                          const char* remote_name);
extern "C" int brs_internal_emit_ssdp(std::uintptr_t agent, const char* dev_info);
extern "C" int brs_internal_emit_printer_connected(std::uintptr_t agent, const char* topic);
extern "C" int brs_internal_emit_message(std::uintptr_t agent, const char* dev_id, const char* message);
extern "C" int brs_internal_emit_local_connect(std::uintptr_t agent, int status, const char* dev_id, const char* message);
extern "C" int brs_internal_emit_local_message(std::uintptr_t agent, const char* dev_id, const char* message);
extern "C" int brs_internal_emit_server_error(std::uintptr_t agent, const char* url, int status);

using BrsStringEvent = void (*)(void*, const char*);
using BrsMessageEvent = void (*)(void*, const char*, const char*);
using BrsLocalConnectEvent = void (*)(void*, int, const char*, const char*);
using BrsUserLoginEvent = void (*)(void*, int, bool);
using BrsServerConnectedEvent = void (*)(void*, int, int);
using BrsHttpErrorEvent = void (*)(void*, unsigned, const char*);
using BrsServerErrorEvent = void (*)(void*, const char*, int);

extern "C" int brs_set_event_sink(
    std::uintptr_t agent,
    void* user,
    BrsStringEvent on_ssdp_msg,
    BrsUserLoginEvent on_user_login,
    BrsStringEvent on_printer_connected,
    BrsServerConnectedEvent on_server_connected,
    BrsHttpErrorEvent on_http_error,
    BrsStringEvent on_subscribe_failure,
    BrsMessageEvent on_message,
    BrsMessageEvent on_user_message,
    BrsLocalConnectEvent on_local_connect,
    BrsMessageEvent on_local_message,
    BrsServerErrorEvent on_server_error);

namespace {

constexpr int unsupported_result = Slic3r::BAMBU_NETWORK_ERR_CONNECT_FAILED;
constexpr int canceled_result = -18;
constexpr int printing_stage_create = 0;
constexpr int printing_stage_upload = 1;
constexpr int printing_stage_sending = 3;
constexpr int printing_stage_finished = 6;
constexpr int printing_stage_error = 7;
constexpr int ft_ok = 0;
constexpr int ft_einval = -1;
constexpr int ft_estate = -2;
constexpr int ft_eio = -3;
constexpr int ft_etimeout = -4;
constexpr int ft_ecancelled = -5;
constexpr int ft_exception = -6;

struct FtJobResult {
    int ec{};
    int resp_ec{};
    const char* json{};
    const void* bin{};
    std::uint32_t bin_size{};
};

struct FtJobMsg {
    int kind{};
    const char* json{};
};

using FtConnectionCallback = void (*)(void*, int, int, const char*);
using FtStatusCallback = void (*)(void*, int, int, int, const char*);
using FtResultCallback = void (*)(void*, FtJobResult);
using FtMsgCallback = void (*)(void*, FtJobMsg);

struct FtTunnel {
    int ref_count{1};
    std::string url;
    std::string dev_ip;
    std::string username;
    std::string password;
    int port{};
    int status{};
    bool connected{};
    FtStatusCallback status_callback{};
    void* status_user{};
};

struct FtJob {
    int ref_count{1};
    std::string params_json;
    bool cancelled{};
    bool completed{};
    int ec{ft_estate};
    int resp_ec{ft_estate};
    std::string result_json;
    std::vector<unsigned char> result_bin;
    std::vector<std::pair<int, std::string>> messages;
    FtResultCallback result_callback{};
    void* result_user{};
    FtMsgCallback msg_callback{};
    void* msg_user{};
};

struct CameraEndpoint {
    std::string dev_ip;
    std::string username;
    std::string password;
    bool rtsps{true};
};

std::string from_cstr(const char* value)
{
    return value ? std::string(value) : std::string();
}

char from_hex(char ch)
{
    if (ch >= '0' && ch <= '9')
        return static_cast<char>(ch - '0');
    if (ch >= 'a' && ch <= 'f')
        return static_cast<char>(10 + ch - 'a');
    if (ch >= 'A' && ch <= 'F')
        return static_cast<char>(10 + ch - 'A');
    return 0;
}

std::string percent_decode(const std::string& value)
{
    std::string out;
    out.reserve(value.size());
    for (std::size_t i = 0; i < value.size(); ++i) {
        if (value[i] == '%' && i + 2 < value.size()) {
            out.push_back(static_cast<char>((from_hex(value[i + 1]) << 4) | from_hex(value[i + 2])));
            i += 2;
        } else if (value[i] == '+') {
            out.push_back(' ');
        } else {
            out.push_back(value[i]);
        }
    }
    return out;
}

std::map<std::string, std::string> parse_query(const std::string& query)
{
    std::map<std::string, std::string> values;
    std::size_t start = 0;
    while (start <= query.size()) {
        const auto end = query.find('&', start);
        const auto token = query.substr(start, end == std::string::npos ? std::string::npos : end - start);
        if (!token.empty()) {
            const auto separator = token.find('=');
            const auto key = percent_decode(token.substr(0, separator));
            const auto value = separator == std::string::npos ? std::string() : percent_decode(token.substr(separator + 1));
            values[key] = value;
        }
        if (end == std::string::npos)
            break;
        start = end + 1;
    }
    return values;
}

bool parse_local_tunnel_url(FtTunnel& tunnel, const char* url)
{
    tunnel.url = from_cstr(url);
    const std::string prefix = "bambu:///local/";
    if (tunnel.url.rfind(prefix, 0) != 0)
        return false;

    const auto rest_start = prefix.size();
    const auto query_start = tunnel.url.find('?', rest_start);
    tunnel.dev_ip = tunnel.url.substr(rest_start, query_start == std::string::npos ? std::string::npos : query_start - rest_start);
    while (!tunnel.dev_ip.empty() && tunnel.dev_ip.back() == '.')
        tunnel.dev_ip.pop_back();
    if (tunnel.dev_ip.empty())
        return false;

    if (query_start == std::string::npos)
        return true;

    const auto query = parse_query(tunnel.url.substr(query_start + 1));
    if (const auto it = query.find("user"); it != query.end())
        tunnel.username = it->second;
    if (const auto it = query.find("passwd"); it != query.end())
        tunnel.password = it->second;
    if (const auto it = query.find("port"); it != query.end()) {
        try {
            tunnel.port = std::stoi(it->second);
        } catch (...) {
            tunnel.port = 0;
        }
    }
    return true;
}

char* duplicate_for_ffi(const std::string& value)
{
    auto* buffer = static_cast<char*>(std::malloc(value.size() + 1));
    if (!buffer)
        return nullptr;
    std::memcpy(buffer, value.c_str(), value.size() + 1);
    return buffer;
}

std::string basename_from_path(const std::string& path)
{
    const auto separator = path.find_last_of("/\\");
    return separator == std::string::npos ? path : path.substr(separator + 1);
}

std::string json_string_value(const nlohmann::json& json, const char* key)
{
    const auto it = json.find(key);
    if (it == json.end() || !it->is_string())
        return {};
    return it->get<std::string>();
}

void retain_tunnel(FtTunnel* tunnel)
{
    if (tunnel)
        ++tunnel->ref_count;
}

void release_tunnel(FtTunnel* tunnel)
{
    if (tunnel && --tunnel->ref_count == 0)
        delete tunnel;
}

void retain_job(FtJob* job)
{
    if (job)
        ++job->ref_count;
}

void release_job(FtJob* job)
{
    if (job && --job->ref_count == 0)
        delete job;
}

void emit_tunnel_status(FtTunnel& tunnel, int new_status, int error, const char* message)
{
    const int old_status = tunnel.status;
    tunnel.status = new_status;
    if (tunnel.status_callback)
        tunnel.status_callback(tunnel.status_user, old_status, new_status, error, message);
}

FtJobResult make_result_payload(const FtJob& job)
{
    FtJobResult result;
    result.ec = job.ec;
    result.resp_ec = job.resp_ec;
    result.json = duplicate_for_ffi(job.result_json);
    if (!job.result_bin.empty()) {
        auto* bin = static_cast<unsigned char*>(std::malloc(job.result_bin.size()));
        if (bin) {
            std::memcpy(bin, job.result_bin.data(), job.result_bin.size());
            result.bin = bin;
            result.bin_size = static_cast<std::uint32_t>(job.result_bin.size());
        }
    }
    return result;
}

FtJobMsg make_msg_payload(int kind, const std::string& json)
{
    return FtJobMsg{kind, duplicate_for_ffi(json)};
}

void complete_job(FtJob& job, int ec, int resp_ec, std::string json)
{
    if (job.cancelled) {
        ec = ft_ecancelled;
        resp_ec = ft_ecancelled;
        json = R"({"error":"cancelled"})";
    }
    job.completed = true;
    job.ec = ec;
    job.resp_ec = resp_ec;
    job.result_json = std::move(json);
    if (job.result_callback) {
        auto result = make_result_payload(job);
        job.result_callback(job.result_user, result);
    }
}

void emit_job_message(FtJob& job, int kind, std::string json)
{
    job.messages.emplace_back(kind, json);
    if (job.msg_callback) {
        auto message = make_msg_payload(kind, json);
        job.msg_callback(job.msg_user, message);
    }
}

int upload_with_tunnel(const FtTunnel& tunnel, const std::string& file_path, const std::string& remote_name)
{
    const auto agent = brs_create_agent("");
    if (agent == 0)
        return ft_eio;
    const int result = brs_upload_file_to_printer(
        agent,
        tunnel.dev_ip.c_str(),
        tunnel.username.empty() ? "bblp" : tunnel.username.c_str(),
        tunnel.password.c_str(),
        false,
        file_path.c_str(),
        remote_name.c_str());
    brs_destroy_agent(agent);
    return result == 0 ? ft_ok : ft_eio;
}

void run_file_transfer_job(FtTunnel& tunnel, FtJob& job)
{
    nlohmann::json params;
    try {
        params = nlohmann::json::parse(job.params_json.empty() ? "{}" : job.params_json);
    } catch (...) {
        complete_job(job, ft_einval, ft_einval, R"({"error":"invalid job json"})");
        return;
    }

    const int command = params.value("cmd_type", 0);
    if (command == 7) {
        complete_job(job, ft_ok, ft_ok, R"(["emmc","sdcard"])");
        return;
    }

    if (command != 5) {
        complete_job(job, ft_estate, ft_estate, R"({"error":"unsupported command"})");
        return;
    }

    const std::string file_path = json_string_value(params, "file_path");
    std::string remote_name = json_string_value(params, "dest_name");
    if (remote_name.empty())
        remote_name = basename_from_path(file_path);
    if (file_path.empty() || remote_name.empty()) {
        complete_job(job, ft_einval, ft_einval, R"({"error":"missing file_path or dest_name"})");
        return;
    }

    emit_job_message(job, 0, R"({"progress":0})");
    const int upload_result = upload_with_tunnel(tunnel, file_path, remote_name);
    if (upload_result == ft_ok) {
        emit_job_message(job, 0, R"({"progress":100})");
        complete_job(job, ft_ok, ft_ok, R"({})");
        return;
    }
    complete_job(job, ft_eio, ft_eio, R"({"error":"upload failed"})");
}

struct ShimAgent {
    std::uintptr_t rust_agent{};
    Slic3r::OnMsgArrivedFn on_ssdp_msg;
    Slic3r::OnUserLoginFn on_user_login;
    Slic3r::OnPrinterConnectedFn on_printer_connected;
    Slic3r::OnServerConnectedFn on_server_connected;
    Slic3r::OnHttpErrorFn on_http_error;
    Slic3r::GetCountryCodeFn get_country_code;
    Slic3r::GetSubscribeFailureFn on_subscribe_failure;
    Slic3r::OnMessageFn on_message;
    Slic3r::OnMessageFn on_user_message;
    Slic3r::OnLocalConnectedFn on_local_connect;
    Slic3r::OnMessageFn on_local_message;
    Slic3r::QueueOnMainFn queue_on_main;
    Slic3r::OnServerErrFn on_server_error;
    std::map<std::string, CameraEndpoint> camera_endpoints;
};

ShimAgent* shim_agent(void* agent)
{
    return static_cast<ShimAgent*>(agent);
}

std::uintptr_t rust_agent(void* agent)
{
    auto* shim = shim_agent(agent);
    return shim ? shim->rust_agent : 0;
}

int result_for_agent(void* agent)
{
    return agent ? unsupported_result : Slic3r::BAMBU_NETWORK_ERR_INVALID_HANDLE;
}

bool env_flag_enabled(const char* name)
{
    const char* value = std::getenv(name);
    return value && (std::strcmp(value, "1") == 0 || std::strcmp(value, "true") == 0 || std::strcmp(value, "TRUE") == 0);
}

bool synthetic_cloud_service_enabled()
{
    return env_flag_enabled("BAMBU_NETWORK_ENABLE_SYNTHETIC_CLOUD_SERVICE");
}

bool configured_cloud_service_enabled(void* agent)
{
    return brs_cloud_configured(rust_agent(agent));
}

int result_for_cloud_service(void* agent)
{
    if (!agent)
        return Slic3r::BAMBU_NETWORK_ERR_INVALID_HANDLE;
    return synthetic_cloud_service_enabled() || configured_cloud_service_enabled(agent) ? 0 : unsupported_result;
}

void set_http_json(unsigned int* http_code, std::string* http_body, const std::string& body)
{
    if (http_code)
        *http_code = synthetic_cloud_service_enabled() ? 200 : 0;
    if (http_body)
        *http_body = synthetic_cloud_service_enabled() ? body : std::string();
}

int call_configured_cloud_service(void* agent,
                                  const char* operation,
                                  const nlohmann::json& request,
                                  unsigned int* http_code,
                                  std::string* body,
                                  int* int_value = nullptr)
{
    if (!agent)
        return Slic3r::BAMBU_NETWORK_ERR_INVALID_HANDLE;
    if (!configured_cloud_service_enabled(agent))
        return unsupported_result;

    int result_code = unsupported_result;
    int value = 0;
    std::string request_json = request.dump();
    const char* response = brs_cloud_call(rust_agent(agent), operation, request_json.c_str(), http_code, &result_code, &value);
    if (body)
        *body = response ? response : "";
    if (int_value)
        *int_value = value;
    return result_code;
}

int assign_service_url(void* agent, std::string* url, const std::string& operation, const std::string& value, nlohmann::json request = nlohmann::json::object())
{
    if (configured_cloud_service_enabled(agent)) {
        std::string body;
        const int result = call_configured_cloud_service(agent, operation.c_str(), request, nullptr, &body);
        if (url)
            *url = body;
        return result;
    }
    if (url)
        *url = synthetic_cloud_service_enabled() ? value : std::string();
    return result_for_cloud_service(agent);
}

std::string project_file_path(const Slic3r::PrintParams& params)
{
    if (!params.dst_file.empty())
        return params.dst_file;
    if (!params.ftp_file.empty())
        return params.ftp_file;
    return params.filename;
}

std::string project_remote_name(const Slic3r::PrintParams& params)
{
    if (!params.ftp_file.empty())
        return params.ftp_file;
    if (!params.dst_file.empty())
        return params.dst_file;
    return {};
}

std::string base_dev_id(const std::string& dev_id)
{
    const auto separator = dev_id.find('|');
    return separator == std::string::npos ? dev_id : dev_id.substr(0, separator);
}

void remember_camera_endpoint(void* agent, const std::string& dev_id, const std::string& dev_ip, const std::string& username, const std::string& password, bool rtsps)
{
    auto* shim = shim_agent(agent);
    const std::string key = base_dev_id(dev_id);
    if (!shim || key.empty() || dev_ip.empty() || username.empty() || password.empty())
        return;

    shim->camera_endpoints[key] = CameraEndpoint{dev_ip, username, password, rtsps};
}

std::string camera_url_for_endpoint(const CameraEndpoint& endpoint)
{
    const char* proto = endpoint.rtsps ? "rtsps" : "rtsp";
    std::string url = "bambu:///";
    url += proto;
    url += "___";
    url += endpoint.username;
    url += ":";
    url += endpoint.password;
    url += "@";
    url += endpoint.dev_ip;
    url += "/streaming/live/1?proto=";
    url += proto;
    return url;
}

int get_camera_url_common(void* agent, const std::string& dev_id, const std::function<void(std::string)>& callback)
{
    auto* shim = shim_agent(agent);
    if (!shim)
        return Slic3r::BAMBU_NETWORK_ERR_INVALID_HANDLE;

    const auto it = shim->camera_endpoints.find(base_dev_id(dev_id));
    if (it == shim->camera_endpoints.end())
        return unsupported_result;

    if (callback)
        callback(camera_url_for_endpoint(it->second));
    return 0;
}

int start_local_print_common(void* agent, const Slic3r::PrintParams& params)
{
    const std::string remote_name = project_remote_name(params);
    const int result = brs_start_local_print(rust_agent(agent),
                                             params.dev_id.c_str(),
                                             params.dev_ip.c_str(),
                                             params.username.c_str(),
                                             params.password.c_str(),
                                             params.use_ssl_for_ftp,
                                             params.use_ssl_for_mqtt,
                                             "0",
                                             params.plate_index,
                                             params.filename.c_str(),
                                             remote_name.c_str(),
                                             params.ftp_file_md5.c_str(),
                                             params.task_bed_type.c_str(),
                                             params.task_bed_leveling,
                                             params.task_flow_cali,
                                             params.task_vibration_cali,
                                             params.task_layer_inspect,
                                             params.task_record_timelapse,
                                             params.task_use_ams,
                                             params.ams_mapping.c_str());
    if (result == 0)
        remember_camera_endpoint(agent, params.dev_id, params.dev_ip, params.username, params.password, params.use_ssl_for_mqtt);
    return result;
}

int upload_file_to_printer(void* agent, const Slic3r::PrintParams& params)
{
    const std::string remote_name = project_remote_name(params);
    return brs_upload_file_to_printer(rust_agent(agent),
                                      params.dev_ip.c_str(),
                                      params.username.c_str(),
                                      params.password.c_str(),
                                      params.use_ssl_for_ftp,
                                      params.filename.c_str(),
                                      remote_name.c_str());
}

bool is_cancelled(const Slic3r::WasCancelledFn& cancel)
{
    return cancel && cancel();
}

void emit_print_status(const Slic3r::OnUpdateStatusFn& update, int stage, int code, const std::string& message)
{
    if (update)
        update(stage, code, message);
}

int finish_print_job(int result, const Slic3r::OnUpdateStatusFn& update, const std::string& success_message)
{
    if (result == 0) {
        emit_print_status(update, printing_stage_finished, 100, success_message);
        return result;
    }

    emit_print_status(update, printing_stage_error, result, {});
    return result;
}

template <typename Callback>
int store_callback(void* agent, Callback ShimAgent::*slot, Callback fn)
{
    auto* shim = shim_agent(agent);
    if (!shim)
        return Slic3r::BAMBU_NETWORK_ERR_INVALID_HANDLE;
    shim->*slot = std::move(fn);
    return 0;
}

void emit_on_ssdp_msg(void* user, const char* dev_info)
{
    auto* shim = static_cast<ShimAgent*>(user);
    if (shim && shim->on_ssdp_msg)
        shim->on_ssdp_msg(from_cstr(dev_info));
}

void emit_on_user_login(void* user, int online_login, bool login)
{
    auto* shim = static_cast<ShimAgent*>(user);
    if (shim && shim->on_user_login)
        shim->on_user_login(online_login, login);
}

void emit_on_printer_connected(void* user, const char* topic)
{
    auto* shim = static_cast<ShimAgent*>(user);
    if (shim && shim->on_printer_connected)
        shim->on_printer_connected(from_cstr(topic));
}

void emit_on_server_connected(void* user, int return_code, int reason_code)
{
    auto* shim = static_cast<ShimAgent*>(user);
    if (shim && shim->on_server_connected)
        shim->on_server_connected(return_code, reason_code);
}

void emit_on_http_error(void* user, unsigned http_code, const char* http_body)
{
    auto* shim = static_cast<ShimAgent*>(user);
    if (shim && shim->on_http_error)
        shim->on_http_error(http_code, from_cstr(http_body));
}

void emit_on_subscribe_failure(void* user, const char* topic)
{
    auto* shim = static_cast<ShimAgent*>(user);
    if (shim && shim->on_subscribe_failure)
        shim->on_subscribe_failure(from_cstr(topic));
}

void emit_on_message(void* user, const char* dev_id, const char* message)
{
    auto* shim = static_cast<ShimAgent*>(user);
    if (shim && shim->on_message)
        shim->on_message(from_cstr(dev_id), from_cstr(message));
}

void emit_on_user_message(void* user, const char* dev_id, const char* message)
{
    auto* shim = static_cast<ShimAgent*>(user);
    if (shim && shim->on_user_message)
        shim->on_user_message(from_cstr(dev_id), from_cstr(message));
}

void emit_on_local_connect(void* user, int status, const char* dev_id, const char* message)
{
    auto* shim = static_cast<ShimAgent*>(user);
    if (shim && shim->on_local_connect)
        shim->on_local_connect(status, from_cstr(dev_id), from_cstr(message));
}

void emit_on_local_message(void* user, const char* dev_id, const char* message)
{
    auto* shim = static_cast<ShimAgent*>(user);
    if (shim && shim->on_local_message)
        shim->on_local_message(from_cstr(dev_id), from_cstr(message));
}

void emit_on_server_error(void* user, const char* url, int status)
{
    auto* shim = static_cast<ShimAgent*>(user);
    if (shim && shim->on_server_error)
        shim->on_server_error(from_cstr(url), status);
}

}

extern "C" std::string bambu_network_get_version()
{
    return from_cstr(brs_get_version());
}

extern "C" void* bambu_network_create_agent(std::string log_dir)
{
    const auto rust = brs_create_agent(log_dir.c_str());
    if (rust == 0)
        return nullptr;
    auto* shim = new ShimAgent();
    shim->rust_agent = rust;
    brs_set_event_sink(
        rust,
        shim,
        emit_on_ssdp_msg,
        emit_on_user_login,
        emit_on_printer_connected,
        emit_on_server_connected,
        emit_on_http_error,
        emit_on_subscribe_failure,
        emit_on_message,
        emit_on_user_message,
        emit_on_local_connect,
        emit_on_local_message,
        emit_on_server_error);
    return shim;
}

extern "C" int bambu_network_destroy_agent(void* agent)
{
    auto* shim = shim_agent(agent);
    if (!shim)
        return Slic3r::BAMBU_NETWORK_ERR_INVALID_HANDLE;
    const int result = brs_destroy_agent(shim->rust_agent);
    delete shim;
    return result;
}

extern "C" bool bambu_network_is_user_login(void* agent)
{
    return brs_is_user_login(rust_agent(agent));
}

extern "C" std::string bambu_network_get_user_id(void* agent)
{
    return from_cstr(brs_get_user_id(rust_agent(agent)));
}

extern "C" std::string bambu_network_get_user_name(void* agent)
{
    return from_cstr(brs_get_user_name(rust_agent(agent)));
}

extern "C" std::string bambu_network_get_user_nickanme(void* agent)
{
    return from_cstr(brs_get_user_nickname(rust_agent(agent)));
}

extern "C" std::string bambu_network_build_login_cmd(void* agent)
{
    return from_cstr(brs_build_login_cmd(rust_agent(agent)));
}

extern "C" std::string bambu_network_build_login_info(void* agent)
{
    return from_cstr(brs_build_login_info(rust_agent(agent)));
}

extern "C" std::string bambu_network_build_logout_cmd(void* agent)
{
    return from_cstr(brs_build_logout_cmd(rust_agent(agent)));
}

extern "C" int bambu_network_init_log(void* agent)
{
    return brs_init_log(rust_agent(agent));
}

extern "C" int bambu_network_set_config_dir(void* agent, std::string config_dir)
{
    return brs_set_config_dir(rust_agent(agent), config_dir.c_str());
}

extern "C" int bambu_network_set_country_code(void* agent, std::string country_code)
{
    return brs_set_country_code(rust_agent(agent), country_code.c_str());
}

extern "C" int bambu_network_start(void* agent)
{
    return brs_start(rust_agent(agent));
}

extern "C" bool bambu_network_check_debug_consistent(bool)
{
    return true;
}

extern "C" int bambu_network_set_cert_file(void* agent, std::string, std::string)
{
    return agent ? 0 : Slic3r::BAMBU_NETWORK_ERR_INVALID_HANDLE;
}

extern "C" int bambu_network_set_on_ssdp_msg_fn(void* agent, Slic3r::OnMsgArrivedFn fn)
{
    return store_callback(agent, &ShimAgent::on_ssdp_msg, std::move(fn));
}

extern "C" int bambu_network_set_on_user_login_fn(void* agent, Slic3r::OnUserLoginFn fn)
{
    return store_callback(agent, &ShimAgent::on_user_login, std::move(fn));
}

extern "C" int bambu_network_set_on_printer_connected_fn(void* agent, Slic3r::OnPrinterConnectedFn fn)
{
    return store_callback(agent, &ShimAgent::on_printer_connected, std::move(fn));
}

extern "C" int bambu_network_set_on_server_connected_fn(void* agent, Slic3r::OnServerConnectedFn fn)
{
    return store_callback(agent, &ShimAgent::on_server_connected, std::move(fn));
}

extern "C" int bambu_network_set_on_http_error_fn(void* agent, Slic3r::OnHttpErrorFn fn)
{
    return store_callback(agent, &ShimAgent::on_http_error, std::move(fn));
}

extern "C" int bambu_network_set_get_country_code_fn(void* agent, Slic3r::GetCountryCodeFn fn)
{
    return store_callback(agent, &ShimAgent::get_country_code, std::move(fn));
}

extern "C" int bambu_network_set_on_subscribe_failure_fn(void* agent, Slic3r::GetSubscribeFailureFn fn)
{
    return store_callback(agent, &ShimAgent::on_subscribe_failure, std::move(fn));
}

extern "C" int bambu_network_set_on_message_fn(void* agent, Slic3r::OnMessageFn fn)
{
    return store_callback(agent, &ShimAgent::on_message, std::move(fn));
}

extern "C" int bambu_network_set_on_user_message_fn(void* agent, Slic3r::OnMessageFn fn)
{
    return store_callback(agent, &ShimAgent::on_user_message, std::move(fn));
}

extern "C" int bambu_network_set_on_local_connect_fn(void* agent, Slic3r::OnLocalConnectedFn fn)
{
    return store_callback(agent, &ShimAgent::on_local_connect, std::move(fn));
}

extern "C" int bambu_network_set_on_local_message_fn(void* agent, Slic3r::OnMessageFn fn)
{
    return store_callback(agent, &ShimAgent::on_local_message, std::move(fn));
}

extern "C" int bambu_network_set_queue_on_main_fn(void* agent, Slic3r::QueueOnMainFn fn)
{
    return store_callback(agent, &ShimAgent::queue_on_main, std::move(fn));
}

extern "C" int bambu_network_set_server_callback(void* agent, Slic3r::OnServerErrFn fn)
{
    return store_callback(agent, &ShimAgent::on_server_error, std::move(fn));
}

extern "C" int bambu_network_connect_server(void* agent)
{
    if (configured_cloud_service_enabled(agent))
        return call_configured_cloud_service(agent, "connect_server", nlohmann::json::object(), nullptr, nullptr);
    return result_for_cloud_service(agent);
}

extern "C" bool bambu_network_is_server_connected(void* agent)
{
    if (configured_cloud_service_enabled(agent))
        return brs_cloud_is_server_connected(rust_agent(agent));
    return synthetic_cloud_service_enabled();
}

extern "C" int bambu_network_refresh_connection(void* agent)
{
    if (configured_cloud_service_enabled(agent))
        return call_configured_cloud_service(agent, "connect_server", nlohmann::json::object(), nullptr, nullptr);
    return result_for_cloud_service(agent);
}
extern "C" int bambu_network_start_subscribe(void* agent, std::string) { return result_for_cloud_service(agent); }
extern "C" int bambu_network_stop_subscribe(void* agent, std::string) { return result_for_cloud_service(agent); }
extern "C" int bambu_network_add_subscribe(void* agent, std::vector<std::string>) { return result_for_cloud_service(agent); }
extern "C" int bambu_network_del_subscribe(void* agent, std::vector<std::string>) { return result_for_cloud_service(agent); }
extern "C" void bambu_network_enable_multi_machine(void*, bool) {}
extern "C" int bambu_network_send_message(void* agent, std::string dev_id, std::string message, int qos, int flag)
{
    return brs_send_message(rust_agent(agent), dev_id.c_str(), message.c_str(), qos, flag);
}

extern "C" int bambu_network_connect_printer(void* agent, std::string dev_id, std::string dev_ip, std::string username, std::string password, bool use_ssl)
{
    const int result = brs_connect_printer(rust_agent(agent), dev_id.c_str(), dev_ip.c_str(), username.c_str(), password.c_str(), use_ssl);
    if (result == 0)
        remember_camera_endpoint(agent, dev_id, dev_ip, username, password, use_ssl);
    return result;
}

extern "C" int bambu_network_disconnect_printer(void* agent)
{
    auto* shim = shim_agent(agent);
    if (shim)
        shim->camera_endpoints.clear();
    return brs_disconnect_printer(rust_agent(agent));
}

extern "C" int bambu_network_send_message_to_printer(void* agent, std::string dev_id, std::string message, int qos, int flag)
{
    return brs_send_message_to_printer(rust_agent(agent), dev_id.c_str(), message.c_str(), qos, flag);
}

extern "C" int bambu_network_update_cert(void* agent) { return result_for_agent(agent); }
extern "C" void bambu_network_install_device_cert(void*, std::string, bool) {}
extern "C" bool bambu_network_start_discovery(void* agent, bool start, bool sending)
{
    return brs_start_discovery(rust_agent(agent), start, sending);
}

extern "C" int brs_shim_test_emit_ssdp(void* agent, const char* dev_info)
{
    return brs_internal_emit_ssdp(rust_agent(agent), dev_info);
}

extern "C" int brs_shim_test_emit_printer_connected(void* agent, const char* topic)
{
    return brs_internal_emit_printer_connected(rust_agent(agent), topic);
}

extern "C" int brs_shim_test_emit_message(void* agent, const char* dev_id, const char* message)
{
    return brs_internal_emit_message(rust_agent(agent), dev_id, message);
}

extern "C" int brs_shim_test_emit_local_connect(void* agent, int status, const char* dev_id, const char* message)
{
    return brs_internal_emit_local_connect(rust_agent(agent), status, dev_id, message);
}

extern "C" int brs_shim_test_emit_local_message(void* agent, const char* dev_id, const char* message)
{
    return brs_internal_emit_local_message(rust_agent(agent), dev_id, message);
}

extern "C" int brs_shim_test_emit_server_error(void* agent, const char* url, int status)
{
    return brs_internal_emit_server_error(rust_agent(agent), url, status);
}

extern "C" int brs_shim_test_set_camera_endpoint(void* agent, const char* dev_id, const char* dev_ip, const char* username, const char* password, bool rtsps)
{
    if (!agent)
        return Slic3r::BAMBU_NETWORK_ERR_INVALID_HANDLE;
    remember_camera_endpoint(agent, from_cstr(dev_id), from_cstr(dev_ip), from_cstr(username), from_cstr(password), rtsps);
    return 0;
}
extern "C" int bambu_network_change_user(void* agent, std::string user_info)
{
    return brs_change_user(rust_agent(agent), user_info.c_str());
}

extern "C" int bambu_network_user_logout(void* agent, bool)
{
    return brs_user_logout(rust_agent(agent));
}

extern "C" std::string bambu_network_get_user_avatar(void* agent)
{
    return from_cstr(brs_get_user_avatar(rust_agent(agent)));
}
extern "C" int bambu_network_ping_bind(void* agent, std::string) { return result_for_agent(agent); }

extern "C" int bambu_network_bind_detect(void* agent, std::string, std::string, Slic3r::detectResult& detect)
{
    detect = {};
    return result_for_agent(agent);
}

extern "C" int bambu_network_report_consent(void* agent, std::string) { return result_for_agent(agent); }
extern "C" int bambu_network_bind(void* agent, std::string, std::string, std::string, std::string, bool, Slic3r::OnUpdateStatusFn) { return result_for_agent(agent); }
extern "C" int bambu_network_unbind(void* agent, std::string) { return result_for_agent(agent); }
extern "C" std::string bambu_network_get_bambulab_host(void*) { return "https://bambulab.com"; }
extern "C" std::string bambu_network_get_user_selected_machine(void*) { return {}; }
extern "C" int bambu_network_set_user_selected_machine(void* agent, std::string) { return result_for_agent(agent); }

extern "C" int bambu_network_start_print(void* agent, Slic3r::PrintParams, Slic3r::OnUpdateStatusFn, Slic3r::WasCancelledFn, Slic3r::OnWaitFn) { return result_for_agent(agent); }
extern "C" int bambu_network_start_local_print_with_record(void* agent, Slic3r::PrintParams params, Slic3r::OnUpdateStatusFn update, Slic3r::WasCancelledFn cancel, Slic3r::OnWaitFn)
{
    if (!agent)
        return Slic3r::BAMBU_NETWORK_ERR_INVALID_HANDLE;
    if (is_cancelled(cancel))
        return canceled_result;

    emit_print_status(update, printing_stage_create, 0, "Preparing...");
    emit_print_status(update, printing_stage_upload, 0, "Uploading...");
    const int result = start_local_print_common(agent, params);
    if (result == 0)
        emit_print_status(update, printing_stage_sending, 0, "Starting print...");
    return finish_print_job(result, update, "Print started");
}
extern "C" int bambu_network_start_send_gcode_to_sdcard(void* agent, Slic3r::PrintParams params, Slic3r::OnUpdateStatusFn update, Slic3r::WasCancelledFn cancel, Slic3r::OnWaitFn)
{
    if (!agent)
        return Slic3r::BAMBU_NETWORK_ERR_INVALID_HANDLE;
    if (is_cancelled(cancel))
        return canceled_result;

    emit_print_status(update, printing_stage_create, 0, "Preparing...");
    emit_print_status(update, printing_stage_upload, 0, "Uploading...");
    return finish_print_job(upload_file_to_printer(agent, params), update, "File uploaded");
}
extern "C" int bambu_network_start_local_print(void* agent, Slic3r::PrintParams params, Slic3r::OnUpdateStatusFn update, Slic3r::WasCancelledFn cancel)
{
    if (!agent)
        return Slic3r::BAMBU_NETWORK_ERR_INVALID_HANDLE;
    if (is_cancelled(cancel))
        return canceled_result;

    emit_print_status(update, printing_stage_create, 0, "Preparing...");
    emit_print_status(update, printing_stage_upload, 0, "Uploading...");
    const int result = start_local_print_common(agent, params);
    if (result == 0)
        emit_print_status(update, printing_stage_sending, 0, "Starting print...");
    return finish_print_job(result, update, "Print started");
}
extern "C" int bambu_network_start_sdcard_print(void* agent, Slic3r::PrintParams params, Slic3r::OnUpdateStatusFn update, Slic3r::WasCancelledFn cancel)
{
    if (!agent)
        return Slic3r::BAMBU_NETWORK_ERR_INVALID_HANDLE;
    if (is_cancelled(cancel))
        return canceled_result;

    emit_print_status(update, printing_stage_sending, 0, "Starting print...");
    const std::string file_path = project_file_path(params);
    const int result = brs_start_sdcard_print(rust_agent(agent),
                                              params.dev_id.c_str(),
                                              params.dev_ip.c_str(),
                                              params.username.c_str(),
                                              params.password.c_str(),
                                              params.use_ssl_for_mqtt,
                                              "0",
                                              params.plate_index,
                                              file_path.c_str(),
                                              params.ftp_file_md5.c_str(),
                                              params.task_bed_type.c_str(),
                                              params.task_bed_leveling,
                                              params.task_flow_cali,
                                              params.task_vibration_cali,
                                              params.task_layer_inspect,
                                              params.task_record_timelapse,
                                              params.task_use_ams,
                                              params.ams_mapping.c_str());
    return finish_print_job(result, update, "Print started");
}

extern "C" int bambu_network_get_user_presets(void* agent, std::map<std::string, std::map<std::string, std::string>>* user_presets)
{
    if (user_presets)
        user_presets->clear();
    return result_for_agent(agent);
}

extern "C" std::string bambu_network_request_setting_id(void* agent, std::string, std::map<std::string, std::string>*, unsigned int* http_code)
{
    if (http_code)
        *http_code = 0;
    return agent ? std::string() : std::string();
}

extern "C" int bambu_network_put_setting(void* agent, std::string, std::string, std::map<std::string, std::string>*, unsigned int* http_code)
{
    if (http_code)
        *http_code = 0;
    return result_for_agent(agent);
}

extern "C" int bambu_network_get_setting_list(void* agent, std::string, Slic3r::ProgressFn, Slic3r::WasCancelledFn) { return result_for_agent(agent); }
extern "C" int bambu_network_get_setting_list2(void* agent, std::string, Slic3r::CheckFn, Slic3r::ProgressFn, Slic3r::WasCancelledFn) { return result_for_agent(agent); }
extern "C" int bambu_network_delete_setting(void* agent, std::string) { return result_for_agent(agent); }
extern "C" std::string bambu_network_get_studio_info_url(void*) { return "https://api.bambulab.com/v1/iot-service/api/slicer/resource"; }
extern "C" int bambu_network_set_extra_http_header(void* agent, std::map<std::string, std::string>) { return result_for_agent(agent); }

extern "C" int bambu_network_get_my_message(void* agent, int, int, int, unsigned int* http_code, std::string* http_body)
{
    if (configured_cloud_service_enabled(agent))
        return call_configured_cloud_service(agent, "get_my_message", nlohmann::json::object(), http_code, http_body);
    set_http_json(http_code, http_body, R"({"messages":[]})");
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_check_user_task_report(void* agent, int* task_id, bool* printable)
{
    if (task_id)
        *task_id = 0;
    if (printable)
        *printable = false;
    return result_for_agent(agent);
}

extern "C" int bambu_network_get_user_print_info(void* agent, unsigned int* http_code, std::string* http_body)
{
    if (configured_cloud_service_enabled(agent))
        return call_configured_cloud_service(agent, "get_user_print_info", nlohmann::json::object(), http_code, http_body);
    set_http_json(http_code, http_body, R"({"printers":[]})");
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_get_user_tasks(void* agent, Slic3r::TaskQueryParams params, std::string* http_body)
{
    if (configured_cloud_service_enabled(agent)) {
        nlohmann::json request{
            {"dev_id", params.dev_id},
            {"status", params.status},
            {"offset", params.offset},
            {"limit", params.limit},
        };
        return call_configured_cloud_service(agent, "get_user_tasks", request, nullptr, http_body);
    }
    if (http_body)
        *http_body = synthetic_cloud_service_enabled() ? R"({"tasks":[]})" : std::string();
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_get_printer_firmware(void* agent, std::string dev_id, unsigned* http_code, std::string* http_body)
{
    if (configured_cloud_service_enabled(agent)) {
        unsigned int code = 0;
        const int result = call_configured_cloud_service(agent, "get_printer_firmware", {{"dev_id", dev_id}}, &code, http_body);
        if (http_code)
            *http_code = code;
        return result;
    }
    if (http_code)
        *http_code = synthetic_cloud_service_enabled() ? 200 : 0;
    if (http_body)
        *http_body = synthetic_cloud_service_enabled() ? R"({"firmware":[]})" : std::string();
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_get_task_plate_index(void* agent, std::string task_id, int* plate_index)
{
    if (configured_cloud_service_enabled(agent)) {
        int value = -1;
        const int result = call_configured_cloud_service(agent, "get_task_plate_index", {{"task_id", task_id}}, nullptr, nullptr, &value);
        if (plate_index)
            *plate_index = value;
        return result;
    }
    if (plate_index)
        *plate_index = synthetic_cloud_service_enabled() ? 0 : -1;
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_get_user_info(void* agent, int* identifier)
{
    if (configured_cloud_service_enabled(agent)) {
        int value = 0;
        const int result = call_configured_cloud_service(agent, "get_user_info", nlohmann::json::object(), nullptr, nullptr, &value);
        if (identifier)
            *identifier = value;
        return result;
    }
    if (identifier)
        *identifier = synthetic_cloud_service_enabled() ? 1 : 0;
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_request_bind_ticket(void* agent, std::string* ticket)
{
    if (configured_cloud_service_enabled(agent))
        return call_configured_cloud_service(agent, "request_bind_ticket", nlohmann::json::object(), nullptr, ticket);
    if (ticket)
        *ticket = synthetic_cloud_service_enabled() ? "synthetic-bind-ticket" : std::string();
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_get_subtask_info(void* agent, std::string subtask_id, std::string* task_json, unsigned int* http_code, std::string* http_body)
{
    if (configured_cloud_service_enabled(agent)) {
        std::string body;
        const int result = call_configured_cloud_service(agent, "get_subtask_info", {{"subtask_id", subtask_id}}, http_code, &body);
        if (task_json)
            *task_json = body;
        if (http_body)
            *http_body = body;
        return result;
    }
    if (task_json)
        *task_json = synthetic_cloud_service_enabled() ? R"({"subtasks":[]})" : std::string();
    set_http_json(http_code, http_body, R"({"subtasks":[]})");
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_get_slice_info(void* agent, std::string project_id, std::string profile_id, int plate_index, std::string* slice_json)
{
    if (configured_cloud_service_enabled(agent)) {
        return call_configured_cloud_service(agent,
                                             "get_slice_info",
                                             {{"project_id", project_id}, {"profile_id", profile_id}, {"plate_index", plate_index}},
                                             nullptr,
                                             slice_json);
    }
    if (slice_json)
        *slice_json = synthetic_cloud_service_enabled() ? R"({"slices":[]})" : std::string();
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_query_bind_status(void* agent, std::vector<std::string> query_list, unsigned int* http_code, std::string* http_body)
{
    if (configured_cloud_service_enabled(agent))
        return call_configured_cloud_service(agent, "query_bind_status", {{"query_list", query_list}}, http_code, http_body);
    set_http_json(http_code, http_body, R"({"devices":[]})");
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_modify_printer_name(void* agent, std::string, std::string) { return result_for_agent(agent); }
extern "C" int bambu_network_get_camera_url(void* agent, std::string dev_id, std::function<void(std::string)> callback)
{
    return get_camera_url_common(agent, dev_id, callback);
}
extern "C" int bambu_network_get_camera_url_for_golive(void* agent, std::string dev_id, std::string, std::function<void(std::string)> callback)
{
    return get_camera_url_common(agent, dev_id, callback);
}
extern "C" int bambu_network_get_design_staffpick(void* agent, int offset, int limit, std::function<void(std::string)> callback)
{
    std::string body;
    int result = result_for_cloud_service(agent);
    if (configured_cloud_service_enabled(agent))
        result = call_configured_cloud_service(agent, "get_design_staffpick", {{"offset", offset}, {"limit", limit}}, nullptr, &body);
    else if (synthetic_cloud_service_enabled())
        body = R"({"staffpicks":[]})";
    if (callback && result == 0)
        callback(body);
    return result;
}
extern "C" int bambu_network_start_publish(void* agent, Slic3r::PublishParams, Slic3r::OnUpdateStatusFn, Slic3r::WasCancelledFn, std::string* out)
{
    if (out)
        out->clear();
    return result_for_agent(agent);
}

extern "C" int bambu_network_get_model_publish_url(void* agent, std::string* url)
{
    return assign_service_url(agent, url, "get_model_publish_url", "https://makerworld.com/en/upload");
}

extern "C" int bambu_network_get_subtask(void* agent, Slic3r::BBLModelTask*, Slic3r::OnGetSubTaskFn) { return result_for_agent(agent); }

extern "C" int bambu_network_get_model_mall_home_url(void* agent, std::string* url)
{
    return assign_service_url(agent, url, "get_model_mall_home_url", "https://makerworld.com/");
}

extern "C" int bambu_network_get_model_mall_detail_url(void* agent, std::string* url, std::string id)
{
    return assign_service_url(agent, url, "get_model_mall_detail_url", "https://makerworld.com/en/models/synthetic", {{"id", id}});
}

extern "C" int bambu_network_get_my_token(void* agent, std::string ticket, unsigned int* http_code, std::string* http_body)
{
    if (configured_cloud_service_enabled(agent))
        return call_configured_cloud_service(agent, "get_my_token", {{"ticket", ticket}}, http_code, http_body);
    set_http_json(http_code, http_body, R"({"access_token":"synthetic-access-token","refresh_token":"synthetic-refresh-token","expires_in":3600})");
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_get_my_profile(void* agent, std::string token, unsigned int* http_code, std::string* http_body)
{
    if (configured_cloud_service_enabled(agent))
        return call_configured_cloud_service(agent, "get_my_profile", {{"token", token}}, http_code, http_body);
    set_http_json(http_code, http_body, R"({"id":"synthetic-user","name":"Synthetic User"})");
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_track_enable(void* agent, bool) { return result_for_agent(agent); }
extern "C" int bambu_network_track_remove_files(void* agent) { return result_for_agent(agent); }
extern "C" int bambu_network_track_event(void* agent, std::string, std::string) { return result_for_agent(agent); }
extern "C" int bambu_network_track_header(void* agent, std::string) { return result_for_agent(agent); }
extern "C" int bambu_network_track_update_property(void* agent, std::string, std::string, std::string) { return result_for_agent(agent); }

extern "C" int bambu_network_track_get_property(void* agent, std::string, std::string& value, std::string)
{
    value.clear();
    return result_for_agent(agent);
}

extern "C" int bambu_network_put_model_mall_rating(void* agent, int, int, std::string, std::vector<std::string>, unsigned int& http_code, std::string& http_error)
{
    http_code = 0;
    http_error.clear();
    return result_for_agent(agent);
}

extern "C" int bambu_network_get_oss_config(void* agent, std::string& config, std::string country_code, unsigned int& http_code, std::string& http_error)
{
    if (configured_cloud_service_enabled(agent)) {
        const int result = call_configured_cloud_service(agent, "get_oss_config", {{"country_code", country_code}}, &http_code, &config);
        http_error.clear();
        return result;
    }
    config = synthetic_cloud_service_enabled() ? R"({"bucket":"synthetic"})" : std::string();
    http_code = synthetic_cloud_service_enabled() ? 200 : 0;
    http_error.clear();
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_put_rating_picture_oss(void* agent, std::string& config, std::string& pic_oss_path, std::string model_id, int profile_id, unsigned int& http_code, std::string& http_error)
{
    if (configured_cloud_service_enabled(agent)) {
        std::string body;
        const int result = call_configured_cloud_service(
            agent, "put_rating_picture_oss", {{"config", config}, {"pic_oss_path", pic_oss_path}, {"model_id", model_id}, {"profile_id", profile_id}}, &http_code, &body);
        if (!body.empty())
            config = body;
        http_error.clear();
        return result;
    }
    config = synthetic_cloud_service_enabled() ? R"({"bucket":"synthetic"})" : std::string();
    pic_oss_path = synthetic_cloud_service_enabled() ? "synthetic/rating-picture.jpg" : std::string();
    http_code = synthetic_cloud_service_enabled() ? 200 : 0;
    http_error.clear();
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_get_model_mall_rating(void* agent, int job_id, std::string& rating_result, unsigned int& http_code, std::string& http_error)
{
    if (configured_cloud_service_enabled(agent)) {
        const int result = call_configured_cloud_service(agent, "get_model_mall_rating", {{"job_id", job_id}}, &http_code, &rating_result);
        http_error.clear();
        return result;
    }
    rating_result = synthetic_cloud_service_enabled() ? R"({"ratings":[]})" : std::string();
    http_code = synthetic_cloud_service_enabled() ? 200 : 0;
    http_error.clear();
    return result_for_cloud_service(agent);
}

extern "C" int bambu_network_get_mw_user_preference(void* agent, std::function<void(std::string)> callback)
{
    std::string body;
    int result = result_for_cloud_service(agent);
    if (configured_cloud_service_enabled(agent))
        result = call_configured_cloud_service(agent, "get_mw_user_preference", nlohmann::json::object(), nullptr, &body);
    else if (synthetic_cloud_service_enabled())
        body = R"({"preferences":{}})";
    if (callback && result == 0)
        callback(body);
    return result;
}

extern "C" int bambu_network_get_mw_user_4ulist(void* agent, int offset, int limit, std::function<void(std::string)> callback)
{
    std::string body;
    int result = result_for_cloud_service(agent);
    if (configured_cloud_service_enabled(agent))
        result = call_configured_cloud_service(agent, "get_mw_user_4ulist", {{"offset", offset}, {"limit", limit}}, nullptr, &body);
    else if (synthetic_cloud_service_enabled())
        body = R"({"items":[]})";
    if (callback && result == 0)
        callback(body);
    return result;
}

extern "C" int bambu_network_get_hms_snapshot(void* agent, std::string dev_id, std::string module, std::function<void(std::string, int)> callback)
{
    unsigned int http_code = 0;
    std::string body;
    int result = result_for_cloud_service(agent);
    if (configured_cloud_service_enabled(agent))
        result = call_configured_cloud_service(agent, "get_hms_snapshot", {{"dev_id", dev_id}, {"module", module}}, &http_code, &body);
    else if (synthetic_cloud_service_enabled()) {
        http_code = 200;
        body = R"({"hms":[]})";
    }
    if (callback && result == 0)
        callback(body, static_cast<int>(http_code));
    return result;
}

extern "C" int ft_abi_version() { return 1; }
extern "C" void ft_free(void* value)
{
    std::free(value);
}

extern "C" void ft_job_result_destroy(FtJobResult* result)
{
    if (!result)
        return;
    std::free(const_cast<char*>(result->json));
    std::free(const_cast<void*>(result->bin));
    *result = {};
}

extern "C" void ft_job_msg_destroy(FtJobMsg* message)
{
    if (!message)
        return;
    std::free(const_cast<char*>(message->json));
    *message = {};
}

extern "C" int ft_tunnel_create(const char* url, FtTunnel** out)
{
    if (!out)
        return ft_einval;
    *out = nullptr;
    auto* tunnel = new FtTunnel();
    if (!parse_local_tunnel_url(*tunnel, url)) {
        delete tunnel;
        return ft_einval;
    }
    *out = tunnel;
    return ft_ok;
}

extern "C" void ft_tunnel_retain(FtTunnel* tunnel)
{
    retain_tunnel(tunnel);
}

extern "C" void ft_tunnel_release(FtTunnel* tunnel)
{
    release_tunnel(tunnel);
}

extern "C" int ft_tunnel_start_connect(FtTunnel* tunnel, FtConnectionCallback callback, void* user)
{
    if (!tunnel)
        return ft_einval;
    emit_tunnel_status(*tunnel, 1, ft_ok, "connecting");
    tunnel->connected = true;
    emit_tunnel_status(*tunnel, 2, ft_ok, "connected");
    if (callback)
        callback(user, 0, ft_ok, "connected");
    return ft_ok;
}

extern "C" int ft_tunnel_sync_connect(FtTunnel* tunnel)
{
    if (!tunnel)
        return ft_einval;
    tunnel->connected = true;
    emit_tunnel_status(*tunnel, 2, ft_ok, "connected");
    return ft_ok;
}

extern "C" int ft_tunnel_set_status_cb(FtTunnel* tunnel, FtStatusCallback callback, void* user)
{
    if (!tunnel)
        return ft_einval;
    tunnel->status_callback = callback;
    tunnel->status_user = user;
    return ft_ok;
}

extern "C" int ft_tunnel_shutdown(FtTunnel* tunnel)
{
    if (!tunnel)
        return ft_einval;
    tunnel->connected = false;
    emit_tunnel_status(*tunnel, 0, ft_ok, "shutdown");
    return ft_ok;
}

extern "C" int ft_job_create(const char* params_json, FtJob** out)
{
    if (!out)
        return ft_einval;
    *out = nullptr;
    try {
        const auto parsed = nlohmann::json::parse(from_cstr(params_json));
        if (!parsed.contains("cmd_type") || !parsed["cmd_type"].is_number_integer())
            return ft_exception;
    } catch (...) {
        return ft_exception;
    }
    *out = new FtJob();
    (*out)->params_json = from_cstr(params_json);
    return ft_ok;
}

extern "C" void ft_job_retain(FtJob* job)
{
    retain_job(job);
}

extern "C" void ft_job_release(FtJob* job)
{
    release_job(job);
}

extern "C" int ft_job_set_result_cb(FtJob* job, FtResultCallback callback, void* user)
{
    if (!job)
        return ft_einval;
    job->result_callback = callback;
    job->result_user = user;
    if (job->completed && callback) {
        auto result = make_result_payload(*job);
        callback(user, result);
    }
    return ft_ok;
}

extern "C" int ft_job_get_result(FtJob* job, std::uint32_t, FtJobResult* out_result)
{
    if (!job || !out_result)
        return ft_einval;
    if (!job->completed)
        return ft_estate;
    *out_result = make_result_payload(*job);
    return ft_ok;
}

extern "C" int ft_tunnel_start_job(FtTunnel* tunnel, FtJob* job)
{
    if (!tunnel || !job)
        return ft_einval;
    if (!tunnel->connected)
        return ft_estate;
    run_file_transfer_job(*tunnel, *job);
    return ft_ok;
}

extern "C" int ft_job_cancel(FtJob* job)
{
    if (!job)
        return ft_einval;
    job->cancelled = true;
    if (!job->completed)
        complete_job(*job, ft_ecancelled, ft_ecancelled, R"({"error":"cancelled"})");
    return ft_ok;
}

extern "C" int ft_job_set_msg_cb(FtJob* job, FtMsgCallback callback, void* user)
{
    if (!job)
        return ft_einval;
    job->msg_callback = callback;
    job->msg_user = user;
    if (callback) {
        for (const auto& [kind, json] : job->messages) {
            auto message = make_msg_payload(kind, json);
            callback(user, message);
        }
    }
    return ft_ok;
}

extern "C" int ft_job_try_get_msg(FtJob* job, FtJobMsg* out_msg)
{
    if (!job || !out_msg)
        return ft_einval;
    if (job->messages.empty())
        return ft_etimeout;
    const auto message = job->messages.front();
    job->messages.erase(job->messages.begin());
    *out_msg = make_msg_payload(message.first, message.second);
    return ft_ok;
}

extern "C" int ft_job_get_msg(FtJob* job, std::uint32_t, FtJobMsg* out_msg)
{
    return ft_job_try_get_msg(job, out_msg);
}
