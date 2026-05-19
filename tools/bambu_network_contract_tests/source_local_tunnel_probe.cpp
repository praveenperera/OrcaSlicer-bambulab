#include <arpa/inet.h>
#include <dlfcn.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <map>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "../../src/slic3r/GUI/Printer/BambuTunnel.h"

namespace {

using BambuInitFn = int (*)();
using BambuDeinitFn = void (*)();
using BambuCreateFn = int (*)(Bambu_Tunnel*, const char*);
using BambuOpenFn = int (*)(Bambu_Tunnel);
using BambuStartStreamExFn = int (*)(Bambu_Tunnel, int);
using BambuSendMessageFn = int (*)(Bambu_Tunnel, int, const char*, int);
using BambuRecvMessageFn = int (*)(Bambu_Tunnel, int*, char*, int*);
using BambuReadSampleFn = int (*)(Bambu_Tunnel, Bambu_Sample*);
using BambuCloseFn = void (*)(Bambu_Tunnel);
using BambuDestroyFn = void (*)(Bambu_Tunnel);
using BambuLastErrorFn = const char* (*)();

constexpr int CtrlStreamType = 0x3001;
constexpr int WouldBlock = Bambu_would_block;

struct Args {
    std::string source_plugin;
};

struct Loaded {
    void* module{nullptr};
    BambuInitFn init{nullptr};
    BambuDeinitFn deinit{nullptr};
    BambuCreateFn create{nullptr};
    BambuOpenFn open{nullptr};
    BambuStartStreamExFn start_stream_ex{nullptr};
    BambuSendMessageFn send_message{nullptr};
    BambuRecvMessageFn recv_message{nullptr};
    BambuReadSampleFn read_sample{nullptr};
    BambuCloseFn close{nullptr};
    BambuDestroyFn destroy{nullptr};
    BambuLastErrorFn last_error{nullptr};
    std::vector<std::string> missing;
};

struct ServerState {
    std::mutex mutex;
    std::string received;
    bool accepted{false};
    int responses_sent{0};
    int error{0};
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
        if (arg == "--source-plugin" && i + 1 < argc) {
            args.source_plugin = argv[++i];
        } else {
            return false;
        }
    }
    return !args.source_plugin.empty();
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

Loaded load_source(const std::string& path)
{
    Loaded loaded;
    loaded.module = dlopen(path.c_str(), RTLD_LAZY | RTLD_LOCAL);
    if (!loaded.module)
        return loaded;

    loaded.init = load_symbol<BambuInitFn>(loaded.module, "Bambu_Init", loaded.missing);
    loaded.deinit = load_symbol<BambuDeinitFn>(loaded.module, "Bambu_Deinit", loaded.missing);
    loaded.create = load_symbol<BambuCreateFn>(loaded.module, "Bambu_Create", loaded.missing);
    loaded.open = load_symbol<BambuOpenFn>(loaded.module, "Bambu_Open", loaded.missing);
    loaded.start_stream_ex = load_symbol<BambuStartStreamExFn>(loaded.module, "Bambu_StartStreamEx", loaded.missing);
    loaded.send_message = load_symbol<BambuSendMessageFn>(loaded.module, "Bambu_SendMessage", loaded.missing);
    loaded.recv_message = load_symbol<BambuRecvMessageFn>(loaded.module, "Bambu_RecvMessage", loaded.missing);
    loaded.read_sample = load_symbol<BambuReadSampleFn>(loaded.module, "Bambu_ReadSample", loaded.missing);
    loaded.close = load_symbol<BambuCloseFn>(loaded.module, "Bambu_Close", loaded.missing);
    loaded.destroy = load_symbol<BambuDestroyFn>(loaded.module, "Bambu_Destroy", loaded.missing);
    loaded.last_error = load_symbol<BambuLastErrorFn>(loaded.module, "Bambu_GetLastErrorMsg", loaded.missing);
    return loaded;
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

void write_bool_map(const std::map<std::string, bool>& values)
{
    std::cout << "{";
    std::size_t index = 0;
    for (const auto& [key, value] : values) {
        if (index++ > 0)
            std::cout << ", ";
        std::cout << "\"" << json_escape(key) << "\": " << (value ? "true" : "false");
    }
    std::cout << "}";
}

int create_loopback_server(std::uint16_t& port)
{
    const int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0)
        return -1;

    int reuse = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

    sockaddr_in address {};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = 0;
    if (bind(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0) {
        close(fd);
        return -1;
    }
    if (listen(fd, 1) != 0) {
        close(fd);
        return -1;
    }

    socklen_t length = sizeof(address);
    if (getsockname(fd, reinterpret_cast<sockaddr*>(&address), &length) != 0) {
        close(fd);
        return -1;
    }
    port = ntohs(address.sin_port);
    return fd;
}

bool wait_readable(int fd, int timeout_ms)
{
    fd_set read_set;
    FD_ZERO(&read_set);
    FD_SET(fd, &read_set);
    timeval timeout {};
    timeout.tv_sec = timeout_ms / 1000;
    timeout.tv_usec = (timeout_ms % 1000) * 1000;
    return select(fd + 1, &read_set, nullptr, nullptr, &timeout) > 0 && FD_ISSET(fd, &read_set);
}

void run_loopback_server(int listen_fd, ServerState& state)
{
    int client_fd = -1;
    if (wait_readable(listen_fd, 5000)) {
        client_fd = accept(listen_fd, nullptr, nullptr);
    }
    if (client_fd < 0) {
        std::lock_guard<std::mutex> lock(state.mutex);
        state.error = errno ? errno : ETIMEDOUT;
        close(listen_fd);
        return;
    }

    {
        std::lock_guard<std::mutex> lock(state.mutex);
        state.accepted = true;
    }

    const std::vector<std::string> responses = {
        "{\"result\":0,\"sequence\":1,\"reply\":\"recv-loopback\"}\n",
        "{\"result\":0,\"sequence\":2,\"reply\":\"sample-loopback\"}\n",
    };
    for (const std::string& response : responses) {
        char buffer[4096] {};
        if (!wait_readable(client_fd, 5000)) {
            std::lock_guard<std::mutex> lock(state.mutex);
            state.error = ETIMEDOUT;
            break;
        }

        const ssize_t received = recv(client_fd, buffer, sizeof(buffer), 0);
        if (received <= 0) {
            std::lock_guard<std::mutex> lock(state.mutex);
            state.error = errno ? errno : ECONNRESET;
            break;
        }

        {
            std::lock_guard<std::mutex> lock(state.mutex);
            state.received.append(buffer, static_cast<std::size_t>(received));
        }

        const ssize_t sent = send(client_fd, response.data(), response.size(), 0);
        std::lock_guard<std::mutex> lock(state.mutex);
        if (sent == static_cast<ssize_t>(response.size()))
            ++state.responses_sent;
        else if (state.error == 0)
            state.error = errno ? errno : EIO;
    }
    close(client_fd);
    close(listen_fd);
}

std::string number(int value)
{
    return std::to_string(value);
}

}

int main(int argc, char** argv)
{
    std::signal(SIGPIPE, SIG_IGN);
    setenv("BAMBU_SOURCE_DISABLE_LOCAL_TLS", "1", 1);

    Args args;
    if (!parse_args(argc, argv, args)) {
        std::cerr << "usage: " << argv[0] << " --source-plugin <path>\n";
        return 2;
    }

    std::uint16_t port = 0;
    const int listen_fd = create_loopback_server(port);
    if (listen_fd < 0) {
        std::cerr << "failed to create loopback server\n";
        return 3;
    }

    ServerState server_state;
    std::thread server_thread(run_loopback_server, listen_fd, std::ref(server_state));

    Loaded source = load_source(args.source_plugin);
    std::map<std::string, std::string> results;
    std::map<std::string, bool> semantic;
    if (!source.module) {
        std::cerr << "dlopen source failed: " << (dlerror() ? dlerror() : "unknown error") << "\n";
        server_thread.join();
        return 4;
    }

    if (source.init)
        results["Bambu_Init"] = number(source.init());

    const std::string url = "bambu:///local/127.0.0.1?port=" + std::to_string(port) + "&user=bblp&passwd=<redacted>";
    Bambu_Tunnel tunnel = nullptr;
    if (source.create)
        results["Bambu_Create"] = number(source.create(&tunnel, url.c_str()));
    if (source.open)
        results["Bambu_Open"] = number(source.open(tunnel));
    if (source.start_stream_ex)
        results["Bambu_StartStreamEx"] = number(source.start_stream_ex(tunnel, CtrlStreamType));

    const std::string recv_request = "{\"sequence\":1,\"command\":\"recv-loopback\"}\n";
    if (source.send_message)
        results["Bambu_SendMessage_recv"] = number(source.send_message(
            tunnel,
            CtrlStreamType,
            recv_request.c_str(),
            static_cast<int>(recv_request.size())));

    int recv_type = 99;
    int recv_size = 4096;
    std::vector<char> recv_buffer(static_cast<std::size_t>(recv_size), 0);
    int recv_result = WouldBlock;
    std::string recv_text;
    const auto recv_deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    while (source.recv_message && std::chrono::steady_clock::now() < recv_deadline) {
        recv_size = static_cast<int>(recv_buffer.size());
        recv_result = source.recv_message(tunnel, &recv_type, recv_buffer.data(), &recv_size);
        if (recv_result == Bambu_success) {
            recv_text.assign(recv_buffer.data(), static_cast<std::size_t>(recv_size));
            break;
        }
        if (recv_result != WouldBlock)
            break;
        std::this_thread::sleep_for(std::chrono::milliseconds(25));
    }
    results["Bambu_RecvMessage"] = number(recv_result);

    const std::string sample_request = "{\"sequence\":2,\"command\":\"sample-loopback\"}\n";
    if (source.send_message)
        results["Bambu_SendMessage_sample"] = number(source.send_message(
            tunnel,
            CtrlStreamType,
            sample_request.c_str(),
            static_cast<int>(sample_request.size())));

    Bambu_Sample sample {};
    std::string sample_text;
    int read_result = WouldBlock;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    while (source.read_sample && std::chrono::steady_clock::now() < deadline) {
        read_result = source.read_sample(tunnel, &sample);
        if (read_result == Bambu_success) {
            sample_text.assign(reinterpret_cast<const char*>(sample.buffer), static_cast<std::size_t>(sample.size));
            break;
        }
        if (read_result != WouldBlock)
            break;
        std::this_thread::sleep_for(std::chrono::milliseconds(25));
    }
    results["Bambu_ReadSample"] = number(read_result);
    if (source.last_error)
        results["Bambu_GetLastErrorMsg"] = "\"" + json_escape(source.last_error()) + "\"";

    if (source.close && tunnel)
        source.close(tunnel);
    if (source.destroy && tunnel)
        source.destroy(tunnel);
    if (source.deinit)
        source.deinit();

    if (server_thread.joinable())
        server_thread.join();

    std::string server_received;
    bool server_accepted = false;
    int server_responses_sent = 0;
    int server_error = 0;
    {
        std::lock_guard<std::mutex> lock(server_state.mutex);
        server_received = server_state.received;
        server_accepted = server_state.accepted;
        server_responses_sent = server_state.responses_sent;
        server_error = server_state.error;
    }

    semantic["server_accepted"] = server_accepted;
    semantic["server_received_message"] =
        server_received.find("\"command\":\"recv-loopback\"") != std::string::npos
        && server_received.find("\"command\":\"sample-loopback\"") != std::string::npos;
    semantic["server_response_sent"] = server_responses_sent == 2;
    semantic["opened"] = results["Bambu_Open"] == "0";
    semantic["stream_started"] = results["Bambu_StartStreamEx"] == "0";
    semantic["send_ok"] = results["Bambu_SendMessage_recv"] == "0" && results["Bambu_SendMessage_sample"] == "0";
    semantic["recv_message_read"] = recv_result == Bambu_success;
    semantic["recv_message_contains_response"] = recv_text.find("\"reply\":\"recv-loopback\"") != std::string::npos;
    semantic["recv_message_type"] = recv_type == 0;
    semantic["sample_read"] = read_result == Bambu_success;
    semantic["sample_size_positive"] = sample.size > 0;
    semantic["sample_contains_response"] = sample_text.find("\"reply\":\"sample-loopback\"") != std::string::npos;
    semantic["server_clean"] = server_error == 0;

    const bool ok = source.module
        && source.missing.empty()
        && semantic["server_accepted"]
        && semantic["server_received_message"]
        && semantic["server_response_sent"]
        && semantic["opened"]
        && semantic["stream_started"]
        && semantic["send_ok"]
        && semantic["recv_message_read"]
        && semantic["recv_message_contains_response"]
        && semantic["recv_message_type"]
        && semantic["sample_read"]
        && semantic["sample_size_positive"]
        && semantic["sample_contains_response"]
        && semantic["server_clean"];

    std::cout << "{\n";
    std::cout << "  \"source_plugin\": \"" << json_escape(args.source_plugin) << "\",\n";
    std::cout << "  \"url\": \"bambu:///local/127.0.0.1?port=<loopback>&user=bblp&passwd=<redacted>\",\n";
    std::cout << "  \"missing_symbols\": ";
    write_string_array(source.missing);
    std::cout << ",\n";
    std::cout << "  \"results\": ";
    write_result_map(results);
    std::cout << ",\n";
    std::cout << "  \"semantic\": ";
    write_bool_map(semantic);
    std::cout << ",\n";
    std::cout << "  \"server_error\": " << server_error << ",\n";
    std::cout << "  \"server_received_size\": " << server_received.size() << ",\n";
    std::cout << "  \"recv_size\": " << recv_size << ",\n";
    std::cout << "  \"sample_size\": " << sample.size << ",\n";
    std::cout << "  \"ok\": " << (ok ? "true" : "false") << "\n";
    std::cout << "}\n";

    dlclose(source.module);
    return ok ? 0 : 1;
}
