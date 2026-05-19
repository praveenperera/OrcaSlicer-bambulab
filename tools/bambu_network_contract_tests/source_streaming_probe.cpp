#include <dlfcn.h>

#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#include <thread>
#include <vector>

#include "../../src/slic3r/GUI/Printer/BambuTunnel.h"

namespace {

using BambuInitFn = int (*)();
using BambuDeinitFn = void (*)();
using BambuCreateFn = int (*)(Bambu_Tunnel*, const char*);
using BambuOpenFn = int (*)(Bambu_Tunnel);
using BambuStartStreamFn = int (*)(Bambu_Tunnel, bool);
using BambuStartStreamExFn = int (*)(Bambu_Tunnel, int);
using BambuGetStreamCountFn = int (*)(Bambu_Tunnel);
using BambuGetStreamInfoFn = int (*)(Bambu_Tunnel, int, Bambu_StreamInfo*);
using BambuSendMessageFn = int (*)(Bambu_Tunnel, int, const char*, int);
using BambuRecvMessageFn = int (*)(Bambu_Tunnel, int*, char*, int*);
using BambuReadSampleFn = int (*)(Bambu_Tunnel, Bambu_Sample*);
using BambuCloseFn = void (*)(Bambu_Tunnel);
using BambuDestroyFn = void (*)(Bambu_Tunnel);
using BambuSetLoggerFn = void (*)(Bambu_Tunnel, void (*)(void*, int, const char*), void*);
using BambuLastErrorFn = const char* (*)();

constexpr int CtrlStreamType = 0x3001;

struct Args {
    std::string source_plugin;
    std::string url;
    std::string mode{"video"};
    std::string message;
    int timeout_ms{10000};
    int poll_ms{50};
    int ctrl_type{CtrlStreamType};
    bool expect_success{false};
};

struct Loaded {
    void* module{nullptr};
    BambuInitFn init{nullptr};
    BambuDeinitFn deinit{nullptr};
    BambuCreateFn create{nullptr};
    BambuOpenFn open{nullptr};
    BambuStartStreamFn start_stream{nullptr};
    BambuStartStreamExFn start_stream_ex{nullptr};
    BambuGetStreamCountFn get_stream_count{nullptr};
    BambuGetStreamInfoFn get_stream_info{nullptr};
    BambuSendMessageFn send_message{nullptr};
    BambuRecvMessageFn recv_message{nullptr};
    BambuReadSampleFn read_sample{nullptr};
    BambuCloseFn close{nullptr};
    BambuDestroyFn destroy{nullptr};
    BambuSetLoggerFn set_logger{nullptr};
    BambuLastErrorFn last_error{nullptr};
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

std::string redact_url(std::string url)
{
    const std::string marker = "___";
    const auto marker_pos = url.find(marker);
    const auto at_pos = url.find('@', marker_pos == std::string::npos ? 0 : marker_pos + marker.size());
    if (marker_pos != std::string::npos && at_pos != std::string::npos) {
        const auto userinfo_start = marker_pos + marker.size();
        const auto colon_pos = url.find(':', userinfo_start);
        if (colon_pos != std::string::npos && colon_pos < at_pos)
            url.replace(colon_pos + 1, at_pos - colon_pos - 1, "<redacted>");
    }

    const std::string passwd_key = "passwd=";
    std::size_t search_pos = 0;
    while ((search_pos = url.find(passwd_key, search_pos)) != std::string::npos) {
        const auto value_start = search_pos + passwd_key.size();
        auto value_end = url.find('&', value_start);
        if (value_end == std::string::npos)
            value_end = url.size();
        url.replace(value_start, value_end - value_start, "<redacted>");
        search_pos = value_start + std::strlen("<redacted>");
    }
    return url;
}

bool parse_int(const char* value, int& out)
{
    try {
        std::size_t consumed = 0;
        const int parsed = std::stoi(value, &consumed);
        if (consumed != std::strlen(value))
            return false;
        out = parsed;
        return true;
    } catch (...) {
        return false;
    }
}

bool parse_args(int argc, char** argv, Args& args)
{
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--source-plugin" && i + 1 < argc) {
            args.source_plugin = argv[++i];
        } else if (arg == "--url" && i + 1 < argc) {
            args.url = argv[++i];
        } else if (arg == "--mode" && i + 1 < argc) {
            args.mode = argv[++i];
        } else if (arg == "--message" && i + 1 < argc) {
            args.message = argv[++i];
        } else if (arg == "--timeout-ms" && i + 1 < argc) {
            if (!parse_int(argv[++i], args.timeout_ms))
                return false;
        } else if (arg == "--poll-ms" && i + 1 < argc) {
            if (!parse_int(argv[++i], args.poll_ms))
                return false;
        } else if (arg == "--ctrl-type" && i + 1 < argc) {
            if (!parse_int(argv[++i], args.ctrl_type))
                return false;
        } else if (arg == "--expect-success") {
            args.expect_success = true;
        } else {
            return false;
        }
    }
    return !args.source_plugin.empty()
        && !args.url.empty()
        && (args.mode == "video" || args.mode == "control")
        && args.timeout_ms > 0
        && args.poll_ms > 0;
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
    loaded.start_stream = load_symbol<BambuStartStreamFn>(loaded.module, "Bambu_StartStream", loaded.missing);
    loaded.start_stream_ex = load_symbol<BambuStartStreamExFn>(loaded.module, "Bambu_StartStreamEx", loaded.missing);
    loaded.get_stream_count = load_symbol<BambuGetStreamCountFn>(loaded.module, "Bambu_GetStreamCount", loaded.missing);
    loaded.get_stream_info = load_symbol<BambuGetStreamInfoFn>(loaded.module, "Bambu_GetStreamInfo", loaded.missing);
    loaded.send_message = load_symbol<BambuSendMessageFn>(loaded.module, "Bambu_SendMessage", loaded.missing);
    loaded.recv_message = load_symbol<BambuRecvMessageFn>(loaded.module, "Bambu_RecvMessage", loaded.missing);
    loaded.read_sample = load_symbol<BambuReadSampleFn>(loaded.module, "Bambu_ReadSample", loaded.missing);
    loaded.close = load_symbol<BambuCloseFn>(loaded.module, "Bambu_Close", loaded.missing);
    loaded.destroy = load_symbol<BambuDestroyFn>(loaded.module, "Bambu_Destroy", loaded.missing);
    loaded.set_logger = load_symbol<BambuSetLoggerFn>(loaded.module, "Bambu_SetLogger", loaded.missing);
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

std::string number(int value)
{
    return std::to_string(value);
}

std::string boolean(bool value)
{
    return value ? "true" : "false";
}

void logger(void*, int, const char*) {}

int start_stream_once(const Loaded& source, Bambu_Tunnel tunnel, const Args& args)
{
    if (args.mode == "control")
        return source.start_stream_ex ? source.start_stream_ex(tunnel, args.ctrl_type) : -1;
    return source.start_stream ? source.start_stream(tunnel, true) : -1;
}

int read_until_ready(const Loaded& source, Bambu_Tunnel tunnel, const Args& args, Bambu_Sample& sample, int& attempts)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(args.timeout_ms);
    int result = -1;
    while (std::chrono::steady_clock::now() <= deadline) {
        ++attempts;
        result = source.read_sample ? source.read_sample(tunnel, &sample) : -1;
        if (result != Bambu_would_block && result != Bambu_buffer_limit)
            return result;
        std::this_thread::sleep_for(std::chrono::milliseconds(args.poll_ms));
    }
    return result;
}

