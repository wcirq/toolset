add_executable(mfvc_frame_probe main.cpp)
target_include_directories(mfvc_frame_probe PRIVATE ../../native/common/include)
target_link_libraries(mfvc_frame_probe PRIVATE
    mfplat
    mf
    mfreadwrite
    mfuuid
    ole32
)
set_target_properties(mfvc_frame_probe PROPERTIES OUTPUT_NAME "SSKJVirtualCameraProbe")
