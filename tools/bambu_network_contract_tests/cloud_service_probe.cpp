#include <dlfcn.h>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <string>
#include <utility>
#include <vector>

#include "../bambu_network_rust_plugin/shim/bambu_networking_abi.hpp"

namespace {

using CreateAgentFn = void* (*)(std::string);
using DestroyAgentFn = int (*)(void*);
using IntAgentFn = int (*)(void*);
using BoolAgentFn = bool (*)(void*);
using StringAgentFn = std::string (*)(void*);
using SetStringFn = int (*)(void*, std::string);
using SetCertFileFn = int (*)(void*, std::string, std::string);
using ChangeUserFn = int (*)(void*, std::string);
using UserLogoutFn = int (*)(void*, bool);
using SubscribeFn = int (*)(void*, std::string);
using SubscribeListFn = int (*)(void*, std::vector<std::string>);
using StringOutFn = int (*)(void*, std::string*);
using StringOutWithInputFn = int (*)(void*, std::string*, std::string);
using GetMyTokenFn = int (*)(void*, std::string, unsigned int*, std::string*);
using GetMyMessageFn = int (*)(void*, int, int, int, unsigned int*, std::string*);
using GetUserPrintInfoFn = int (*)(void*, unsigned int*, std::string*);
using GetUserTasksFn = int (*)(void*, Slic3r::TaskQueryParams, std::string*);
using RequestBindTicketFn = int (*)(void*, std::string*);
using QueryBindStatusFn = int (*)(void*, std::vector<std::string>, unsigned int*, std::string*);
using GetUserInfoFn = int (*)(void*, int*);
using GetTaskPlateIndexFn = int (*)(void*, std::string, int*);
using GetModelMallRatingFn = int (*)(void*, int, std::string&, unsigned int&, std::string&);
using DesignStaffpickFn = int (*)(void*, int, int, std::function<void(std::string)>);
using MwUserPreferenceFn = int (*)(void*, std::function<void(std::string)>);
using MwUser4uListFn = int (*)(void*, int, int, std::function<void(std::string)>);
using HmsSnapshotFn = int (*)(void*, std::string, std::string, std::function<void(std::string, int)>);
using SetUserLoginFn = int (*)(void*, std::function<void(int, bool)>);
using SetServerConnectedFn = int (*)(void*, std::function<void(int, int)>);
using SetHttpErrorFn = int (*)(void*, std::function<void(unsigned int, std::string)>);
using SetMessageFn = int (*)(void*, std::function<void(std::string, std::string)>);
using SetStringCallbackFn = int (*)(void*, std::function<void(std::string)>);

constexpr int unsupported_result = Slic3r::BAMBU_NETWORK_ERR_CONNECT_FAILED;

struct Args {
    std::string plugin;
    std::string log_dir{"."};
    std::string user_info_file;
    std::string user_info_env;
    std::string ticket_env;
    std::string access_token_env;
    std::string detail_id{"0"};
    std::string task_id{"0"};
    std::string subscribe_module{"app"};
    bool allow_network{false};
    bool expect_success{false};
    bool trace_phases{false};
};

struct Loaded {
    void* module{nullptr};
    CreateAgentFn create_agent{nullptr};
    DestroyAgentFn destroy_agent{nullptr};
    IntAgentFn init_log{nullptr};
    SetStringFn set_config_dir{nullptr};
    SetCertFileFn set_cert_file{nullptr};
    SetStringFn set_country_code{nullptr};
    IntAgentFn start{nullptr};
    IntAgentFn connect_server{nullptr};
    BoolAgentFn is_server_connected{nullptr};
    IntAgentFn refresh_connection{nullptr};
    SubscribeFn start_subscribe{nullptr};
    SubscribeFn stop_subscribe{nullptr};
    SubscribeListFn add_subscribe{nullptr};
    SubscribeListFn del_subscribe{nullptr};
    ChangeUserFn change_user{nullptr};
    BoolAgentFn is_user_login{nullptr};
    UserLogoutFn user_logout{nullptr};
    StringAgentFn get_user_id{nullptr};
    StringAgentFn get_user_name{nullptr};
    StringAgentFn get_user_nickname{nullptr};
    StringAgentFn get_user_avatar{nullptr};
    StringAgentFn build_login_cmd{nullptr};
    StringAgentFn build_login_info{nullptr};
    StringAgentFn build_logout_cmd{nullptr};
    StringAgentFn get_bambulab_host{nullptr};
    StringAgentFn get_studio_info_url{nullptr};
    StringAgentFn get_user_selected_machine{nullptr};
    StringOutFn get_model_mall_home_url{nullptr};
    StringOutWithInputFn get_model_mall_detail_url{nullptr};
    StringOutFn get_model_publish_url{nullptr};
    GetMyTokenFn get_my_token{nullptr};
    GetMyTokenFn get_my_profile{nullptr};
    GetMyMessageFn get_my_message{nullptr};
    GetUserPrintInfoFn get_user_print_info{nullptr};
    GetUserTasksFn get_user_tasks{nullptr};
    RequestBindTicketFn request_bind_ticket{nullptr};
    QueryBindStatusFn query_bind_status{nullptr};
    GetUserInfoFn get_user_info{nullptr};
    GetTaskPlateIndexFn get_task_plate_index{nullptr};
    GetModelMallRatingFn get_model_mall_rating{nullptr};
    DesignStaffpickFn get_design_staffpick{nullptr};
    MwUserPreferenceFn get_mw_user_preference{nullptr};
    MwUser4uListFn get_mw_user_4ulist{nullptr};
    HmsSnapshotFn get_hms_snapshot{nullptr};
    SetUserLoginFn set_on_user_login{nullptr};
    SetServerConnectedFn set_on_server_connected{nullptr};
    SetHttpErrorFn set_on_http_error{nullptr};
    SetMessageFn set_on_message{nullptr};
    SetStringCallbackFn set_on_subscribe_failure{nullptr};
    std::vector<std::string> missing;
};

std::string json_escape(const std::string& value)
{
    std::string out;
    out.reserve(value.size() + 8);
    for (char ch : value) {
        switch (ch) {
        case '\\': out += "\\\\"; break;
        case '"': out += "\\\""; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        default: out.push_back(ch); break;
        }
    }
    return out;
}

bool parse_args(int argc, char** argv, Args& args)
{
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--plugin" && i + 1 < argc) {
            args.plugin = argv[++i];
        } else if (arg == "--log-dir" && i + 1 < argc) {
            args.log_dir = argv[++i];
        } else if (arg == "--user-info-file" && i + 1 < argc) {
            args.user_info_file = argv[++i];
        } else if (arg == "--user-info-env" && i + 1 < argc) {
            args.user_info_env = argv[++i];
        } else if (arg == "--ticket-env" && i + 1 < argc) {
            args.ticket_env = argv[++i];
        } else if (arg == "--access-token-env" && i + 1 < argc) {
            args.access_token_env = argv[++i];
        } else if (arg == "--detail-id" && i + 1 < argc) {
            args.detail_id = argv[++i];
        } else if (arg == "--task-id" && i + 1 < argc) {
            args.task_id = argv[++i];
        } else if (arg == "--subscribe-module" && i + 1 < argc) {
            args.subscribe_module = argv[++i];
        } else if (arg == "--allow-network") {
            args.allow_network = true;
        } else if (arg == "--expect-success") {
            args.expect_success = true;
        } else if (arg == "--trace-phases") {
            args.trace_phases = true;
        } else {
            return false;
        }
    }
    return !args.plugin.empty();
}

