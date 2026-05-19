#include <dlfcn.h>

#include <functional>
#include <iostream>
#include <map>
#include <string>
#include <vector>

#include "../bambu_network_rust_plugin/shim/bambu_networking_abi.hpp"

namespace {

using CreateAgentFn = void* (*)(std::string);
using DestroyAgentFn = int (*)(void*);
using ConnectServerFn = int (*)(void*);
using IsServerConnectedFn = bool (*)(void*);
using IntAgentFn = int (*)(void*);
using StringAgentFn = std::string (*)(void*);
using CheckDebugConsistentFn = bool (*)(bool);
using SetCertFileFn = int (*)(void*, std::string, std::string);
using SetStringFn = int (*)(void*, std::string);
using OnMsgArrivedFn = std::function<void(std::string)>;
using SetSsdpFn = int (*)(void*, OnMsgArrivedFn);
using StartDiscoveryFn = bool (*)(void*, bool, bool);
using ConnectPrinterFn = int (*)(void*, std::string, std::string, std::string, std::string, bool);
using SendMessageFn = int (*)(void*, std::string, std::string, int, int);
using StartSdcardPrintFn = int (*)(void*, Slic3r::PrintParams, Slic3r::OnUpdateStatusFn, Slic3r::WasCancelledFn);
using StartPrintWithWaitFn = int (*)(void*, Slic3r::PrintParams, Slic3r::OnUpdateStatusFn, Slic3r::WasCancelledFn, Slic3r::OnWaitFn);
using GetCameraUrlFn = int (*)(void*, std::string, std::function<void(std::string)>);
using GetCameraUrlForGoliveFn = int (*)(void*, std::string, std::string, std::function<void(std::string)>);
using SubscribeFn = int (*)(void*, std::string);
using SubscribeListFn = int (*)(void*, std::vector<std::string>);
using EnableMultiMachineFn = void (*)(void*, bool);
using InstallDeviceCertFn = void (*)(void*, std::string, bool);
using ChangeUserFn = int (*)(void*, std::string);
using UserLogoutFn = int (*)(void*, bool);
using PingBindFn = int (*)(void*, std::string);
using BindDetectFn = int (*)(void*, std::string, std::string, Slic3r::detectResult&);
using ReportConsentFn = int (*)(void*, std::string);
using BindFn = int (*)(void*, std::string, std::string, std::string, std::string, bool, Slic3r::OnUpdateStatusFn);
using UnbindFn = int (*)(void*, std::string);
using SetUserSelectedMachineFn = int (*)(void*, std::string);
using UserPresetsFn = int (*)(void*, std::map<std::string, std::map<std::string, std::string>>*);
using RequestSettingIdFn = std::string (*)(void*, std::string, std::map<std::string, std::string>*, unsigned int*);
using PutSettingFn = int (*)(void*, std::string, std::string, std::map<std::string, std::string>*, unsigned int*);
using GetSettingListFn = int (*)(void*, std::string, Slic3r::ProgressFn, Slic3r::WasCancelledFn);
using GetSettingList2Fn = int (*)(void*, std::string, Slic3r::CheckFn, Slic3r::ProgressFn, Slic3r::WasCancelledFn);
using DeleteSettingFn = int (*)(void*, std::string);
using SetExtraHttpHeaderFn = int (*)(void*, std::map<std::string, std::string>);
using GetMyMessageFn = int (*)(void*, int, int, int, unsigned int*, std::string*);
using CheckUserTaskReportFn = int (*)(void*, int*, bool*);
using GetUserPrintInfoFn = int (*)(void*, unsigned int*, std::string*);
using GetUserTasksFn = int (*)(void*, Slic3r::TaskQueryParams, std::string*);
using GetPrinterFirmwareFn = int (*)(void*, std::string, unsigned int*, std::string*);
using GetTaskPlateIndexFn = int (*)(void*, std::string, int*);
using GetUserInfoFn = int (*)(void*, int*);
using RequestBindTicketFn = int (*)(void*, std::string*);
using GetSubtaskInfoFn = int (*)(void*, std::string, std::string*, unsigned int*, std::string*);
using GetSliceInfoFn = int (*)(void*, std::string, std::string, int, std::string*);
using QueryBindStatusFn = int (*)(void*, std::vector<std::string>, unsigned int*, std::string*);
using ModifyPrinterNameFn = int (*)(void*, std::string, std::string);
using DesignStaffpickFn = int (*)(void*, int, int, std::function<void(std::string)>);
using StartPublishFn = int (*)(void*, Slic3r::PublishParams, Slic3r::OnUpdateStatusFn, Slic3r::WasCancelledFn, std::string*);
using StringOutFn = int (*)(void*, std::string*);
using StringOutWithInputFn = int (*)(void*, std::string*, std::string);
using GetSubtaskFn = int (*)(void*, Slic3r::BBLModelTask*, Slic3r::OnGetSubTaskFn);
using GetMyTokenFn = int (*)(void*, std::string, unsigned int*, std::string*);
using TrackEnableFn = int (*)(void*, bool);
using TrackEventFn = int (*)(void*, std::string, std::string);
using TrackUpdatePropertyFn = int (*)(void*, std::string, std::string, std::string);
using TrackGetPropertyFn = int (*)(void*, std::string, std::string&, std::string);
using PutModelMallRatingFn = int (*)(void*, int, int, std::string, std::vector<std::string>, unsigned int&, std::string&);
using GetOssConfigFn = int (*)(void*, std::string&, std::string, unsigned int&, std::string&);
using PutRatingPictureOssFn = int (*)(void*, std::string&, std::string&, std::string, int, unsigned int&, std::string&);
using GetModelMallRatingFn = int (*)(void*, int, std::string&, unsigned int&, std::string&);
using StringCallbackFn = int (*)(void*, std::function<void(std::string)>);
using User4uListFn = int (*)(void*, int, int, std::function<void(std::string)>);
using HmsSnapshotFn = int (*)(void*, std::string, std::string, std::function<void(std::string, int)>);
using FtAbiVersionFn = int (*)();
using FtTunnelCreateFn = int (*)(const char*, void**);
using FtTunnelRetainFn = void (*)(void*);
using FtTunnelReleaseFn = void (*)(void*);
using FtTunnelStartConnectFn = int (*)(void*, void (*)(void*, int, int, const char*), void*);
using FtTunnelSetStatusCbFn = int (*)(void*, void (*)(void*, int, int, int, const char*), void*);
using FtJobCreateFn = int (*)(const char*, void**);
using FtJobRetainFn = void (*)(void*);
using FtJobReleaseFn = void (*)(void*);

using BambuInitFn = int (*)();
using BambuCreateFn = int (*)(void**, const char*);
using BambuOpenFn = int (*)(void*);
using BambuGetStreamCountFn = int (*)(void*);
using BambuDestroyFn = void (*)(void*);
using BambuLastErrorFn = const char* (*)();

struct Args {
    std::string network_plugin;
    std::string source_plugin;
    std::string log_dir{"."};
    bool official_compatible{false};
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
        if (arg == "--network-plugin" && i + 1 < argc) {
            args.network_plugin = argv[++i];
        } else if (arg == "--source-plugin" && i + 1 < argc) {
            args.source_plugin = argv[++i];
        } else if (arg == "--log-dir" && i + 1 < argc) {
            args.log_dir = argv[++i];
        } else if (arg == "--official-compatible") {
            args.official_compatible = true;
        } else {
            return false;
        }
    }
    return !args.network_plugin.empty() && !args.source_plugin.empty();
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

std::string unsigned_number(unsigned int value)
{
    return std::to_string(value);
}

std::string boolean(bool value)
{
    return value ? "true" : "false";
}

std::string string_value(const std::string& value)
{
    return "\"" + json_escape(value) + "\"";
}

}

