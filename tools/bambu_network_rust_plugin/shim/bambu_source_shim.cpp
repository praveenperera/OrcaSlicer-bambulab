#include <cstddef>
#include <cstdint>
#include <climits>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <cctype>
#include <cstdio>
#include <string>
#include <utility>
#include <vector>

#ifndef _WIN32
#include <fcntl.h>
#include <netdb.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

#include "../../../src/slic3r/GUI/Printer/BambuTunnel.h"

extern "C" std::uintptr_t brs_source_tls_connect(const char* host, const char* port, int timeout_ms);
extern "C" int brs_source_tls_send(std::uintptr_t handle, const unsigned char* data, std::uintptr_t len);
extern "C" int brs_source_tls_recv(std::uintptr_t handle, unsigned char* data, std::uintptr_t capacity, std::uintptr_t* bytes_read);
extern "C" void brs_source_tls_close(std::uintptr_t handle);

namespace {

thread_local std::string last_error = "Unknown error!";

enum class SourceKind {
    Unknown,
    LocalFileTunnel,
    LocalRtspCamera,
};

struct DummyTunnel {
    bool open{false};
    bool valid_url{false};
    bool stream_started{false};
    std::uint64_t samples_read{0};
    SourceKind kind{SourceKind::Unknown};
    std::string url;
    std::string protocol;
    std::string host;
    std::string port;
    std::string username;
    std::string password;
    std::string path;
    std::string rtsp_url;
    std::string rtsp_session;
    std::string rtsp_play_url;
    int video_width{0};
    int video_height{0};
    int video_frame_rate{0};
    std::vector<unsigned char> format_buffer;
    std::vector<unsigned char> read_buffer;
    std::vector<unsigned char> sample_buffer;
    std::uint32_t control_sequence{1};
    std::uintptr_t tls_handle{0};
#ifndef _WIN32
    int socket_fd{-1};
#endif
};

bool starts_with(const std::string& value, const char* prefix)
{
    return value.rfind(prefix, 0) == 0;
}

bool synthetic_stream_enabled()
{
    const char* value = std::getenv("BAMBU_SOURCE_ENABLE_SYNTHETIC_STREAM");
    return value && std::strcmp(value, "1") == 0;
}

bool local_tls_disabled()
{
    const char* value = std::getenv("BAMBU_SOURCE_DISABLE_LOCAL_TLS");
    return value && std::strcmp(value, "1") == 0;
}

bool is_synthetic_stream(const DummyTunnel& tunnel)
{
    return synthetic_stream_enabled() && tunnel.kind == SourceKind::LocalRtspCamera && tunnel.host == "synthetic.local";
}

std::string query_value(const std::string& query, const char* key)
{
    const std::string prefix = std::string(key) + "=";
    std::size_t offset = 0;
    while (offset <= query.size()) {
        const auto next = query.find('&', offset);
        const std::string part = query.substr(offset, next == std::string::npos ? std::string::npos : next - offset);
        if (starts_with(part, prefix.c_str()))
            return part.substr(prefix.size());
        if (next == std::string::npos)
            break;
        offset = next + 1;
    }
    return {};
}

void parse_url(DummyTunnel& tunnel, const char* path)
{
    tunnel.url = path ? path : "";
    tunnel.valid_url = false;
    tunnel.kind = SourceKind::Unknown;
    tunnel.protocol.clear();
    tunnel.host.clear();
    tunnel.port.clear();
    tunnel.username.clear();
    tunnel.password.clear();
    tunnel.path.clear();
    tunnel.rtsp_url.clear();
    tunnel.rtsp_session.clear();
    tunnel.rtsp_play_url.clear();
    tunnel.video_width = 0;
    tunnel.video_height = 0;
    tunnel.video_frame_rate = 0;
    tunnel.format_buffer.clear();
    tunnel.read_buffer.clear();
    tunnel.sample_buffer.clear();

    if (starts_with(tunnel.url, "bambu:///local/")) {
        tunnel.kind = SourceKind::LocalFileTunnel;
        tunnel.protocol = "local";
        const std::string rest = tunnel.url.substr(std::strlen("bambu:///local/"));
        const auto query_start = rest.find('?');
        tunnel.host = rest.substr(0, query_start);
        if (!tunnel.host.empty() && tunnel.host.back() == '.')
            tunnel.host.pop_back();
        if (query_start != std::string::npos) {
            const std::string query = rest.substr(query_start + 1);
            tunnel.port = query_value(query, "port");
            tunnel.username = query_value(query, "user");
            tunnel.password = query_value(query, "passwd");
        }
        tunnel.valid_url = !tunnel.host.empty();
        return;
    }

    if (starts_with(tunnel.url, "bambu:///rtsps___") || starts_with(tunnel.url, "bambu:///rtsp___")) {
        tunnel.kind = SourceKind::LocalRtspCamera;
        tunnel.protocol = starts_with(tunnel.url, "bambu:///rtsps___") ? "rtsps" : "rtsp";
        const auto prefix_size = tunnel.protocol == "rtsps"
            ? std::strlen("bambu:///rtsps___")
            : std::strlen("bambu:///rtsp___");
        const std::string rest = tunnel.url.substr(prefix_size);
        tunnel.rtsp_url = tunnel.protocol + "://" + rest;
        const auto at = rest.find('@');
        if (at == std::string::npos)
            return;
        const auto host_start = at + 1;
        const auto host_end = rest.find('/', host_start);
        const std::string authority = rest.substr(host_start, host_end == std::string::npos ? std::string::npos : host_end - host_start);
        const auto port_start = authority.rfind(':');
        if (port_start == std::string::npos) {
            tunnel.host = authority;
            tunnel.port = tunnel.protocol == "rtsps" ? "322" : "554";
        } else {
            tunnel.host = authority.substr(0, port_start);
            tunnel.port = authority.substr(port_start + 1);
        }
        tunnel.path = host_end == std::string::npos ? "/" : rest.substr(host_end);
        tunnel.valid_url = !tunnel.host.empty();
        return;
    }
}

DummyTunnel* from_public_tunnel(Bambu_Tunnel tunnel)
{
    return static_cast<DummyTunnel*>(tunnel);
}

#ifndef _WIN32
void close_tls(DummyTunnel& tunnel)
{
    if (tunnel.tls_handle != 0) {
        brs_source_tls_close(tunnel.tls_handle);
        tunnel.tls_handle = 0;
    }
}

void close_socket(DummyTunnel& tunnel)
{
    if (tunnel.socket_fd >= 0) {
        close(tunnel.socket_fd);
        tunnel.socket_fd = -1;
    }
}

bool set_nonblocking(int fd)
{
    const int flags = fcntl(fd, F_GETFL, 0);
    return flags >= 0 && fcntl(fd, F_SETFL, flags | O_NONBLOCK) == 0;
}

int connect_socket(const std::string& host, const std::string& port, int timeout_ms = 2000)
{
    if (host.empty() || port.empty())
        return -1;

    addrinfo hints {};
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    addrinfo* addresses = nullptr;
    if (getaddrinfo(host.c_str(), port.c_str(), &hints, &addresses) != 0)
        return -1;

    int connected = -1;
    for (addrinfo* address = addresses; address && connected < 0; address = address->ai_next) {
        const int fd = socket(address->ai_family, address->ai_socktype, address->ai_protocol);
        if (fd < 0)
            continue;

#ifdef SO_NOSIGPIPE
        int no_sigpipe = 1;
        setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &no_sigpipe, sizeof(no_sigpipe));
#endif

        if (!set_nonblocking(fd)) {
            close(fd);
            continue;
        }

        const int result = connect(fd, address->ai_addr, address->ai_addrlen);
        if (result == 0) {
            connected = fd;
            break;
        }
        if (errno == EINPROGRESS) {
            fd_set write_set;
            FD_ZERO(&write_set);
            FD_SET(fd, &write_set);
            timeval timeout {};
            timeout.tv_sec = timeout_ms / 1000;
            timeout.tv_usec = (timeout_ms % 1000) * 1000;
            const int ready = select(fd + 1, nullptr, &write_set, nullptr, &timeout);
            if (ready > 0 && FD_ISSET(fd, &write_set)) {
                int socket_error = 0;
                socklen_t socket_error_size = sizeof(socket_error);
                if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &socket_error, &socket_error_size) == 0 && socket_error == 0) {
                    connected = fd;
                    break;
                }
            }
        }

        close(fd);
    }

    freeaddrinfo(addresses);
    return connected;
}

