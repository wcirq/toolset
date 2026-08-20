#pragma once

namespace mfvc {

inline constexpr wchar_t kProductName[] = L"SSKJ MF Virtual Camera";
inline constexpr wchar_t kFriendlyName[] = L"SSKJ";
inline constexpr wchar_t kWeComTestFriendlyName[] = L"SSKJ WeCom Detection Test";
inline constexpr wchar_t kMediaSourceClsid[] = L"{7C81C5D6-7424-47DC-8F4D-12261522C239}";
inline constexpr wchar_t kWeComTestMediaSourceClsid[] = L"{E98467C5-18B5-46B3-9408-1CE4C5C59437}";
inline constexpr wchar_t kSharedMemoryName[] = L"Local\\SSKJ.MFVirtualCamera.FrameBuffer.v1";
inline constexpr wchar_t kSharedMemoryPath[] =
    L"C:\\ProgramData\\SSKJVirtualCamera\\frames.v1.bin";
inline constexpr wchar_t kFrameReadyEventName[] = L"Local\\SSKJ.MFVirtualCamera.FrameReady.v1";

}  // namespace mfvc
