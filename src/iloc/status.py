import asyncio

from pymobiledevice3.lockdown import create_using_usbmux

from .errors import explain_exception
from .paths import load_state
from .process_utils import is_pid_alive
from .tunnel import get_active_tunnel


async def _gather_device_status() -> dict:
    info: dict = {"connected": False, "error": None}

    try:
        lockdown = await create_using_usbmux()
    except Exception as e:
        info["error"] = explain_exception(e) or str(e)
        return info

    try:
        info["connected"] = True
        info["name"] = lockdown.all_values.get("DeviceName")
        info["udid"] = lockdown.udid
        info["product_type"] = lockdown.product_type
        info["ios_version"] = lockdown.product_version
        info["developer_mode_enabled"] = await lockdown.get_developer_mode_status()
    finally:
        await lockdown.close()

    return info


def get_device_status() -> dict:
    return asyncio.run(_gather_device_status())


def get_simulation_status() -> dict:
    state = load_state()
    tunnel = get_active_tunnel()
    holder_pid = state.get("holder_pid")
    simulation_active = bool(holder_pid and is_pid_alive(holder_pid))
    return {
        "tunnel_active": tunnel is not None,
        "simulation_active": simulation_active,
        "latitude": state.get("latitude") if simulation_active else None,
        "longitude": state.get("longitude") if simulation_active else None,
    }
