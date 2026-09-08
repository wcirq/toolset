#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <imm.h>
#include <windowsx.h>
#include <cstdint>

namespace {
thread_local HWND target = nullptr, controller = nullptr;
thread_local ULONGLONG armed_until = 0, mouse_until = 0;
thread_local RECT button_rect{}, frame_rect{}, pressed_button{}, pressed_frame{};
thread_local bool have_button = false, have_frame = false;
thread_local HWND mouse_owner = nullptr;
thread_local bool ctrl_send = false, pending = false, swallowed = false;
UINT id(const wchar_t* name) { return RegisterWindowMessageW(name); }
bool down(int key) { return (GetKeyState(key) & 0x8000) != 0; }
bool composing(HWND hwnd) {
    if (!ImmIsIME(GetKeyboardLayout(0))) return false;
    HIMC context = ImmGetContext(hwnd);
    if (!context) return ImmIsIME(GetKeyboardLayout(0)) != FALSE;
    LONG length = ImmGetCompositionStringW(context, GCS_COMPSTR, nullptr, 0);
    ImmReleaseContext(hwnd, context);
    return length > 0 || length == IMM_ERROR_GENERAL;
}
POINT unpack(std::uintptr_t value) {
    return {static_cast<LONG>(value & 0xffffffff), static_cast<LONG>(value >> 32)};
}
RECT unpack_rect(WPARAM first, LPARAM last) {
    POINT a = unpack(first), b = unpack(static_cast<std::uintptr_t>(last));
    return {a.x, a.y, b.x, b.y};
}
bool physical_frame(RECT& rect) {
    auto previous = SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    if (!previous) return false;
    bool ok = GetWindowRect(target, &rect) != FALSE;
    SetThreadDpiAwarenessContext(previous);
    return ok;
}
bool button_hit(const MSG* msg) {
    RECT current{};
    if (!IsWindow(controller) || GetForegroundWindow() != target ||
        GetAncestor(msg->hwnd, GA_ROOT) != target || GetTickCount64() >= mouse_until ||
        !physical_frame(current) || !EqualRect(&current, &frame_rect)) return false;
    POINT point{GET_X_LPARAM(msg->lParam), GET_Y_LPARAM(msg->lParam)};
    if (!ClientToScreen(msg->hwnd, &point) ||
        !LogicalToPhysicalPointForPerMonitorDPI(msg->hwnd, &point)) return false;
    return PtInRect(&button_rect, point) != FALSE;
}
void release_mouse() {
    HWND owner = mouse_owner;
    mouse_owner = nullptr;
    if (owner && GetCapture() == owner) ReleaseCapture();
}
bool request_review(bool mouse) {
    if (pending) return true;
    if (!PostMessageW(controller, id(mouse ? L"CoolCat.SendGuard.Click.v1" :
                                    L"CoolCat.SendGuard.Request.v1"),
                      reinterpret_cast<WPARAM>(target), GetCurrentProcessId())) return false;
    pending = true;
    return true;
}

}

// Exposes only readiness flags, never keyboard or message text (local diagnostics).
extern "C" __declspec(dllexport)
DWORD CoolCatSendReadiness() {
    return (IsWindow(controller) ? 1 : 0) |
           (GetForegroundWindow() == target ? 2 : 0) |
           (GetTickCount64() < armed_until ? 4 : 0) |
           ((down(VK_SHIFT) || down(VK_MENU) || down(VK_LWIN) || down(VK_RWIN)) ? 8 : 0) |
           (down(VK_CONTROL) == ctrl_send ? 16 : 0) |
           (composing(GetFocus()) ? 32 : 0);
}

