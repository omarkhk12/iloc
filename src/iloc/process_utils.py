import os
import sys

_WINDOWS = sys.platform == "win32"

if _WINDOWS:
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259

    def is_pid_alive(pid: int | None) -> bool:
        if not pid:
            return False
        # Note: os.kill(pid, 0) is NOT a safe existence probe on Windows --
        # signal value 0 is CTRL_C_EVENT there, so it would actually attempt
        # to send a break event instead of just checking. Use the Win32 API
        # directly instead.
        handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not _kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == _STILL_ACTIVE
        finally:
            _kernel32.CloseHandle(handle)

else:

    def is_pid_alive(pid: int | None) -> bool:
        if not pid:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but is owned by someone else -- still alive.
            return True
        return True
