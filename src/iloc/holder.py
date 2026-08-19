"""Background process that opens a DVT connection, sets the simulated
location, and holds the connection open until it receives SIGTERM.

This is a separate process (not just a function) because the simulated
location is tied to the lifetime of the DVT connection: the moment the
connection closes, iOS reverts to the real GPS fix. To make `iloc set`
return control to the shell immediately, something has to keep that
connection alive in the background -- this script is that something.
It's launched by iloc.simulate.start_simulated_location() and stopped by
iloc.simulate.stop_simulated_location().

Not meant to be run directly by users -- invoked internally as:
    python -m iloc.holder --host <host> --port <port> --lat <lat> --lon <lon>
"""

import argparse
import asyncio
import signal
import sys

from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

from .errors import explain_exception

_WINDOWS = sys.platform == "win32"


async def hold_location(host: str, port: int, latitude: float, longitude: float) -> None:
    rsd = RemoteServiceDiscoveryService((host, port))
    await rsd.connect()
    try:
        async with DvtProvider(rsd) as dvt, LocationSimulation(dvt) as location_simulation:
            await location_simulation.set(latitude, longitude)
            # Signals the parent process (watching our log file) that the
            # location was applied successfully and it can stop waiting.
            print("READY", flush=True)

            if _WINDOWS:
                # asyncio's add_signal_handler() isn't supported on Windows'
                # event loop, and there's no cross-process equivalent of a
                # graceful POSIX SIGTERM here anyway -- the parent
                # (iloc.simulate.stop_simulated_location) instead terminates
                # this process outright, which the OS-level socket teardown
                # makes just as effective at reverting the device's GPS.
                # Just block until that happens.
                await asyncio.Event().wait()
            else:
                stop_event = asyncio.Event()
                loop = asyncio.get_running_loop()
                for sig in (signal.SIGTERM, signal.SIGINT):
                    loop.add_signal_handler(sig, stop_event.set)
                await stop_event.wait()
            # Falling out of the `async with` blocks here closes the DVT
            # connection, which is what causes the device to revert to its
            # real GPS location.
    finally:
        await rsd.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--lat", required=True, type=float)
    parser.add_argument("--lon", required=True, type=float)
    args = parser.parse_args()

    try:
        asyncio.run(hold_location(args.host, args.port, args.lat, args.lon))
    except Exception as e:
        hint = explain_exception(e)
        if hint:
            print(f"ERROR: {hint}", file=sys.stderr, flush=True)
        else:
            print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
