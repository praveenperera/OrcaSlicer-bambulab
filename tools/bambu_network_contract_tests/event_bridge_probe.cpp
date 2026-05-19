#include <dlfcn.h>

#include <functional>
#include <iostream>
#include <map>
#include <string>
#include <vector>

namespace {

using CreateAgentFn = void* (*)(std::string);
using DestroyAgentFn = int (*)(void*);
using SetSsdpFn = int (*)(void*, std::function<void(std::string)>);
using SetPrinterConnectedFn = int (*)(void*, std::function<void(std::string)>);
using SetMessageFn = int (*)(void*, std::function<void(std::string, std::string)>);
using SetLocalConnectedFn = int (*)(void*, std::function<void(int, std::string, std::string)>);
using SetServerCallbackFn = int (*)(void*, std::function<void(std::string, int)>);

using EmitStringFn = int (*)(void*, const char*);
using EmitMessageFn = int (*)(void*, const char*, const char*);
using EmitLocalConnectFn = int (*)(void*, int, const char*, const char*);
using EmitServerErrorFn = int (*)(void*, const char*, int);

struct Args {
    std::string plugin_path;
    std::string log_dir{"."};
};

struct Counters {
    int ssdp{0};
    int printer_connected{0};
    int message{0};
    int local_connect{0};
    int local_message{0};
    int server_error{0};
};

std::string json_escape(const std::string& value)
{
    std::string out;
    out.reserve(value.size() + 8);
    for (char ch : value) {
        switch (ch) {
        case '\\':
            out += "\\\\";
            break;
        case '"':
            out += "\\\"";
            break;
        case '\n':
            out += "\\n";
            break;
        case '\r':
            out += "\\r";
            break;
        case '\t':
            out += "\\t";
            break;
        default:
            out.push_back(ch);
            break;
        }
    }
    return out;
}

bool parse_args(int argc, char** argv, Args& args)
{
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--plugin" && i + 1 < argc) {
            args.plugin_path = argv[++i];
        } else if (arg == "--log-dir" && i + 1 < argc) {
            args.log_dir = argv[++i];
        } else {
            return false;
        }
    }
    return !args.plugin_path.empty();
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

void write_result_map(const std::map<std::string, int>& values)
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

} // namespace

