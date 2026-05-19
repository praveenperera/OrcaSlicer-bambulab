#pragma once

#include <functional>
#include <map>
#include <string>
#include <vector>

namespace Slic3r {

constexpr int BAMBU_NETWORK_ERR_INVALID_HANDLE = -1;
constexpr int BAMBU_NETWORK_ERR_CONNECT_FAILED = -2;

using OnUserLoginFn = std::function<void(int online_login, bool login)>;
using OnPrinterConnectedFn = std::function<void(std::string topic_str)>;
using OnLocalConnectedFn = std::function<void(int status, std::string dev_id, std::string msg)>;
using OnServerConnectedFn = std::function<void(int return_code, int reason_code)>;
using OnMessageFn = std::function<void(std::string dev_id, std::string msg)>;
using OnHttpErrorFn = std::function<void(unsigned http_code, std::string http_body)>;
using GetCountryCodeFn = std::function<std::string()>;
using GetSubscribeFailureFn = std::function<void(std::string topic)>;
using OnUpdateStatusFn = std::function<void(int status, int code, std::string msg)>;
using WasCancelledFn = std::function<bool()>;
using OnWaitFn = std::function<bool(int status, std::string job_info)>;
using OnMsgArrivedFn = std::function<void(std::string dev_info_json_str)>;
using QueueOnMainFn = std::function<void(std::function<void()>)>;
using ProgressFn = std::function<void(int progress)>;
using LoginFn = std::function<void(int retcode, std::string info)>;
using ResultFn = std::function<void(int result, std::string info)>;
using CancelFn = std::function<bool()>;
using CheckFn = std::function<bool(std::map<std::string, std::string> info)>;
using OnServerErrFn = std::function<void(std::string url, int status)>;

struct detectResult {
    std::string result_msg;
    std::string command;
    std::string dev_id;
    std::string model_id;
    std::string dev_name;
    std::string version;
    std::string bind_state;
    std::string connect_type;
};

struct PrintParams {
    std::string dev_id;
    std::string task_name;
    std::string project_name;
    std::string preset_name;
    std::string filename;
    std::string config_filename;
    int plate_index;
    std::string ftp_folder;
    std::string ftp_file;
    std::string ftp_file_md5;
    std::string nozzle_mapping;
    std::string ams_mapping;
    std::string ams_mapping2;
    std::string ams_mapping_info;
    std::string nozzles_info;
    std::string connection_type;
    std::string comments;
    int origin_profile_id = 0;
    int stl_design_id = 0;
    std::string origin_model_id;
    std::string print_type;
    std::string dst_file;
    std::string dev_name;
    std::string dev_ip;
    bool use_ssl_for_ftp;
    bool use_ssl_for_mqtt;
    std::string username;
    std::string password;
    bool task_bed_leveling;
    bool task_flow_cali;
    bool task_vibration_cali;
    bool task_layer_inspect;
    bool task_record_timelapse;
    bool task_use_ams;
    std::string task_bed_type;
    std::string extra_options;
    int auto_bed_leveling{0};
    int auto_flow_cali{0};
    int auto_offset_cali{0};
    int extruder_cali_manual_mode{-1};
    bool task_ext_change_assist;
    bool try_emmc_print;
};

struct TaskQueryParams {
    std::string dev_id;
    int status = 0;
    int offset = 0;
    int limit = 20;
};

struct PublishParams {
    std::string project_name;
    std::string project_3mf_file;
    std::string preset_name;
    std::string project_model_id;
    std::string design_id;
    std::string config_filename;
};

class BBLModelTask;
using OnGetSubTaskFn = std::function<void(BBLModelTask* subtask)>;

}

namespace BBL = Slic3r;
