set(MFVC_BASECLASSES_DIR "${PROJECT_SOURCE_DIR}/third_party/microsoft/directshow_baseclasses")

set(MFVC_BASECLASSES_SOURCES
    amextra.cpp amfilter.cpp amvideo.cpp arithutil.cpp combase.cpp cprop.cpp
    ctlutil.cpp ddmm.cpp dllentry.cpp dllsetup.cpp mtype.cpp outputq.cpp
    perflog.cpp pstream.cpp pullpin.cpp refclock.cpp renbase.cpp schedule.cpp
    seekpt.cpp source.cpp strmctl.cpp sysclock.cpp transfrm.cpp transip.cpp
    videoctl.cpp vtrans.cpp winctrl.cpp winutil.cpp wxdebug.cpp wxlist.cpp wxutil.cpp
)
list(TRANSFORM MFVC_BASECLASSES_SOURCES PREPEND "${MFVC_BASECLASSES_DIR}/")

add_library(mfvc_directshow_baseclasses STATIC ${MFVC_BASECLASSES_SOURCES})
target_include_directories(mfvc_directshow_baseclasses PUBLIC ${MFVC_BASECLASSES_DIR})
target_compile_definitions(mfvc_directshow_baseclasses PRIVATE _LIB)
target_compile_options(mfvc_directshow_baseclasses PRIVATE /W1 /permissive /UNOMINMAX)
target_link_libraries(mfvc_directshow_baseclasses PUBLIC strmiids winmm)

add_library(mfvc_directshow_source SHARED
    src/directshow_source.cpp
    src/dllsetup.cpp
    ../media_source/src/shared_frame_reader.cpp
)
target_include_directories(mfvc_directshow_source PRIVATE
    include
    ../common/include
    ../media_source/include
)
target_link_libraries(mfvc_directshow_source PRIVATE
    mfvc_directshow_baseclasses
    mfvc_protocol
    strmiids
    ole32
    oleaut32
    uuid
    winmm
    vcruntime
    ucrt
)
target_compile_options(mfvc_directshow_source PRIVATE /permissive)
set_target_properties(mfvc_directshow_source PROPERTIES
    OUTPUT_NAME "SSKJDirectShowCamera"
)
target_link_options(mfvc_directshow_source PRIVATE
    "/DEF:${CMAKE_CURRENT_SOURCE_DIR}/src/exports.def"
    "/ENTRY:DllEntryPoint"
)