template <typename Fn>
Fn load_symbol(void* module, const char* name, std::vector<std::string>& missing)
{
    dlerror();
    void* symbol = dlsym(module, name);
    const char* error = dlerror();
    if (!symbol || error) {
        missing.push_back(name);
        return nullptr;
    }
    return reinterpret_cast<Fn>(symbol);
}

std::string read_file(const std::string& path)
{
    std::ifstream input(path);
    return std::string(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
}

std::string env_value(const std::string& name)
{
    if (name.empty())
        return {};
    const char* value = std::getenv(name.c_str());
    return value ? std::string(value) : std::string();
}

std::string user_info_payload(const Args& args)
{
    if (!args.user_info_file.empty())
        return read_file(args.user_info_file);
    return env_value(args.user_info_env);
}

std::string boolean(bool value)
{
    return value ? "true" : "false";
}

std::string number(int value)
{
    return std::to_string(value);
}

std::string unsigned_number(unsigned int value)
{
    return std::to_string(value);
}

std::string normalized_string(const std::string& value)
{
    return "{\"present\":" + boolean(!value.empty())
        + ",\"looks_json\":" + boolean(!value.empty() && (value.front() == '{' || value.front() == '['))
        + ",\"length\":" + std::to_string(value.size()) + "}";
}

std::string normalized_url(const std::string& value)
{
    const bool present = !value.empty();
    const bool http = value.rfind("http://", 0) == 0 || value.rfind("https://", 0) == 0;
    return "{\"present\":" + boolean(present)
        + ",\"http\":" + boolean(http)
        + ",\"length\":" + std::to_string(value.size()) + "}";
}

void write_string_array(const std::vector<std::string>& values)
{
    std::cout << "[";
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i > 0)
            std::cout << ", ";
        std::cout << "\"" << json_escape(values[i]) << "\"";
    }
    std::cout << "]";
}

