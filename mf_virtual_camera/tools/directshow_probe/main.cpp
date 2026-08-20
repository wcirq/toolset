#include <Windows.h>
#include <dshow.h>

#include <iostream>
#include <sstream>
#include <string>

namespace {

constexpr GUID kNullRendererClsid{
    0xc1f400a4, 0x3f08, 0x11d3, {0x9f, 0x0b, 0x00, 0x60, 0x08, 0x03, 0x9e, 0x37}};

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
    const bool open_camera = argc == 2 && std::wstring_view(argv[1]) == L"--open";
    const HRESULT initialized = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(initialized)) return 1;

    ICreateDevEnum* device_enumerator = nullptr;
    HRESULT result = CoCreateInstance(CLSID_SystemDeviceEnum, nullptr, CLSCTX_INPROC_SERVER,
                                      IID_PPV_ARGS(&device_enumerator));
    IEnumMoniker* cameras = nullptr;
    if (SUCCEEDED(result)) {
        result = device_enumerator->CreateClassEnumerator(
            CLSID_VideoInputDeviceCategory, &cameras, 0);
    }

    if (result == S_FALSE) {
        std::cout << "DirectShow video capture devices: 0\n";
        device_enumerator->Release();
        CoUninitialize();
        return 0;
    }
    if (FAILED(result)) {
        std::cerr << "DirectShow enumeration failed: 0x" << std::hex
                  << static_cast<unsigned long>(result) << "\n";
        if (device_enumerator) device_enumerator->Release();
        CoUninitialize();
        return 2;
    }

    unsigned int count = 0;
    IMoniker* selected = nullptr;
    IMoniker* camera = nullptr;
    while (cameras->Next(1, &camera, nullptr) == S_OK) {
        IPropertyBag* properties = nullptr;
        std::wstring name = L"<unnamed>";
        if (SUCCEEDED(camera->BindToStorage(nullptr, nullptr, IID_PPV_ARGS(&properties)))) {
            VARIANT value;
            VariantInit(&value);
            if (SUCCEEDED(properties->Read(L"FriendlyName", &value, nullptr)) &&
                value.vt == VT_BSTR && value.bstrVal) {
                name.assign(value.bstrVal, SysStringLen(value.bstrVal));
            }
            VariantClear(&value);
            properties->Release();
        }
        std::cout << "  [" << count++ << "] " << printable_name(name) << "\n";
        if (!selected && name.find(L"SSKJ DirectShow Camera") != std::wstring::npos) {
            selected = camera;
            selected->AddRef();
        }
        camera->Release();
    }
    std::cout << "DirectShow video capture device count: " << count << "\n";

    cameras->Release();
    device_enumerator->Release();

    if (open_camera) {
        if (!selected) {
            std::cerr << "SSKJ DirectShow Camera was not found.\n";
            CoUninitialize();
            return 3;
        }
        IBaseFilter* source = nullptr;
        IGraphBuilder* graph = nullptr;
        ICaptureGraphBuilder2* capture = nullptr;
        IBaseFilter* renderer = nullptr;
        IMediaControl* control = nullptr;
        result = selected->BindToObject(nullptr, nullptr, IID_PPV_ARGS(&source));
        if (SUCCEEDED(result)) result = CoCreateInstance(CLSID_FilterGraph, nullptr,
                                                         CLSCTX_INPROC_SERVER,
                                                         IID_PPV_ARGS(&graph));
        if (SUCCEEDED(result)) result = CoCreateInstance(CLSID_CaptureGraphBuilder2, nullptr,
                                                         CLSCTX_INPROC_SERVER,
                                                         IID_PPV_ARGS(&capture));
        if (SUCCEEDED(result)) result = CoCreateInstance(kNullRendererClsid, nullptr,
                                                         CLSCTX_INPROC_SERVER,
                                                         IID_PPV_ARGS(&renderer));
        if (SUCCEEDED(result)) result = capture->SetFiltergraph(graph);
        if (SUCCEEDED(result)) result = graph->AddFilter(source, L"SSKJ Camera");
        if (SUCCEEDED(result)) result = graph->AddFilter(renderer, L"Null Renderer");
        if (SUCCEEDED(result)) result = capture->RenderStream(&PIN_CATEGORY_CAPTURE,
                                                               &MEDIATYPE_Video, source,
                                                               nullptr, renderer);
        if (SUCCEEDED(result)) result = graph->QueryInterface(IID_PPV_ARGS(&control));
        if (SUCCEEDED(result)) result = control->Run();
        if (SUCCEEDED(result)) {
            Sleep(1200);
            control->Stop();
            std::cout << "DirectShow graph ran successfully for 1200 ms.\n";
        } else {
            std::cerr << "DirectShow graph failed: 0x" << std::hex
                      << static_cast<unsigned long>(result) << "\n";
        }
        if (control) control->Release();
        if (renderer) renderer->Release();
        if (capture) capture->Release();
        if (graph) graph->Release();
        if (source) source->Release();
        selected->Release();
        CoUninitialize();
        return SUCCEEDED(result) ? 0 : 4;
    }
    if (selected) selected->Release();
    CoUninitialize();
    return 0;
}
