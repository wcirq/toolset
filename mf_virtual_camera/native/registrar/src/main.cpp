#include <Windows.h>
#include <mfapi.h>
#include <mfvirtualcamera.h>
#include <ks.h>
#include <ksmedia.h>

#include <iomanip>
#include <iostream>
#include <string>
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

HRESULT open_camera(std::wstring_view friendly_name, std::wstring_view source_id,
                    mfvc::ComPtr<IMFVirtualCamera>& camera) {
    constexpr GUID categories[] = {KSCATEGORY_VIDEO_CAMERA, KSCATEGORY_CAPTURE};
    const std::wstring friendly_name_string(friendly_name);
    const std::wstring source_id_string(source_id);
    return MFCreateVirtualCamera(
        MFVirtualCameraType_SoftwareCameraSource,
        MFVirtualCameraLifetime_System,
        MFVirtualCameraAccess_CurrentUser,
        friendly_name_string.c_str(),
        source_id_string.c_str(),
        categories,
        static_cast<ULONG>(std::size(categories)),
        camera.put());
}

HRESULT verify_media_source_registered(std::wstring_view source_id) {
    CLSID source_clsid{};
    const std::wstring source_id_string(source_id);
    HRESULT result = CLSIDFromString(source_id_string.c_str(), &source_clsid);
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

int run(std::wstring_view command, std::wstring_view custom_name = {},
        std::wstring_view custom_source_id = {}) {
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

    const bool is_test_camera =
        command == L"install-wecom-test" || command == L"start-wecom-test" ||
        command == L"stop-wecom-test" || command == L"remove-wecom-test";
    const bool is_legacy_test_camera = command == L"remove-wecom-test-legacy";
    const bool is_custom_camera =
        command == L"install-custom" || command == L"start-custom" ||
        command == L"stop-custom" || command == L"remove-custom";
    const bool is_install_or_start =
        command == L"install" || command == L"start" ||
        command == L"install-wecom-test" || command == L"start-wecom-test" ||
        command == L"install-custom" || command == L"start-custom";

    const std::wstring_view source_id = is_custom_camera
        ? custom_source_id
        : (is_test_camera ? std::wstring_view(mfvc::kWeComTestMediaSourceClsid)
                          : std::wstring_view(mfvc::kMediaSourceClsid));
    const std::wstring_view friendly_name = is_custom_camera
        ? custom_name
        : ((is_test_camera || is_legacy_test_camera)
               ? std::wstring_view(mfvc::kWeComTestFriendlyName)
               : std::wstring_view(mfvc::kFriendlyName));
    if (friendly_name.empty() || source_id.empty()) return 2;

    if (is_install_or_start) {
        result = verify_media_source_registered(source_id);
        if (FAILED(result)) {
            std::wcerr << L"MediaSource COM component is not registered or cannot be loaded.\n";
            print_error(L"CoGetClassObject", result);
            return 1;
        }
    }

    mfvc::ComPtr<IMFVirtualCamera> camera;
    result = open_camera(friendly_name, source_id, camera);
    if (FAILED(result)) {
        print_error(L"MFCreateVirtualCamera", result);
        return 1;
    }

    if (command == L"install" || command == L"start" ||
        command == L"install-wecom-test" || command == L"start-wecom-test") {
        result = camera->Start(nullptr);
    } else if (command == L"install-custom" || command == L"start-custom") {
        result = camera->Start(nullptr);
    } else if (command == L"stop" || command == L"stop-wecom-test") {
        result = camera->Stop();
    } else if (command == L"stop-custom") {
        result = camera->Stop();
    } else if (command == L"remove" || command == L"remove-wecom-test" ||
               command == L"remove-wecom-test-legacy") {
        result = camera->Remove();
    } else if (command == L"remove-custom") {
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
    const bool custom = argc == 4 &&
        (std::wstring_view(argv[1]) == L"install-custom" ||
         std::wstring_view(argv[1]) == L"start-custom" ||
         std::wstring_view(argv[1]) == L"stop-custom" ||
         std::wstring_view(argv[1]) == L"remove-custom");
    if (argc != 2 && !custom) {
        std::wcerr << L"Usage: SSKJVirtualCameraRegistrar "
                      L"<install|start|stop|remove|install-wecom-test|"
                      L"start-wecom-test|stop-wecom-test|remove-wecom-test|"
                      L"remove-wecom-test-legacy>\n"
                      L"       SSKJVirtualCameraRegistrar "
                      L"<install-custom|start-custom|stop-custom|remove-custom> "
                      L"<friendly-name> <source-clsid>\n";
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
    const int exit_code = custom ? run(argv[1], argv[2], argv[3]) : run(argv[1]);
    MFShutdown();
    return exit_code;
}
