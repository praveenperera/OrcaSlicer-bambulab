#include <dlfcn.h>

#include <chrono>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <map>
#include <string>
#include <thread>
#include <vector>

#include "../bambu_network_rust_plugin/shim/bambu_networking_abi.hpp"

namespace {

using CreateAgentFn = void* (*)(std::string);
using DestroyAgentFn = int (*)(void*);
using IntAgentFn = int (*)(void*);
using SetStringFn = int (*)(void*, std::string);
using StartPrintFn = int (*)(void*, Slic3r::PrintParams, Slic3r::OnUpdateStatusFn, Slic3r::WasCancelledFn);
using StartPrintWithWaitFn = int (*)(void*, Slic3r::PrintParams, Slic3r::OnUpdateStatusFn, Slic3r::WasCancelledFn, Slic3r::OnWaitFn);

struct Args {
    std::string plugin_path;
    std::string log_dir{"."};
    std::string mode{"upload-only"};
    std::string dev_id;
    std::string dev_ip;
    std::string username{"bblp"};
    std::string password_env{"BAMBU_NETWORK_PRINTER_PASSWORD"};
    std::string country_code{"US"};
    std::string file_path;
    std::string remote_name;
    std::string file_md5;
    std::string bed_type{"auto"};
    std::string ams_mapping;
    int plate_index{1};
    int wait_ms{1000};
    bool use_ssl_for_ftp{true};
    bool use_ssl_for_mqtt{true};
    bool bed_leveling{false};
    bool flow_cali{false};
    bool vibration_cali{false};
    bool layer_inspect{false};
    bool timelapse{false};
    bool use_ams{false};
    bool expect_success{false};
};

struct StatusEvent {
    int status{0};
    int code{0};
    std::string message;
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
        } else if (arg == "--mode" && i + 1 < argc) {
            args.mode = argv[++i];
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
        } else if (arg == "--file" && i + 1 < argc) {
            args.file_path = argv[++i];
        } else if (arg == "--remote-name" && i + 1 < argc) {
            args.remote_name = argv[++i];
        } else if (arg == "--file-md5" && i + 1 < argc) {
            args.file_md5 = argv[++i];
        } else if (arg == "--bed-type" && i + 1 < argc) {
            args.bed_type = argv[++i];
        } else if (arg == "--ams-mapping" && i + 1 < argc) {
            args.ams_mapping = argv[++i];
        } else if (arg == "--plate-index" && i + 1 < argc) {
            args.plate_index = std::stoi(argv[++i]);
        } else if (arg == "--wait-ms" && i + 1 < argc) {
            args.wait_ms = std::stoi(argv[++i]);
        } else if (arg == "--use-ssl-for-ftp" && i + 1 < argc) {
            args.use_ssl_for_ftp = parse_bool(argv[++i]);
        } else if (arg == "--use-ssl-for-mqtt" && i + 1 < argc) {
            args.use_ssl_for_mqtt = parse_bool(argv[++i]);
        } else if (arg == "--bed-leveling" && i + 1 < argc) {
            args.bed_leveling = parse_bool(argv[++i]);
        } else if (arg == "--flow-cali" && i + 1 < argc) {
            args.flow_cali = parse_bool(argv[++i]);
        } else if (arg == "--vibration-cali" && i + 1 < argc) {
            args.vibration_cali = parse_bool(argv[++i]);
        } else if (arg == "--layer-inspect" && i + 1 < argc) {
            args.layer_inspect = parse_bool(argv[++i]);
        } else if (arg == "--timelapse" && i + 1 < argc) {
            args.timelapse = parse_bool(argv[++i]);
        } else if (arg == "--use-ams" && i + 1 < argc) {
            args.use_ams = parse_bool(argv[++i]);
        } else if (arg == "--expect-success") {
            args.expect_success = true;
        } else {
            return false;
        }
    }

    const bool valid_mode = args.mode == "upload-only" || args.mode == "local-print" || args.mode == "sdcard-print";
    return valid_mode && !args.plugin_path.empty() && !args.dev_id.empty() && !args.dev_ip.empty();
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