int send_all(int fd, const char* data, int len)
{
    if (fd < 0 || !data || len < 0)
        return -1;

    int sent = 0;
    while (sent < len) {
#ifdef MSG_NOSIGNAL
        constexpr int send_flags = MSG_NOSIGNAL;
#else
        constexpr int send_flags = 0;
#endif
        const ssize_t result = send(fd, data + sent, static_cast<std::size_t>(len - sent), send_flags);
        if (result > 0) {
            sent += static_cast<int>(result);
            continue;
        }
        if (result < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            fd_set write_set;
            FD_ZERO(&write_set);
            FD_SET(fd, &write_set);
            timeval timeout {};
            timeout.tv_sec = 2;
            const int ready = select(fd + 1, nullptr, &write_set, nullptr, &timeout);
            if (ready > 0)
                continue;
        }
        return -1;
    }
    return Bambu_success;
}

int recv_nonblocking(int fd, unsigned char* data, int capacity, int& bytes_read)
{
    bytes_read = 0;
    if (fd < 0 || !data || capacity <= 0)
        return -1;

    const ssize_t result = recv(fd, data, static_cast<std::size_t>(capacity), 0);
    if (result > 0) {
        bytes_read = static_cast<int>(result);
        return Bambu_success;
    }
    if (result == 0)
        return Bambu_stream_end;
    if (errno == EAGAIN || errno == EWOULDBLOCK)
        return Bambu_would_block;
    return -1;
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

std::string trim(std::string value)
{
    const auto begin = std::find_if_not(value.begin(), value.end(), [](unsigned char ch) { return std::isspace(ch); });
    const auto end = std::find_if_not(value.rbegin(), value.rend(), [](unsigned char ch) { return std::isspace(ch); }).base();
    if (begin >= end)
        return {};
    return std::string(begin, end);
}

std::string header_value(const std::string& response, const char* name)
{
    const std::string prefix = std::string(name) + ":";
    std::size_t line_start = 0;
    while (line_start < response.size()) {
        const auto line_end = response.find("\r\n", line_start);
        const std::string line = response.substr(line_start, line_end == std::string::npos ? std::string::npos : line_end - line_start);
        if (line.size() >= prefix.size()
            && std::equal(prefix.begin(), prefix.end(), line.begin(), [](char lhs, char rhs) {
                   return std::tolower(static_cast<unsigned char>(lhs)) == std::tolower(static_cast<unsigned char>(rhs));
               }))
            return trim(line.substr(prefix.size()));
        if (line_end == std::string::npos)
            break;
        line_start = line_end + 2;
    }
    return {};
}

int content_length(const std::string& response)
{
    const std::string value = header_value(response, "Content-Length");
    if (value.empty())
        return 0;
    return std::max(0, std::atoi(value.c_str()));
}

int read_rtsp_response(DummyTunnel& tunnel, std::string& response)
{
    response.clear();
    int expected_size = -1;
    for (int attempt = 0; attempt < 200; ++attempt) {
        if (!wait_readable(tunnel.socket_fd, 25))
            continue;
        unsigned char buffer[4096] {};
        int bytes_read = 0;
        const int result = recv_nonblocking(tunnel.socket_fd, buffer, static_cast<int>(sizeof(buffer)), bytes_read);
        if (result != Bambu_success)
            return result;
        response.append(reinterpret_cast<const char*>(buffer), static_cast<std::size_t>(bytes_read));
        const auto header_end = response.find("\r\n\r\n");
        if (header_end != std::string::npos && expected_size < 0)
            expected_size = static_cast<int>(header_end + 4) + content_length(response.substr(0, header_end + 4));
        if (expected_size >= 0 && static_cast<int>(response.size()) >= expected_size)
            return Bambu_success;
    }
    return Bambu_would_block;
}

bool rtsp_ok(const std::string& response)
{
    return starts_with(response, "RTSP/1.0 200");
}

int send_rtsp_request(DummyTunnel& tunnel, const std::string& request, std::string& response)
{
    const int sent = send_all(tunnel.socket_fd, request.c_str(), static_cast<int>(request.size()));
    if (sent != Bambu_success)
        return sent;
    const int read = read_rtsp_response(tunnel, response);
    if (read != Bambu_success)
        return read;
    return rtsp_ok(response) ? Bambu_success : -1;
}

std::string sdp_body(const std::string& response)
{
    const auto header_end = response.find("\r\n\r\n");
    if (header_end == std::string::npos)
        return {};
    return response.substr(header_end + 4);
}

std::vector<std::string> split_lines(const std::string& value)
{
    std::vector<std::string> lines;
    std::size_t offset = 0;
    while (offset <= value.size()) {
        auto next = value.find('\n', offset);
        std::string line = value.substr(offset, next == std::string::npos ? std::string::npos : next - offset);
        if (!line.empty() && line.back() == '\r')
            line.pop_back();
        lines.push_back(line);
        if (next == std::string::npos)
            break;
        offset = next + 1;
    }
    return lines;
}

std::string join_rtsp_url(const std::string& base, const std::string& control)
{
    if (starts_with(control, "rtsp://") || starts_with(control, "rtsps://"))
        return control;
    if (base.empty())
        return control;
    if (!base.empty() && base.back() == '/')
        return base + control;
    return base + "/" + control;
}

std::string parse_rtsp_session(const std::string& response)
{
    std::string session = header_value(response, "Session");
    const auto params = session.find(';');
    if (params != std::string::npos)
        session = session.substr(0, params);
    return trim(session);
}

void parse_sdp(DummyTunnel& tunnel, const std::string& describe_response, std::string& setup_url)
{
    const std::string base = header_value(describe_response, "Content-Base").empty()
        ? tunnel.rtsp_url
        : header_value(describe_response, "Content-Base");
    tunnel.rtsp_play_url = base;
    std::string media_control;
    for (const std::string& line : split_lines(sdp_body(describe_response))) {
        if (starts_with(line, "a=framesize:")) {
            int payload = 0;
            int width = 0;
            int height = 0;
            if (std::sscanf(line.c_str(), "a=framesize:%d %d-%d", &payload, &width, &height) == 3) {
                tunnel.video_width = width;
                tunnel.video_height = height;
            }
        } else if (starts_with(line, "a=framerate:")) {
            tunnel.video_frame_rate = std::max(1, std::atoi(line.substr(std::strlen("a=framerate:")).c_str()));
        } else if (starts_with(line, "a=fmtp:")) {
            tunnel.format_buffer.assign(line.begin(), line.end());
        } else if (starts_with(line, "a=control:")) {
            const std::string control = line.substr(std::strlen("a=control:"));
            if (control != "*")
                media_control = control;
        }
    }
    if (tunnel.video_frame_rate == 0)
        tunnel.video_frame_rate = 5;
    if (tunnel.format_buffer.empty())
        tunnel.format_buffer = {'H', '2', '6', '4'};
    setup_url = media_control.empty() ? tunnel.rtsp_url : join_rtsp_url(base, media_control);
}

int start_rtsp_stream(DummyTunnel& tunnel)
{
    close_socket(tunnel);
    tunnel.socket_fd = connect_socket(tunnel.host, tunnel.port, 100);
    if (tunnel.socket_fd < 0)
        return 2;

    std::string response;
    int cseq = 2;
    const std::string user_agent = "User-Agent: BambuLabStudio_RTSP_Client\r\n";
    std::string request = "OPTIONS " + tunnel.rtsp_url + " RTSP/1.0\r\nCSeq: " + std::to_string(cseq++) + "\r\n" + user_agent + "\r\n";
    if (send_rtsp_request(tunnel, request, response) != Bambu_success)
        return 2;
    request = "DESCRIBE " + tunnel.rtsp_url + " RTSP/1.0\r\nCSeq: " + std::to_string(cseq++) + "\r\n" + user_agent + "Accept: application/sdp\r\n\r\n";
    if (send_rtsp_request(tunnel, request, response) != Bambu_success)
        return 2;
    std::string setup_url;
    parse_sdp(tunnel, response, setup_url);
    request = "SETUP " + setup_url + " RTSP/1.0\r\nCSeq: " + std::to_string(cseq++) + "\r\n" + user_agent
        + "Transport: RTP/AVP/TCP;unicast;interleaved=0-1\r\n\r\n";
    if (send_rtsp_request(tunnel, request, response) != Bambu_success)
        return 2;
    tunnel.rtsp_session = parse_rtsp_session(response);
    if (tunnel.rtsp_session.empty())
        return 2;
    request = "PLAY " + tunnel.rtsp_play_url + " RTSP/1.0\r\nCSeq: " + std::to_string(cseq++) + "\r\n" + user_agent
        + "Session: " + tunnel.rtsp_session + "\r\nRange: npt=0.000-\r\n\r\n";
    if (send_rtsp_request(tunnel, request, response) != Bambu_success)
        return 2;
    tunnel.stream_started = true;
    return Bambu_success;
}

int read_rtsp_sample(DummyTunnel& tunnel, Bambu_Sample* sample)
{
    for (int attempt = 0; attempt < 4; ++attempt) {
        while (!tunnel.read_buffer.empty() && tunnel.read_buffer.front() != '$')
            tunnel.read_buffer.erase(tunnel.read_buffer.begin());
        if (tunnel.read_buffer.size() >= 4) {
            const std::size_t packet_size = (static_cast<std::size_t>(tunnel.read_buffer[2]) << 8) | tunnel.read_buffer[3];
            if (tunnel.read_buffer.size() >= packet_size + 4) {
                const unsigned char* packet = tunnel.read_buffer.data() + 4;
                std::size_t header_size = 12;
                if (packet_size >= 12)
                    header_size += (packet[0] & 0x0f) * 4;
                if (packet_size <= header_size) {
                    tunnel.read_buffer.erase(tunnel.read_buffer.begin(), tunnel.read_buffer.begin() + static_cast<std::ptrdiff_t>(packet_size + 4));
                    continue;
                }
                tunnel.sample_buffer.assign(packet + header_size, packet + packet_size);
                tunnel.read_buffer.erase(tunnel.read_buffer.begin(), tunnel.read_buffer.begin() + static_cast<std::ptrdiff_t>(packet_size + 4));
                sample->itrack = 0;
                sample->size = static_cast<int>(tunnel.sample_buffer.size());
                sample->flags = f_sync;
                sample->buffer = tunnel.sample_buffer.data();
                sample->decode_time = tunnel.samples_read++;
                return Bambu_success;
            }
        }

        if (!wait_readable(tunnel.socket_fd, 25))
            continue;
        unsigned char buffer[8192] {};
        int bytes_read = 0;
        const int result = recv_nonblocking(tunnel.socket_fd, buffer, static_cast<int>(sizeof(buffer)), bytes_read);
        if (result != Bambu_success)
            return result;
        tunnel.read_buffer.insert(tunnel.read_buffer.end(), buffer, buffer + bytes_read);
    }
    return Bambu_would_block;
}

void append_u32_le(std::vector<unsigned char>& out, std::uint32_t value)
{
    out.push_back(static_cast<unsigned char>(value & 0xff));
    out.push_back(static_cast<unsigned char>((value >> 8) & 0xff));
    out.push_back(static_cast<unsigned char>((value >> 16) & 0xff));
    out.push_back(static_cast<unsigned char>((value >> 24) & 0xff));
}

void append_fixed_string(std::vector<unsigned char>& out, const std::string& value, std::size_t size)
{
    for (std::size_t index = 0; index < size; ++index)
        out.push_back(index < value.size() ? static_cast<unsigned char>(value[index]) : 0);
}

std::vector<unsigned char> local_control_header(DummyTunnel& tunnel, std::size_t payload_size, unsigned char channel)
{
    std::vector<unsigned char> header;
    append_u32_le(header, static_cast<std::uint32_t>(payload_size));
    header.push_back(0x3f);
    header.push_back(0x01);
    header.push_back(channel);
    header.push_back(0x01);
    append_u32_le(header, tunnel.control_sequence++);
    append_u32_le(header, 0);
    return header;
}

std::vector<unsigned char> local_control_login_credentials(const DummyTunnel& tunnel)
{
    std::vector<unsigned char> credentials;
    append_fixed_string(credentials, tunnel.username.empty() ? "bblp" : tunnel.username, 8);
    append_fixed_string(credentials, tunnel.password, 8);
    return credentials;
}

int start_local_control_tls(DummyTunnel& tunnel)
{
    tunnel.tls_handle = brs_source_tls_connect(tunnel.host.c_str(), tunnel.port.c_str(), 300);
    if (tunnel.tls_handle == 0)
        return -1;

    tunnel.control_sequence = 1;
    const auto login = local_control_header(tunnel, 16, 0x01);
    const auto credentials = local_control_login_credentials(tunnel);
    if (brs_source_tls_send(tunnel.tls_handle, login.data(), login.size()) != Bambu_success
        || brs_source_tls_send(tunnel.tls_handle, credentials.data(), credentials.size()) != Bambu_success) {
        close_tls(tunnel);
        return -1;
    }
    return Bambu_success;
}

int send_local_control_tls(DummyTunnel& tunnel, int ctrl_type, const char* data, int len)
{
    std::string payload = "{\"mtype\":" + std::to_string(ctrl_type) + ",";
    if (data && len > 1)
        payload.append(data + 1, data + len);
    const auto header = local_control_header(tunnel, payload.size(), 0x02);
    if (brs_source_tls_send(tunnel.tls_handle, header.data(), header.size()) != Bambu_success)
        return -1;
    return brs_source_tls_send(
        tunnel.tls_handle,
        reinterpret_cast<const unsigned char*>(payload.data()),
        payload.size());
}

int read_local_control_tls(DummyTunnel& tunnel, std::vector<unsigned char>& payload)
{
    payload.clear();
    for (int attempt = 0; attempt < 2; ++attempt) {
        if (tunnel.read_buffer.size() >= 16) {
            const std::size_t payload_size = static_cast<std::size_t>(tunnel.read_buffer[0])
                | (static_cast<std::size_t>(tunnel.read_buffer[1]) << 8)
                | (static_cast<std::size_t>(tunnel.read_buffer[2]) << 16)
                | (static_cast<std::size_t>(tunnel.read_buffer[3]) << 24);
            if (payload_size > 1024 * 1024) {
                tunnel.read_buffer.clear();
                return -1;
            }
            if (tunnel.read_buffer.size() >= payload_size + 16) {
                payload.assign(tunnel.read_buffer.begin() + 16, tunnel.read_buffer.begin() + static_cast<std::ptrdiff_t>(16 + payload_size));
                tunnel.read_buffer.erase(tunnel.read_buffer.begin(), tunnel.read_buffer.begin() + static_cast<std::ptrdiff_t>(16 + payload_size));
                return Bambu_success;
            }
        }

        unsigned char buffer[8192] {};
        std::uintptr_t bytes_read = 0;
        const int result = brs_source_tls_recv(tunnel.tls_handle, buffer, sizeof(buffer), &bytes_read);
        if (result == Bambu_success) {
            tunnel.read_buffer.insert(tunnel.read_buffer.end(), buffer, buffer + bytes_read);
            continue;
        }
        return result;
    }
    return Bambu_would_block;
}
#endif

const unsigned char kSyntheticJpeg[] = {
    0xff, 0xd8, 0xff, 0xdb, 0x00, 0x43, 0x00, 0x08, 0x06, 0x06, 0x07, 0x06,
    0x05, 0x08, 0x07, 0x07, 0x07, 0x09, 0x09, 0x08, 0x0a, 0x0c, 0x14, 0x0d,
    0x0c, 0x0b, 0x0b, 0x0c, 0x19, 0x12, 0x13, 0x0f, 0x14, 0x1d, 0x1a, 0x1f,
    0x1e, 0x1d, 0x1a, 0x1c, 0x1c, 0x20, 0x24, 0x2e, 0x27, 0x20, 0x22, 0x2c,
    0x23, 0x1c, 0x1c, 0x28, 0x37, 0x29, 0x2c, 0x30, 0x31, 0x34, 0x34, 0x34,
    0x1f, 0x27, 0x39, 0x3d, 0x38, 0x32, 0x3c, 0x2e, 0x33, 0x34, 0x32, 0xff,
    0xc0, 0x00, 0x0b, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01, 0x01, 0x11, 0x00,
    0xff, 0xc4, 0x00, 0x14, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07, 0xff, 0xc4,
    0x00, 0x14, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xff, 0xda, 0x00, 0x08,
    0x01, 0x01, 0x00, 0x00, 0x3f, 0x00, 0x37, 0xff, 0xd9,
};

const unsigned char kSyntheticFormat[] = {'M', 'J', 'P', 'G'};

}

