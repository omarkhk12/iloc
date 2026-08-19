import json
import os
import sys
from pathlib import Path

_WINDOWS = sys.platform == "win32"

if not _WINDOWS:
    import pwd


def _resolve_home() -> Path:
    """The real (invoking) user's home directory, even when running elevated.

    `set`/`clear` require elevated privileges (to create the tunnel's network
    interface) while `status` does not. On POSIX this matters because sudo
    switches the effective user to root, so state written by `sudo iloc set`
    would otherwise land in root's home directory, and a later plain
    `iloc status` would look in the wrong place and report no active
    simulation even though one is running. On Windows, UAC elevation keeps
    the same user account (just a different token), so there's no such split
    -- Path.home() already resolves correctly either way.
    """
    if _WINDOWS:
        return Path.home()
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        try:
            return Path(pwd.getpwnam(sudo_user).pw_dir)
        except KeyError:
            pass
    return Path.home()


# Runtime state lives outside the git repo, in the invoking user's home directory.
STATE_DIR = _resolve_home() / ".iloc"
STATE_FILE = STATE_DIR / "state.json"
TUNNEL_LOG = STATE_DIR / "tunnel.log"
HOLDER_LOG = STATE_DIR / "holder.log"


def _real_uid_gid() -> tuple[int, int] | None:
    if _WINDOWS:
        return None
    uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
    if uid is not None and gid is not None:
        return int(uid), int(gid)
    return None


def claim_for_real_user(path: Path) -> None:
    """When running as root via sudo, hand ownership of `path` back to the
    invoking user, so a later non-sudo `iloc status` can read what
    `sudo iloc set` wrote. No-op on Windows: UAC elevation doesn't switch
    the user account, so there's no ownership split to fix."""
    if _WINDOWS:
        return
    ids = _real_uid_gid()
    if ids is not None and os.geteuid() == 0:
        os.chown(path, *ids)


def ensure_state_dir() -> None:
    STATE_DIR.mkdir(mode=0o700, exist_ok=True)
    claim_for_real_user(STATE_DIR)


def load_state() -> dict:
    ensure_state_dir()
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def save_state(state: dict) -> None:
    ensure_state_dir()
    STATE_FILE.write_text(json.dumps(state, indent=2))
    claim_for_real_user(STATE_FILE)
