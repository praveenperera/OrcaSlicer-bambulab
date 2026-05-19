#include <arpa/inet.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <condition_variable>
#include <functional>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace {

using CreateAgentFn = void* (*)(std::string);
using DestroyAgentFn = int (*)(void*);
using IntAgentFn = int (*)(void*);
using SetCertFileFn = int (*)(void*, std::string, std::string);
using SetStringFn = int (*)(void*, std::string);
using SetSsdpFn = int (*)(void*, std::function<void(std::string)>);
using StartDiscoveryFn = bool (*)(void*, bool, bool);

constexpr int DISCOVERY_PORT_1 = 1990;
constexpr int DISCOVERY_PORT_2 = 2021;

struct Args {
    std::string plugin_path;
    std::string log_dir{"."};
};

struct CallbackState {
    std::mutex mutex;
    std::condition_variable cv;
    int calls{0};
    std::string last_payload;
};

class ProbeLock
{
public:
    explicit ProbeLock(const char* path)
        : m_fd(open(path, O_CREAT | O_RDWR, 0600))
    {
        if (m_fd >= 0)
            m_locked = flock(m_fd, LOCK_EX) == 0;
    }

    ~ProbeLock()
    {
        if (m_fd >= 0) {
            if (m_locked)
                flock(m_fd, LOCK_UN);
            close(m_fd);
        }
    }

    explicit operator bool() const { return m_locked; }

private:
    int m_fd{-1};
    bool m_locked{false};
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

bool send_discovery_packet(int port)
{
    const std::string packet =
        "NOTIFY * HTTP/1.1\r\n"
        "Host: 239.255.255.250:1990\r\n"
        "NT: urn:bambulab-com:device:3dprinter:1\r\n"
        "NTS: ssdp:alive\r\n"
        "USN: RUSTDISCOVERY123\r\n"
        "Location: 127.0.0.1\r\n"
        "DevModel.bambu.com: 3DPrinter-X1-Carbon\r\n"
        "DevName.bambu.com: Rust Discovery Probe\r\n"
        "DevSignal.bambu.com: -42\r\n"
        "DevConnect.bambu.com: lan\r\n"
        "DevBind.bambu.com: free\r\n"
        "Devseclink.bambu.com: secure\r\n"
        "\r\n";

    int socket_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (socket_fd < 0)
        return false;

    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port   = htons(port);
    if (inet_pton(AF_INET, "127.0.0.1", &address.sin_addr) != 1) {
        close(socket_fd);
        return false;
    }

    const ssize_t sent = sendto(socket_fd, packet.data(), packet.size(), 0, reinterpret_cast<sockaddr*>(&address), sizeof(address));
    close(socket_fd);
    return sent == static_cast<ssize_t>(packet.size());
}

bool contains(const std::string& haystack, const std::string& needle) { return haystack.find(needle) != std::string::npos; }

} // namespace

