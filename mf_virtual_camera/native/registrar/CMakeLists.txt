add_executable(mfvc_registrar src/main.cpp)
target_include_directories(mfvc_registrar PRIVATE ../common/include)
target_link_libraries(mfvc_registrar PRIVATE mfplat mfsensorgroup ole32)

set_target_properties(mfvc_registrar PROPERTIES
    OUTPUT_NAME "SSKJVirtualCameraRegistrar"
)

