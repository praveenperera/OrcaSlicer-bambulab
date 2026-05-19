#include <dlfcn.h>

#include <chrono>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <map>
#include <string>
#include <thread>
#include <vector>

namespace {

using CreateAgentFn = void* (*)(std::string);
using DestroyAgentFn = int (*)(void*);
using IntAgentFn = int (*)(void*);
using SetStringFn = int (*)(void*, std::string);
using SetPrinterConnectedFn = int (*)(void*, std::function<void(std::string)>);
using SetLocalConnectedFn = int (*)(void*, std::function<void(int, std::string, std::string)>);
using SetMessageFn = int (*)(void*, std::function<void(std::string, std::string)>);
using ConnectPrinterFn = int (*)(void*, std::string, std::string, std::string, std::string, bool);
using DisconnectPrinterFn = int (*)(void*);
using SendMessageFn = int (*)(void*, std::string, std::string, int, int);

struct Args {
    std::string plugin_path;
    std::string log_dir{"."};
    std::string dev_id;
    std::string dev_ip;
    std::string username{"bblp"};
    std::string password_env{"BAMBU_NETWORK_PRINTER_PASSWORD"};
    std::string country_code{"US"};
    std::string message;
    int qos{0};
    int flag{0};
    int wait_ms{1000};
    bool use_ssl{false};
    bool expect_connect_success{false};
};

struct Event {
    std::string name;
    int status{0};
    std::string dev_id;
    std::string payload;
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

bool parse_bool(const std::string& value)
{
    return value == "1" || value == "true" || value == "yes" || value == "on";
}

bool parse_args(int argc, char** argv, Args& args)
{
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--plugin" && i + 1 < argc) {
            args.plugin_path = argv[++i];
        } else if (arg == "--log-dir" && i + 1 < argc) {
            args.log_dir = argv[++i];
        } else if (arg == "--dev-id" && i + 1 < argc) {
            args.dev_id = argv[++i];
        } else if (arg == "--dev-ip" && i + 1 < argc) {
            args.dev_ip = argv[++i];
        } else if (arg == "--username" && i + 1 < argc) {
            args.username = argv[++i];
        } else if (arg == "--password-env" && i + 1 < argc) {
            args.password_env = argv[++i];
        } else if (arg == "--country-code" && i + 1 < argc) {
            args.country_code = argv[++i];
        } else if (arg == "--message" && i + 1 < argc) {
            args.message = argv[++i];
        } else if (arg == "--qos" && i + 1 < argc) {
            args.qos = std::stoi(argv[++i]);
        } else if (arg == "--flag" && i + 1 < argc) {
            args.flag = std::stoi(argv[++i]);
        } else if (arg == "--wait-ms" && i + 1 < argc) {
            args.wait_ms = std::stoi(argv[++i]);
        } else if (arg == "--use-ssl" && i + 1 < argc) {
            args.use_ssl = parse_bool(argv[++i]);
        } else if (arg == "--expect-connect-success") {
            args.expect_connect_success = true;
        } else {
            return false;
        }
    }

    return !args.plugin_path.empty() && !args.dev_id.empty() && !args.dev_ip.empty();
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

void write_event_array(const std::vector<Event>& events)
{
    std::cout << "[";
    for (std::size_t i = 0; i < events.size(); ++i) {
        if (i > 0)
            std::cout << ", ";
        const auto& event = events[i];
        std::cout << "{\"name\": \"" << json_escape(event.name) << "\", "
                  << "\"status\": " << event.status << ", "
                  << "\"dev_id\": \"" << json_escape(event.dev_id) << "\", "
                  << "\"payload\": \"" << json_escape(event.payload) << "\"}";
    }
    std::cout << "]";
}

std::string read_password(const std::string& env_name)
{
    const char* value = std::getenv(env_name.c_str());
    return value ? std::string(value) : std::string();
}

void sleep_after_call(int wait_ms)
{
    if (wait_ms > 0)
        std::this_thread::sleep_for(std::chrono::milliseconds(wait_ms));
}

} // namespace

