#include <dlfcn.h>

#include <cstdint>
#include <filesystem>
#include <iostream>
#include <map>
#include <string>
#include <vector>

namespace {

struct FtJobResult {
    int ec;
    int resp_ec;
    const char* json;
    const void* bin;
    std::uint32_t bin_size;
};

struct FtJobMsg {
    int kind;
    const char* json;
};

using FtTunnelCreateFn = int (*)(const char*, void**);
using FtTunnelReleaseFn = void (*)(void*);
using FtTunnelStartConnectFn = int (*)(void*, void (*)(void*, int, int, const char*), void*);
using FtTunnelSyncConnectFn = int (*)(void*);
using FtTunnelSetStatusCbFn = int (*)(void*, void (*)(void*, int, int, int, const char*), void*);
using FtTunnelShutdownFn = int (*)(void*);
using FtTunnelStartJobFn = int (*)(void*, void*);
using FtJobCreateFn = int (*)(const char*, void**);
using FtJobReleaseFn = void (*)(void*);
using FtJobSetResultCbFn = int (*)(void*, void (*)(void*, FtJobResult), void*);
using FtJobGetResultFn = int (*)(void*, std::uint32_t, FtJobResult*);
using FtJobResultDestroyFn = void (*)(FtJobResult*);
using FtJobCancelFn = int (*)(void*);
using FtJobSetMsgCbFn = int (*)(void*, void (*)(void*, FtJobMsg), void*);
using FtJobGetMsgFn = int (*)(void*, std::uint32_t, FtJobMsg*);
using FtJobTryGetMsgFn = int (*)(void*, FtJobMsg*);
using FtJobMsgDestroyFn = void (*)(FtJobMsg*);
using FtFreeFn = void (*)(void*);
using FtAbiVersionFn = int (*)();
using CreateAgentFn = void* (*)(std::string);
using DestroyAgentFn = int (*)(void*);
using IntAgentFn = int (*)(void*);
using SetStringFn = int (*)(void*, std::string);
using SetCertFileFn = int (*)(void*, std::string, std::string);

FtJobResultDestroyFn g_destroy_result = nullptr;
FtJobMsgDestroyFn g_destroy_msg = nullptr;

struct ResultCapture {
    int calls{};
    int ec{999};
    int resp_ec{999};
    std::string json;
};

struct MsgCapture {
    int calls{};
    int first_kind{999};
    std::string first_json;
};

struct ConnectionCapture {
    int calls{};
    bool success{};
    int error{999};
    std::string message;
};

struct StatusCapture {
    int calls{};
    int last_old{999};
    int last_new{999};
    int last_error{999};
    std::string last_message;
};

struct Args {
    std::string plugin;
    std::string log_dir{"."};
    std::string tunnel_url{"bambu:///local/127.0.0.1?port=6000&user=bblp&passwd=secret"};
    bool skip_agent_bootstrap{false};
    bool job_only{false};
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
        } else if (arg == "--tunnel-url" && i + 1 < argc) {
            args.tunnel_url = argv[++i];
        } else if (arg == "--skip-agent-bootstrap") {
            args.skip_agent_bootstrap = true;
        } else if (arg == "--job-only") {
            args.job_only = true;
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

void on_result(void* user, FtJobResult result)
{
    auto* capture = static_cast<ResultCapture*>(user);
    capture->calls++;
    capture->ec = result.ec;
    capture->resp_ec = result.resp_ec;
    capture->json = result.json ? result.json : "";
    if (g_destroy_result)
        g_destroy_result(&result);
}

void on_msg(void* user, FtJobMsg msg)
{
    auto* capture = static_cast<MsgCapture*>(user);
    capture->calls++;
    if (capture->calls == 1) {
        capture->first_kind = msg.kind;
        capture->first_json = msg.json ? msg.json : "";
    }
    if (g_destroy_msg)
        g_destroy_msg(&msg);
}

void on_connect(void* user, int ok, int error, const char* message)
{
    auto* capture = static_cast<ConnectionCapture*>(user);
    capture->calls++;
    capture->success = ok == 0;
    capture->error = error;
    capture->message = message ? message : "";
}

void on_status(void* user, int old_status, int new_status, int error, const char* message)
{
    auto* capture = static_cast<StatusCapture*>(user);
    capture->calls++;
    capture->last_old = old_status;
    capture->last_new = new_status;
    capture->last_error = error;
    capture->last_message = message ? message : "";
}

bool contains(const std::string& value, const std::string& needle)
{
    return value.find(needle) != std::string::npos;
}

}

int main(int argc, char** argv)
{
    Args args;
    if (!parse_args(argc, argv, args)) {
        std::cerr << "usage: " << argv[0] << " --plugin <path> [--log-dir <path>] [--tunnel-url <url>] [--skip-agent-bootstrap] [--job-only]\n";
        return 2;
    }
    std::filesystem::create_directories(args.log_dir);

    void* network = dlopen(args.plugin.c_str(), RTLD_LAZY | RTLD_LOCAL);
    if (!network) {
        const char* error = dlerror();
        std::cerr << "dlopen failed: " << (error ? error : "unknown error") << "\n";
        return 3;
    }

    std::vector<std::string> missing;
    auto ft_abi_version = load_symbol<FtAbiVersionFn>(network, "ft_abi_version", missing);
    auto create_agent = load_symbol<CreateAgentFn>(network, "bambu_network_create_agent", missing);
    auto destroy_agent = load_symbol<DestroyAgentFn>(network, "bambu_network_destroy_agent", missing);
    auto init_log = load_symbol<IntAgentFn>(network, "bambu_network_init_log", missing);
    auto set_config_dir = load_symbol<SetStringFn>(network, "bambu_network_set_config_dir", missing);
    auto set_cert_file = load_symbol<SetCertFileFn>(network, "bambu_network_set_cert_file", missing);
    auto set_country_code = load_symbol<SetStringFn>(network, "bambu_network_set_country_code", missing);
    auto tunnel_create = load_symbol<FtTunnelCreateFn>(network, "ft_tunnel_create", missing);
    auto tunnel_release = load_symbol<FtTunnelReleaseFn>(network, "ft_tunnel_release", missing);
    auto tunnel_start_connect = load_symbol<FtTunnelStartConnectFn>(network, "ft_tunnel_start_connect", missing);
    auto tunnel_sync_connect = load_symbol<FtTunnelSyncConnectFn>(network, "ft_tunnel_sync_connect", missing);
    auto tunnel_set_status_cb = load_symbol<FtTunnelSetStatusCbFn>(network, "ft_tunnel_set_status_cb", missing);
    auto tunnel_shutdown = load_symbol<FtTunnelShutdownFn>(network, "ft_tunnel_shutdown", missing);
    auto tunnel_start_job = load_symbol<FtTunnelStartJobFn>(network, "ft_tunnel_start_job", missing);
    auto job_create = load_symbol<FtJobCreateFn>(network, "ft_job_create", missing);
    auto job_release = load_symbol<FtJobReleaseFn>(network, "ft_job_release", missing);
    auto job_set_result_cb = load_symbol<FtJobSetResultCbFn>(network, "ft_job_set_result_cb", missing);
    auto job_get_result = load_symbol<FtJobGetResultFn>(network, "ft_job_get_result", missing);
    g_destroy_result = load_symbol<FtJobResultDestroyFn>(network, "ft_job_result_destroy", missing);
    auto job_cancel = load_symbol<FtJobCancelFn>(network, "ft_job_cancel", missing);
    auto job_set_msg_cb = load_symbol<FtJobSetMsgCbFn>(network, "ft_job_set_msg_cb", missing);
    auto job_get_msg = load_symbol<FtJobGetMsgFn>(network, "ft_job_get_msg", missing);
    auto job_try_get_msg = load_symbol<FtJobTryGetMsgFn>(network, "ft_job_try_get_msg", missing);
    g_destroy_msg = load_symbol<FtJobMsgDestroyFn>(network, "ft_job_msg_destroy", missing);
    auto ft_free = load_symbol<FtFreeFn>(network, "ft_free", missing);

    void* tunnel = nullptr;
    ConnectionCapture connection;
    StatusCapture status;
    ResultCapture media_result;
    ResultCapture upload_result;
    ResultCapture media_polled_result;
    MsgCapture upload_msg;

    std::map<std::string, std::string> results;
    if (ft_abi_version)
        results["ft_abi_version"] = std::to_string(ft_abi_version());
    void* agent = nullptr;
    if (!args.skip_agent_bootstrap) {
        std::cerr << "ft_probe: create_agent\n";
        agent = create_agent ? create_agent(args.log_dir) : nullptr;
        results["agent_handle"] = agent ? "true" : "false";
        if (set_config_dir)
            results["set_config_dir"] = std::to_string(set_config_dir(agent, args.log_dir));
        if (init_log)
            results["init_log"] = std::to_string(init_log(agent));
        if (set_cert_file)
            results["set_cert_file"] = std::to_string(set_cert_file(agent, "resources/cert", "slicer_base64.cer"));
        if (set_country_code)
            results["set_country_code"] = std::to_string(set_country_code(agent, "US"));
    } else {
        results["agent_bootstrap_skipped"] = "true";
    }

    if (args.job_only) {
        void* job = nullptr;
        if (job_create)
            results["job_create_empty"] = std::to_string(job_create("{}", &job));
        results["job_handle"] = job ? "true" : "false";
        if (job_release && job)
            job_release(job);
        if (destroy_agent && agent)
            results["destroy_agent"] = std::to_string(destroy_agent(agent));

        const bool ok = missing.empty()
            && results["ft_abi_version"] == "1"
            && results["job_create_empty"] == "-6"
            && results["job_handle"] == "false";

        std::cout << "{\n";
        std::cout << "  \"plugin\": \"" << json_escape(args.plugin) << "\",\n";
        std::cout << "  \"missing_symbols\": ";
        write_string_array(missing);
        std::cout << ",\n";
        std::cout << "  \"results\": {";
        std::size_t index = 0;
        for (const auto& [key, value] : results) {
            if (index++ > 0)
                std::cout << ", ";
            std::cout << "\"" << json_escape(key) << "\": " << value;
        }
        std::cout << "},\n";
        std::cout << "  \"ok\": " << (ok ? "true" : "false") << "\n";
        std::cout << "}\n";

        dlclose(network);
        return ok ? 0 : 1;
    }

    if (tunnel_create)
        results["tunnel_create"] = std::to_string(tunnel_create(args.tunnel_url.c_str(), &tunnel));
    results["tunnel_handle"] = tunnel ? "true" : "false";
    if (tunnel_set_status_cb)
        results["tunnel_set_status_cb"] = std::to_string(tunnel_set_status_cb(tunnel, on_status, &status));
    if (tunnel_start_connect)
        results["tunnel_start_connect"] = std::to_string(tunnel_start_connect(tunnel, on_connect, &connection));
    if (tunnel_sync_connect)
        results["tunnel_sync_connect"] = std::to_string(tunnel_sync_connect(tunnel));

    void* media_job = nullptr;
    if (job_create)
        results["media_job_create"] = std::to_string(job_create(R"({"cmd_type":7})", &media_job));
    if (job_set_result_cb)
        results["media_job_set_result_cb"] = std::to_string(job_set_result_cb(media_job, on_result, &media_result));
    if (tunnel_start_job)
        results["media_tunnel_start_job"] = std::to_string(tunnel_start_job(tunnel, media_job));
    if (job_get_result) {
        FtJobResult result{};
        results["media_job_get_result"] = std::to_string(job_get_result(media_job, 0, &result));
        media_polled_result.ec = result.ec;
        media_polled_result.resp_ec = result.resp_ec;
        media_polled_result.json = result.json ? result.json : "";
        if (g_destroy_result)
            g_destroy_result(&result);
    }

    void* upload_job = nullptr;
    if (job_create)
        results["upload_job_create"] = std::to_string(job_create(R"({"cmd_type":5,"dest_storage":"emmc","dest_name":"missing.3mf","file_path":"/tmp/bambu-network-ft-missing.3mf"})", &upload_job));
    if (job_set_result_cb)
        results["upload_job_set_result_cb"] = std::to_string(job_set_result_cb(upload_job, on_result, &upload_result));
    if (job_set_msg_cb)
        results["upload_job_set_msg_cb"] = std::to_string(job_set_msg_cb(upload_job, on_msg, &upload_msg));
    if (tunnel_start_job)
        results["upload_tunnel_start_job"] = std::to_string(tunnel_start_job(tunnel, upload_job));
    FtJobMsg polled_msg{};
    if (job_try_get_msg) {
        results["upload_job_try_get_msg"] = std::to_string(job_try_get_msg(upload_job, &polled_msg));
        if (g_destroy_msg)
            g_destroy_msg(&polled_msg);
    }
    FtJobMsg empty_msg{};
    if (job_get_msg)
        results["upload_job_get_msg_after_drain"] = std::to_string(job_get_msg(upload_job, 0, &empty_msg));

    void* cancel_job = nullptr;
    ResultCapture cancel_result;
    if (job_create)
        results["cancel_job_create"] = std::to_string(job_create(R"({"cmd_type":7})", &cancel_job));
    if (job_set_result_cb)
        results["cancel_job_set_result_cb"] = std::to_string(job_set_result_cb(cancel_job, on_result, &cancel_result));
    if (job_cancel)
        results["cancel_job_cancel"] = std::to_string(job_cancel(cancel_job));
    if (ft_free) {
        ft_free(nullptr);
        results["ft_free_null_called"] = "true";
    }
    if (tunnel_shutdown)
        results["tunnel_shutdown"] = std::to_string(tunnel_shutdown(tunnel));

    if (job_release && cancel_job)
        job_release(cancel_job);
    if (job_release && upload_job)
        job_release(upload_job);
    if (job_release && media_job)
        job_release(media_job);
    if (tunnel_release && tunnel)
        tunnel_release(tunnel);
    if (destroy_agent && agent)
        results["destroy_agent"] = std::to_string(destroy_agent(agent));

    const bool ok = missing.empty()
        && results["tunnel_create"] == "0"
        && results["tunnel_handle"] == "true"
        && results["tunnel_set_status_cb"] == "0"
        && results["tunnel_start_connect"] == "0"
        && results["tunnel_sync_connect"] == "0"
        && connection.calls == 1
        && connection.success
        && status.calls >= 2
        && results["media_job_create"] == "0"
        && results["media_job_set_result_cb"] == "0"
        && results["media_tunnel_start_job"] == "0"
        && media_result.calls == 1
        && media_result.ec == 0
        && contains(media_result.json, "emmc")
        && results["media_job_get_result"] == "0"
        && media_polled_result.ec == 0
        && contains(media_polled_result.json, "sdcard")
        && results["upload_job_create"] == "0"
        && results["upload_job_set_result_cb"] == "0"
        && results["upload_job_set_msg_cb"] == "0"
        && results["upload_tunnel_start_job"] == "0"
        && results["upload_job_try_get_msg"] == "0"
        && results["upload_job_get_msg_after_drain"] == "-4"
        && upload_result.calls == 1
        && upload_result.ec == -3
        && upload_msg.calls >= 1
        && contains(upload_msg.first_json, "progress")
        && results["cancel_job_create"] == "0"
        && results["cancel_job_set_result_cb"] == "0"
        && results["cancel_job_cancel"] == "0"
        && cancel_result.calls == 1
        && cancel_result.ec == -5
        && results["ft_free_null_called"] == "true"
        && results["tunnel_shutdown"] == "0";

    std::cout << "{\n";
    std::cout << "  \"plugin\": \"" << json_escape(args.plugin) << "\",\n";
    std::cout << "  \"missing_symbols\": ";
    write_string_array(missing);
    std::cout << ",\n";
    std::cout << "  \"results\": {";
    std::size_t index = 0;
    for (const auto& [key, value] : results) {
        if (index++ > 0)
            std::cout << ", ";
        std::cout << "\"" << json_escape(key) << "\": " << value;
    }
    std::cout << "},\n";
    std::cout << "  \"connection_calls\": " << connection.calls << ",\n";
    std::cout << "  \"connection_success\": " << (connection.success ? "true" : "false") << ",\n";
    std::cout << "  \"status_calls\": " << status.calls << ",\n";
    std::cout << "  \"media_result_calls\": " << media_result.calls << ",\n";
    std::cout << "  \"media_result_ec\": " << media_result.ec << ",\n";
    std::cout << "  \"media_result_json\": \"" << json_escape(media_result.json) << "\",\n";
    std::cout << "  \"media_polled_result_ec\": " << media_polled_result.ec << ",\n";
    std::cout << "  \"media_polled_result_json\": \"" << json_escape(media_polled_result.json) << "\",\n";
    std::cout << "  \"upload_result_calls\": " << upload_result.calls << ",\n";
    std::cout << "  \"upload_result_ec\": " << upload_result.ec << ",\n";
    std::cout << "  \"upload_msg_calls\": " << upload_msg.calls << ",\n";
    std::cout << "  \"upload_first_msg\": \"" << json_escape(upload_msg.first_json) << "\",\n";
    std::cout << "  \"cancel_result_calls\": " << cancel_result.calls << ",\n";
    std::cout << "  \"cancel_result_ec\": " << cancel_result.ec << ",\n";
    std::cout << "  \"ok\": " << (ok ? "true" : "false") << "\n";
    std::cout << "}\n";

    dlclose(network);
    return ok ? 0 : 1;
}
