#include <Windows.h>
#include <mfapi.h>
#include <mfidl.h>

#include <cassert>
#include <cstring>
#include <iostream>

#include "mfvc/com_ptr.h"
#include "mfvc/constants.h"
#include "mfvc/frame_protocol.h"
#include "mfvc/media_source.h"

int wmain() {
    std::wcerr << L"checkpoint: COM startup\n";
    HRESULT result = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    assert(SUCCEEDED(result));
    result = MFStartup(MF_VERSION, MFSTARTUP_FULL);
    assert(SUCCEEDED(result));

    HMODULE module = LoadLibraryW(MFVC_DLL_PATH);
    assert(module != nullptr);
    using GetClassObjectFn = HRESULT(__stdcall*)(REFCLSID, REFIID, void**);
    using CanUnloadNowFn = HRESULT(__stdcall*)();
    const auto get_class_object = reinterpret_cast<GetClassObjectFn>(
        GetProcAddress(module, "DllGetClassObject"));
    const auto can_unload_now = reinterpret_cast<CanUnloadNowFn>(
        GetProcAddress(module, "DllCanUnloadNow"));
    assert(get_class_object != nullptr);
    assert(can_unload_now != nullptr);
    std::wcerr << L"checkpoint: DLL loaded\n";

    mfvc::ComPtr<IClassFactory> factory;
    result = get_class_object(
        mfvc::kMediaSourceGuid,
        IID_IClassFactory,
        reinterpret_cast<void**>(factory.put()));
    assert(SUCCEEDED(result));
    std::wcerr << L"checkpoint: class factory created\n";

    mfvc::ComPtr<IMFActivate> activation;
    result = factory->CreateInstance(
        nullptr,
        IID_IMFActivate,
        reinterpret_cast<void**>(activation.put()));
    assert(SUCCEEDED(result));
    std::wcerr << L"checkpoint: activation created\n";

    mfvc::ComPtr<IMFMediaSource> source;
    result = activation->ActivateObject(
        IID_IMFMediaSource,
        reinterpret_cast<void**>(source.put()));
    if (FAILED(result)) {
        std::wcerr << L"ActivateObject failed: 0x" << std::hex
                   << static_cast<unsigned long>(result) << L"\n";
        return 20;
    }
    std::wcerr << L"checkpoint: source activated\n";

    DWORD characteristics = 0;
    result = source->GetCharacteristics(&characteristics);
    assert(SUCCEEDED(result));
    assert((characteristics & MFMEDIASOURCE_IS_LIVE) != 0);

    mfvc::ComPtr<IMFPresentationDescriptor> presentation;
    result = source->CreatePresentationDescriptor(presentation.put());
    assert(SUCCEEDED(result));
    DWORD stream_count = 0;
    result = presentation->GetStreamDescriptorCount(&stream_count);
    assert(SUCCEEDED(result));
    assert(stream_count == 1);
    std::wcerr << L"checkpoint: presentation validated\n";

    PROPVARIANT start_position;
    PropVariantInit(&start_position);
    result = source->Start(presentation.get(), &GUID_NULL, &start_position);
    if (FAILED(result)) return 30;

    mfvc::ComPtr<IMFMediaEvent> source_event;
    result = source->GetEvent(0, source_event.put());
    if (FAILED(result)) return 31;
    MediaEventType event_type = MEUnknown;
    result = source_event->GetType(&event_type);
    if (FAILED(result) || event_type != MENewStream) return 32;

    PROPVARIANT stream_value;
    PropVariantInit(&stream_value);
    result = source_event->GetValue(&stream_value);
    if (FAILED(result) || stream_value.vt != VT_UNKNOWN) return 33;
    mfvc::ComPtr<IMFMediaStream> stream;
    result = stream_value.punkVal->QueryInterface(IID_PPV_ARGS(stream.put()));
    PropVariantClear(&stream_value);
    if (FAILED(result)) return 34;

    source_event.reset();
    result = source->GetEvent(0, source_event.put());
    if (FAILED(result)) return 35;
    result = source_event->GetType(&event_type);
    if (FAILED(result) || event_type != MESourceStarted) return 36;

    mfvc::ComPtr<IMFMediaEvent> stream_event;
    result = stream->GetEvent(0, stream_event.put());
    if (FAILED(result)) return 37;
    result = stream_event->GetType(&event_type);
    if (FAILED(result) || event_type != MEStreamStarted) return 38;

    constexpr DWORD frame_size = 1280 * 720 * 3 / 2;
    constexpr DWORD mapping_size = sizeof(mfvc::protocol::FrameHeader) +
                                   mfvc::protocol::kSlotCount * frame_size;
    HANDLE mapping = CreateFileMappingW(
        INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, mapping_size, mfvc::kSharedMemoryName);
    if (!mapping) return 381;
    auto* mapping_view = static_cast<std::byte*>(
        MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, mapping_size));
    if (!mapping_view) return 382;
    mfvc::protocol::FrameHeader header{};
    header.magic = mfvc::protocol::kMagic;
    header.version_major = mfvc::protocol::kVersionMajor;
    header.version_minor = mfvc::protocol::kVersionMinor;
    header.header_size = sizeof(header);
    header.slot_count = mfvc::protocol::kSlotCount;
    header.slot_size = frame_size;
    header.width = 1280;
    header.height = 720;
    header.stride = 1280;
    header.pixel_format = mfvc::protocol::PixelFormat::nv12;
    header.fps_numerator = 30;
    header.fps_denominator = 1;
    const std::size_t published_slot = sizeof(header) + frame_size;
    std::memset(mapping_view + published_slot, 42, frame_size);
    header.published_sequence = 1;
    std::memcpy(mapping_view, &header, sizeof(header));

    result = stream->RequestSample(nullptr);
    if (FAILED(result)) return 39;
    stream_event.reset();
    result = stream->GetEvent(0, stream_event.put());
    if (FAILED(result)) return 40;
    result = stream_event->GetType(&event_type);
    if (FAILED(result) || event_type != MEMediaSample) return 41;

    PROPVARIANT sample_value;
    PropVariantInit(&sample_value);
    result = stream_event->GetValue(&sample_value);
    if (FAILED(result) || sample_value.vt != VT_UNKNOWN) return 42;
    mfvc::ComPtr<IMFSample> sample;
    result = sample_value.punkVal->QueryInterface(IID_PPV_ARGS(sample.put()));
    PropVariantClear(&sample_value);
    if (FAILED(result)) return 43;
    DWORD buffer_count = 0;
    result = sample->GetBufferCount(&buffer_count);
    if (FAILED(result) || buffer_count != 1) return 44;
    mfvc::ComPtr<IMFMediaBuffer> sample_buffer;
    result = sample->GetBufferByIndex(0, sample_buffer.put());
    if (FAILED(result)) return 441;
    BYTE* sample_bytes = nullptr;
    DWORD sample_length = 0;
    result = sample_buffer->Lock(&sample_bytes, nullptr, &sample_length);
    if (FAILED(result)) return 442;
    const bool shared_frame_received = sample_length == frame_size && sample_bytes[0] == 42 &&
                                       sample_bytes[frame_size - 1] == 42;
    sample_buffer->Unlock();
    if (!shared_frame_received) return 443;
    std::wcerr << L"checkpoint: sample produced\n";

    result = source->Stop();
    if (FAILED(result)) return 45;
    stream.reset();
    sample.reset();
    UnmapViewOfFile(mapping_view);
    CloseHandle(mapping);

    result = activation->ShutdownObject();
    assert(SUCCEEDED(result));
    std::wcerr << L"checkpoint: source shutdown\n";
    source.reset();
    activation.reset();
    factory.reset();

    MFShutdown();
    CoUninitialize();
    std::wcerr << L"checkpoint: MF shutdown\n";
    assert(can_unload_now() == S_OK);
    FreeLibrary(module);
    return 0;
}
