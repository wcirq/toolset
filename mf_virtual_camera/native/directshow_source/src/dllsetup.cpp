#include <streams.h>

#include <iterator>
#include <string>

#include "mfvc/directshow_source.h"

namespace {

const AMOVIESETUP_MEDIATYPE kPinTypes[]{{&MEDIATYPE_Video, &MEDIASUBTYPE_YUY2}};

const AMOVIESETUP_PIN kPins[]{
    {const_cast<LPWSTR>(L"Capture"), FALSE, TRUE, FALSE, FALSE, &CLSID_NULL, nullptr,
     static_cast<int>(std::size(kPinTypes)), kPinTypes},
};

const AMOVIESETUP_FILTER kFilter{
    &mfvc::kDirectShowCameraGuid,
    L"SSKJ DirectShow Camera",
    MERIT_DO_NOT_USE,
    static_cast<int>(std::size(kPins)),
    kPins,
};

}  // namespace

CFactoryTemplate g_Templates[]{
    {L"SSKJ DirectShow Camera", &mfvc::kDirectShowCameraGuid,
     mfvc::DirectShowSource::CreateInstance, nullptr, &kFilter},
};
int g_cTemplates = static_cast<int>(std::size(g_Templates));

STDAPI DllRegisterServer() {
    HRESULT result = AMovieDllRegisterServer2(TRUE);
    if (FAILED(result)) return result;

    wchar_t category[64]{};
    wchar_t filter[64]{};
    StringFromGUID2(CLSID_VideoInputDeviceCategory, category, static_cast<int>(std::size(category)));
    StringFromGUID2(mfvc::kDirectShowCameraGuid, filter, static_cast<int>(std::size(filter)));
    const std::wstring path = L"CLSID\\" + std::wstring(category) + L"\\Instance\\" + filter;
    HKEY key = nullptr;
    const LSTATUS created = RegCreateKeyExW(HKEY_CLASSES_ROOT, path.c_str(), 0, nullptr, 0,
                                             KEY_WRITE, nullptr, &key, nullptr);
    if (created != ERROR_SUCCESS) return HRESULT_FROM_WIN32(created);
    const wchar_t name[] = L"SSKJ DirectShow Camera";
    RegSetValueExW(key, L"FriendlyName", 0, REG_SZ,
                   reinterpret_cast<const BYTE*>(name), sizeof(name));
    RegSetValueExW(key, L"CLSID", 0, REG_SZ,
                   reinterpret_cast<const BYTE*>(filter),
                   static_cast<DWORD>((wcslen(filter) + 1) * sizeof(wchar_t)));
    RegCloseKey(key);
    return S_OK;
}

STDAPI DllUnregisterServer() {
    wchar_t category[64]{};
    wchar_t filter[64]{};
    StringFromGUID2(CLSID_VideoInputDeviceCategory, category, static_cast<int>(std::size(category)));
    StringFromGUID2(mfvc::kDirectShowCameraGuid, filter, static_cast<int>(std::size(filter)));
    const std::wstring path = L"CLSID\\" + std::wstring(category) + L"\\Instance\\" + filter;
    RegDeleteTreeW(HKEY_CLASSES_ROOT, path.c_str());
    return AMovieDllRegisterServer2(FALSE);
}
