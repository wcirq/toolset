#include <Windows.h>
#include <unknwn.h>
#include <winrt/base.h>

#include <string>

#include "mfvc/constants.h"
#include "mfvc/media_source.h"

namespace {
HMODULE module_handle = nullptr;

HRESULT set_registry_value(HKEY root, const std::wstring& path, const wchar_t* name,
                           const wchar_t* value) noexcept {
    HKEY key = nullptr;
    const LSTATUS created = RegCreateKeyExW(root, path.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &key, nullptr);
    if (created != ERROR_SUCCESS) return HRESULT_FROM_WIN32(created);
    const DWORD bytes = static_cast<DWORD>((wcslen(value) + 1) * sizeof(wchar_t));
    const LSTATUS written = RegSetValueExW(key, name, 0, REG_SZ,
        reinterpret_cast<const BYTE*>(value), bytes);
    RegCloseKey(key);
    return HRESULT_FROM_WIN32(written);
}
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        module_handle = instance;
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}

extern "C" HRESULT __stdcall DllCanUnloadNow() {
    return winrt::get_module_lock() ? S_FALSE : S_OK;
}

extern "C" HRESULT __stdcall DllGetClassObject(REFCLSID clsid, REFIID iid, void** object) {
    if (!object) return E_POINTER;
    *object = nullptr;
    if (clsid != mfvc::kMediaSourceGuid) return CLASS_E_CLASSNOTAVAILABLE;
    try { return winrt::make_self<mfvc::ClassFactory>()->QueryInterface(iid, object); }
    catch (...) { return winrt::to_hresult(); }
}

extern "C" HRESULT __stdcall DllRegisterServer() {
    wchar_t module_path[MAX_PATH]{};
    if (!GetModuleFileNameW(module_handle, module_path, MAX_PATH)) {
        return HRESULT_FROM_WIN32(GetLastError());
    }
    const std::wstring clsid_path = L"Software\\Classes\\CLSID\\" +
                                    std::wstring(mfvc::kMediaSourceClsid);
    HRESULT result = set_registry_value(HKEY_LOCAL_MACHINE, clsid_path, nullptr, mfvc::kProductName);
    if (FAILED(result)) return result;
    result = set_registry_value(HKEY_LOCAL_MACHINE, clsid_path + L"\\InprocServer32", nullptr, module_path);
    if (FAILED(result)) return result;
    return set_registry_value(HKEY_LOCAL_MACHINE, clsid_path + L"\\InprocServer32",
                              L"ThreadingModel", L"Both");
}

extern "C" HRESULT __stdcall DllUnregisterServer() {
    const std::wstring clsid_path = L"Software\\Classes\\CLSID\\" +
                                    std::wstring(mfvc::kMediaSourceClsid);
    const LSTATUS removed = RegDeleteTreeW(HKEY_LOCAL_MACHINE, clsid_path.c_str());
    return removed == ERROR_SUCCESS || removed == ERROR_FILE_NOT_FOUND
               ? S_OK : HRESULT_FROM_WIN32(removed);
}
