#include <dlfcn.h>

#include <functional>
#include <iostream>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace {

using CreateAgentFn = void* (*)(std::string);
using DestroyAgentFn = int (*)(void*);
using IntAgentFn = int (*)(void*);
using SetCertFileFn = int (*)(void*, std::string, std::string);
using SetStringFn = int (*)(void*, std::string);
using OnUserLoginFn = std::function<void(int online_login, bool login)>;
using OnPrinterConnectedFn = std::function<void(std::string topic_str)>;
using OnLocalConnectedFn = std::function<void(int status, std::string dev_id, std::string msg)>;
using OnServerConnectedFn = std::function<void(int return_code, int reason_code)>;
using OnMessageFn = std::function<void(std::string dev_id, std::string msg)>;
using OnHttpErrorFn = std::function<void(unsigned http_code, std::string http_body)>;
using GetCountryCodeFn = std::function<std::string()>;
using GetSubscribeFailureFn = std::function<void(std::string topic)>;
using OnMsgArrivedFn = std::function<void(std::string dev_info_json_str)>;
using QueueOnMainFn = std::function<void(std::function<void()>)>;
using OnServerErrFn = std::function<void(std::string url, int status)>;

using SetSsdpFn = int (*)(void*, OnMsgArrivedFn);
using SetUserLoginFn = int (*)(void*, OnUserLoginFn);
using SetPrinterConnectedFn = int (*)(void*, OnPrinterConnectedFn);
using SetServerConnectedFn = int (*)(void*, OnServerConnectedFn);
using SetHttpErrorFn = int (*)(void*, OnHttpErrorFn);
using SetGetCountryCodeFn = int (*)(void*, GetCountryCodeFn);
using SetSubscribeFailureFn = int (*)(void*, GetSubscribeFailureFn);
using SetMessageFn = int (*)(void*, OnMessageFn);
using SetLocalConnectedFn = int (*)(void*, OnLocalConnectedFn);
using SetQueueOnMainFn = int (*)(void*, QueueOnMainFn);
using SetServerCallbackFn = int (*)(void*, OnServerErrFn);

struct Args {
    std::string plugin_path;
    std::string log_dir{"."};
};

