#include <dlfcn.h>

#include <functional>
#include <iostream>
#include <string>
#include <vector>

namespace {

using CreateAgentFn = void* (*)(std::string);
using DestroyAgentFn = int (*)(void*);
using GetCameraUrlFn = int (*)(void*, std::string, std::function<void(std::string)>);
using SetCameraEndpointFn = int (*)(void*, const char*, const char*, const char*, const char*, bool);

struct Args {
    std::string plugin_path;
    std::string log_dir{"."};
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
        return 1;
    }

    std::vector<std::string> missing;
    auto create_agent = load_symbol<CreateAgentFn>(module, "bambu_network_create_agent", missing);
    auto destroy_agent = load_symbol<DestroyAgentFn>(module, "bambu_network_destroy_agent", missing);
    auto get_camera_url = load_symbol<GetCameraUrlFn>(module, "bambu_network_get_camera_url", missing);
    auto set_endpoint = load_symbol<SetCameraEndpointFn>(module, "brs_shim_test_set_camera_endpoint", missing);

    void* agent = create_agent ? create_agent(args.log_dir) : nullptr;
    int empty_result = -999999;
    int set_result = -999999;
    int camera_result = -999999;
    int callback_calls = 0;
    std::string last_url;

    if (agent && get_camera_url)
        empty_result = get_camera_url(agent, "SERIAL123", [&](std::string url) {
            callback_calls++;
            last_url = std::move(url);
        });

    if (agent && set_endpoint)
        set_result = set_endpoint(agent, "SERIAL123", "192.0.2.10", "bblp", "12345678", true);

    if (agent && get_camera_url)
        camera_result = get_camera_url(agent, "SERIAL123|01.08.00.00|\"tutk\"", [&](std::string url) {
            callback_calls++;
            last_url = std::move(url);
        });

    int destroy_result = -999999;
    if (agent && destroy_agent)
        destroy_result = destroy_agent(agent);

    const bool url_ok = last_url == "bambu:///rtsps___bblp:12345678@192.0.2.10/streaming/live/1?proto=rtsps";
    const bool ok = missing.empty() && agent && empty_result == -2 && set_result == 0 && camera_result == 0 && callback_calls == 1 && url_ok
        && destroy_result == 0;

    std::cout << "{\n";
    std::cout << "  \"plugin\": \"" << json_escape(args.plugin_path) << "\",\n";
    std::cout << "  \"log_dir\": \"" << json_escape(args.log_dir) << "\",\n";
    std::cout << "  \"agent_created\": " << (agent ? "true" : "false") << ",\n";
    std::cout << "  \"missing_symbols\": ";
    write_string_array(missing);
    std::cout << ",\n";
    std::cout << "  \"empty_result\": " << empty_result << ",\n";
    std::cout << "  \"set_result\": " << set_result << ",\n";
    std::cout << "  \"camera_result\": " << camera_result << ",\n";
    std::cout << "  \"callback_calls\": " << callback_calls << ",\n";
    std::cout << "  \"last_url\": \"" << json_escape(last_url) << "\",\n";
    std::cout << "  \"url_ok\": " << (url_ok ? "true" : "false") << ",\n";
    std::cout << "  \"destroy_result\": " << destroy_result << ",\n";
    std::cout << "  \"ok\": " << (ok ? "true" : "false") << "\n";
    std::cout << "}\n";

    dlclose(module);
    return ok ? 0 : 1;
}