int main(int argc, char** argv)
{
    Args args;
    if (!parse_args(argc, argv, args)) {
        std::cerr << "usage: " << argv[0] << " --network-plugin <path> --source-plugin <path> [--log-dir <path>] [--official-compatible]\n";
        return 2;
    }

    void* network = dlopen(args.network_plugin.c_str(), RTLD_LAZY | RTLD_LOCAL);
    if (!network) {
        const char* error = dlerror();
        std::cerr << "dlopen network failed: " << (error ? error : "unknown error") << "\n";
        return 3;
    }
    void* source = dlopen(args.source_plugin.c_str(), RTLD_LAZY | RTLD_LOCAL);
    if (!source) {
        const char* error = dlerror();
        std::cerr << "dlopen source failed: " << (error ? error : "unknown error") << "\n";
        return 3;
    }

    std::vector<std::string> missing;
    auto create_agent = load_symbol<CreateAgentFn>(network, "bambu_network_create_agent", missing);
    auto destroy_agent = load_symbol<DestroyAgentFn>(network, "bambu_network_destroy_agent", missing);
    auto init_log = load_symbol<IntAgentFn>(network, "bambu_network_init_log", missing);
    auto set_config_dir = load_symbol<SetStringFn>(network, "bambu_network_set_config_dir", missing);
    auto check_debug_consistent = load_symbol<CheckDebugConsistentFn>(network, "bambu_network_check_debug_consistent", missing);
    auto set_cert_file = load_symbol<SetCertFileFn>(network, "bambu_network_set_cert_file", missing);
    auto set_country_code = load_symbol<SetStringFn>(network, "bambu_network_set_country_code", missing);
    auto set_ssdp = load_symbol<SetSsdpFn>(network, "bambu_network_set_on_ssdp_msg_fn", missing);
    auto connect_server = load_symbol<ConnectServerFn>(network, "bambu_network_connect_server", missing);
    auto is_server_connected = load_symbol<IsServerConnectedFn>(network, "bambu_network_is_server_connected", missing);
    auto start_discovery = load_symbol<StartDiscoveryFn>(network, "bambu_network_start_discovery", missing);
    auto connect_printer = load_symbol<ConnectPrinterFn>(network, "bambu_network_connect_printer", missing);
    auto send_message = load_symbol<SendMessageFn>(network, "bambu_network_send_message", missing);
    auto send_message_to_printer = load_symbol<SendMessageFn>(network, "bambu_network_send_message_to_printer", missing);
    auto start_sdcard_print = load_symbol<StartSdcardPrintFn>(network, "bambu_network_start_sdcard_print", missing);
    auto start_local_print = load_symbol<StartSdcardPrintFn>(network, "bambu_network_start_local_print", missing);
    auto start_send_gcode_to_sdcard = load_symbol<StartPrintWithWaitFn>(network, "bambu_network_start_send_gcode_to_sdcard", missing);
    auto get_camera_url = load_symbol<GetCameraUrlFn>(network, "bambu_network_get_camera_url", missing);
    auto get_camera_url_for_golive = load_symbol<GetCameraUrlForGoliveFn>(network, "bambu_network_get_camera_url_for_golive", missing);
    auto refresh_connection = load_symbol<IntAgentFn>(network, "bambu_network_refresh_connection", missing);
    auto start_subscribe = load_symbol<SubscribeFn>(network, "bambu_network_start_subscribe", missing);
    auto stop_subscribe = load_symbol<SubscribeFn>(network, "bambu_network_stop_subscribe", missing);
    auto add_subscribe = load_symbol<SubscribeListFn>(network, "bambu_network_add_subscribe", missing);
    auto del_subscribe = load_symbol<SubscribeListFn>(network, "bambu_network_del_subscribe", missing);
    auto enable_multi_machine = load_symbol<EnableMultiMachineFn>(network, "bambu_network_enable_multi_machine", missing);
    auto update_cert = load_symbol<IntAgentFn>(network, "bambu_network_update_cert", missing);
    auto install_device_cert = load_symbol<InstallDeviceCertFn>(network, "bambu_network_install_device_cert", missing);
    auto change_user = load_symbol<ChangeUserFn>(network, "bambu_network_change_user", missing);
    auto user_logout = load_symbol<UserLogoutFn>(network, "bambu_network_user_logout", missing);
    auto get_user_avatar = load_symbol<StringAgentFn>(network, "bambu_network_get_user_avatar", missing);
    auto ping_bind = load_symbol<PingBindFn>(network, "bambu_network_ping_bind", missing);
    auto bind_detect = load_symbol<BindDetectFn>(network, "bambu_network_bind_detect", missing);
    auto report_consent = load_symbol<ReportConsentFn>(network, "bambu_network_report_consent", missing);
    auto bind = load_symbol<BindFn>(network, "bambu_network_bind", missing);
    auto unbind = load_symbol<UnbindFn>(network, "bambu_network_unbind", missing);
    auto get_bambulab_host = load_symbol<StringAgentFn>(network, "bambu_network_get_bambulab_host", missing);
    auto get_user_selected_machine = load_symbol<StringAgentFn>(network, "bambu_network_get_user_selected_machine", missing);
    auto set_user_selected_machine = load_symbol<SetUserSelectedMachineFn>(network, "bambu_network_set_user_selected_machine", missing);
    auto start_print = load_symbol<StartPrintWithWaitFn>(network, "bambu_network_start_print", missing);
    auto get_user_presets = load_symbol<UserPresetsFn>(network, "bambu_network_get_user_presets", missing);
    auto request_setting_id = load_symbol<RequestSettingIdFn>(network, "bambu_network_request_setting_id", missing);
    auto put_setting = load_symbol<PutSettingFn>(network, "bambu_network_put_setting", missing);
    auto get_setting_list = load_symbol<GetSettingListFn>(network, "bambu_network_get_setting_list", missing);
    auto get_setting_list2 = load_symbol<GetSettingList2Fn>(network, "bambu_network_get_setting_list2", missing);
    auto delete_setting = load_symbol<DeleteSettingFn>(network, "bambu_network_delete_setting", missing);
    auto get_studio_info_url = load_symbol<StringAgentFn>(network, "bambu_network_get_studio_info_url", missing);
    auto set_extra_http_header = load_symbol<SetExtraHttpHeaderFn>(network, "bambu_network_set_extra_http_header", missing);
    auto get_my_message = load_symbol<GetMyMessageFn>(network, "bambu_network_get_my_message", missing);
    auto check_user_task_report = load_symbol<CheckUserTaskReportFn>(network, "bambu_network_check_user_task_report", missing);
    auto get_user_print_info = load_symbol<GetUserPrintInfoFn>(network, "bambu_network_get_user_print_info", missing);
    auto get_user_tasks = load_symbol<GetUserTasksFn>(network, "bambu_network_get_user_tasks", missing);
    auto get_printer_firmware = load_symbol<GetPrinterFirmwareFn>(network, "bambu_network_get_printer_firmware", missing);
    auto get_task_plate_index = load_symbol<GetTaskPlateIndexFn>(network, "bambu_network_get_task_plate_index", missing);
    auto get_user_info = load_symbol<GetUserInfoFn>(network, "bambu_network_get_user_info", missing);
    auto request_bind_ticket = load_symbol<RequestBindTicketFn>(network, "bambu_network_request_bind_ticket", missing);
    auto get_subtask_info = load_symbol<GetSubtaskInfoFn>(network, "bambu_network_get_subtask_info", missing);
    auto get_slice_info = load_symbol<GetSliceInfoFn>(network, "bambu_network_get_slice_info", missing);
    auto query_bind_status = load_symbol<QueryBindStatusFn>(network, "bambu_network_query_bind_status", missing);
    auto modify_printer_name = load_symbol<ModifyPrinterNameFn>(network, "bambu_network_modify_printer_name", missing);
    auto get_design_staffpick = load_symbol<DesignStaffpickFn>(network, "bambu_network_get_design_staffpick", missing);
    auto start_publish = load_symbol<StartPublishFn>(network, "bambu_network_start_publish", missing);
    auto get_model_publish_url = load_symbol<StringOutFn>(network, "bambu_network_get_model_publish_url", missing);
    auto get_subtask = load_symbol<GetSubtaskFn>(network, "bambu_network_get_subtask", missing);
    auto get_model_mall_home_url = load_symbol<StringOutFn>(network, "bambu_network_get_model_mall_home_url", missing);
    auto get_model_mall_detail_url = load_symbol<StringOutWithInputFn>(network, "bambu_network_get_model_mall_detail_url", missing);
    auto get_my_token = load_symbol<GetMyTokenFn>(network, "bambu_network_get_my_token", missing);
    auto get_my_profile = load_symbol<GetMyTokenFn>(network, "bambu_network_get_my_profile", missing);
    auto track_enable = load_symbol<TrackEnableFn>(network, "bambu_network_track_enable", missing);
    auto track_remove_files = load_symbol<IntAgentFn>(network, "bambu_network_track_remove_files", missing);
    auto track_event = load_symbol<TrackEventFn>(network, "bambu_network_track_event", missing);
    auto track_header = load_symbol<ReportConsentFn>(network, "bambu_network_track_header", missing);
    auto track_update_property = load_symbol<TrackUpdatePropertyFn>(network, "bambu_network_track_update_property", missing);
    auto track_get_property = load_symbol<TrackGetPropertyFn>(network, "bambu_network_track_get_property", missing);
    auto put_model_mall_rating = load_symbol<PutModelMallRatingFn>(network, "bambu_network_put_model_mall_rating", missing);
    auto get_oss_config = load_symbol<GetOssConfigFn>(network, "bambu_network_get_oss_config", missing);
    auto put_rating_picture_oss = load_symbol<PutRatingPictureOssFn>(network, "bambu_network_put_rating_picture_oss", missing);
    auto get_model_mall_rating = load_symbol<GetModelMallRatingFn>(network, "bambu_network_get_model_mall_rating", missing);
    auto get_mw_user_preference = load_symbol<StringCallbackFn>(network, "bambu_network_get_mw_user_preference", missing);
    auto get_mw_user_4ulist = load_symbol<User4uListFn>(network, "bambu_network_get_mw_user_4ulist", missing);
    auto get_hms_snapshot = load_symbol<HmsSnapshotFn>(network, "bambu_network_get_hms_snapshot", missing);
    auto ft_abi_version = load_symbol<FtAbiVersionFn>(network, "ft_abi_version", missing);
    auto ft_tunnel_create = load_symbol<FtTunnelCreateFn>(network, "ft_tunnel_create", missing);
    auto ft_tunnel_retain = load_symbol<FtTunnelRetainFn>(network, "ft_tunnel_retain", missing);
    auto ft_tunnel_release = load_symbol<FtTunnelReleaseFn>(network, "ft_tunnel_release", missing);
    auto ft_tunnel_start_connect = load_symbol<FtTunnelStartConnectFn>(network, "ft_tunnel_start_connect", missing);
    auto ft_tunnel_set_status_cb = load_symbol<FtTunnelSetStatusCbFn>(network, "ft_tunnel_set_status_cb", missing);
    auto ft_job_create = load_symbol<FtJobCreateFn>(network, "ft_job_create", missing);
    auto ft_job_retain = load_symbol<FtJobRetainFn>(network, "ft_job_retain", missing);
    auto ft_job_release = load_symbol<FtJobReleaseFn>(network, "ft_job_release", missing);

    auto bambu_init = load_symbol<BambuInitFn>(source, "Bambu_Init", missing);
    auto bambu_create = load_symbol<BambuCreateFn>(source, "Bambu_Create", missing);
    auto bambu_open = load_symbol<BambuOpenFn>(source, "Bambu_Open", missing);
    auto bambu_get_stream_count = load_symbol<BambuGetStreamCountFn>(source, "Bambu_GetStreamCount", missing);
    auto bambu_destroy = load_symbol<BambuDestroyFn>(source, "Bambu_Destroy", missing);
    auto bambu_last_error = load_symbol<BambuLastErrorFn>(source, "Bambu_GetLastErrorMsg", missing);

    void* agent = create_agent ? create_agent(args.log_dir) : nullptr;
    std::map<std::string, std::string> results;
    int camera_callbacks = 0;
    int string_callbacks = 0;
    int hms_callbacks = 0;
    if (check_debug_consistent)
        results["check_debug_consistent"] = boolean(check_debug_consistent(false));
    if (set_config_dir)
        results["set_config_dir"] = number(set_config_dir(agent, args.log_dir));
    if (init_log)
        results["init_log"] = number(init_log(agent));
    if (set_cert_file)
        results["set_cert_file"] = number(set_cert_file(agent, "resources/cert", "slicer_base64.cer"));
    if (set_country_code)
        results["set_country_code"] = number(set_country_code(agent, "US"));
    if (set_ssdp)
        results["set_on_ssdp_msg_fn"] = number(set_ssdp(agent, [](std::string) {}));
    if (args.official_compatible) {
        if (ft_abi_version)
            results["ft_abi_version"] = number(ft_abi_version());
        if (bambu_init)
            results["Bambu_Init"] = number(bambu_init());
        if (set_ssdp)
            results["clear_on_ssdp_msg_fn"] = number(set_ssdp(agent, nullptr));

        int destroy_result = -999999;
        if (destroy_agent && agent)
            destroy_result = destroy_agent(agent);

        std::cout << "{\n";
        std::cout << "  \"network_plugin\": \"" << json_escape(args.network_plugin) << "\",\n";
        std::cout << "  \"source_plugin\": \"" << json_escape(args.source_plugin) << "\",\n";
        std::cout << "  \"log_dir\": \"" << json_escape(args.log_dir) << "\",\n";
        std::cout << "  \"official_compatible\": true,\n";
        std::cout << "  \"agent_created\": " << (agent ? "true" : "false") << ",\n";
        std::cout << "  \"missing_symbols\": ";
        write_string_array(missing);
        std::cout << ",\n";
        std::cout << "  \"results\": ";
        write_result_map(results);
        std::cout << ",\n";
        std::cout << "  \"destroy_result\": " << destroy_result << "\n";
        std::cout << "}\n";

        dlclose(source);
        dlclose(network);
        return missing.empty() && agent ? 0 : 1;
    }
    if (connect_server)
        results["connect_server"] = number(connect_server(agent));
    if (is_server_connected)
        results["is_server_connected"] = boolean(is_server_connected(agent));
    if (start_discovery)
        results["start_discovery"] = boolean(start_discovery(agent, true, false));
    if (connect_printer)
        results["connect_printer"] = number(connect_printer(agent, "dev", "127.0.0.1", "user", "pass", false));
    if (send_message)
        results["send_message"] = number(send_message(agent, "dev", "{}", 0, 0));
    if (send_message)
        results["send_message_invalid_json"] = number(send_message(agent, "dev", "{", 0, 0));
    if (send_message_to_printer)
        results["send_message_to_printer_invalid_json"] = number(send_message_to_printer(agent, "dev", "{", 0, 0));
    if (send_message_to_printer)
        results["send_message_to_printer_invalid_dev_id"] = number(send_message_to_printer(agent, "bad/id", "{}", 0, 0));
    if (start_sdcard_print) {
        Slic3r::PrintParams valid_sdcard_print;
        valid_sdcard_print.dev_id = "dev";
        valid_sdcard_print.plate_index = 1;
        valid_sdcard_print.dst_file = "file:///sdcard/existing.3mf";
        results["start_sdcard_print_without_session"] = number(start_sdcard_print(agent, valid_sdcard_print, nullptr, nullptr));

        Slic3r::PrintParams invalid_sdcard_print;
        invalid_sdcard_print.dev_id = "bad/id";
        invalid_sdcard_print.plate_index = 1;
        results["start_sdcard_print_invalid_dev_id"] = number(start_sdcard_print(agent, invalid_sdcard_print, nullptr, nullptr));
    }
    if (start_send_gcode_to_sdcard) {
        Slic3r::PrintParams missing_file_name;
        missing_file_name.dev_ip = "127.0.0.1";
        missing_file_name.username = "bblp";
        missing_file_name.password = "pass";
        missing_file_name.use_ssl_for_ftp = false;
        results["start_send_gcode_missing_file_name"] = number(start_send_gcode_to_sdcard(agent, missing_file_name, nullptr, nullptr, nullptr));

        Slic3r::PrintParams nonexistent_file;
        nonexistent_file.dev_ip = "127.0.0.1";
        nonexistent_file.username = "bblp";
        nonexistent_file.password = "pass";
        nonexistent_file.filename = "/tmp/bambu-network-contract-missing-file.3mf";
        nonexistent_file.use_ssl_for_ftp = false;
        results["start_send_gcode_nonexistent_file"] = number(start_send_gcode_to_sdcard(agent, nonexistent_file, nullptr, nullptr, nullptr));
    }
    if (start_local_print) {
        Slic3r::PrintParams nonexistent_file;
        nonexistent_file.dev_id = "dev";
        nonexistent_file.dev_ip = "127.0.0.1";
        nonexistent_file.username = "bblp";
        nonexistent_file.password = "pass";
        nonexistent_file.filename = "/tmp/bambu-network-contract-missing-file.3mf";
        nonexistent_file.plate_index = 1;
        nonexistent_file.use_ssl_for_ftp = false;
        nonexistent_file.use_ssl_for_mqtt = false;
        results["start_local_print_nonexistent_file"] = number(start_local_print(agent, nonexistent_file, nullptr, nullptr));
    }
    if (get_camera_url)
        results["get_camera_url"] = number(get_camera_url(agent, "dev", [&](std::string) { camera_callbacks++; }));
    if (get_camera_url_for_golive)
        results["get_camera_url_for_golive"] = number(get_camera_url_for_golive(agent, "dev", "live", [&](std::string) { camera_callbacks++; }));
    if (refresh_connection)
        results["refresh_connection"] = number(refresh_connection(agent));
    if (start_subscribe)
        results["start_subscribe"] = number(start_subscribe(agent, "device/dev/report"));
    if (stop_subscribe)
        results["stop_subscribe"] = number(stop_subscribe(agent, "device/dev/report"));
    if (add_subscribe)
        results["add_subscribe"] = number(add_subscribe(agent, {"device/dev/report"}));
    if (del_subscribe)
        results["del_subscribe"] = number(del_subscribe(agent, {"device/dev/report"}));
    if (enable_multi_machine) {
        enable_multi_machine(agent, true);
        results["enable_multi_machine_called"] = boolean(true);
    }
    if (update_cert)
        results["update_cert"] = number(update_cert(agent));
    if (install_device_cert) {
        install_device_cert(agent, "dev", false);
        results["install_device_cert_called"] = boolean(true);
    }
    if (change_user)
        results["change_user"] = number(change_user(agent, "{}"));
    if (user_logout)
        results["user_logout"] = number(user_logout(agent, false));
    if (get_user_avatar)
        results["get_user_avatar"] = string_value(get_user_avatar(agent));
    if (ping_bind)
        results["ping_bind"] = number(ping_bind(agent, "dev"));
    if (bind_detect) {
        Slic3r::detectResult detect;
        detect.result_msg = "dirty";
        results["bind_detect"] = number(bind_detect(agent, "dev", "code", detect));
        results["bind_detect_result_msg"] = string_value(detect.result_msg);
    }
    if (report_consent)
        results["report_consent"] = number(report_consent(agent, "{}"));
    if (bind)
        results["bind"] = number(bind(agent, "dev", "code", "pin", "name", false, nullptr));
    if (unbind)
        results["unbind"] = number(unbind(agent, "dev"));
    if (get_bambulab_host)
        results["get_bambulab_host"] = string_value(get_bambulab_host(agent));
    if (get_user_selected_machine)
        results["get_user_selected_machine"] = string_value(get_user_selected_machine(agent));
    if (set_user_selected_machine)
        results["set_user_selected_machine"] = number(set_user_selected_machine(agent, "dev"));
    if (start_print) {
        Slic3r::PrintParams params;
        params.dev_id = "dev";
        results["start_print"] = number(start_print(agent, params, nullptr, nullptr, nullptr));
    }
    if (get_user_presets) {
        std::map<std::string, std::map<std::string, std::string>> presets{{"dirty", {{"dirty", "dirty"}}}};
        results["get_user_presets"] = number(get_user_presets(agent, &presets));
        results["get_user_presets_size"] = number(static_cast<int>(presets.size()));
    }
    if (request_setting_id) {
        std::map<std::string, std::string> setting;
        unsigned int http_code = 999;
        results["request_setting_id"] = string_value(request_setting_id(agent, "preset", &setting, &http_code));
        results["request_setting_id_http_code"] = unsigned_number(http_code);
    }
    if (put_setting) {
        std::map<std::string, std::string> setting;
        unsigned int http_code = 999;
        results["put_setting"] = number(put_setting(agent, "preset", "body", &setting, &http_code));
        results["put_setting_http_code"] = unsigned_number(http_code);
    }
    if (get_setting_list)
        results["get_setting_list"] = number(get_setting_list(agent, "preset", nullptr, nullptr));
    if (get_setting_list2)
        results["get_setting_list2"] = number(get_setting_list2(agent, "preset", nullptr, nullptr, nullptr));
    if (delete_setting)
        results["delete_setting"] = number(delete_setting(agent, "preset"));
    if (get_studio_info_url)
        results["get_studio_info_url"] = string_value(get_studio_info_url(agent));
    if (set_extra_http_header)
        results["set_extra_http_header"] = number(set_extra_http_header(agent, {{"x-contract", "1"}}));
    if (get_my_message) {
        unsigned int http_code = 999;
        std::string body = "dirty";
        results["get_my_message"] = number(get_my_message(agent, 0, 0, 20, &http_code, &body));
        results["get_my_message_http_code"] = unsigned_number(http_code);
        results["get_my_message_body"] = string_value(body);
    }
    if (check_user_task_report) {
        int task_id = 999;
        bool printable = true;
        results["check_user_task_report"] = number(check_user_task_report(agent, &task_id, &printable));
        results["check_user_task_report_task_id"] = number(task_id);
        results["check_user_task_report_printable"] = boolean(printable);
    }
    if (get_user_print_info) {
        unsigned int http_code = 999;
        std::string body = "dirty";
        results["get_user_print_info"] = number(get_user_print_info(agent, &http_code, &body));
        results["get_user_print_info_http_code"] = unsigned_number(http_code);
        results["get_user_print_info_body"] = string_value(body);
    }
    if (get_user_tasks) {
        Slic3r::TaskQueryParams query;
        std::string body = "dirty";
        results["get_user_tasks"] = number(get_user_tasks(agent, query, &body));
        results["get_user_tasks_body"] = string_value(body);
    }
    if (get_printer_firmware) {
        unsigned int http_code = 999;
        std::string body = "dirty";
        results["get_printer_firmware"] = number(get_printer_firmware(agent, "dev", &http_code, &body));
        results["get_printer_firmware_http_code"] = unsigned_number(http_code);
        results["get_printer_firmware_body"] = string_value(body);
    }
    if (get_task_plate_index) {
        int plate_index = 999;
        results["get_task_plate_index"] = number(get_task_plate_index(agent, "task", &plate_index));
        results["get_task_plate_index_value"] = number(plate_index);
    }
    if (get_user_info) {
        int identifier = 999;
        results["get_user_info"] = number(get_user_info(agent, &identifier));
        results["get_user_info_identifier"] = number(identifier);
    }
    if (request_bind_ticket) {
        std::string ticket = "dirty";
        results["request_bind_ticket"] = number(request_bind_ticket(agent, &ticket));
        results["request_bind_ticket_value"] = string_value(ticket);
    }
    if (get_subtask_info) {
        std::string task_json = "dirty";
        unsigned int http_code = 999;
        std::string body = "dirty";
        results["get_subtask_info"] = number(get_subtask_info(agent, "task", &task_json, &http_code, &body));
        results["get_subtask_info_task_json"] = string_value(task_json);
        results["get_subtask_info_http_code"] = unsigned_number(http_code);
        results["get_subtask_info_body"] = string_value(body);
    }
    if (get_slice_info) {
        std::string slice_json = "dirty";
        results["get_slice_info"] = number(get_slice_info(agent, "task", "subtask", 0, &slice_json));
        results["get_slice_info_json"] = string_value(slice_json);
    }
    if (query_bind_status) {
        unsigned int http_code = 999;
        std::string body = "dirty";
        results["query_bind_status"] = number(query_bind_status(agent, {"dev"}, &http_code, &body));
        results["query_bind_status_http_code"] = unsigned_number(http_code);
        results["query_bind_status_body"] = string_value(body);
    }
    if (modify_printer_name)
        results["modify_printer_name"] = number(modify_printer_name(agent, "dev", "name"));
    if (get_design_staffpick)
        results["get_design_staffpick"] = number(get_design_staffpick(agent, 0, 20, [&](std::string) { string_callbacks++; }));
    if (start_publish) {
        Slic3r::PublishParams params;
        std::string out = "dirty";
        results["start_publish"] = number(start_publish(agent, params, nullptr, nullptr, &out));
        results["start_publish_out"] = string_value(out);
    }
    if (get_model_publish_url) {
        std::string url = "dirty";
        results["get_model_publish_url"] = number(get_model_publish_url(agent, &url));
        results["get_model_publish_url_value"] = string_value(url);
    }
    if (get_subtask)
        results["get_subtask"] = number(get_subtask(agent, nullptr, nullptr));
    if (get_model_mall_home_url) {
        std::string url = "dirty";
        results["get_model_mall_home_url"] = number(get_model_mall_home_url(agent, &url));
        results["get_model_mall_home_url_value"] = string_value(url);
    }
    if (get_model_mall_detail_url) {
        std::string url = "dirty";
        results["get_model_mall_detail_url"] = number(get_model_mall_detail_url(agent, &url, "model"));
        results["get_model_mall_detail_url_value"] = string_value(url);
    }
    if (get_my_token) {
        unsigned int http_code = 999;
        std::string body = "dirty";
        results["get_my_token"] = number(get_my_token(agent, "scope", &http_code, &body));
        results["get_my_token_http_code"] = unsigned_number(http_code);
        results["get_my_token_body"] = string_value(body);
    }
    if (get_my_profile) {
        unsigned int http_code = 999;
        std::string body = "dirty";
        results["get_my_profile"] = number(get_my_profile(agent, "scope", &http_code, &body));
        results["get_my_profile_http_code"] = unsigned_number(http_code);
        results["get_my_profile_body"] = string_value(body);
    }
    if (track_enable)
        results["track_enable"] = number(track_enable(agent, true));
    if (track_remove_files)
        results["track_remove_files"] = number(track_remove_files(agent));
    if (track_event)
        results["track_event"] = number(track_event(agent, "category", "{}"));
    if (track_header)
        results["track_header"] = number(track_header(agent, "{}"));
    if (track_update_property)
        results["track_update_property"] = number(track_update_property(agent, "name", "value", "scope"));
    if (track_get_property) {
        std::string value = "dirty";
        results["track_get_property"] = number(track_get_property(agent, "name", value, "scope"));
        results["track_get_property_value"] = string_value(value);
    }
    if (put_model_mall_rating) {
        unsigned int http_code = 999;
        std::string http_error = "dirty";
        results["put_model_mall_rating"] = number(put_model_mall_rating(agent, 1, 5, "text", {}, http_code, http_error));
        results["put_model_mall_rating_http_code"] = unsigned_number(http_code);
        results["put_model_mall_rating_http_error"] = string_value(http_error);
    }
    if (get_oss_config) {
        std::string config = "dirty";
        unsigned int http_code = 999;
        std::string http_error = "dirty";
        results["get_oss_config"] = number(get_oss_config(agent, config, "scene", http_code, http_error));
        results["get_oss_config_config"] = string_value(config);
        results["get_oss_config_http_code"] = unsigned_number(http_code);
        results["get_oss_config_http_error"] = string_value(http_error);
    }
    if (put_rating_picture_oss) {
        std::string config = "dirty";
        std::string path = "dirty";
        unsigned int http_code = 999;
        std::string http_error = "dirty";
        results["put_rating_picture_oss"] = number(put_rating_picture_oss(agent, config, path, "file", 0, http_code, http_error));
        results["put_rating_picture_oss_config"] = string_value(config);
        results["put_rating_picture_oss_path"] = string_value(path);
        results["put_rating_picture_oss_http_code"] = unsigned_number(http_code);
        results["put_rating_picture_oss_http_error"] = string_value(http_error);
    }
    if (get_model_mall_rating) {
        std::string rating = "dirty";
        unsigned int http_code = 999;
        std::string http_error = "dirty";
        results["get_model_mall_rating"] = number(get_model_mall_rating(agent, 1, rating, http_code, http_error));
        results["get_model_mall_rating_value"] = string_value(rating);
        results["get_model_mall_rating_http_code"] = unsigned_number(http_code);
        results["get_model_mall_rating_http_error"] = string_value(http_error);
    }
    if (get_mw_user_preference)
        results["get_mw_user_preference"] = number(get_mw_user_preference(agent, [&](std::string) { string_callbacks++; }));
    if (get_mw_user_4ulist)
        results["get_mw_user_4ulist"] = number(get_mw_user_4ulist(agent, 0, 20, [&](std::string) { string_callbacks++; }));
    if (get_hms_snapshot)
        results["get_hms_snapshot"] = number(get_hms_snapshot(agent, "dev", "task", [&](std::string, int) { hms_callbacks++; }));
    if (ft_abi_version)
        results["ft_abi_version"] = number(ft_abi_version());
    if (ft_tunnel_create) {
        void* tunnel = nullptr;
        results["ft_tunnel_create"] = number(ft_tunnel_create("wss://example.invalid", &tunnel));
        results["ft_tunnel_created_handle"] = boolean(tunnel != nullptr);
        if (tunnel && ft_tunnel_release)
            ft_tunnel_release(tunnel);
    }
    if (ft_tunnel_retain)
        ft_tunnel_retain(nullptr);
    if (ft_tunnel_start_connect)
        results["ft_tunnel_start_connect_null"] = number(ft_tunnel_start_connect(nullptr, nullptr, nullptr));
    if (ft_tunnel_set_status_cb)
        results["ft_tunnel_set_status_cb_null"] = number(ft_tunnel_set_status_cb(nullptr, nullptr, nullptr));
    if (ft_job_create) {
        void* job = nullptr;
        results["ft_job_create"] = number(ft_job_create("{}", &job));
        results["ft_job_created_handle"] = boolean(job != nullptr);
        if (job && ft_job_release)
            ft_job_release(job);
    }
    if (ft_job_retain)
        ft_job_retain(nullptr);

    void* source_tunnel = nullptr;
    if (bambu_init)
        results["Bambu_Init"] = number(bambu_init());
    if (bambu_create)
        results["Bambu_Create"] = number(bambu_create(&source_tunnel, "wss://example.invalid"));
    if (bambu_open)
        results["Bambu_Open"] = number(bambu_open(source_tunnel));
    if (bambu_get_stream_count)
        results["Bambu_GetStreamCount"] = number(bambu_get_stream_count(source_tunnel));
    if (bambu_last_error)
        results["Bambu_GetLastErrorMsg"] = "\"" + json_escape(bambu_last_error()) + "\"";
    if (bambu_destroy && source_tunnel)
        bambu_destroy(source_tunnel);

    void* camera_tunnel = nullptr;
    if (bambu_create)
        results["Bambu_Create_valid_camera"] = number(bambu_create(&camera_tunnel, "bambu:///rtsps___bblp:12345678@192.0.2.10/streaming/live/1?proto=rtsps"));
    if (bambu_open)
        results["Bambu_Open_valid_camera"] = number(bambu_open(camera_tunnel));
    if (bambu_last_error)
        results["Bambu_GetLastErrorMsg_valid_camera"] = "\"" + json_escape(bambu_last_error()) + "\"";
    if (bambu_destroy && camera_tunnel)
        bambu_destroy(camera_tunnel);

    if (start_discovery)
        results["stop_discovery"] = boolean(start_discovery(agent, false, false));
    if (set_ssdp)
        results["clear_on_ssdp_msg_fn"] = number(set_ssdp(agent, nullptr));

    int destroy_result = -999999;
    if (destroy_agent && agent)
        destroy_result = destroy_agent(agent);

    std::cout << "{\n";
    std::cout << "  \"network_plugin\": \"" << json_escape(args.network_plugin) << "\",\n";
    std::cout << "  \"source_plugin\": \"" << json_escape(args.source_plugin) << "\",\n";
    std::cout << "  \"log_dir\": \"" << json_escape(args.log_dir) << "\",\n";
    std::cout << "  \"agent_created\": " << (agent ? "true" : "false") << ",\n";
    std::cout << "  \"missing_symbols\": ";
    write_string_array(missing);
    std::cout << ",\n";
    std::cout << "  \"results\": ";
    write_result_map(results);
    std::cout << ",\n";
    std::cout << "  \"camera_callbacks\": " << camera_callbacks << ",\n";
    std::cout << "  \"string_callbacks\": " << string_callbacks << ",\n";
    std::cout << "  \"hms_callbacks\": " << hms_callbacks << ",\n";
    std::cout << "  \"destroy_result\": " << destroy_result << "\n";
    std::cout << "}\n";

    dlclose(source);
    dlclose(network);
    return missing.empty() && agent ? 0 : 1;
}