int start_until_ready(const Loaded& source, Bambu_Tunnel tunnel, const Args& args, int& attempts)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(args.timeout_ms);
    int result = -1;
    while (std::chrono::steady_clock::now() <= deadline) {
        ++attempts;
        result = start_stream_once(source, tunnel, args);
        if (result != Bambu_would_block && result != Bambu_buffer_limit)
            return result;
        std::this_thread::sleep_for(std::chrono::milliseconds(args.poll_ms));
    }
    return result;
}

} // namespace

int main(int argc, char** argv)
{
    std::signal(SIGPIPE, SIG_IGN);

    Args args;
    if (!parse_args(argc, argv, args)) {
        std::cerr << "usage: " << argv[0]
                  << " --source-plugin <path> --url <bambu-url> [--mode video|control] [--expect-success]\n";
        return 2;
    }

    Loaded source = load_source(args.source_plugin);
    if (!source.module) {
        const char* error = dlerror();
        std::cerr << "dlopen source failed: " << (error ? error : "unknown error") << "\n";
        return 3;
    }

    std::map<std::string, std::string> results;
    std::map<std::string, std::string> contract;
    std::map<std::string, std::string> diagnostics;
    bool opened = false;
    bool stream_started = false;
    bool stream_info_available = false;
    bool message_sent = false;
    bool sample_message_sent = false;
    bool message_received = false;
    bool sample_read = false;

    if (source.init)
        results["Bambu_Init"] = number(source.init());

    Bambu_Tunnel tunnel = nullptr;
    if (source.create)
        results["Bambu_Create"] = number(source.create(&tunnel, args.url.c_str()));
    if (source.set_logger)
        source.set_logger(tunnel, logger, nullptr);
    if (source.open) {
        const int open_result = source.open(tunnel);
        results["Bambu_Open"] = number(open_result);
        opened = open_result == Bambu_success;
    }

    int start_attempts = 0;
    const int start_result = start_until_ready(source, tunnel, args, start_attempts);
    results["Bambu_StartStream_final"] = number(start_result);
    results["Bambu_StartStream_success"] = boolean(start_result == Bambu_success);
    diagnostics["start_attempts"] = number(start_attempts);
    stream_started = start_result == Bambu_success;

    int stream_count = -1;
    if (source.get_stream_count) {
        stream_count = source.get_stream_count(tunnel);
        results["Bambu_GetStreamCount"] = number(stream_count);
        contract["stream_count_positive"] = boolean(stream_count > 0);
    }

    Bambu_StreamInfo info{};
    int info_result = -1;
    if (source.get_stream_info) {
        info_result = source.get_stream_info(tunnel, 0, &info);
        results["Bambu_GetStreamInfo"] = number(info_result);
        stream_info_available = info_result == Bambu_success;
        contract["stream_type"] = number(static_cast<int>(info.type));
        contract["stream_sub_type"] = number(info.sub_type);
        contract["stream_format_type"] = number(info.format_type);
        contract["stream_format_size_positive"] = boolean(info.format_size > 0);
        contract["stream_max_frame_size_positive"] = boolean(info.max_frame_size > 0);
        contract["stream_width"] = number(info.format.video.width);
        contract["stream_height"] = number(info.format.video.height);
        contract["stream_frame_rate"] = number(info.format.video.frame_rate);
        diagnostics["format_buffer_present"] = boolean(info.format_buffer != nullptr);
    }

    if (args.mode == "control" && source.send_message && !args.message.empty()) {
        const int send_result = source.send_message(
            tunnel,
            args.ctrl_type,
            args.message.c_str(),
            static_cast<int>(args.message.size()));
        results["Bambu_SendMessage"] = number(send_result);
        message_sent = send_result == Bambu_success;
    }

    if (args.mode == "control" && source.recv_message) {
        int ctrl = 0;
        int len = 4096;
        char buffer[4096] = {};
        int recv_result = Bambu_would_block;
        const auto recv_deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(args.timeout_ms);
        while (std::chrono::steady_clock::now() <= recv_deadline) {
            len = static_cast<int>(sizeof(buffer));
            recv_result = source.recv_message(tunnel, &ctrl, buffer, &len);
            if (recv_result != Bambu_would_block && recv_result != Bambu_buffer_limit)
                break;
            std::this_thread::sleep_for(std::chrono::milliseconds(args.poll_ms));
        }
        results["Bambu_RecvMessage"] = number(recv_result);
        diagnostics["recv_ctrl"] = number(ctrl);
        diagnostics["recv_len"] = number(len);
        message_received = recv_result == Bambu_success && len > 0;
    }

    if (args.mode == "control" && source.send_message && !args.message.empty()) {
        const int send_result = source.send_message(
            tunnel,
            args.ctrl_type,
            args.message.c_str(),
            static_cast<int>(args.message.size()));
        results["Bambu_SendMessage_sample"] = number(send_result);
        sample_message_sent = send_result == Bambu_success;
    }

    Bambu_Sample sample{};
    int read_attempts = 0;
    const int read_result = read_until_ready(source, tunnel, args, sample, read_attempts);
    results["Bambu_ReadSample_final"] = number(read_result);
    results["Bambu_ReadSample_success"] = boolean(read_result == Bambu_success);
    contract["sample_has_buffer"] = boolean(sample.buffer != nullptr);
    contract["sample_size_positive"] = boolean(sample.size > 0);
    contract["sample_track"] = number(sample.itrack);
    contract["sample_flags"] = number(sample.flags);
    diagnostics["read_attempts"] = number(read_attempts);
    diagnostics["sample_size"] = number(sample.size);
    diagnostics["sample_decode_time"] = std::to_string(sample.decode_time);
    sample_read = read_result == Bambu_success && sample.buffer != nullptr && sample.size > 0;

    if (source.last_error) {
        const char* error = source.last_error();
        diagnostics["last_error"] = "\"" + json_escape(error ? error : "") + "\"";
    }
    if (source.close && tunnel)
        source.close(tunnel);
    if (source.destroy && tunnel)
        source.destroy(tunnel);
    if (source.deinit)
        source.deinit();

    const bool semantic_success = args.mode == "control"
        ? source.missing.empty() && opened && stream_started && message_sent && message_received && sample_message_sent && sample_read
        : source.missing.empty() && opened && stream_started && stream_info_available && sample_read;
    const bool ok = args.expect_success ? semantic_success : source.missing.empty();

    std::cout << "{\n";
    std::cout << "  \"source_plugin\": \"" << json_escape(args.source_plugin) << "\",\n";
    std::cout << "  \"url\": \"" << json_escape(redact_url(args.url)) << "\",\n";
    std::cout << "  \"mode\": \"" << json_escape(args.mode) << "\",\n";
    std::cout << "  \"expect_success\": " << (args.expect_success ? "true" : "false") << ",\n";
    std::cout << "  \"missing_symbols\": ";
    write_string_array(source.missing);
    std::cout << ",\n";
    std::cout << "  \"results\": ";
    write_result_map(results);
    std::cout << ",\n";
    std::cout << "  \"stream_contract\": ";
    write_result_map(contract);
    std::cout << ",\n";
    std::cout << "  \"semantic\": {"
              << "\"opened\": " << (opened ? "true" : "false") << ", "
              << "\"stream_started\": " << (stream_started ? "true" : "false") << ", "
              << "\"stream_info_available\": " << (stream_info_available ? "true" : "false") << ", "
              << "\"message_sent\": " << (message_sent ? "true" : "false") << ", "
              << "\"message_received\": " << (message_received ? "true" : "false") << ", "
              << "\"sample_message_sent\": " << (sample_message_sent ? "true" : "false") << ", "
              << "\"sample_read\": " << (sample_read ? "true" : "false")
              << "},\n";
    std::cout << "  \"diagnostics\": ";
    write_result_map(diagnostics);
    std::cout << ",\n";
    std::cout << "  \"ok\": " << (ok ? "true" : "false") << "\n";
    std::cout << "}\n";

    dlclose(source.module);
    return ok ? 0 : 1;
}