extern "C" int Bambu_Init()
{
    return 0;
}

extern "C" void Bambu_Deinit() {}

extern "C" const char* Bambu_GetLastErrorMsg()
{
    return last_error.c_str();
}

extern "C" int Bambu_Create(Bambu_Tunnel* out, const char* path)
{
    if (!out)
        return -1;
    auto* tunnel = new DummyTunnel();
    parse_url(*tunnel, path);
    if (!tunnel->valid_url) {
        delete tunnel;
        *out = nullptr;
        return -1;
    }
    *out = static_cast<Bambu_Tunnel>(tunnel);
    return 0;
}

extern "C" int Bambu_Open(Bambu_Tunnel tunnel)
{
    auto* source = from_public_tunnel(tunnel);
    if (!source)
        return -1;
#ifndef _WIN32
    if (source->kind == SourceKind::LocalFileTunnel) {
        close_socket(*source);
        close_tls(*source);
        if (!local_tls_disabled() && start_local_control_tls(*source) == Bambu_success) {
            source->open = true;
            return Bambu_success;
        }
        source->socket_fd = connect_socket(source->host, source->port, 300);
        source->open = source->socket_fd >= 0;
        return source->open ? Bambu_success : -3001;
    }
#else
    if (source->kind == SourceKind::LocalFileTunnel)
        return -3001;
#endif
    source->open = true;
    return 0;
}

