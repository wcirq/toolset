add_executable(frame_protocol_test frame_protocol_test.cpp)
target_link_libraries(frame_protocol_test PRIVATE mfvc_protocol)
add_test(NAME frame_protocol_test COMMAND frame_protocol_test)

add_executable(media_source_smoke_test media_source_smoke_test.cpp)
target_include_directories(media_source_smoke_test PRIVATE
    ../../native/common/include
    ../../native/media_source/include
)
target_link_libraries(media_source_smoke_test PRIVATE
    mfvc_protocol
    mfplat
    mfuuid
    ole32
)
add_dependencies(media_source_smoke_test mfvc_media_source)
target_compile_definitions(media_source_smoke_test PRIVATE
    MFVC_DLL_PATH=L"$<TARGET_FILE:mfvc_media_source>"
)
add_test(NAME media_source_smoke_test COMMAND media_source_smoke_test)
set_tests_properties(media_source_smoke_test PROPERTIES TIMEOUT 10)
