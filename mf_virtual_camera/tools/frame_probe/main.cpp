#include <Windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>

#include <iostream>
#include <sstream>
#include <string>

#include "mfvc/com_ptr.h"
#include "mfvc/constants.h"

namespace {

void print_hresult(const wchar_t* operation, HRESULT result) {
    std::wcerr << operation << L" failed: 0x" << std::hex << std::uppercase
               << static_cast<unsigned long>(result) << L"\n";
}

bool contains_sskj(IMFActivate* device, std::wstring& name) {
    wchar_t* allocated = nullptr;
    UINT32 length = 0;
    if (FAILED(device->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME, &allocated, &length))) {
        return false;
    }
    name.assign(allocated, length);
    while (!name.empty() && name.back() == L'\0') name.pop_back();
    CoTaskMemFree(allocated);
    return name.find(L"SSKJ") != std::wstring::npos;
}

std::string printable_name(std::wstring_view name) {
    std::ostringstream output;
    for (const wchar_t character : name) {
        if (character >= 0x20 && character <= 0x7e) {
            output << static_cast<char>(character);
        } else {
            output << "\\u" << std::hex << std::uppercase;
            output.width(4);
            output.fill('0');
            output << static_cast<unsigned int>(character) << std::dec;
        }
    }
    return output.str();
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    const bool direct = argc == 2 && std::wstring_view(argv[1]) == L"--direct";
    const bool list_only = argc == 2 && std::wstring_view(argv[1]) == L"--list";
    HRESULT result = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(result)) { print_hresult(L"CoInitializeEx", result); return 1; }
    result = MFStartup(MF_VERSION, MFSTARTUP_FULL);
    if (FAILED(result)) { print_hresult(L"MFStartup", result); CoUninitialize(); return 1; }

    mfvc::ComPtr<IMFAttributes> attributes;
    result = MFCreateAttributes(attributes.put(), 1);
    if (SUCCEEDED(result)) {
        result = attributes->SetGUID(
            MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE,
            MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID);
    }

    IMFActivate** devices = nullptr;
    UINT32 count = 0;
    if (SUCCEEDED(result)) result = MFEnumDeviceSources(attributes.get(), &devices, &count);
    if (FAILED(result)) {
        print_hresult(L"MFEnumDeviceSources", result);
        MFShutdown();
        CoUninitialize();
        return 1;
    }

    std::cout << "Video capture devices: " << count << "\n";
    IMFActivate* selected = nullptr;
    for (UINT32 index = 0; index < count; ++index) {
        std::wstring name;
        const bool match = contains_sskj(devices[index], name);
        std::cout << "  [" << index << "] "
                  << (name.empty() ? "<unnamed>" : printable_name(name)) << "\n";
        if (match && !selected) {
            selected = devices[index];
            selected->AddRef();
        }
    }
    for (UINT32 index = 0; index < count; ++index) devices[index]->Release();
    CoTaskMemFree(devices);

    if (list_only) {
        if (selected) selected->Release();
        MFShutdown();
        CoUninitialize();
        return 0;
    }

    if (!selected) {
        std::wcerr << L"SSKJ virtual camera was not found.\n";
        MFShutdown();
        CoUninitialize();
        return 2;
    }

    mfvc::ComPtr<IMFMediaSource> source;
    if (direct) {
        mfvc::ComPtr<IMFActivate> activation;
        CLSID source_clsid{};
        result = CLSIDFromString(mfvc::kMediaSourceClsid, &source_clsid);
        if (SUCCEEDED(result)) {
            result = CoCreateInstance(source_clsid, nullptr, CLSCTX_INPROC_SERVER,
                                      IID_PPV_ARGS(activation.put()));
        }
        if (SUCCEEDED(result)) result = activation->ActivateObject(IID_PPV_ARGS(source.put()));
    } else {
        result = selected->ActivateObject(IID_PPV_ARGS(source.put()));
    }
    selected->Release();
    if (FAILED(result)) {
        print_hresult(L"ActivateObject", result);
        MFShutdown();
        CoUninitialize();
        return 3;
    }

    mfvc::ComPtr<IMFSourceReader> reader;
    result = MFCreateSourceReaderFromMediaSource(source.get(), nullptr, reader.put());
    if (FAILED(result)) {
        print_hresult(L"MFCreateSourceReaderFromMediaSource", result);
        reader.reset();
        source->Shutdown();
        MFShutdown();
        CoUninitialize();
        return 4;
    }

    DWORD stream_index = 0;
    DWORD flags = 0;
    LONGLONG timestamp = 0;
    mfvc::ComPtr<IMFSample> sample;
    for (int attempt = 0; attempt < 10 && !sample; ++attempt) {
        result = reader->ReadSample(
            MF_SOURCE_READER_FIRST_VIDEO_STREAM,
            0,
            &stream_index,
            &flags,
            &timestamp,
            sample.put());
        std::wcout << L"ReadSample attempt " << (attempt + 1) << L": hr=0x"
                   << std::hex << static_cast<unsigned long>(result)
                   << L", flags=0x" << flags << std::dec << std::endl;
        if (FAILED(result) || (flags & MF_SOURCE_READERF_ENDOFSTREAM)) break;
    }
    if (FAILED(result) || !sample) {
        if (FAILED(result)) print_hresult(L"ReadSample", result);
        else std::wcerr << L"ReadSample returned no frame after 10 attempts.\n";
        reader.reset();
        source->Shutdown();
        MFShutdown();
        CoUninitialize();
        return 5;
    }

    DWORD buffers = 0;
    sample->GetBufferCount(&buffers);
    std::wcout << L"Captured one frame: stream=" << stream_index
               << L", buffers=" << buffers << L", timestamp=" << timestamp << L"\n";
    sample.reset();
    reader.reset();
    source->Shutdown();
    source.reset();
    MFShutdown();
    CoUninitialize();
    return 0;
}
