"""Read-only inspection of Send button capability; never invokes it."""
import sys
from coolcat.platform.wechat import _with_uia


def inspect(a, u):
    root = a.ElementFromHandle(int(sys.argv[1]))
    buttons = root.FindAll(4, a.CreateAndCondition(a.CreatePropertyCondition(30003, 50000),
                                                a.CreatePropertyCondition(30005, '发送')))
    print('buttons', buttons.Length)
    if buttons.Length == 1:
        button = buttons.GetElement(0)
        print('enabled', button.CurrentIsEnabled, 'offscreen', button.CurrentIsOffscreen)
        try:
            pattern = button.GetCurrentPattern(10000).QueryInterface(u.IUIAutomationInvokePattern)
            print('invoke_available', bool(pattern))
        except Exception as exc:
            print(type(exc).__name__, str(exc))


if __name__ == '__main__':
    _with_uia(inspect)
