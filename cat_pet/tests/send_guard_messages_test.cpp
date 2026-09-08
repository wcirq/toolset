// Deterministic native message test: hidden owned windows, no real mouse input.
// Only foreground selection is substituted; geometry and hook code are real.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cassert>
#include <iostream>
HWND test_foreground = nullptr;
HWND WINAPI TestForegroundWindow() { return test_foreground; }
#define GetForegroundWindow TestForegroundWindow
#include "../native/send_guard/send_guard.cpp"
#undef GetForegroundWindow

WPARAM point32(LONG x, LONG y) {
    return static_cast<WPARAM>(static_cast<DWORD>(x)) |
           (static_cast<WPARAM>(static_cast<DWORD>(y)) << 32);
}
MSG deliver(HWND hwnd, UINT message, WPARAM wparam=0, LPARAM lparam=0) {
    MSG msg{}; msg.hwnd=hwnd; msg.message=message; msg.wParam=wparam; msg.lParam=lparam;
    CoolCatSendHook(HC_ACTION, PM_REMOVE, reinterpret_cast<LPARAM>(&msg));
    return msg;
}
void require(bool ok, const char* name) {
    if (!ok) { std::cerr << "FAIL: " << name << '\n'; ExitProcess(1); }
}

int main() {
    HWND root=CreateWindowExW(0,L"STATIC",L"hidden local test",WS_OVERLAPPEDWINDOW,
                             -700,100,600,400,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
    HWND button=CreateWindowExW(0,L"BUTTON",L"local send",WS_CHILD,300,200,100,40,
                               root,nullptr,GetModuleHandleW(nullptr),nullptr);
    HWND receiver=CreateWindowExW(0,L"STATIC",L"receiver",0,0,0,1,1,
                                 HWND_MESSAGE,nullptr,GetModuleHandleW(nullptr),nullptr);
    require(root && button && receiver,"create owned windows");
    test_foreground=root;
    deliver(root,id(L"CoolCat.SendGuard.Install.v1"),reinterpret_cast<WPARAM>(receiver));
    RECT frame{}; require(physical_frame(frame),"physical frame");
    POINT a{0,0},b{100,40};
    ClientToScreen(button,&a); ClientToScreen(button,&b);
    LogicalToPhysicalPointForPerMonitorDPI(button,&a);
    LogicalToPhysicalPointForPerMonitorDPI(button,&b);
    auto arm=[&]() {
        deliver(root,id(L"CoolCat.SendGuard.Button.v1"),point32(a.x,a.y),point32(b.x,b.y));
        deliver(root,id(L"CoolCat.SendGuard.Frame.v1"),point32(frame.left,frame.top),point32(frame.right,frame.bottom));
        deliver(root,id(L"CoolCat.SendGuard.Mouse.v1"),reinterpret_cast<WPARAM>(receiver),1);
    };
    auto cancel=[&]() { deliver(root,id(L"CoolCat.SendGuard.Cancel.v1")); };
    auto mouse=[&](UINT message,int x=20,int y=20) {
        return deliver(button,message,MK_LBUTTON,MAKELPARAM(x,y)).message;
    };
    arm();
    require(mouse(WM_LBUTTONDOWN)==WM_NULL,"mouse down suppressed without keyboard focus");
    require(!pending,"no review until release");
    require(mouse(WM_LBUTTONUP)==WM_NULL && pending,"release requests review");
    MSG notification{};
    require(PeekMessageW(&notification,receiver,id(L"CoolCat.SendGuard.Click.v1"),id(L"CoolCat.SendGuard.Click.v1"),PM_REMOVE),"click notification");
    arm(); mouse(WM_LBUTTONDBLCLK); mouse(WM_LBUTTONUP);
    require(!PeekMessageW(&notification,receiver,id(L"CoolCat.SendGuard.Click.v1"),id(L"CoolCat.SendGuard.Click.v1"),PM_REMOVE),"double click deduplicated");
    cancel(); arm(); mouse(WM_LBUTTONDOWN);
    require(mouse(WM_LBUTTONUP,150)==WM_NULL && !pending,"drag out cancels");
    arm(); require(mouse(WM_LBUTTONDOWN,-20)==WM_LBUTTONDOWN,"outside passes");
    arm(); mouse_until=0;
    require(mouse(WM_LBUTTONDOWN)==WM_LBUTTONDOWN,"expired region passes");
    arm(); test_foreground=nullptr;
    require(mouse(WM_LBUTTONDOWN)==WM_LBUTTONDOWN,"other foreground passes");
    test_foreground=root; arm();
    frame_rect.left+=1;
    require(mouse(WM_LBUTTONDOWN)==WM_LBUTTONDOWN,"stale frame passes");
    arm(); deliver(root,id(L"CoolCat.SendGuard.Mouse.v1"),reinterpret_cast<WPARAM>(receiver),0);
    require(mouse(WM_LBUTTONDOWN)==WM_LBUTTONDOWN,"disable passes");
    arm();
    require(deliver(button,BM_CLICK).message==BM_CLICK,"programmatic confirmation bypasses mouse hook");
    deliver(root,id(L"CoolCat.SendGuard.Uninstall.v1"));
    require(mouse(WM_LBUTTONDOWN)==WM_LBUTTONDOWN,"uninstall passes");
    DestroyWindow(receiver); DestroyWindow(root);
    std::cout << "PASS: 11 native mouse hook scenarios, negative screen coordinates; foreground mocked\n";
}