int main(int argc, char** argv)
{
    Args args;
    if (!parse_args(argc, argv, args)) {
        std::cerr << "usage: " << argv[0]
                  << " --plugin <path> --dev-id <id> --dev-ip <ip> [--username <user>] [--password-env <name>]"
                  << " [--message <json>] [--wait-ms <ms>] [--use-ssl true|false] [--expect-connect-success]\n";
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
    auto set_country_code = load_symbol<SetStringFn>(module, "bambu_network_set_country_code", missing);
    auto start = load_symbol<IntAgentFn>(module, "bambu_network_start", missing);
    auto set_printer_connected = load_symbol<SetPrinterConnectedFn>(module, "bambu_network_set_on_printer_connected_fn", missing);
    auto set_local_connect = load_symbol<SetLocalConnectedFn>(module, "bambu_network_set_on_local_connect_fn", missing);
    auto set_message = load_symbol<SetMessageFn>(module, "bambu_network_set_on_message_fn", missing);
    auto set_local_message = load_symbol<SetMessageFn>(module, "bambu_network_set_on_local_message_fn", missing);
    auto connect_printer = load_symbol<ConnectPrinterFn>(module, "bambu_network_connect_printer", missing);
    auto send_message_to_printer = load_symbol<SendMessageFn>(module, "bambu_network_send_message_to_printer", missing);
    auto disconnect_printer = load_symbol<DisconnectPrinterFn>(module, "bambu_network_disconnect_printer", missing);

    void* agent = create_agent ? create_agent(args.log_dir) : nullptr;
    std::map<std::string, int> results;
    std::vector<Event> events;

    if (init_log && agent)
        results["init_log"] = init_log(agent);
    if (set_config_dir && agent)
        results["set_config_dir"] = set_config_dir(agent, args.log_dir);
    if (set_country_code && agent)
        results["set_country_code"] = set_country_code(agent, args.country_code);

    if (set_printer_connected)
        results["set_on_printer_connected_fn"] = set_printer_connected(agent, [&](std::string topic) {
            events.push_back({"printer_connected", 0, {}, topic});
        });
    if (set_local_connect)
        results["set_on_local_connect_fn"] = set_local_connect(agent, [&](int status, std::string dev_id, std::string msg) {
            events.push_back({"local_connect", status, dev_id, msg});
        });
    if (set_message)
        results["set_on_message_fn"] = set_message(agent, [&](std::string dev_id, std::string msg) {
            events.push_back({"message", 0, dev_id, msg});
        });
    if (set_local_message)
        results["set_on_local_message_fn"] = set_local_message(agent, [&](std::string dev_id, std::string msg) {
            events.push_back({"local_message", 0, dev_id, msg});
        });

    if (start && agent)
        results["start"] = start(agent);

    const std::string password = read_password(args.password_env);
    if (connect_printer && agent)
        results["connect_printer"] = connect_printer(agent, args.dev_id, args.dev_ip, args.username, password, args.use_ssl);
    sleep_after_call(args.wait_ms);

    if (send_message_to_printer && agent && !args.message.empty())
        results["send_message_to_printer"] = send_message_to_printer(agent, args.dev_id, args.message, args.qos, args.flag);
    sleep_after_call(args.wait_ms);

    if (disconnect_printer && agent)
        results["disconnect_printer"] = disconnect_printer(agent);
    sleep_after_call(args.wait_ms);

    int destroy_result = -999999;
    if (destroy_agent && agent)
        destroy_result = destroy_agent(agent);

    std::cout << "{\n";
    std::cout << "  \"plugin\": \"" << json_escape(args.plugin_path) << "\",\n";
    std::cout << "  \"log_dir\": \"" << json_escape(args.log_dir) << "\",\n";
    std::cout << "  \"dev_id\": \"" << json_escape(args.dev_id) << "\",\n";
    std::cout << "  \"dev_ip\": \"" << json_escape(args.dev_ip) << "\",\n";
    std::cout << "  \"username\": \"" << json_escape(args.username) << "\",\n";
    std::cout << "  \"password_env\": \"" << json_escape(args.password_env) << "\",\n";
    std::cout << "  \"password_present\": " << (!password.empty() ? "true" : "false") << ",\n";
    std::cout << "  \"use_ssl\": " << (args.use_ssl ? "true" : "false") << ",\n";
    std::cout << "  \"agent_created\": " << (agent ? "true" : "false") << ",\n";
    std::cout << "  \"missing_symbols\": ";
    write_string_array(missing);
    std::cout << ",\n";
    std::cout << "  \"results\": ";
    write_result_map(results);
    std::cout << ",\n";
    std::cout << "  \"events\": ";
    write_event_array(events);
    std::cout << ",\n";
    std::cout << "  \"destroy_result\": " << destroy_result << "\n";
    std::cout << "}\n";

    dlclose(module);

    const bool connect_ok = !args.expect_connect_success || results["connect_printer"] == 0;
    return missing.empty() && agent && destroy_result == 0 && connect_ok ? 0 : 1;
}
