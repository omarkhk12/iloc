"""Manages the iOS 17+ RemoteXPC tunnel that developer services (like DVT
location simulation) are reached through.

Creating the tunnel requires root, since it sets up a real kernel network
interface (utun) on the Mac. We shell out to pymobiledevice3's own
`lockdown start-tunnel --script-mode` for that part rather than
reimplementing the interface/routing setup ourselves -- that's
internal, fast-moving plumbing that's best left to the library that
already tests it against real devices.
"""

import subprocess
import sys
import time
from pathlib import Path

from .errors import format_failure
from .paths import TUNNEL_LOG, claim_for_real_user, ensure_state_dir, load_state, save_state
from .process_utils import is_pid_alive


class TunnelError(RuntimeError):
    pass


def get_active_tunnel() -> tuple[str, int] | None:
    """Return (host, port) of a tunnel we previously started and is still alive, or None."""
    state = load_state()
    pid = state.get("tunnel_pid")
    host = state.get("tunnel_host")
    port = state.get("tunnel_port")
    if pid and host and port and is_pid_alive(pid):
        return host, port
    return None


def start_tunnel(timeout: float = 20.0) -> tuple[str, int]:
    """Return (host, port) of a running tunnel, starting a new one if needed."""
    existing = get_active_tunnel()
    if existing is not None:
        return existing

    ensure_state_dir()
    log_file = open(TUNNEL_LOG, "wb")
    claim_for_real_user(TUNNEL_LOG)
    proc = subprocess.Popen(
        [sys.executable, "-m", "pymobiledevice3", "lockdown", "start-tunnel", "--script-mode"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    host, port = _wait_for_rsd_line(TUNNEL_LOG, proc, timeout)

    state = load_state()
    state["tunnel_pid"] = proc.pid
    state["tunnel_host"] = host
    state["tunnel_port"] = port
    save_state(state)
    return host, port


def _wait_for_rsd_line(log_path: Path, proc: subprocess.Popen, timeout: float) -> tuple[str, int]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            text = log_path.read_text(errors="ignore") if log_path.exists() else ""
            raise TunnelError(format_failure(text or "pymobiledevice3 lockdown start-tunnel exited unexpectedly."))
        text = log_path.read_text(errors="ignore") if log_path.exists() else ""
        for line in text.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].isdigit():
                return parts[0], int(parts[1])
        time.sleep(0.3)
    raise TunnelError(
        f"Timed out waiting for the tunnel to come up after {timeout:.0f}s. "
        f"This usually means the iPhone needs to be unlocked, or a 'Trust This Computer?' "
        f"prompt is waiting on the device. See {log_path} for the raw log."
    )
