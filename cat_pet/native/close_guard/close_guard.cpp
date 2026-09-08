#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commctrl.h>

namespace {
constexpr wchar_t INSTALL_MESSAGE[] = L"CoolCat.CloseGuard.Install.v1";
constexpr wchar_t UNINSTALL_MESSAGE[] = L"CoolCat.CloseGuard.Uninstall.v1";
constexpr wchar_t REQUEST_MESSAGE[] = L"CoolCat.CloseGuard.Request.v1";
constexpr wchar_t ALLOW_MESSAGE[] = L"CoolCat.CloseGuard.Allow.v1";
constexpr wchar_t CANCEL_MESSAGE[] = L"CoolCat.CloseGuard.Cancel.v1";

HMODULE module_handle = nullptr;
UINT install_message = 0;
UINT uninstall_message = 0;
UINT request_message = 0;
UINT allow_message = 0;
UINT cancel_message = 0;
constexpr wchar_t STATE_PROPERTY[] = L"CoolCat.CloseGuard.State.v1";

struct GuardState {
    HWND controller = nullptr;
    bool request_pending = false;
    bool allow_once = false;
    UINT close_message = WM_CLOSE;
    WPARAM close_wparam = 0;
    LPARAM close_lparam = 0;
};

UINT message_id(const wchar_t* name, UINT& cached) {
    if (!cached) cached = RegisterWindowMessageW(name);
    return cached;
}

LRESULT CALLBACK guard_subclass(HWND hwnd, UINT message, WPARAM wparam,
                                LPARAM lparam, UINT_PTR subclass_id,
                                DWORD_PTR reference_data) {
    auto* state = reinterpret_cast<GuardState*>(reference_data);
    if (!state) return DefSubclassProc(hwnd, message, wparam, lparam);
    if (message == message_id(UNINSTALL_MESSAGE, uninstall_message)) {
        RemoveWindowSubclass(hwnd, guard_subclass, subclass_id);
        RemovePropW(hwnd, STATE_PROPERTY);
        delete state;
        return 0;
    }
    if (message == message_id(CANCEL_MESSAGE, cancel_message)) {
        state->request_pending = false;
        return 0;
    }
    if (message == message_id(ALLOW_MESSAGE, allow_message)) {
        state->request_pending = false;
        state->allow_once = true;
        PostMessageW(hwnd, state->close_message,
                     state->close_wparam, state->close_lparam);
        return 0;
    }

    const bool closing = message == WM_CLOSE ||
        (message == WM_SYSCOMMAND && (wparam & 0xFFF0) == SC_CLOSE);
    if (closing) {
        if (state->allow_once) {
            state->allow_once = false;
            return DefSubclassProc(hwnd, message, wparam, lparam);
        }
        // Never trap an application when the controller has disappeared.
        if (!state->controller || !IsWindow(state->controller)) {
            RemoveWindowSubclass(hwnd, guard_subclass, subclass_id);
            RemovePropW(hwnd, STATE_PROPERTY);
            LRESULT result = DefSubclassProc(hwnd, message, wparam, lparam);
            delete state;
            return result;
        }
        if (!state->request_pending) {
            state->request_pending = true;
            state->close_message = message;
            state->close_wparam = wparam;
            state->close_lparam = lparam;
            if (!PostMessageW(state->controller,
                              message_id(REQUEST_MESSAGE, request_message),
                              reinterpret_cast<WPARAM>(hwnd),
                              static_cast<LPARAM>(GetCurrentProcessId()))) {
                state->request_pending = false;
                return DefSubclassProc(hwnd, message, wparam, lparam);
            }
        }
        return 0;
    }
    if (message == WM_NCDESTROY) {
        LRESULT result = DefSubclassProc(hwnd, message, wparam, lparam);
        RemoveWindowSubclass(hwnd, guard_subclass, subclass_id);
        RemovePropW(hwnd, STATE_PROPERTY);
        delete state;
        return result;
    }
    return DefSubclassProc(hwnd, message, wparam, lparam);
}

void install_for_message(const MSG* message) {
    if (!message || !message->hwnd || !message->wParam) return;
    HWND target = message->hwnd;
    HWND controller = reinterpret_cast<HWND>(message->wParam);
    if (!IsWindow(target) || !IsWindow(controller)) return;

    auto* existing = reinterpret_cast<GuardState*>(GetPropW(target, STATE_PROPERTY));
    if (existing) {
        existing->controller = controller;
        existing->request_pending = existing->allow_once = false;
        return;
    }
    // Keep the module mapped if the Python controller exits unexpectedly;
    // the subclass then detects the missing controller and fails open.
    HMODULE pinned = nullptr;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                       GET_MODULE_HANDLE_EX_FLAG_PIN,
                       reinterpret_cast<LPCWSTR>(&guard_subclass), &pinned);
    auto* state = new GuardState();
    state->controller = controller;
    const UINT_PTR subclass_id = reinterpret_cast<UINT_PTR>(state);
    if (SetWindowSubclass(target, guard_subclass, subclass_id,
                          reinterpret_cast<DWORD_PTR>(state))) {
        if (!SetPropW(target, STATE_PROPERTY, reinterpret_cast<HANDLE>(state))) {
            RemoveWindowSubclass(target, guard_subclass, subclass_id);
            delete state;
        }
    } else {
        delete state;
    }
}
}  // namespace

extern "C" __declspec(dllexport)
LRESULT CALLBACK CoolCatGetMsgHook(int code, WPARAM wparam, LPARAM lparam) {
    if (code >= 0 && lparam) {
        MSG* message = reinterpret_cast<MSG*>(lparam);
        if (message->message == message_id(INSTALL_MESSAGE, install_message)) {
            install_for_message(message);
            message->message = WM_NULL;
        }
    }
    return CallNextHookEx(nullptr, code, wparam, lparam);
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        module_handle = instance;
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