extern "C" int Bambu_StartStream(Bambu_Tunnel tunnel, bool)
{
    auto* source = from_public_tunnel(tunnel);
    if (source && source->open && source->kind == SourceKind::LocalFileTunnel) {
        source->stream_started = true;
        return Bambu_success;
    }
    if (source && source->open && is_synthetic_stream(*source)) {
        source->stream_started = true;
        return Bambu_success;
    }
#ifndef _WIN32
    if (source && source->open && source->kind == SourceKind::LocalRtspCamera && source->protocol == "rtsp")
        return start_rtsp_stream(*source);
#endif
    return 2;
}

extern "C" int Bambu_StartStreamEx(Bambu_Tunnel tunnel, int)
{
    auto* source = from_public_tunnel(tunnel);
    if (source && source->open && source->kind == SourceKind::LocalFileTunnel) {
        source->stream_started = true;
        return Bambu_success;
    }
    if (source && source->open && is_synthetic_stream(*source)) {
        source->stream_started = true;
        return Bambu_success;
    }
#ifndef _WIN32
    if (source && source->open && source->kind == SourceKind::LocalRtspCamera && source->protocol == "rtsp")
        return start_rtsp_stream(*source);
#endif
    return 2;
}

extern "C" int Bambu_GetStreamCount(Bambu_Tunnel tunnel)
{
    auto* source = from_public_tunnel(tunnel);
    if (!source)
        return -1;
    return source->kind == SourceKind::LocalRtspCamera ? 1 : -1;
}

