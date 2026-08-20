add_library(mfvc_media_source SHARED
    src/dllmain.cpp
    src/media_source.cpp
    src/shared_frame_reader.cpp
)

target_include_directories(mfvc_media_source PRIVATE
    include
    ../common/include
)
target_link_libraries(mfvc_media_source PRIVATE
    mfvc_protocol
    mfplat
    mf
    mfuuid
    ole32
    runtimeobject
)

set_target_properties(mfvc_media_source PROPERTIES
    OUTPUT_NAME "SSKJVirtualCameraMediaSource"
)

target_link_options(mfvc_media_source PRIVATE "/DEF:${CMAKE_CURRENT_SOURCE_DIR}/src/exports.def")
