#include <Windows.h>
#include <mfapi.h>
#include <mfvirtualcamera.h>
#include <ks.h>
#include <ksmedia.h>

#include <iomanip>
#include <iostream>
#include <string_view>

#include "mfvc/com_ptr.h"
#include "mfvc/constants.h"

namespace {

class ComApartment final {
public:
    ComApartment() noexcept : result_(CoInitializeEx(nullptr, COINIT_MULTITHREADED)) {}
    ~ComApartment() {
        if (SUCCEEDED(result_)) {
            CoUninitialize();
        }
    }
    [[nodiscard]] HRESULT result() const noexcept { return result_; }

private:
    HRESULT result_;
};

void print_error(std::wstring_view operation, HRESULT result) {
    std::wcerr << operation << L" failed (HRESULT=0x" << std::hex << std::uppercase
               << static_cast<unsigned long>(result) << L")\n";
}

HRESULT open_camera(mfvc::ComPtr<IMFVirtualCamera>& camera) {
    constexpr GUID categories[] = {KSCATEGORY_VIDEO_CAMERA, KSCATEGORY_CAPTURE};
    return MFCreateVirtualCamera(
        MFVirtualCameraType_SoftwareCameraSource,
        MFVirtualCameraLifetime_System,
        MFVirtualCameraAccess_CurrentUser,
        mfvc::kFriendlyName,
        mfvc::kMediaSourceClsid,
        categories,
        static_cast<ULONG>(std::size(categories)),
        camera.put());
}

HRESULT verify_media_source_registered() {
    CLSID source_clsid{};
    HRESULT result = CLSIDFromString(mfvc::kMediaSourceClsid, &source_clsid);
    if (FAILED(result)) {
        return result;
    }

    mfvc::ComPtr<IClassFactory> factory;
    return CoGetClassObject(
        source_clsid,
        CLSCTX_INPROC_SERVER,
        nullptr,
        IID_IClassFactory,
        reinterpret_cast<void**>(factory.put()));
}

int run(std::wstring_view command) {
    BOOL supported = FALSE;
    HRESULT result = MFIsVirtualCameraTypeSupported(MFVirtualCameraType_SoftwareCameraSource, &supported);
    if (FAILED(result)) {
        print_error(L"MFIsVirtualCameraTypeSupported", result);
        return 1;
    }
    if (!supported) {
        std::wcerr << L"Software virtual cameras are not supported on this Windows build.\n";
        return 2;
    }

    if (command == L"install" || command == L"start") {
        result = verify_media_source_registered();
        if (FAILED(result)) {
            std::wcerr << L"MediaSource COM component is not registered or cannot be loaded.\n";
            print_error(L"CoGetClassObject", result);
            return 1;
        }
    }

    mfvc::ComPtr<IMFVirtualCamera> camera;
    result = open_camera(camera);
    if (FAILED(result)) {
        print_error(L"MFCreateVirtualCamera", result);
        return 1;
    }

    if (command == L"install" || command == L"start") {
        result = camera->Start(nullptr);
    } else if (command == L"stop") {
        result = camera->Stop();
    } else if (command == L"remove") {
        result = camera->Remove();
    } else {
        std::wcerr << L"Unknown command: " << command << L"\n";
        return 2;
    }

    if (FAILED(result)) {
        print_error(command, result);
        return 1;
    }
    std::wcout << mfvc::kProductName << L": " << command << L" succeeded.\n";
    return 0;
}

}  // namespace

int wmain(int argc, wchar_t* argv[]) {
    if (argc != 2) {
        std::wcerr << L"Usage: SSKJVirtualCameraRegistrar <install|start|stop|remove>\n";
        return 2;
    }

    ComApartment apartment;
    if (FAILED(apartment.result())) {
        print_error(L"CoInitializeEx", apartment.result());
        return 1;
    }

    const HRESULT startup = MFStartup(MF_VERSION, MFSTARTUP_FULL);
    if (FAILED(startup)) {
        print_error(L"MFStartup", startup);
        return 1;
    }
    const int exit_code = run(argv[1]);
    MFShutdown();
    return exit_code;
}
