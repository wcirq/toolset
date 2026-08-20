add_executable(mfvc_directshow_probe main.cpp)
target_link_libraries(mfvc_directshow_probe PRIVATE strmiids ole32 oleaut32)

set_target_properties(mfvc_directshow_probe PROPERTIES
    OUTPUT_NAME "SSKJDirectShowProbe"
)
