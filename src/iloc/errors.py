"""Friendly, actionable translations of the pymobiledevice3 failures iloc is
most likely to hit.

Message text deliberately matches what pymobiledevice3's own CLI
(pymobiledevice3/__main__.py's invoke_cli_with_error_handling) prints for the
same exceptions, confirmed by reading that source directly -- so iloc's
guidance stays consistent with the underlying tool instead of guessing at
wording.

Two matching paths are needed because iloc talks to pymobiledevice3 two
different ways:

- The tunnel is created by running `pymobiledevice3 lockdown start-tunnel`
  as a *subprocess*. Its own CLI error handler already turns exceptions into
  one of the log lines below, so we recognize failures as substrings of its
  captured output (`explain_log_text`).
- The location simulation itself is done by iloc.holder importing
  pymobiledevice3 as a *library*, so its errors are real Python exception
  objects we can match by type (`explain_exception`).
"""

import sys

from pymobiledevice3.exceptions import (
    AccessDeniedError,
    ConnectionFailedError,
    ConnectionFailedToUsbmuxdError,
    ConnectionTerminatedError,
    DeveloperModeIsNotEnabledError,
    DeviceNotFoundError,
    NoDeviceConnectedError,
    NotPairedError,
    PasswordRequiredError,
    UserDeniedPairingError,
)

_NO_DEVICE = "No iPhone was detected. Check the USB cable, unlock the phone, and confirm 'Trust This Computer' if it's prompted."
_CONN_TERMINATED = "The connection to the iPhone was terminated abruptly. Reconnect the cable and try again."
_NOT_PAIRED = "This Mac isn't paired with the iPhone. Reconnect the cable and tap 'Trust This Computer' on the device."
_PAIRING_DENIED = "Pairing was declined on the iPhone. Reconnect the cable and tap 'Trust' when prompted."
_LOCKED = "The iPhone is locked. Unlock it and try again."
_DEV_MODE_OFF = (
    "Developer Mode is off. Enable it: Settings -> Privacy & Security -> Developer Mode "
    "-> toggle on -> Restart -> confirm 'Turn On' after the phone restarts and unlocks."
)
_NO_USBMUXD = "Couldn't reach usbmuxd, the local macOS service used to talk to the iPhone over USB."
_CONN_FAILED = "Failed to connect to the device's service port. Try reconnecting the cable."
_NEEDS_ROOT = (
    "This operation needs Administrator privileges, to create the device tunnel's network "
    "interface. Re-run from an Administrator PowerShell or Command Prompt."
    if sys.platform == "win32"
    else "This operation needs root, to create the device tunnel's network interface. Re-run with sudo."
)
_NOT_FOUND = "The requested device wasn't found. Is the right iPhone connected?"

# Exception type -> friendly message. Checked in order, so subclasses must
# come before their base classes.
_EXCEPTION_MESSAGES: tuple[tuple[type[BaseException], str], ...] = (
    (NoDeviceConnectedError, _NO_DEVICE),
    (ConnectionTerminatedError, _CONN_TERMINATED),
    (UserDeniedPairingError, _PAIRING_DENIED),
    (NotPairedError, _NOT_PAIRED),
    (PasswordRequiredError, _LOCKED),
    (DeveloperModeIsNotEnabledError, _DEV_MODE_OFF),
    (ConnectionFailedToUsbmuxdError, _NO_USBMUXD),
    (ConnectionFailedError, _CONN_FAILED),
    (AccessDeniedError, _NEEDS_ROOT),
    (DeviceNotFoundError, _NOT_FOUND),
)

# Substrings pymobiledevice3's own CLI logs for these same failures --
# recognized in captured subprocess output.
_LOG_HINTS: tuple[tuple[str, str], ...] = (
    ("Device is not connected", _NO_DEVICE),
    ("Connection was terminated abruptly", _CONN_TERMINATED),
    ("Device is not paired", _NOT_PAIRED),
    ("User refused to trust this computer", _PAIRING_DENIED),
    ("Developer Mode is disabled", _DEV_MODE_OFF),
    ("Failed to connect to usbmuxd", _NO_USBMUXD),
    ("Device is password protected", _LOCKED),
    ("Device not found", _NOT_FOUND),
)


def explain_exception(exc: BaseException) -> str | None:
    """Friendly message for a known pymobiledevice3 exception object, or None."""
    for exc_type, message in _EXCEPTION_MESSAGES:
        if isinstance(exc, exc_type):
            return message
    return None


def explain_log_text(text: str) -> str | None:
    """Friendly message if captured subprocess output contains a known
    pymobiledevice3 CLI error string, or None."""
    for needle, message in _LOG_HINTS:
        if needle in text:
            return message
    return None


def format_failure(raw_output: str) -> str:
    """Build a user-facing error message from captured subprocess output:
    a friendly headline (if recognized) followed by the raw details."""
    hint = explain_log_text(raw_output)
    if hint:
        return f"{hint}\n\nDetails:\n{raw_output.strip()}"
    return raw_output.strip()
