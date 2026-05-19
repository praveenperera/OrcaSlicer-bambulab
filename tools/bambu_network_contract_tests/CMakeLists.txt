cmake_minimum_required(VERSION 3.16)
project(bambu_network_contract_tests LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(bambu_network_contract_probe
    contract_probe.cpp
)

add_executable(bambu_network_lifecycle_probe
    lifecycle_probe.cpp
)

add_executable(bambu_network_callback_probe
    callback_probe.cpp
)

add_executable(bambu_network_unsupported_probe
    unsupported_probe.cpp
)

add_executable(bambu_network_cloud_service_probe
    cloud_service_probe.cpp
)

add_executable(bambu_network_source_behavior_probe
    source_behavior_probe.cpp
)

add_executable(bambu_network_source_streaming_probe
    source_streaming_probe.cpp
)

add_executable(bambu_network_source_local_tunnel_probe
    source_local_tunnel_probe.cpp
)

add_executable(bambu_network_printer_workflow_probe
    printer_workflow_probe.cpp
)

add_executable(bambu_network_print_job_probe
    print_job_probe.cpp
)

add_executable(bambu_network_event_bridge_probe
    event_bridge_probe.cpp
)

add_executable(bambu_network_discovery_probe
    discovery_probe.cpp
)

add_executable(bambu_network_camera_url_probe
    camera_url_probe.cpp
)

add_executable(bambu_network_ft_behavior_probe
    ft_behavior_probe.cpp
)

if (NOT WIN32)
    target_link_libraries(bambu_network_contract_probe PRIVATE ${CMAKE_DL_LIBS})
    target_link_libraries(bambu_network_lifecycle_probe PRIVATE ${CMAKE_DL_LIBS})
    target_link_libraries(bambu_network_callback_probe PRIVATE ${CMAKE_DL_LIBS})
    target_link_libraries(bambu_network_unsupported_probe PRIVATE ${CMAKE_DL_LIBS})
    target_link_libraries(bambu_network_cloud_service_probe PRIVATE ${CMAKE_DL_LIBS})
    target_link_libraries(bambu_network_source_behavior_probe PRIVATE ${CMAKE_DL_LIBS})
    target_link_libraries(bambu_network_source_streaming_probe PRIVATE ${CMAKE_DL_LIBS})
    target_link_libraries(bambu_network_source_local_tunnel_probe PRIVATE ${CMAKE_DL_LIBS})
    target_link_libraries(bambu_network_printer_workflow_probe PRIVATE ${CMAKE_DL_LIBS})
    target_link_libraries(bambu_network_print_job_probe PRIVATE ${CMAKE_DL_LIBS})
    target_link_libraries(bambu_network_event_bridge_probe PRIVATE ${CMAKE_DL_LIBS})
    target_link_libraries(bambu_network_discovery_probe PRIVATE ${CMAKE_DL_LIBS})
    target_link_libraries(bambu_network_camera_url_probe PRIVATE ${CMAKE_DL_LIBS})
    target_link_libraries(bambu_network_ft_behavior_probe PRIVATE ${CMAKE_DL_LIBS})
endif()