void write_result_map(const std::map<std::string, std::string>& values)
{
    std::cout << "{";
    std::size_t index = 0;
    for (const auto& [key, value] : values) {
        if (index++ > 0)
            std::cout << ", ";
        std::cout << "\"" << json_escape(key) << "\": " << value;
    }
    std::cout << "}";
}

Loaded load_plugin(const std::string& path)
{
    Loaded loaded;
    loaded.module = dlopen(path.c_str(), RTLD_LAZY | RTLD_LOCAL);
    if (!loaded.module)
        return loaded;

    loaded.create_agent = load_symbol<CreateAgentFn>(loaded.module, "bambu_network_create_agent", loaded.missing);
    loaded.destroy_agent = load_symbol<DestroyAgentFn>(loaded.module, "bambu_network_destroy_agent", loaded.missing);
    loaded.init_log = load_symbol<IntAgentFn>(loaded.module, "bambu_network_init_log", loaded.missing);
    loaded.set_config_dir = load_symbol<SetStringFn>(loaded.module, "bambu_network_set_config_dir", loaded.missing);
    loaded.set_cert_file = load_symbol<SetCertFileFn>(loaded.module, "bambu_network_set_cert_file", loaded.missing);
    loaded.set_country_code = load_symbol<SetStringFn>(loaded.module, "bambu_network_set_country_code", loaded.missing);
    loaded.start = load_symbol<IntAgentFn>(loaded.module, "bambu_network_start", loaded.missing);
    loaded.connect_server = load_symbol<IntAgentFn>(loaded.module, "bambu_network_connect_server", loaded.missing);
    loaded.is_server_connected = load_symbol<BoolAgentFn>(loaded.module, "bambu_network_is_server_connected", loaded.missing);
    loaded.refresh_connection = load_symbol<IntAgentFn>(loaded.module, "bambu_network_refresh_connection", loaded.missing);
    loaded.start_subscribe = load_symbol<SubscribeFn>(loaded.module, "bambu_network_start_subscribe", loaded.missing);
    loaded.stop_subscribe = load_symbol<SubscribeFn>(loaded.module, "bambu_network_stop_subscribe", loaded.missing);
    loaded.add_subscribe = load_symbol<SubscribeListFn>(loaded.module, "bambu_network_add_subscribe", loaded.missing);
    loaded.del_subscribe = load_symbol<SubscribeListFn>(loaded.module, "bambu_network_del_subscribe", loaded.missing);
    loaded.change_user = load_symbol<ChangeUserFn>(loaded.module, "bambu_network_change_user", loaded.missing);
    loaded.is_user_login = load_symbol<BoolAgentFn>(loaded.module, "bambu_network_is_user_login", loaded.missing);
    loaded.user_logout = load_symbol<UserLogoutFn>(loaded.module, "bambu_network_user_logout", loaded.missing);
    loaded.get_user_id = load_symbol<StringAgentFn>(loaded.module, "bambu_network_get_user_id", loaded.missing);
    loaded.get_user_name = load_symbol<StringAgentFn>(loaded.module, "bambu_network_get_user_name", loaded.missing);
    loaded.get_user_nickname = load_symbol<StringAgentFn>(loaded.module, "bambu_network_get_user_nickanme", loaded.missing);
    loaded.get_user_avatar = load_symbol<StringAgentFn>(loaded.module, "bambu_network_get_user_avatar", loaded.missing);
    loaded.build_login_cmd = load_symbol<StringAgentFn>(loaded.module, "bambu_network_build_login_cmd", loaded.missing);
    loaded.build_login_info = load_symbol<StringAgentFn>(loaded.module, "bambu_network_build_login_info", loaded.missing);
    loaded.build_logout_cmd = load_symbol<StringAgentFn>(loaded.module, "bambu_network_build_logout_cmd", loaded.missing);
    loaded.get_bambulab_host = load_symbol<StringAgentFn>(loaded.module, "bambu_network_get_bambulab_host", loaded.missing);
    loaded.get_studio_info_url = load_symbol<StringAgentFn>(loaded.module, "bambu_network_get_studio_info_url", loaded.missing);
    loaded.get_user_selected_machine = load_symbol<StringAgentFn>(loaded.module, "bambu_network_get_user_selected_machine", loaded.missing);
    loaded.get_model_mall_home_url = load_symbol<StringOutFn>(loaded.module, "bambu_network_get_model_mall_home_url", loaded.missing);
    loaded.get_model_mall_detail_url = load_symbol<StringOutWithInputFn>(loaded.module, "bambu_network_get_model_mall_detail_url", loaded.missing);
    loaded.get_model_publish_url = load_symbol<StringOutFn>(loaded.module, "bambu_network_get_model_publish_url", loaded.missing);
    loaded.get_my_token = load_symbol<GetMyTokenFn>(loaded.module, "bambu_network_get_my_token", loaded.missing);
    loaded.get_my_profile = load_symbol<GetMyTokenFn>(loaded.module, "bambu_network_get_my_profile", loaded.missing);
    loaded.get_my_message = load_symbol<GetMyMessageFn>(loaded.module, "bambu_network_get_my_message", loaded.missing);
    loaded.get_user_print_info = load_symbol<GetUserPrintInfoFn>(loaded.module, "bambu_network_get_user_print_info", loaded.missing);
    loaded.get_user_tasks = load_symbol<GetUserTasksFn>(loaded.module, "bambu_network_get_user_tasks", loaded.missing);
    loaded.request_bind_ticket = load_symbol<RequestBindTicketFn>(loaded.module, "bambu_network_request_bind_ticket", loaded.missing);
    loaded.query_bind_status = load_symbol<QueryBindStatusFn>(loaded.module, "bambu_network_query_bind_status", loaded.missing);
    loaded.get_user_info = load_symbol<GetUserInfoFn>(loaded.module, "bambu_network_get_user_info", loaded.missing);
    loaded.get_task_plate_index = load_symbol<GetTaskPlateIndexFn>(loaded.module, "bambu_network_get_task_plate_index", loaded.missing);
    loaded.get_model_mall_rating = load_symbol<GetModelMallRatingFn>(loaded.module, "bambu_network_get_model_mall_rating", loaded.missing);
    loaded.get_design_staffpick = load_symbol<DesignStaffpickFn>(loaded.module, "bambu_network_get_design_staffpick", loaded.missing);
    loaded.get_mw_user_preference = load_symbol<MwUserPreferenceFn>(loaded.module, "bambu_network_get_mw_user_preference", loaded.missing);
    loaded.get_mw_user_4ulist = load_symbol<MwUser4uListFn>(loaded.module, "bambu_network_get_mw_user_4ulist", loaded.missing);
    loaded.get_hms_snapshot = load_symbol<HmsSnapshotFn>(loaded.module, "bambu_network_get_hms_snapshot", loaded.missing);
    loaded.set_on_user_login = load_symbol<SetUserLoginFn>(loaded.module, "bambu_network_set_on_user_login_fn", loaded.missing);
    loaded.set_on_server_connected = load_symbol<SetServerConnectedFn>(loaded.module, "bambu_network_set_on_server_connected_fn", loaded.missing);
    loaded.set_on_http_error = load_symbol<SetHttpErrorFn>(loaded.module, "bambu_network_set_on_http_error_fn", loaded.missing);
    loaded.set_on_message = load_symbol<SetMessageFn>(loaded.module, "bambu_network_set_on_message_fn", loaded.missing);
    loaded.set_on_subscribe_failure = load_symbol<SetStringCallbackFn>(loaded.module, "bambu_network_set_on_subscribe_failure_fn", loaded.missing);
    return loaded;
}

