#include <dlfcn.h>

#include <csignal>
#include <cstdint>
#include <iostream>
#include <map>
#include <string>
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
using BambuGetDurationFn = unsigned long (*)(Bambu_Tunnel);
using BambuSeekFn = int (*)(Bambu_Tunnel, unsigned long);
using BambuSendMessageFn = int (*)(Bambu_Tunnel, int, const char*, int);
using BambuRecvMessageFn = int (*)(Bambu_Tunnel, int*, char*, int*);
using BambuReadSampleFn = int (*)(Bambu_Tunnel, Bambu_Sample*);
using BambuCloseFn = void (*)(Bambu_Tunnel);
using BambuDestroyFn = void (*)(Bambu_Tunnel);
using BambuSetLoggerFn = void (*)(Bambu_Tunnel, void (*)(void*, int, const char*), void*);
using BambuFreeLogMsgFn = void (*)(const char*);
using BambuLastErrorFn = const char* (*)();

struct Args {
    std::string source_plugin;
    bool record_only{false};
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
        } else if (arg == "--record-only") {
            args.record_only = true;
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

std::string unsigned_number(unsigned long value)
{
    return std::to_string(value);
}

std::string boolean(bool value)
{
    return value ? "true" : "false";
}

bool result_is(const std::map<std::string, std::string>& results, const std::string& key, const std::string& expected)
{
    const auto it = results.find(key);
    return it != results.end() && it->second == expected;
}

void logger(void*, int, const char*) {}

}