int main(int argc, char** argv)
{
    Args args;
    if (!parse_args(argc, argv, args)) {
        std::cerr << "usage: " << argv[0] << " --plugin <path> [--log-dir <path>]\n";
        return 2;
    }

    void* module = dlopen(args.plugin_path.c_str(), RTLD_LAZY | RTLD_LOCAL);
    if (!module) {
        const char* error = dlerror();
        std::cerr << "dlopen failed: " << (error ? error : "unknown error") << "\n";
        return 3;
    }

    std::vector<std::string> missing;
    auto create_agent = load_symbol<CreateAgentFn>(module, "bambu_network_create_agent", missing);
    auto destroy_agent = load_symbol<DestroyAgentFn>(module, "bambu_network_destroy_agent", missing);
    auto set_ssdp = load_symbol<SetSsdpFn>(module, "bambu_network_set_on_ssdp_msg_fn", missing);
    auto set_printer_connected = load_symbol<SetPrinterConnectedFn>(module, "bambu_network_set_on_printer_connected_fn", missing);
    auto set_message = load_symbol<SetMessageFn>(module, "bambu_network_set_on_message_fn", missing);
    auto set_local_connect = load_symbol<SetLocalConnectedFn>(module, "bambu_network_set_on_local_connect_fn", missing);
    auto set_local_message = load_symbol<SetMessageFn>(module, "bambu_network_set_on_local_message_fn", missing);
    auto set_server_callback = load_symbol<SetServerCallbackFn>(module, "bambu_network_set_server_callback", missing);

    auto emit_ssdp = load_symbol<EmitStringFn>(module, "brs_shim_test_emit_ssdp", missing);
    auto emit_printer_connected = load_symbol<EmitStringFn>(module, "brs_shim_test_emit_printer_connected", missing);
    auto emit_message = load_symbol<EmitMessageFn>(module, "brs_shim_test_emit_message", missing);
    auto emit_local_connect = load_symbol<EmitLocalConnectFn>(module, "brs_shim_test_emit_local_connect", missing);
    auto emit_local_message = load_symbol<EmitMessageFn>(module, "brs_shim_test_emit_local_message", missing);
    auto emit_server_error = load_symbol<EmitServerErrorFn>(module, "brs_shim_test_emit_server_error", missing);

    void* agent = create_agent ? create_agent(args.log_dir) : nullptr;
    Counters counters;
    std::map<std::string, int> results;

    std::string last_ssdp;
    std::string last_printer_topic;
    std::string last_message;
    std::string last_local_connect;
    std::string last_local_message;
    std::string last_server_error;

    if (set_ssdp)
        results["set_ssdp"] = set_ssdp(agent, [&](std::string value) {
            counters.ssdp++;
            last_ssdp = value;
        });
    if (set_printer_connected)
        results["set_printer_connected"] = set_printer_connected(agent, [&](std::string value) {
            counters.printer_connected++;
            last_printer_topic = value;
        });
    if (set_message)
        results["set_message"] = set_message(agent, [&](std::string dev_id, std::string value) {
            counters.message++;
            last_message = dev_id + "|" + value;
        });
    if (set_local_connect)
        results["set_local_connect"] = set_local_connect(agent, [&](int status, std::string dev_id, std::string value) {
            counters.local_connect++;
            last_local_connect = std::to_string(status) + "|" + dev_id + "|" + value;
        });
    if (set_local_message)
        results["set_local_message"] = set_local_message(agent, [&](std::string dev_id, std::string value) {
            counters.local_message++;
            last_local_message = dev_id + "|" + value;
        });
    if (set_server_callback)
        results["set_server_callback"] = set_server_callback(agent, [&](std::string url, int status) {
            counters.server_error++;
            last_server_error = url + "|" + std::to_string(status);
        });

    if (emit_ssdp)
        results["emit_ssdp"] = emit_ssdp(agent, "{\"dev_id\":\"dev-1\"}");
    if (emit_printer_connected)
        results["emit_printer_connected"] = emit_printer_connected(agent, "topic-1");
    if (emit_message)
        results["emit_message"] = emit_message(agent, "dev-1", "{\"command\":\"pushall\"}");
    if (emit_local_connect)
        results["emit_local_connect"] = emit_local_connect(agent, 7, "dev-1", "connected");
    if (emit_local_message)
        results["emit_local_message"] = emit_local_message(agent, "dev-1", "{\"print\":\"status\"}");
    if (emit_server_error)
        results["emit_server_error"] = emit_server_error(agent, "https://example.invalid", 503);

    int destroy_result = -999999;
    if (destroy_agent && agent)
        destroy_result = destroy_agent(agent);

    const bool payloads_ok = last_ssdp == "{\"dev_id\":\"dev-1\"}" && last_printer_topic == "topic-1"
        && last_message == "dev-1|{\"command\":\"pushall\"}" && last_local_connect == "7|dev-1|connected"
        && last_local_message == "dev-1|{\"print\":\"status\"}" && last_server_error == "https://example.invalid|503";
    const bool counters_ok = counters.ssdp == 1 && counters.printer_connected == 1 && counters.message == 1
        && counters.local_connect == 1 && counters.local_message == 1 && counters.server_error == 1;

    std::cout << "{\n";
    std::cout << "  \"plugin\": \"" << json_escape(args.plugin_path) << "\",\n";
    std::cout << "  \"log_dir\": \"" << json_escape(args.log_dir) << "\",\n";
    std::cout << "  \"agent_created\": " << (agent ? "true" : "false") << ",\n";
    std::cout << "  \"missing_symbols\": ";
    write_string_array(missing);
    std::cout << ",\n";
    std::cout << "  \"results\": ";
    write_result_map(results);
    std::cout << ",\n";
    std::cout << "  \"callback_invocations\": {"
              << "\"ssdp\": " << counters.ssdp << ", "
              << "\"printer_connected\": " << counters.printer_connected << ", "
              << "\"message\": " << counters.message << ", "
              << "\"local_connect\": " << counters.local_connect << ", "
              << "\"local_message\": " << counters.local_message << ", "
              << "\"server_error\": " << counters.server_error << "},\n";
    std::cout << "  \"payloads_ok\": " << (payloads_ok ? "true" : "false") << ",\n";
    std::cout << "  \"counters_ok\": " << (counters_ok ? "true" : "false") << ",\n";
    std::cout << "  \"destroy_result\": " << destroy_result << "\n";
    std::cout << "}\n";

    dlclose(module);
    return missing.empty() && agent && payloads_ok && counters_ok && destroy_result == 0 ? 0 : 1;
}