extern "C" int Bambu_GetStreamInfo(Bambu_Tunnel tunnel, int index, Bambu_StreamInfo* info)
{
    auto* source = from_public_tunnel(tunnel);
    if (index == 0 && info && source && source->stream_started && is_synthetic_stream(*source)) {
        std::memset(info, 0, sizeof(*info));
        info->type = VIDE;
        info->sub_type = MJPG;
        info->format.video.width = 1;
        info->format.video.height = 1;
        info->format.video.frame_rate = 1;
        info->format_type = video_jpeg;
        info->format_size = static_cast<int>(sizeof(kSyntheticFormat));
        info->max_frame_size = static_cast<int>(sizeof(kSyntheticJpeg));
        info->format_buffer = kSyntheticFormat;
        return Bambu_success;
    }
    if (index == 0 && info && source && source->stream_started && source->kind == SourceKind::LocalRtspCamera) {
        std::memset(info, 0, sizeof(*info));
        info->type = VIDE;
        info->sub_type = AVC1;
        info->format.video.width = source->video_width;
        info->format.video.height = source->video_height;
        info->format.video.frame_rate = source->video_frame_rate;
        info->format_type = video_avc_byte_stream;
        info->format_size = static_cast<int>(source->format_buffer.size());
        info->max_frame_size = 0;
        info->format_buffer = source->format_buffer.empty() ? nullptr : source->format_buffer.data();
        return Bambu_success;
    }
    return -1;
}