int main(int argc, char** argv)
{
    std::signal(SIGPIPE, SIG_IGN);

    Args args;
    if (!parse_args(argc, argv, args)) {
        std::cerr << "usage: " << argv[0] << " --source-plugin <path>\n";
        return 2;
    }

    void* source = dlopen(args.source_plugin.c_str(), RTLD_LAZY | RTLD_LOCAL);
    if (!source) {
        const char* error = dlerror();
        std::cerr << "dlopen source failed: " << (error ? error : "unknown error") << "\n";
        return 3;
    }

    std::vector<std::string> missing;
    auto bambu_init = load_symbol<BambuInitFn>(source, "Bambu_Init", missing);
    auto bambu_deinit = load_symbol<BambuDeinitFn>(source, "Bambu_Deinit", missing);
    auto bambu_create = load_symbol<BambuCreateFn>(source, "Bambu_Create", missing);
    auto bambu_open = load_symbol<BambuOpenFn>(source, "Bambu_Open", missing);
    auto bambu_start_stream = load_symbol<BambuStartStreamFn>(source, "Bambu_StartStream", missing);
    auto bambu_start_stream_ex = load_symbol<BambuStartStreamExFn>(source, "Bambu_StartStreamEx", missing);
    auto bambu_get_stream_count = load_symbol<BambuGetStreamCountFn>(source, "Bambu_GetStreamCount", missing);
    auto bambu_get_stream_info = load_symbol<BambuGetStreamInfoFn>(source, "Bambu_GetStreamInfo", missing);
    auto bambu_get_duration = load_symbol<BambuGetDurationFn>(source, "Bambu_GetDuration", missing);
    auto bambu_seek = load_symbol<BambuSeekFn>(source, "Bambu_Seek", missing);
    auto bambu_send_message = load_symbol<BambuSendMessageFn>(source, "Bambu_SendMessage", missing);
    auto bambu_recv_message = load_symbol<BambuRecvMessageFn>(source, "Bambu_RecvMessage", missing);
    auto bambu_read_sample = load_symbol<BambuReadSampleFn>(source, "Bambu_ReadSample", missing);
    auto bambu_close = load_symbol<BambuCloseFn>(source, "Bambu_Close", missing);
    auto bambu_destroy = load_symbol<BambuDestroyFn>(source, "Bambu_Destroy", missing);
    auto bambu_set_logger = load_symbol<BambuSetLoggerFn>(source, "Bambu_SetLogger", missing);
    auto bambu_free_log_msg = load_symbol<BambuFreeLogMsgFn>(source, "Bambu_FreeLogMsg", missing);
    auto bambu_last_error = load_symbol<BambuLastErrorFn>(source, "Bambu_GetLastErrorMsg", missing);

    std::map<std::string, std::string> results;
    if (bambu_init)
        results["Bambu_Init"] = number(bambu_init());
    if (bambu_create && !args.record_only)
        results["Bambu_Create_null_out"] = number(bambu_create(
            nullptr,
            "bambu:///rtsps___bblp:12345678@192.0.2.10/streaming/live/1?proto=rtsps"));
    if (bambu_open)
        results["Bambu_Open_null"] = number(bambu_open(nullptr));
    if (bambu_get_stream_count)
        results["Bambu_GetStreamCount_null"] = number(bambu_get_stream_count(nullptr));
    if (bambu_get_duration)
        results["Bambu_GetDuration_null"] = unsigned_number(bambu_get_duration(nullptr));
    if (bambu_set_logger)
        bambu_set_logger(nullptr, logger, nullptr);
    if (bambu_free_log_msg && !args.record_only)
        bambu_free_log_msg(nullptr);

    Bambu_Tunnel invalid_tunnel = nullptr;
    if (bambu_create)
        results["Bambu_Create_invalid"] = number(bambu_create(&invalid_tunnel, "wss://example.invalid"));
    if (bambu_open)
        results["Bambu_Open_invalid"] = number(bambu_open(invalid_tunnel));
    if (bambu_get_stream_count)
        results["Bambu_GetStreamCount_invalid"] = number(bambu_get_stream_count(invalid_tunnel));
    if (bambu_destroy && invalid_tunnel)
        bambu_destroy(invalid_tunnel);

    Bambu_Tunnel camera_tunnel = nullptr;
    if (bambu_create)
        results["Bambu_Create_camera"] = number(bambu_create(
            &camera_tunnel,
            "bambu:///rtsps___bblp:12345678@192.0.2.10/streaming/live/1?proto=rtsps"));
    if (bambu_open)
        results["Bambu_Open_camera"] = number(bambu_open(camera_tunnel));
    if (bambu_start_stream)
        results["Bambu_StartStream_camera"] = number(bambu_start_stream(camera_tunnel, true));
    if (bambu_start_stream_ex)
        results["Bambu_StartStreamEx_camera"] = number(bambu_start_stream_ex(camera_tunnel, 0));
    if (bambu_get_stream_count)
        results["Bambu_GetStreamCount_camera"] = number(bambu_get_stream_count(camera_tunnel));
    Bambu_StreamInfo info;
    info.type = static_cast<Bambu_StreamType>(99);
    if (bambu_get_stream_info) {
        results["Bambu_GetStreamInfo_camera"] = number(bambu_get_stream_info(camera_tunnel, 0, &info));
        results["Bambu_GetStreamInfo_camera_zeroed"] = boolean(info.type == 0 && info.format_buffer == nullptr && info.format_size == 0);
    }
    if (bambu_get_duration)
        results["Bambu_GetDuration_camera"] = unsigned_number(bambu_get_duration(camera_tunnel));
    if (bambu_seek)
        results["Bambu_Seek_camera"] = number(bambu_seek(camera_tunnel, 100));
    if (bambu_send_message)
        results["Bambu_SendMessage_camera"] = number(bambu_send_message(camera_tunnel, 1, "{}", 2));
    int message_type = 99;
    int message_size = 99;
    char message_buffer[4] = {'x', 'x', 'x', '\0'};
    if (bambu_recv_message) {
        results["Bambu_RecvMessage_camera"] = number(bambu_recv_message(camera_tunnel, &message_type, message_buffer, &message_size));
        results["Bambu_RecvMessage_camera_zeroed"] = boolean(
            message_type == 0 && message_size == 0 && message_buffer[0] == '\0');
    }
    Bambu_Sample sample;
    sample.size = 99;
    if (bambu_read_sample) {
        results["Bambu_ReadSample_camera"] = number(bambu_read_sample(camera_tunnel, &sample));
        results["Bambu_ReadSample_camera_zeroed"] = boolean(sample.itrack == 0 && sample.buffer == nullptr && sample.size == 0);
    }
    if (bambu_close && camera_tunnel)
        bambu_close(camera_tunnel);
    if (bambu_destroy && camera_tunnel)
        bambu_destroy(camera_tunnel);

    Bambu_Tunnel local_tunnel = nullptr;
    if (bambu_create)
        results["Bambu_Create_local"] = number(bambu_create(&local_tunnel, "bambu:///local/127.0.0.1"));
    if (bambu_open)
        results["Bambu_Open_local"] = number(bambu_open(local_tunnel));
    if (bambu_close && local_tunnel)
        bambu_close(local_tunnel);
    if (bambu_destroy && local_tunnel)
        bambu_destroy(local_tunnel);

    if (bambu_last_error)
        results["Bambu_GetLastErrorMsg"] = "\"" + json_escape(bambu_last_error()) + "\"";
    if (bambu_deinit)
        bambu_deinit();

    const bool strict_ok = missing.empty()
        && result_is(results, "Bambu_Init", "0")
        && result_is(results, "Bambu_Create_null_out", "-1")
        && result_is(results, "Bambu_Open_null", "-1")
        && result_is(results, "Bambu_GetStreamCount_null", "-1")
        && result_is(results, "Bambu_Create_invalid", "-1")
        && result_is(results, "Bambu_Open_invalid", "-1")
        && result_is(results, "Bambu_GetStreamCount_invalid", "-1")
        && result_is(results, "Bambu_Create_camera", "0")
        && result_is(results, "Bambu_Open_camera", "0")
        && result_is(results, "Bambu_StartStream_camera", "2")
        && result_is(results, "Bambu_StartStreamEx_camera", "2")
        && result_is(results, "Bambu_GetStreamCount_camera", "1")
        && result_is(results, "Bambu_GetStreamInfo_camera", "-1")
        && result_is(results, "Bambu_GetStreamInfo_camera_zeroed", "false")
        && result_is(results, "Bambu_GetDuration_camera", std::to_string(static_cast<unsigned long>(-1)))
        && result_is(results, "Bambu_Seek_camera", "-1")
        && result_is(results, "Bambu_SendMessage_camera", "-1")
        && result_is(results, "Bambu_RecvMessage_camera", "-1")
        && result_is(results, "Bambu_RecvMessage_camera_zeroed", "false")
        && result_is(results, "Bambu_ReadSample_camera", "2")
        && result_is(results, "Bambu_ReadSample_camera_zeroed", "false")
        && result_is(results, "Bambu_Create_local", "0")
        && result_is(results, "Bambu_Open_local", "-3001");
    const bool ok = args.record_only || strict_ok;

    std::cout << "{\n";
    std::cout << "  \"source_plugin\": \"" << json_escape(args.source_plugin) << "\",\n";
    std::cout << "  \"record_only\": " << (args.record_only ? "true" : "false") << ",\n";
    std::cout << "  \"missing_symbols\": ";
    write_string_array(missing);
    std::cout << ",\n";
    std::cout << "  \"results\": ";
    write_result_map(results);
    std::cout << ",\n";
    std::cout << "  \"strict_ok\": " << (strict_ok ? "true" : "false") << ",\n";
    std::cout << "  \"ok\": " << (ok ? "true" : "false") << "\n";
    std::cout << "}\n";

    dlclose(source);
    return ok ? 0 : 1;
}
