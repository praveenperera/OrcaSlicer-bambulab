cmake_minimum_required(VERSION 3.18)
project(bambu_network_rust_plugin LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(RUST_CORE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/rust_core")
set(RUST_TARGET_DIR "${CMAKE_CURRENT_BINARY_DIR}/cargo")
set(RUST_TARGET "" CACHE STRING "Optional Cargo target triple")
if (CMAKE_BUILD_TYPE MATCHES "^(Release|RelWithDebInfo|MinSizeRel)$")
    set(RUST_CARGO_PROFILE "release")
    set(RUST_CARGO_PROFILE_ARGS "--release")
else()
    set(RUST_CARGO_PROFILE "debug")
    set(RUST_CARGO_PROFILE_ARGS "")
endif()
set(RUST_CARGO_TARGET_ARGS "")
if (RUST_TARGET)
    set(RUST_CARGO_TARGET_ARGS "--target" "${RUST_TARGET}")
    set(RUST_CARGO_PROFILE_DIR "${RUST_TARGET_DIR}/${RUST_TARGET}/${RUST_CARGO_PROFILE}")
else()
    set(RUST_CARGO_PROFILE_DIR "${RUST_TARGET_DIR}/${RUST_CARGO_PROFILE}")
endif()
set(RUST_CORE_LIB "${RUST_CARGO_PROFILE_DIR}/${CMAKE_STATIC_LIBRARY_PREFIX}bambu_network_rust_core${CMAKE_STATIC_LIBRARY_SUFFIX}")

set(RUST_CARGO_ENV "CARGO_TARGET_DIR=${RUST_TARGET_DIR}")
set(ZIG_CC_X86_64_LINUX_GNU "${CMAKE_CURRENT_SOURCE_DIR}/scripts/zig-cc-x86_64-linux-gnu")
if (RUST_TARGET STREQUAL "x86_64-unknown-linux-gnu" AND EXISTS "${ZIG_CC_X86_64_LINUX_GNU}")
    list(APPEND RUST_CARGO_ENV
        "CC_x86_64_unknown_linux_gnu=${ZIG_CC_X86_64_LINUX_GNU}"
        "AR_x86_64_unknown_linux_gnu=zig ar"
    )
endif()

add_custom_command(
    OUTPUT "${RUST_CORE_LIB}"
    COMMAND "${CMAKE_COMMAND}" -E env ${RUST_CARGO_ENV}
        cargo build --manifest-path "${RUST_CORE_DIR}/Cargo.toml" ${RUST_CARGO_PROFILE_ARGS} ${RUST_CARGO_TARGET_ARGS}
    DEPENDS
        "${RUST_CORE_DIR}/Cargo.toml"
        "${RUST_CORE_DIR}/Cargo.lock"
        "${RUST_CORE_DIR}/src/agent.rs"
        "${RUST_CORE_DIR}/src/cloud.rs"
        "${RUST_CORE_DIR}/src/discovery.rs"
        "${RUST_CORE_DIR}/src/event.rs"
        "${RUST_CORE_DIR}/src/lan_mqtt.rs"
        "${RUST_CORE_DIR}/src/lib.rs"
        "${RUST_CORE_DIR}/src/protocol.rs"
        "${RUST_CORE_DIR}/src/source_tls.rs"
        "${RUST_CORE_DIR}/src/transport.rs"
    WORKING_DIRECTORY "${RUST_CORE_DIR}"
    VERBATIM
)

add_custom_target(bambu_network_rust_core_build DEPENDS "${RUST_CORE_LIB}")

add_library(bambu_network_rust_core STATIC IMPORTED GLOBAL)
set_target_properties(bambu_network_rust_core PROPERTIES IMPORTED_LOCATION "${RUST_CORE_LIB}")
add_dependencies(bambu_network_rust_core bambu_network_rust_core_build)

add_library(bambu_networking SHARED
    shim/bambu_networking_shim.cpp
)
add_dependencies(bambu_networking bambu_network_rust_core_build)
target_include_directories(bambu_networking PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../deps_src")
target_link_libraries(bambu_networking PRIVATE bambu_network_rust_core)
set_target_properties(bambu_networking PROPERTIES OUTPUT_NAME "bambu_networking")

if (APPLE)
    target_link_libraries(bambu_networking PRIVATE "-framework Security" "-framework CoreFoundation")
elseif (UNIX)
    target_link_libraries(bambu_networking PRIVATE pthread ${CMAKE_DL_LIBS} m)
endif()

add_library(BambuSource SHARED
    shim/bambu_source_shim.cpp
)
add_dependencies(BambuSource bambu_network_rust_core_build)
target_link_libraries(BambuSource PRIVATE bambu_network_rust_core)
set_target_properties(BambuSource PROPERTIES OUTPUT_NAME "BambuSource")

if (APPLE)
    target_link_libraries(BambuSource PRIVATE "-framework Security" "-framework CoreFoundation")
elseif (UNIX)
    target_link_libraries(BambuSource PRIVATE pthread ${CMAKE_DL_LIBS} m)
endif()