extern "C" __declspec(dllexport)
LRESULT CALLBACK CoolCatSendHook(int code, WPARAM removed, LPARAM data) {
    if (code < 0 || removed != PM_REMOVE || !data)
        return CallNextHookEx(nullptr, code, removed, data);
    MSG* msg = reinterpret_cast<MSG*>(data);
    if (msg->message == id(L"CoolCat.SendGuard.Install.v1")) {
        target = msg->hwnd; controller = reinterpret_cast<HWND>(msg->wParam);
        armed_until = mouse_until = 0;
        have_button = have_frame = false;
        release_mouse();
        pending = swallowed = false;
        PostMessageW(controller, id(L"CoolCat.SendGuard.Ready.v1"),
                     reinterpret_cast<WPARAM>(target), GetCurrentProcessId());
        msg->message = WM_NULL;
    } else if (msg->hwnd == target && msg->message == id(L"CoolCat.SendGuard.Pulse.v1")) {
        if (reinterpret_cast<HWND>(msg->wParam) == controller) {
            armed_until = (msg->lParam & 1) ? GetTickCount64() + 450 : 0;
            ctrl_send = (msg->lParam & 2) != 0;
        }
        msg->message = WM_NULL;
    } else if (msg->hwnd == target && msg->message == id(L"CoolCat.SendGuard.Button.v1")) {
        mouse_until = 0;
        have_frame = false;
        button_rect = unpack_rect(msg->wParam, msg->lParam);
        have_button = !IsRectEmpty(&button_rect);
        msg->message = WM_NULL;
    } else if (msg->hwnd == target && msg->message == id(L"CoolCat.SendGuard.Frame.v1")) {
        frame_rect = unpack_rect(msg->wParam, msg->lParam);
        have_frame = !IsRectEmpty(&frame_rect);
        msg->message = WM_NULL;
    } else if (msg->hwnd == target && msg->message == id(L"CoolCat.SendGuard.Mouse.v1")) {
        RECT overlap{};
        if (reinterpret_cast<HWND>(msg->wParam) == controller) {
            mouse_until = msg->lParam && have_frame && have_button &&
                IntersectRect(&overlap, &button_rect, &frame_rect) &&
                EqualRect(&overlap, &button_rect) ? GetTickCount64() + 450 : 0;
        }
        msg->message = WM_NULL;
    } else if (msg->hwnd == target && msg->message == id(L"CoolCat.SendGuard.Cancel.v1")) {
        pending = false; msg->message = WM_NULL;
    } else if (msg->hwnd == target && msg->message == id(L"CoolCat.SendGuard.Uninstall.v1")) {
        release_mouse();
        target = controller = nullptr;
        armed_until = mouse_until = 0;
        pending = false;
        msg->message = WM_NULL;
    } else if (msg->message == WM_LBUTTONDOWN || msg->message == WM_LBUTTONDBLCLK) {
        release_mouse();
        if (button_hit(msg)) {
            mouse_owner = msg->hwnd;
            pressed_button = button_rect;
            pressed_frame = frame_rect;
            SetCapture(mouse_owner);
            msg->message = WM_NULL;
        }
    } else if (msg->message == WM_LBUTTONUP && mouse_owner) {
        const bool click = button_hit(msg) && EqualRect(&pressed_button, &button_rect) &&
                           EqualRect(&pressed_frame, &frame_rect);
        release_mouse();
        if (click) request_review(true);
        // Consume the matching release even if dragging out, or the cache expired.
        msg->message = WM_NULL;
    } else if (msg->wParam == VK_RETURN && msg->message == WM_KEYUP && swallowed) {
        swallowed = false; msg->message = WM_NULL;
    } else if (msg->wParam == VK_RETURN && msg->message == WM_KEYDOWN) {
        if (swallowed) { msg->message = WM_NULL; }
        else if (IsWindow(controller) && GetForegroundWindow() == target &&
                 GetAncestor(msg->hwnd, GA_ROOT) == target &&
                 GetTickCount64() < armed_until &&
                 !down(VK_SHIFT) && !down(VK_MENU) && !down(VK_LWIN) && !down(VK_RWIN) &&
                 down(VK_CONTROL) == ctrl_send && !composing(GetFocus())) {
            // No UI Automation or network call in this GUI-thread hook.
            if (request_review(false)) {
                swallowed = true;
                msg->message = WM_NULL;  // Before TranslateMessage: no WM_CHAR is generated.
            }
        }
    }
    return CallNextHookEx(nullptr, code, removed, data);
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(instance);
    return TRUE;
}