int main(int argc, char** argv)
{
    Args args;
    if (!parse_args(argc, argv, args)) {
        std::cerr << "usage: " << argv[0] << " --plugin <path> [--log-dir <path>]\n";
        return 2;
    }

    ProbeLock discovery_lock("/tmp/bambu_network_discovery_probe.lock");
    if (!discovery_lock) {
        std::cerr << "failed to acquire discovery probe lock\n";
        return 1;
    }

    void* module = dlopen(args.plugin_path.c_str(), RTLD_LAZY | RTLD_LOCAL);
    if (!module) {
        const char* error = dlerror();
        std::cerr << "dlopen failed: " << (error ? error : "unknown error") << "\n";
        return 1;
    }

    std::vector<std::string> missing;
    auto create_agent    = load_symbol<CreateAgentFn>(module, "bambu_network_create_agent", missing);
    auto destroy_agent   = load_symbol<DestroyAgentFn>(module, "bambu_network_destroy_agent", missing);
    auto init_log        = load_symbol<IntAgentFn>(module, "bambu_network_init_log", missing);
    auto set_config_dir  = load_symbol<SetStringFn>(module, "bambu_network_set_config_dir", missing);
    auto set_cert_file   = load_symbol<SetCertFileFn>(module, "bambu_network_set_cert_file", missing);
    auto set_country_code = load_symbol<SetStringFn>(module, "bambu_network_set_country_code", missing);
    auto set_ssdp        = load_symbol<SetSsdpFn>(module, "bambu_network_set_on_ssdp_msg_fn", missing);
    auto start_discovery = load_symbol<StartDiscoveryFn>(module, "bambu_network_start_discovery", missing);

    void* agent = nullptr;
    if (create_agent)
        agent = create_agent(args.log_dir);

    const int set_config_dir_result = agent && set_config_dir ? set_config_dir(agent, args.log_dir) : -1;
    const int init_log_result = agent && init_log ? init_log(agent) : -1;
    const int set_cert_file_result = agent && set_cert_file ? set_cert_file(agent, "resources/cert", "slicer_base64.cer") : -1;
    const int set_country_code_result = agent && set_country_code ? set_country_code(agent, "US") : -1;

    CallbackState state;
    int set_result = -1;
    if (agent && set_ssdp) {
        set_result = set_ssdp(agent, [&](std::string payload) {
            {
                std::lock_guard<std::mutex> lock(state.mutex);
                state.calls++;
                state.last_payload = std::move(payload);
            }
            state.cv.notify_all();
        });
    }

    bool start_result = false;
    if (agent && start_discovery)
        start_result = start_discovery(agent, true, false);

    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    const bool sent_port_1990 = send_discovery_packet(DISCOVERY_PORT_1);
    const bool sent_port_2021 = send_discovery_packet(DISCOVERY_PORT_2);

    bool callback_received = false;
    {
        std::unique_lock<std::mutex> lock(state.mutex);
        callback_received = state.cv.wait_for(lock, std::chrono::seconds(2), [&] { return state.calls > 0; });
    }

    bool stop_result = false;
    if (agent && start_discovery)
        stop_result = start_discovery(agent, false, false);

    int clear_result = -1;
    if (agent && set_ssdp)
        clear_result = set_ssdp(agent, nullptr);

    int destroy_result = -1;
    if (agent && destroy_agent)
        destroy_result = destroy_agent(agent);

    const bool payload_ok = contains(state.last_payload, "\"dev_id\":\"RUSTDISCOVERY123\"")
        && contains(state.last_payload, "\"dev_ip\":\"127.0.0.1\"")
        && contains(state.last_payload, "\"dev_name\":\"Rust Discovery Probe\"")
        && contains(state.last_payload, "\"connect_type\":\"lan\"");
    const bool ok = missing.empty() && agent && set_result == 0 && start_result && (sent_port_1990 || sent_port_2021) && callback_received
        && payload_ok && stop_result && destroy_result == 0;

    std::cout << "{\n";
    std::cout << "  \"plugin\": \"" << json_escape(args.plugin_path) << "\",\n";
    std::cout << "  \"log_dir\": \"" << json_escape(args.log_dir) << "\",\n";
    std::cout << "  \"agent_created\": " << (agent ? "true" : "false") << ",\n";
    std::cout << "  \"set_config_dir_result\": " << set_config_dir_result << ",\n";
    std::cout << "  \"init_log_result\": " << init_log_result << ",\n";
    std::cout << "  \"set_cert_file_result\": " << set_cert_file_result << ",\n";
    std::cout << "  \"set_country_code_result\": " << set_country_code_result << ",\n";
    std::cout << "  \"missing_symbols\": ";
    write_string_array(missing);
    std::cout << ",\n";
    std::cout << "  \"set_ssdp_result\": " << set_result << ",\n";
    std::cout << "  \"start_result\": " << (start_result ? "true" : "false") << ",\n";
    std::cout << "  \"sent_port_1990\": " << (sent_port_1990 ? "true" : "false") << ",\n";
    std::cout << "  \"sent_port_2021\": " << (sent_port_2021 ? "true" : "false") << ",\n";
    std::cout << "  \"callback_received\": " << (callback_received ? "true" : "false") << ",\n";
    std::cout << "  \"callback_calls\": " << state.calls << ",\n";
    std::cout << "  \"last_payload\": \"" << json_escape(state.last_payload) << "\",\n";
    std::cout << "  \"payload_ok\": " << (payload_ok ? "true" : "false") << ",\n";
    std::cout << "  \"stop_result\": " << (stop_result ? "true" : "false") << ",\n";
    std::cout << "  \"clear_result\": " << clear_result << ",\n";
    std::cout << "  \"destroy_result\": " << destroy_result << ",\n";
    std::cout << "  \"ok\": " << (ok ? "true" : "false") << "\n";
    std::cout << "}\n";

    dlclose(module);
    return ok ? 0 : 1;
}
