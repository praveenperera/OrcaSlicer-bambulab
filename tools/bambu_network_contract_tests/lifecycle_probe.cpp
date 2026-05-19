#include <dlfcn.h>

#include <iostream>
#include <optional>
#include <string>
#include <vector>

namespace {

using GetVersionFn = std::string (*)();
using CreateAgentFn = void* (*)(std::string);
using DestroyAgentFn = int (*)(void*);
using IsUserLoginFn = bool (*)(void*);
using IntAgentFn = int (*)(void*);
using SetCertFileFn = int (*)(void*, std::string, std::string);
using SetStringFn = int (*)(void*, std::string);
using StringAgentFn = std::string (*)(void*);

struct Args {
    std::string plugin_path;
    std::string log_dir{"."};
};

struct JsonField {
    std::string name;
    std::string value;
    bool raw{false};
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

std::optional<std::string> call_string(StringAgentFn fn, void* agent)
{
    if (!fn || !agent)
        return std::nullopt;
    return fn(agent);
}

void write_object(const std::vector<JsonField>& fields)
{
    std::cout << "{\n";
    for (std::size_t i = 0; i < fields.size(); ++i) {
        const auto& field = fields[i];
        std::cout << "  \"" << json_escape(field.name) << "\": ";
        if (field.raw)
            std::cout << field.value;
        else
            std::cout << "\"" << json_escape(field.value) << "\"";
        if (i + 1 < fields.size())
            std::cout << ",";
        std::cout << "\n";
    }
    std::cout << "}\n";
}

std::string string_or_null(const std::optional<std::string>& value)
{
    return value ? "\"" + json_escape(*value) + "\"" : "null";
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
    auto get_version = load_symbol<GetVersionFn>(module, "bambu_network_get_version", missing);
    auto create_agent = load_symbol<CreateAgentFn>(module, "bambu_network_create_agent", missing);
    auto destroy_agent = load_symbol<DestroyAgentFn>(module, "bambu_network_destroy_agent", missing);
    auto init_log = load_symbol<IntAgentFn>(module, "bambu_network_init_log", missing);
    auto set_config_dir = load_symbol<SetStringFn>(module, "bambu_network_set_config_dir", missing);
    auto set_cert_file = load_symbol<SetCertFileFn>(module, "bambu_network_set_cert_file", missing);
    auto set_country_code = load_symbol<SetStringFn>(module, "bambu_network_set_country_code", missing);
    auto start = load_symbol<IntAgentFn>(module, "bambu_network_start", missing);
    auto is_user_login = load_symbol<IsUserLoginFn>(module, "bambu_network_is_user_login", missing);
    auto get_user_id = load_symbol<StringAgentFn>(module, "bambu_network_get_user_id", missing);
    auto get_user_name = load_symbol<StringAgentFn>(module, "bambu_network_get_user_name", missing);
    auto get_user_nickname = load_symbol<StringAgentFn>(module, "bambu_network_get_user_nickanme", missing);
    auto build_login_cmd = load_symbol<StringAgentFn>(module, "bambu_network_build_login_cmd", missing);
    auto build_login_info = load_symbol<StringAgentFn>(module, "bambu_network_build_login_info", missing);
    auto build_logout_cmd = load_symbol<StringAgentFn>(module, "bambu_network_build_logout_cmd", missing);

    std::string version;
    if (get_version)
        version = get_version();

    void* agent = nullptr;
    if (create_agent)
        agent = create_agent(args.log_dir);

    const int set_config_dir_result = set_config_dir && agent ? set_config_dir(agent, args.log_dir) : -999999;
    const int init_log_result = init_log && agent ? init_log(agent) : -999999;
    const int set_cert_file_result = set_cert_file && agent ? set_cert_file(agent, "resources/cert", "slicer_base64.cer") : -999999;
    const int set_country_code_result = set_country_code && agent ? set_country_code(agent, "US") : -999999;
    const int start_result = start && agent ? start(agent) : -999999;
    const bool logged_in = is_user_login && agent ? is_user_login(agent) : false;
    const auto user_id = logged_in ? call_string(get_user_id, agent) : std::nullopt;
    const auto user_name = logged_in ? call_string(get_user_name, agent) : std::nullopt;
    const auto user_nickname = logged_in ? call_string(get_user_nickname, agent) : std::nullopt;
    const auto login_cmd = std::optional<std::string>();
    const auto login_info = std::optional<std::string>();
    const auto logout_cmd = std::optional<std::string>();

    int destroy_result = -999999;
    if (destroy_agent && agent)
        destroy_result = destroy_agent(agent);

    std::string missing_json = "[";
    for (std::size_t i = 0; i < missing.size(); ++i) {
        if (i > 0)
            missing_json += ", ";
        missing_json += "\"" + json_escape(missing[i]) + "\"";
    }
    missing_json += "]";

    write_object({
        {"plugin", args.plugin_path},
        {"log_dir", args.log_dir},
        {"missing_symbols", missing_json, true},
        {"version", version},
        {"agent_created", agent ? "true" : "false", true},
        {"init_log_result", std::to_string(init_log_result), true},
        {"set_config_dir_result", std::to_string(set_config_dir_result), true},
        {"set_cert_file_result", std::to_string(set_cert_file_result), true},
        {"set_country_code_result", std::to_string(set_country_code_result), true},
        {"start_result", std::to_string(start_result), true},
        {"logged_in", logged_in ? "true" : "false", true},
        {"user_id", string_or_null(user_id), true},
        {"user_name", string_or_null(user_name), true},
        {"user_nickname", string_or_null(user_nickname), true},
        {"login_cmd", string_or_null(login_cmd), true},
        {"login_info", string_or_null(login_info), true},
        {"logout_cmd", string_or_null(logout_cmd), true},
        {"destroy_result", std::to_string(destroy_result), true},
    });

    dlclose(module);
    return missing.empty() && agent ? 0 : 1;
}
