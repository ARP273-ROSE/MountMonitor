"""Windows virtual desktops: bring an alert to the desktop the user is on.

A wrong mount setting must be seen even when MountMonitor runs on another
virtual desktop (Windows 10/11 Task View). The documented COM interface
IVirtualDesktopManager lets a program move ITS OWN top-level windows to the
desktop of another window: the alert is moved to the desktop of the window
the user is working in. When that is not possible (shell window in front,
interface missing), the alert is forced to the foreground instead, which
makes Windows switch to MountMonitor's desktop.

Everything here is best effort: on other systems, or on any failure, the
functions return False and the alert simply shows where it is.
"""
import logging
import sys

logger = logging.getLogger(__name__)

_CLSID_MANAGER = '{aa509086-5ca9-4c25-8f95-589d3c07b48a}'
_IID_MANAGER = '{a5cd92ff-29be-454c-8d04-d82879fb3f1b}'
_interface = None


def _manager():
    """The IVirtualDesktopManager COM object (Windows only)."""
    global _interface
    from ctypes import POINTER, wintypes
    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
    from comtypes.client import CreateObject
    if _interface is None:
        class IVirtualDesktopManager(IUnknown):
            _iid_ = GUID(_IID_MANAGER)
            _methods_ = [
                COMMETHOD([], HRESULT, 'IsWindowOnCurrentVirtualDesktop',
                          (['in'], wintypes.HWND, 'topLevelWindow'),
                          (['out', 'retval'], POINTER(wintypes.BOOL), 'onCurrentDesktop')),
                COMMETHOD([], HRESULT, 'GetWindowDesktopId',
                          (['in'], wintypes.HWND, 'topLevelWindow'),
                          (['out', 'retval'], POINTER(GUID), 'desktopId')),
                COMMETHOD([], HRESULT, 'MoveWindowToDesktop',
                          (['in'], wintypes.HWND, 'topLevelWindow'),
                          (['in'], POINTER(GUID), 'desktopId')),
            ]
        _interface = IVirtualDesktopManager
    return CreateObject(GUID(_CLSID_MANAGER), interface=_interface)


def move_to_current_desktop(hwnd: int) -> bool:
    """Move our top-level window `hwnd` to the desktop the user is on.
    True when it is (or already was) there."""
    if sys.platform != 'win32' or not hwnd:
        return False
    try:
        import ctypes
        from comtypes import GUID
        mgr = _manager()
        if mgr.IsWindowOnCurrentVirtualDesktop(hwnd):
            return True
        front = ctypes.windll.user32.GetForegroundWindow()
        if not front:
            return False
        desktop = mgr.GetWindowDesktopId(front)
        if desktop == GUID():          # shell windows belong to no desktop
            return False
        mgr.MoveWindowToDesktop(hwnd, ctypes.byref(desktop))
        return bool(mgr.IsWindowOnCurrentVirtualDesktop(hwnd))
    except Exception as e:             # interface missing, access denied...
        logger.debug(f"Virtual desktop move failed: {e}")
        return False


def force_foreground(hwnd: int) -> bool:
    """Bring `hwnd` to the foreground even from the background; Windows
    switches to its virtual desktop. Uses the usual AttachThreadInput step,
    without which SetForegroundWindow only flashes the taskbar."""
    if sys.platform != 'win32' or not hwnd:
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        front = user32.GetForegroundWindow()
        ours = kernel32.GetCurrentThreadId()
        theirs = user32.GetWindowThreadProcessId(front, None) if front else 0
        if theirs and theirs != ours:
            user32.AttachThreadInput(theirs, ours, True)
        try:
            user32.ShowWindow(hwnd, 5)          # SW_SHOW
            ok = bool(user32.SetForegroundWindow(hwnd))
        finally:
            if theirs and theirs != ours:
                user32.AttachThreadInput(theirs, ours, False)
        return ok
    except Exception as e:
        logger.debug(f"Force foreground failed: {e}")
        return False


def bring_alert_to_user(hwnd: int) -> str:
    """'moved' (alert on the user's desktop), 'switched' (Windows switched to
    MountMonitor's desktop) or '' (left as is)."""
    if move_to_current_desktop(hwnd):
        force_foreground(hwnd)
        return 'moved'
    if force_foreground(hwnd):
        return 'switched'
    return ''