extern "C" unsigned long Bambu_GetDuration(Bambu_Tunnel)
{
    return ULONG_MAX;
}

extern "C" int Bambu_Seek(Bambu_Tunnel, unsigned long)
{
    return -1;
}

extern "C" int Bambu_SendMessage(Bambu_Tunnel tunnel, int ctrl_type, const char* data, int len)
{
#ifndef _WIN32
    auto* source = from_public_tunnel(tunnel);
    if (source && source->open && source->kind == SourceKind::LocalFileTunnel && source->tls_handle != 0)
        return send_local_control_tls(*source, ctrl_type, data, len);
    if (source && source->open && source->kind == SourceKind::LocalFileTunnel)
        return send_all(source->socket_fd, data, len);
#else
    (void) tunnel;
    (void) ctrl_type;
    (void) data;
    (void) len;
#endif
    return -1;
}

extern "C" int Bambu_RecvMessage(Bambu_Tunnel tunnel, int* type, char* data, int* size)
{
#ifndef _WIN32
    auto* source = from_public_tunnel(tunnel);
    if (source && source->open && source->kind == SourceKind::LocalFileTunnel && source->tls_handle != 0 && data && size) {
        std::vector<unsigned char> payload;
        const int result = read_local_control_tls(*source, payload);
        if (result == Bambu_success) {
            const int bytes_to_copy = std::min(*size, static_cast<int>(payload.size()));
            std::memcpy(data, payload.data(), static_cast<std::size_t>(bytes_to_copy));
            if (type)
                *type = 0;
            *size = bytes_to_copy;
        }
        return result;
    }
    if (source && source->open && source->kind == SourceKind::LocalFileTunnel && data && size) {
        int bytes_read = 0;
        const int result = recv_nonblocking(source->socket_fd, reinterpret_cast<unsigned char*>(data), *size, bytes_read);
        if (result == Bambu_success) {
            if (type)
                *type = 0;
            *size = bytes_read;
        }
        return result;
    }
#else
    (void) tunnel;
    (void) type;
    (void) data;
    (void) size;
#endif
    return -1;
}