struct Counters {
    int ssdp{0};
    int user_login{0};
    int printer_connected{0};
    int server_connected{0};
    int http_error{0};
    int get_country_code{0};
    int subscribe_failure{0};
    int message{0};
    int user_message{0};
    int local_connect{0};
    int local_message{0};
    int queue_on_main{0};
    int server_callback{0};
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

}

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
    auto init_log = load_symbol<IntAgentFn>(module, "bambu_network_init_log", missing);
    auto set_config_dir = load_symbol<SetStringFn>(module, "bambu_network_set_config_dir", missing);
    auto set_cert_file = load_symbol<SetCertFileFn>(module, "bambu_network_set_cert_file", missing);
    auto set_country_code = load_symbol<SetStringFn>(module, "bambu_network_set_country_code", missing);
    auto set_ssdp = load_symbol<SetSsdpFn>(module, "bambu_network_set_on_ssdp_msg_fn", missing);
    auto set_user_login = load_symbol<SetUserLoginFn>(module, "bambu_network_set_on_user_login_fn", missing);
    auto set_printer_connected = load_symbol<SetPrinterConnectedFn>(module, "bambu_network_set_on_printer_connected_fn", missing);
    auto set_server_connected = load_symbol<SetServerConnectedFn>(module, "bambu_network_set_on_server_connected_fn", missing);
    auto set_http_error = load_symbol<SetHttpErrorFn>(module, "bambu_network_set_on_http_error_fn", missing);
    auto set_get_country_code = load_symbol<SetGetCountryCodeFn>(module, "bambu_network_set_get_country_code_fn", missing);
    auto set_subscribe_failure = load_symbol<SetSubscribeFailureFn>(module, "bambu_network_set_on_subscribe_failure_fn", missing);
    auto set_message = load_symbol<SetMessageFn>(module, "bambu_network_set_on_message_fn", missing);
    auto set_user_message = load_symbol<SetMessageFn>(module, "bambu_network_set_on_user_message_fn", missing);
    auto set_local_connect = load_symbol<SetLocalConnectedFn>(module, "bambu_network_set_on_local_connect_fn", missing);
    auto set_local_message = load_symbol<SetMessageFn>(module, "bambu_network_set_on_local_message_fn", missing);
    auto set_queue_on_main = load_symbol<SetQueueOnMainFn>(module, "bambu_network_set_queue_on_main_fn", missing);
    auto set_server_callback = load_symbol<SetServerCallbackFn>(module, "bambu_network_set_server_callback", missing);

    void* agent = create_agent ? create_agent(args.log_dir) : nullptr;
    Counters counters;
    std::map<std::string, int> results;

    if (set_config_dir)
        results["set_config_dir"] = set_config_dir(agent, args.log_dir);
    if (init_log)
        results["init_log"] = init_log(agent);
    if (set_cert_file)
        results["set_cert_file"] = set_cert_file(agent, "resources/cert", "slicer_base64.cer");
    if (set_country_code)
        results["set_country_code"] = set_country_code(agent, "US");
    if (set_ssdp)
        results["set_on_ssdp_msg_fn"] = set_ssdp(agent, [&](std::string) { counters.ssdp++; });
    if (set_user_login)
        results["set_on_user_login_fn"] = set_user_login(agent, [&](int, bool) { counters.user_login++; });
    if (set_printer_connected)
        results["set_on_printer_connected_fn"] = set_printer_connected(agent, [&](std::string) { counters.printer_connected++; });
    if (set_server_connected)
        results["set_on_server_connected_fn"] = set_server_connected(agent, [&](int, int) { counters.server_connected++; });
    if (set_http_error)
        results["set_on_http_error_fn"] = set_http_error(agent, [&](unsigned, std::string) { counters.http_error++; });
    if (set_get_country_code)
        results["set_get_country_code_fn"] = set_get_country_code(agent, [&]() {
            counters.get_country_code++;
            return std::string("US");
        });
    if (set_subscribe_failure)
        results["set_on_subscribe_failure_fn"] = set_subscribe_failure(agent, [&](std::string) { counters.subscribe_failure++; });
    if (set_message)
        results["set_on_message_fn"] = set_message(agent, [&](std::string, std::string) { counters.message++; });
    if (set_user_message)
        results["set_on_user_message_fn"] = set_user_message(agent, [&](std::string, std::string) { counters.user_message++; });
    if (set_local_connect)
        results["set_on_local_connect_fn"] = set_local_connect(agent, [&](int, std::string, std::string) { counters.local_connect++; });
    if (set_local_message)
        results["set_on_local_message_fn"] = set_local_message(agent, [&](std::string, std::string) { counters.local_message++; });
    if (set_queue_on_main)
        results["set_queue_on_main_fn"] = set_queue_on_main(agent, [&](std::function<void()> fn) {
            counters.queue_on_main++;
            if (fn)
                fn();
        });
    if (set_server_callback)
        results["set_server_callback"] = set_server_callback(agent, [&](std::string, int) { counters.server_callback++; });

    if (set_ssdp)
        results["clear_on_ssdp_msg_fn"] = set_ssdp(agent, nullptr);
    if (set_user_login)
        results["clear_on_user_login_fn"] = set_user_login(agent, nullptr);
    if (set_printer_connected)
        results["clear_on_printer_connected_fn"] = set_printer_connected(agent, nullptr);
    if (set_server_connected)
        results["clear_on_server_connected_fn"] = set_server_connected(agent, nullptr);
    if (set_http_error)
        results["clear_on_http_error_fn"] = set_http_error(agent, nullptr);
    if (set_subscribe_failure)
        results["clear_on_subscribe_failure_fn"] = set_subscribe_failure(agent, nullptr);
    if (set_message)
        results["clear_on_message_fn"] = set_message(agent, nullptr);
    if (set_user_message)
        results["clear_on_user_message_fn"] = set_user_message(agent, nullptr);
    if (set_local_connect)
        results["clear_on_local_connect_fn"] = set_local_connect(agent, nullptr);
    if (set_local_message)
        results["clear_on_local_message_fn"] = set_local_message(agent, nullptr);
    if (set_queue_on_main)
        results["clear_queue_on_main_fn"] = set_queue_on_main(agent, nullptr);

    int destroy_result = -999999;
    if (destroy_agent && agent)
        destroy_result = destroy_agent(agent);

    std::cout << "{\n";
    std::cout << "  \"plugin\": \"" << json_escape(args.plugin_path) << "\",\n";
    std::cout << "  \"log_dir\": \"" << json_escape(args.log_dir) << "\",\n";
    std::cout << "  \"agent_created\": " << (agent ? "true" : "false") << ",\n";
    std::cout << "  \"missing_symbols\": ";
    write_string_array(missing);
    std::cout << ",\n";
    std::cout << "  \"registration_results\": ";
    write_result_map(results);
    std::cout << ",\n";
    std::cout << "  \"callback_invocations\": {\n";
    std::cout << "    \"ssdp\": " << counters.ssdp << ",\n";
    std::cout << "    \"user_login\": " << counters.user_login << ",\n";
    std::cout << "    \"printer_connected\": " << counters.printer_connected << ",\n";
    std::cout << "    \"server_connected\": " << counters.server_connected << ",\n";
    std::cout << "    \"http_error\": " << counters.http_error << ",\n";
    std::cout << "    \"get_country_code\": " << counters.get_country_code << ",\n";
    std::cout << "    \"subscribe_failure\": " << counters.subscribe_failure << ",\n";
    std::cout << "    \"message\": " << counters.message << ",\n";
    std::cout << "    \"user_message\": " << counters.user_message << ",\n";
    std::cout << "    \"local_connect\": " << counters.local_connect << ",\n";
    std::cout << "    \"local_message\": " << counters.local_message << ",\n";
    std::cout << "    \"queue_on_main\": " << counters.queue_on_main << ",\n";
    std::cout << "    \"server_callback\": " << counters.server_callback << "\n";
    std::cout << "  },\n";
    std::cout << "  \"destroy_result\": " << destroy_result << "\n";
    std::cout << "}\n";

    dlclose(module);
    return missing.empty() && agent ? 0 : 1;
}