void write_status_array(const std::vector<StatusEvent>& events)
{
    std::cout << "[";
    for (std::size_t i = 0; i < events.size(); ++i) {
        if (i > 0)
            std::cout << ", ";
        const auto& event = events[i];
        std::cout << "{\"status\": " << event.status << ", "
                  << "\"code\": " << event.code << ", "
                  << "\"message\": \"" << json_escape(event.message) << "\"}";
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

Slic3r::PrintParams make_params(const Args& args, const std::string& password)
{
    Slic3r::PrintParams params;
    params.dev_id = args.dev_id;
    params.dev_ip = args.dev_ip;
    params.username = args.username;
    params.password = password;
    params.filename = args.file_path;
    params.ftp_file = args.remote_name;
    params.dst_file = args.remote_name;
    params.ftp_file_md5 = args.file_md5;
    params.plate_index = args.plate_index;
    params.use_ssl_for_ftp = args.use_ssl_for_ftp;
    params.use_ssl_for_mqtt = args.use_ssl_for_mqtt;
    params.task_bed_type = args.bed_type;
    params.task_bed_leveling = args.bed_leveling;
    params.task_flow_cali = args.flow_cali;
    params.task_vibration_cali = args.vibration_cali;
    params.task_layer_inspect = args.layer_inspect;
    params.task_record_timelapse = args.timelapse;
    params.task_use_ams = args.use_ams;
    params.ams_mapping = args.ams_mapping;
    params.connection_type = "lan";
    return params;
}

} // namespace

int main(int argc, char** argv)
{
    Args args;
    if (!parse_args(argc, argv, args)) {
        std::cerr << "usage: " << argv[0]
                  << " --plugin <path> --mode upload-only|local-print|sdcard-print --dev-id <id> --dev-ip <ip>"
                  << " [--file <path>] [--remote-name <name>] [--expect-success]\n";
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
    auto upload_only = load_symbol<StartPrintWithWaitFn>(module, "bambu_network_start_send_gcode_to_sdcard", missing);
    auto local_print = load_symbol<StartPrintWithWaitFn>(module, "bambu_network_start_local_print_with_record", missing);
    auto sdcard_print = load_symbol<StartPrintFn>(module, "bambu_network_start_sdcard_print", missing);

    void* agent = create_agent ? create_agent(args.log_dir) : nullptr;
    std::map<std::string, int> results;
    std::vector<StatusEvent> status_events;
    int wait_calls = 0;
    int cancel_calls = 0;

    if (init_log && agent)
        results["init_log"] = init_log(agent);
    if (set_config_dir && agent)
        results["set_config_dir"] = set_config_dir(agent, args.log_dir);
    if (set_country_code && agent)
        results["set_country_code"] = set_country_code(agent, args.country_code);
    if (start && agent)
        results["start"] = start(agent);

    const std::string password = read_password(args.password_env);
    Slic3r::PrintParams params = make_params(args, password);
    Slic3r::OnUpdateStatusFn update = [&](int status, int code, std::string message) {
        status_events.push_back({status, code, message});
    };
    Slic3r::WasCancelledFn cancelled = [&] {
        cancel_calls++;
        return false;
    };
    Slic3r::OnWaitFn wait = [&](int, std::string) {
        wait_calls++;
        return false;
    };

    int job_result = -999999;
    if (agent && args.mode == "upload-only" && upload_only)
        job_result = upload_only(agent, params, update, cancelled, wait);
    else if (agent && args.mode == "local-print" && local_print)
        job_result = local_print(agent, params, update, cancelled, wait);
    else if (agent && args.mode == "sdcard-print" && sdcard_print)
        job_result = sdcard_print(agent, params, update, cancelled);

    sleep_after_call(args.wait_ms);

    int destroy_result = -999999;
    if (destroy_agent && agent)
        destroy_result = destroy_agent(agent);

    const bool job_ok = !args.expect_success || job_result == 0;
    const bool ok = missing.empty() && agent && destroy_result == 0 && job_ok;

    std::cout << "{\n";
    std::cout << "  \"plugin\": \"" << json_escape(args.plugin_path) << "\",\n";
    std::cout << "  \"log_dir\": \"" << json_escape(args.log_dir) << "\",\n";
    std::cout << "  \"mode\": \"" << json_escape(args.mode) << "\",\n";
    std::cout << "  \"dev_id\": \"" << json_escape(args.dev_id) << "\",\n";
    std::cout << "  \"dev_ip\": \"" << json_escape(args.dev_ip) << "\",\n";
    std::cout << "  \"username\": \"" << json_escape(args.username) << "\",\n";
    std::cout << "  \"password_env\": \"" << json_escape(args.password_env) << "\",\n";
    std::cout << "  \"password_present\": " << (!password.empty() ? "true" : "false") << ",\n";
    std::cout << "  \"file_present\": " << (!args.file_path.empty() ? "true" : "false") << ",\n";
    std::cout << "  \"remote_name_present\": " << (!args.remote_name.empty() ? "true" : "false") << ",\n";
    std::cout << "  \"use_ssl_for_ftp\": " << (args.use_ssl_for_ftp ? "true" : "false") << ",\n";
    std::cout << "  \"use_ssl_for_mqtt\": " << (args.use_ssl_for_mqtt ? "true" : "false") << ",\n";
    std::cout << "  \"agent_created\": " << (agent ? "true" : "false") << ",\n";
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
    std::cout << "  \"job_result\": " << job_result << ",\n";
    std::cout << "  \"status_events\": ";
    write_status_array(status_events);
    std::cout << ",\n";
    std::cout << "  \"wait_calls\": " << wait_calls << ",\n";
    std::cout << "  \"cancel_calls\": " << cancel_calls << ",\n";
    std::cout << "  \"destroy_result\": " << destroy_result << ",\n";
    std::cout << "  \"ok\": " << (ok ? "true" : "false") << "\n";
    std::cout << "}\n";

    dlclose(module);
    return ok ? 0 : 1;
}