extern "C" int Bambu_ReadSample(Bambu_Tunnel tunnel, Bambu_Sample* sample)
{
    auto* source = from_public_tunnel(tunnel);
#ifndef _WIN32
    if (sample && source && source->stream_started && source->kind == SourceKind::LocalFileTunnel && source->tls_handle != 0) {
        const int result = read_local_control_tls(*source, source->sample_buffer);
        if (result != Bambu_success)
            return result;
        sample->itrack = 0;
        sample->size = static_cast<int>(source->sample_buffer.size());
        sample->flags = f_sync;
        sample->buffer = source->sample_buffer.data();
        sample->decode_time = source->samples_read++;
        return Bambu_success;
    }
    if (sample && source && source->stream_started && source->kind == SourceKind::LocalFileTunnel) {
        source->read_buffer.assign(64 * 1024, 0);
        int bytes_read = 0;
        const int result = recv_nonblocking(
            source->socket_fd,
            source->read_buffer.data(),
            static_cast<int>(source->read_buffer.size()),
            bytes_read);
        if (result != Bambu_success)
            return result;
        source->read_buffer.resize(static_cast<std::size_t>(bytes_read));
        sample->itrack = 0;
        sample->size = bytes_read;
        sample->flags = f_sync;
        sample->buffer = source->read_buffer.data();
        sample->decode_time = source->samples_read++;
        return Bambu_success;
    }
    if (sample && source && source->stream_started && source->kind == SourceKind::LocalRtspCamera && !is_synthetic_stream(*source))
        return read_rtsp_sample(*source, sample);
#endif
    if (sample && source && source->stream_started && is_synthetic_stream(*source)) {
        sample->itrack = 0;
        sample->size = static_cast<int>(sizeof(kSyntheticJpeg));
        sample->flags = f_sync;
        sample->buffer = kSyntheticJpeg;
        sample->decode_time = source->samples_read++;
        return Bambu_success;
    }
    return 2;
}

extern "C" void Bambu_Close(Bambu_Tunnel tunnel)
{
    auto* source = from_public_tunnel(tunnel);
    if (source) {
#ifndef _WIN32
        close_tls(*source);
        close_socket(*source);
#endif
        source->open = false;
        source->stream_started = false;
    }
}

extern "C" void Bambu_Destroy(Bambu_Tunnel tunnel)
{
    auto* source = from_public_tunnel(tunnel);
    if (source) {
#ifndef _WIN32
        close_tls(*source);
        close_socket(*source);
#endif
        delete source;
    }
}

extern "C" void Bambu_SetLogger(Bambu_Tunnel, Logger, void*) {}

extern "C" void Bambu_FreeLogMsg(tchar const*) {}
