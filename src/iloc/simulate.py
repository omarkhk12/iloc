import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from .errors import format_failure
from .paths import HOLDER_LOG, claim_for_real_user, ensure_state_dir, load_state, save_state
from .process_utils import is_pid_alive
from .tunnel import start_tunnel


class SimulationError(RuntimeError):
    pass


def start_simulated_location(latitude: float, longitude: float, timeout: float = 15.0) -> None:
    # Always start from a clean slate: an old holder from a previous `set`
    # would otherwise keep overriding the location we're about to apply.
    stop_simulated_location()

    host, port = start_tunnel()

    ensure_state_dir()
    log_file = open(HOLDER_LOG, "wb")
    claim_for_real_user(HOLDER_LOG)
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "iloc.holder",
            "--host", host, "--port", str(port),
            "--lat", str(latitude), "--lon", str(longitude),
        ],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    _wait_for_ready(HOLDER_LOG, proc, timeout)

    state = load_state()
    state["holder_pid"] = proc.pid
    state["latitude"] = latitude
    state["longitude"] = longitude
    save_state(state)


def _wait_for_ready(log_path: Path, proc: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            text = log_path.read_text(errors="ignore") if log_path.exists() else ""
            raise SimulationError(format_failure(text or "Location simulation process exited unexpectedly."))
        text = log_path.read_text(errors="ignore") if log_path.exists() else ""
        if "READY" in text.splitlines():
            return
        time.sleep(0.2)
    raise SimulationError(
        f"Timed out waiting for location simulation to start after {timeout:.0f}s. See {log_path} for the raw log."
    )


def stop_simulated_location() -> bool:
    """Stop any active simulation. Returns True if one was actually running."""
    state = load_state()
    pid = state.get("holder_pid")
    stopped = False
    if pid and is_pid_alive(pid):
        # On Windows, os.kill(pid, SIGTERM) already maps to TerminateProcess
        # (an immediate kill, not a graceful signal), so the process should
        # never still be alive by the time this loop finishes; SIGKILL also
        # doesn't exist there, hence the hasattr guard.
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            if not is_pid_alive(pid):
                break
            time.sleep(0.1)
        else:
            if hasattr(signal, "SIGKILL"):
                os.kill(pid, signal.SIGKILL)
        stopped = True
    state.pop("holder_pid", None)
    state.pop("latitude", None)
    state.pop("longitude", None)
    save_state(state)
    return stopped
