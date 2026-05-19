#include <dlfcn.h>

#include <algorithm>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct Args {
    std::string plugin_path;
    std::string symbols_path;
    bool json{false};
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

std::string trim(std::string value)
{
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos)
        return {};
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

bool parse_args(int argc, char** argv, Args& args)
{
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--plugin" && i + 1 < argc) {
            args.plugin_path = argv[++i];
        } else if (arg == "--symbols" && i + 1 < argc) {
            args.symbols_path = argv[++i];
        } else if (arg == "--json") {
            args.json = true;
        } else {
            return false;
        }
    }
    return !args.plugin_path.empty() && !args.symbols_path.empty();
}

std::vector<std::string> load_symbols(const std::string& path)
{
    std::ifstream in(path);
    if (!in)
        throw std::runtime_error("failed to open symbols file: " + path);

    std::vector<std::string> symbols;
    std::string line;
    while (std::getline(in, line)) {
        line = trim(line);
        if (line.empty() || line.front() == '#')
            continue;
        symbols.push_back(line);
    }

    std::sort(symbols.begin(), symbols.end());
    symbols.erase(std::unique(symbols.begin(), symbols.end()), symbols.end());
    return symbols;
}

void write_json_report(const Args& args, const std::vector<std::string>& present, const std::vector<std::string>& missing)
{
    std::cout << "{\n";
    std::cout << "  \"plugin\": \"" << json_escape(args.plugin_path) << "\",\n";
    std::cout << "  \"symbols_file\": \"" << json_escape(args.symbols_path) << "\",\n";
    std::cout << "  \"ok\": " << (missing.empty() ? "true" : "false") << ",\n";
    std::cout << "  \"present_count\": " << present.size() << ",\n";
    std::cout << "  \"missing_count\": " << missing.size() << ",\n";
    std::cout << "  \"missing\": [";
    for (std::size_t i = 0; i < missing.size(); ++i) {
        if (i > 0)
            std::cout << ", ";
        std::cout << "\"" << json_escape(missing[i]) << "\"";
    }
    std::cout << "]\n";
    std::cout << "}\n";
}

void write_text_report(const std::vector<std::string>& present, const std::vector<std::string>& missing)
{
    std::cout << "present: " << present.size() << "\n";
    std::cout << "missing: " << missing.size() << "\n";
    for (const std::string& symbol : missing)
        std::cout << "missing " << symbol << "\n";
}

}

int main(int argc, char** argv)
{
    Args args;
    if (!parse_args(argc, argv, args)) {
        std::cerr << "usage: " << argv[0] << " --plugin <path> --symbols <path> [--json]\n";
        return 2;
    }

    std::vector<std::string> symbols;
    try {
        symbols = load_symbols(args.symbols_path);
    } catch (const std::exception& e) {
        std::cerr << e.what() << "\n";
        return 2;
    }

    void* module = dlopen(args.plugin_path.c_str(), RTLD_LAZY | RTLD_LOCAL);
    if (!module) {
        const char* error = dlerror();
        std::cerr << "dlopen failed: " << (error ? error : "unknown error") << "\n";
        return 3;
    }

    std::vector<std::string> present;
    std::vector<std::string> missing;
    for (const std::string& symbol : symbols) {
        dlerror();
        void* resolved = dlsym(module, symbol.c_str());
        const char* error = dlerror();
        if (resolved && !error)
            present.push_back(symbol);
        else
            missing.push_back(symbol);
    }

    dlclose(module);

    if (args.json)
        write_json_report(args, present, missing);
    else
        write_text_report(present, missing);

    return missing.empty() ? 0 : 1;
}