bool service_result_present(const std::map<std::string, std::string>& results, const std::string& key)
{
    return results.find(key) != results.end() && results.at(key) != std::to_string(unsupported_result);
}

void trace_phase(const Args& args, const char* phase)
{
    if (args.trace_phases)
        std::cerr << "cloud_service_probe phase: " << phase << "\n";
}

void trace_public_value(const Args& args, const char* name, const std::string& value)
{
    if (args.trace_phases)
        std::cerr << "cloud_service_probe value: " << name << "=" << value << "\n";
}

} // namespace

int main(int argc, char** argv)
{
    Args args;
    if (!parse_args(argc, argv, args)) {
        std::cerr << "usage: " << argv[0]
                  << " --plugin <path> [--user-info-file <path>|--user-info-env <name>] [--allow-network] [--expect-success]\n";
        return 2;
    }
    if (args.expect_success && !args.allow_network) {
        std::cerr << "--expect-success requires --allow-network\n";
        return 2;
    }

    std::filesystem::create_directories(args.log_dir);

    trace_phase(args, "load_plugin");
    Loaded plugin = load_plugin(args.plugin);
    if (!plugin.module) {
        const char* error = dlerror();
        std::cerr << "dlopen plugin failed: " << (error ? error : "unknown error") << "\n";
        return 3;
    }

    trace_phase(args, "create_agent");
    void* agent = plugin.create_agent ? plugin.create_agent(args.log_dir) : nullptr;
    std::map<std::string, std::string> results;
    std::map<std::string, std::string> contract;
    int user_login_callbacks = 0;
    int server_connected_callbacks = 0;
    int http_error_callbacks = 0;
    int message_callbacks = 0;
    int subscribe_failure_callbacks = 0;

    trace_phase(args, "configure");
    if (plugin.set_config_dir)
        results["set_config_dir"] = number(plugin.set_config_dir(agent, args.log_dir));
    if (plugin.init_log)
        results["init_log"] = number(plugin.init_log(agent));
    if (plugin.set_cert_file)
        results["set_cert_file"] = number(plugin.set_cert_file(agent, "resources/cert", "slicer_base64.cer"));
    if (plugin.set_country_code)
        results["set_country_code"] = number(plugin.set_country_code(agent, "US"));
    if (plugin.set_on_user_login)
        results["set_on_user_login"] = number(plugin.set_on_user_login(agent, [&](int, bool) { user_login_callbacks++; }));
    if (plugin.set_on_server_connected)
        results["set_on_server_connected"] = number(plugin.set_on_server_connected(agent, [&](int, int) { server_connected_callbacks++; }));
    if (plugin.set_on_http_error)
        results["set_on_http_error"] = number(plugin.set_on_http_error(agent, [&](unsigned int, std::string) { http_error_callbacks++; }));
    if (plugin.set_on_message)
        results["set_on_message"] = number(plugin.set_on_message(agent, [&](std::string, std::string) { message_callbacks++; }));
    if (plugin.set_on_subscribe_failure)
        results["set_on_subscribe_failure"] = number(plugin.set_on_subscribe_failure(agent, [&](std::string) { subscribe_failure_callbacks++; }));
    if (plugin.start)
        results["start"] = number(plugin.start(agent));

    trace_phase(args, "login_state");
    const std::string user_info = user_info_payload(args);
    contract["user_info_supplied"] = boolean(!user_info.empty());
    if (plugin.change_user && !user_info.empty()) {
        trace_phase(args, "change_user");
        results["change_user"] = number(plugin.change_user(agent, user_info));
    }
    if (plugin.is_user_login) {
        trace_phase(args, "is_user_login");
        results["is_user_login"] = boolean(plugin.is_user_login(agent));
    }

    const bool probe_user_details = !user_info.empty()
        || (results.find("is_user_login") != results.end() && results["is_user_login"] == "true");
    contract["user_details_probed"] = boolean(probe_user_details);
    if (probe_user_details && plugin.build_login_cmd) {
        trace_phase(args, "build_login_cmd");
        contract["build_login_cmd"] = normalized_string(plugin.build_login_cmd(agent));
    }
    if (probe_user_details && plugin.build_login_info) {
        trace_phase(args, "build_login_info");
        contract["build_login_info"] = normalized_string(plugin.build_login_info(agent));
    }
    if (probe_user_details && plugin.build_logout_cmd) {
        trace_phase(args, "build_logout_cmd");
        contract["build_logout_cmd"] = normalized_string(plugin.build_logout_cmd(agent));
    }
    if (probe_user_details && plugin.get_user_id) {
        trace_phase(args, "get_user_id");
        contract["get_user_id"] = normalized_string(plugin.get_user_id(agent));
    }
    if (probe_user_details && plugin.get_user_name) {
        trace_phase(args, "get_user_name");
        contract["get_user_name"] = normalized_string(plugin.get_user_name(agent));
    }
    if (probe_user_details && plugin.get_user_nickname) {
        trace_phase(args, "get_user_nickname");
        contract["get_user_nickname"] = normalized_string(plugin.get_user_nickname(agent));
    }
    if (probe_user_details && plugin.get_user_avatar) {
        trace_phase(args, "get_user_avatar");
        contract["get_user_avatar"] = normalized_url(plugin.get_user_avatar(agent));
    }
    if (plugin.get_bambulab_host) {
        trace_phase(args, "get_bambulab_host");
        const std::string value = plugin.get_bambulab_host(agent);
        trace_public_value(args, "get_bambulab_host", value);
        contract["get_bambulab_host"] = normalized_url(value);
    }
    if (plugin.get_studio_info_url) {
        trace_phase(args, "get_studio_info_url");
        const std::string value = plugin.get_studio_info_url(agent);
        trace_public_value(args, "get_studio_info_url", value);
        contract["get_studio_info_url"] = normalized_url(value);
    }
    if (plugin.get_user_selected_machine) {
        trace_phase(args, "get_user_selected_machine");
        contract["get_user_selected_machine"] = normalized_string(plugin.get_user_selected_machine(agent));
    }

    trace_phase(args, "network_services");
    if (args.allow_network && plugin.connect_server)
        results["connect_server"] = number(plugin.connect_server(agent));
    if (args.allow_network && plugin.is_server_connected)
        results["is_server_connected"] = boolean(plugin.is_server_connected(agent));
    if (args.allow_network && plugin.refresh_connection)
        results["refresh_connection"] = number(plugin.refresh_connection(agent));
    if (args.allow_network && plugin.start_subscribe)
        results["start_subscribe"] = number(plugin.start_subscribe(agent, args.subscribe_module));
    if (args.allow_network && plugin.add_subscribe)
        results["add_subscribe"] = number(plugin.add_subscribe(agent, {args.subscribe_module}));

    if (args.allow_network && plugin.get_model_mall_home_url) {
        std::string url;
        results["get_model_mall_home_url"] = number(plugin.get_model_mall_home_url(agent, &url));
        contract["get_model_mall_home_url"] = normalized_url(url);
    }
    if (args.allow_network && plugin.get_model_mall_detail_url) {
        std::string url;
        results["get_model_mall_detail_url"] = number(plugin.get_model_mall_detail_url(agent, &url, args.detail_id));
        contract["get_model_mall_detail_url"] = normalized_url(url);
    }
    if (args.allow_network && plugin.get_model_publish_url) {
        std::string url;
        results["get_model_publish_url"] = number(plugin.get_model_publish_url(agent, &url));
        contract["get_model_publish_url"] = normalized_url(url);
    }
    if (args.allow_network && plugin.get_user_print_info) {
        unsigned int http_code = 0;
        std::string body;
        results["get_user_print_info"] = number(plugin.get_user_print_info(agent, &http_code, &body));
        contract["get_user_print_info_http_code"] = unsigned_number(http_code);
        contract["get_user_print_info_body"] = normalized_string(body);
    }
    if (args.allow_network && plugin.get_user_tasks) {
        Slic3r::TaskQueryParams params;
        std::string body;
        results["get_user_tasks"] = number(plugin.get_user_tasks(agent, params, &body));
        contract["get_user_tasks_body"] = normalized_string(body);
    }
    if (args.allow_network && plugin.get_my_message) {
        unsigned int http_code = 0;
        std::string body;
        results["get_my_message"] = number(plugin.get_my_message(agent, 0, 0, 20, &http_code, &body));
        contract["get_my_message_http_code"] = unsigned_number(http_code);
        contract["get_my_message_body"] = normalized_string(body);
    }
    if (args.allow_network && plugin.request_bind_ticket) {
        std::string ticket;
        results["request_bind_ticket"] = number(plugin.request_bind_ticket(agent, &ticket));
        contract["request_bind_ticket"] = normalized_string(ticket);
    }
    if (args.allow_network && plugin.query_bind_status) {
        unsigned int http_code = 0;
        std::string body;
        results["query_bind_status"] = number(plugin.query_bind_status(agent, {}, &http_code, &body));
        contract["query_bind_status_http_code"] = unsigned_number(http_code);
        contract["query_bind_status_body"] = normalized_string(body);
    }
    if (args.allow_network && plugin.get_user_info) {
        int identifier = 0;
        results["get_user_info"] = number(plugin.get_user_info(agent, &identifier));
        contract["get_user_info_identifier_positive"] = boolean(identifier > 0);
    }
    if (args.allow_network && plugin.get_task_plate_index) {
        int plate_index = -1;
        results["get_task_plate_index"] = number(plugin.get_task_plate_index(agent, args.task_id, &plate_index));
        contract["get_task_plate_index_nonnegative"] = boolean(plate_index >= 0);
    }
    if (args.allow_network && plugin.get_model_mall_rating) {
        std::string rating;
        unsigned int http_code = 0;
        std::string http_error;
        results["get_model_mall_rating"] = number(plugin.get_model_mall_rating(agent, 0, rating, http_code, http_error));
        contract["get_model_mall_rating_http_code"] = unsigned_number(http_code);
        contract["get_model_mall_rating_body"] = normalized_string(rating);
        contract["get_model_mall_rating_http_error"] = normalized_string(http_error);
    }
    if (args.allow_network && plugin.get_design_staffpick) {
        int callback_count = 0;
        std::string body;
        results["get_design_staffpick"] = number(plugin.get_design_staffpick(agent, 0, 20, [&](std::string value) {
            callback_count += 1;
            body = std::move(value);
        }));
        contract["get_design_staffpick_callback_count"] = number(callback_count);
        contract["get_design_staffpick_body"] = normalized_string(body);
    }
    if (args.allow_network && plugin.get_mw_user_preference) {
        int callback_count = 0;
        std::string body;
        results["get_mw_user_preference"] = number(plugin.get_mw_user_preference(agent, [&](std::string value) {
            callback_count += 1;
            body = std::move(value);
        }));
        contract["get_mw_user_preference_callback_count"] = number(callback_count);
        contract["get_mw_user_preference_body"] = normalized_string(body);
    }
    if (args.allow_network && plugin.get_mw_user_4ulist) {
        int callback_count = 0;
        std::string body;
        results["get_mw_user_4ulist"] = number(plugin.get_mw_user_4ulist(agent, 0, 20, [&](std::string value) {
            callback_count += 1;
            body = std::move(value);
        }));
        contract["get_mw_user_4ulist_callback_count"] = number(callback_count);
        contract["get_mw_user_4ulist_body"] = normalized_string(body);
    }
    if (args.allow_network && plugin.get_hms_snapshot) {
        int callback_count = 0;
        int callback_http_code = 0;
        std::string body;
        results["get_hms_snapshot"] = number(plugin.get_hms_snapshot(agent, "mock-dev", args.subscribe_module, [&](std::string value, int code) {
            callback_count += 1;
            callback_http_code = code;
            body = std::move(value);
        }));
        contract["get_hms_snapshot_callback_count"] = number(callback_count);
        contract["get_hms_snapshot_http_code"] = number(callback_http_code);
        contract["get_hms_snapshot_body"] = normalized_string(body);
    }

    const std::string ticket = env_value(args.ticket_env);
    contract["ticket_supplied"] = boolean(!ticket.empty());
    if (args.allow_network && plugin.get_my_token && !ticket.empty()) {
        unsigned int http_code = 0;
        std::string body;
        results["get_my_token"] = number(plugin.get_my_token(agent, ticket, &http_code, &body));
        contract["get_my_token_http_code"] = unsigned_number(http_code);
        contract["get_my_token_body"] = normalized_string(body);
    }

    const std::string access_token = env_value(args.access_token_env);
    contract["access_token_supplied"] = boolean(!access_token.empty());
    if (args.allow_network && plugin.get_my_profile && !access_token.empty()) {
        unsigned int http_code = 0;
        std::string body;
        results["get_my_profile"] = number(plugin.get_my_profile(agent, access_token, &http_code, &body));
        contract["get_my_profile_http_code"] = unsigned_number(http_code);
        contract["get_my_profile_body"] = normalized_string(body);
    }

    if (args.allow_network && plugin.del_subscribe)
        results["del_subscribe"] = number(plugin.del_subscribe(agent, {args.subscribe_module}));
    if (args.allow_network && plugin.stop_subscribe)
        results["stop_subscribe"] = number(plugin.stop_subscribe(agent, args.subscribe_module));
    trace_phase(args, "logout");
    if (plugin.user_logout && !user_info.empty())
        results["user_logout"] = number(plugin.user_logout(agent, false));

    trace_phase(args, "destroy");
    int destroy_result = -999999;
    if (plugin.destroy_agent && agent)
        destroy_result = plugin.destroy_agent(agent);

    int non_unsupported_service_results = 0;
    for (const auto& [key, value] : results) {
        if (key.rfind("get_", 0) == 0 || key.rfind("request_", 0) == 0 || key.rfind("query_", 0) == 0)
            non_unsupported_service_results += service_result_present(results, key) ? 1 : 0;
    }

    const bool login_ok = !user_info.empty()
        && results.find("change_user") != results.end()
        && results["change_user"] == "0"
        && results.find("is_user_login") != results.end()
        && results["is_user_login"] == "true";
    const bool network_ok = !args.allow_network
        || (results.find("connect_server") != results.end() && results["connect_server"] == "0");
    const bool service_ok = !args.allow_network || non_unsupported_service_results > 0;
    const bool semantic_ok = plugin.missing.empty() && agent && login_ok && network_ok && service_ok;
    const bool ok = args.expect_success ? semantic_ok : plugin.missing.empty() && agent;

    std::cout << "{\n";
    std::cout << "  \"plugin\": \"" << json_escape(args.plugin) << "\",\n";
    std::cout << "  \"log_dir\": \"" << json_escape(args.log_dir) << "\",\n";
    std::cout << "  \"allow_network\": " << (args.allow_network ? "true" : "false") << ",\n";
    std::cout << "  \"expect_success\": " << (args.expect_success ? "true" : "false") << ",\n";
    std::cout << "  \"agent_created\": " << (agent ? "true" : "false") << ",\n";
    std::cout << "  \"missing_symbols\": ";
    write_string_array(plugin.missing);
    std::cout << ",\n";
    std::cout << "  \"results\": ";
    write_result_map(results);
    std::cout << ",\n";
    std::cout << "  \"contract\": ";
    write_result_map(contract);
    std::cout << ",\n";
    std::cout << "  \"callbacks\": {"
              << "\"user_login\": " << user_login_callbacks << ", "
              << "\"server_connected\": " << server_connected_callbacks << ", "
              << "\"http_error\": " << http_error_callbacks << ", "
              << "\"message\": " << message_callbacks << ", "
              << "\"subscribe_failure\": " << subscribe_failure_callbacks
              << "},\n";
    std::cout << "  \"semantic\": {"
              << "\"login_ok\": " << (login_ok ? "true" : "false") << ", "
              << "\"network_ok\": " << (network_ok ? "true" : "false") << ", "
              << "\"service_ok\": " << (service_ok ? "true" : "false") << ", "
              << "\"non_unsupported_service_results\": " << non_unsupported_service_results
              << "},\n";
    std::cout << "  \"destroy_result\": " << destroy_result << ",\n";
    std::cout << "  \"ok\": " << (ok ? "true" : "false") << "\n";
    std::cout << "}\n";

    dlclose(plugin.module);
    return ok ? 0 : 1;
}
