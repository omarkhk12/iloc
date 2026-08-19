import os
import subprocess
import sys

import click

from .map_picker import MapPickerCancelledError, pick_location_from_map
from .simulate import SimulationError, start_simulated_location, stop_simulated_location
from .status import get_device_status, get_simulation_status
from .tunnel import TunnelError
from .validation import InvalidCoordinatesError, validate_coordinates

_WINDOWS = sys.platform == "win32"


def _is_admin() -> bool:
    if _WINDOWS:
        import ctypes

        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except OSError:
            return False
    return os.geteuid() == 0


def _require_root() -> None:
    if _is_admin():
        return
    if _WINDOWS:
        click.secho(
            "iloc needs Administrator privileges to create the device tunnel "
            "(it sets up a real network interface on your PC).",
            fg="red",
            err=True,
        )
        click.echo("Re-run this command from an Administrator PowerShell or Command Prompt.", err=True)
    else:
        click.secho(
            "iloc needs root privileges to create the device tunnel "
            "(it sets up a real network interface on your Mac).",
            fg="red",
            err=True,
        )
        click.echo("Re-run with: sudo " + " ".join([sys.argv[0]] + sys.argv[1:]), err=True)
    raise SystemExit(1)


@click.group()
def cli() -> None:
    """iloc -- simulate the location a connected iPhone reports, for security research on your own device."""


@cli.command("set", context_settings={"ignore_unknown_options": True})
@click.argument("latitude", type=float)
@click.argument("longitude", type=float)
def set_command(latitude: float, longitude: float) -> None:
    """Set the iPhone's simulated location to LATITUDE LONGITUDE."""
    _require_root()

    try:
        validate_coordinates(latitude, longitude)
    except InvalidCoordinatesError as e:
        raise click.UsageError(str(e))

    try:
        start_simulated_location(latitude, longitude)
    except (SimulationError, TunnelError) as e:
        raise click.ClickException(str(e))

    click.secho(f"Simulated location set to {latitude}, {longitude}.", fg="green")


@cli.command("clear")
def clear_command() -> None:
    """Stop simulating location and restore the iPhone's real GPS."""
    _require_root()

    stopped = stop_simulated_location()
    if stopped:
        click.secho("Simulation stopped. Device should report its real location again.", fg="green")
    else:
        click.echo("No active simulation to stop.")


@cli.command("pick")
def pick_command() -> None:
    """Open a map to visually choose a location, then simulate it.

    Runs unprivileged (a root/Administrator process can't open GUI windows).
    On macOS/Linux it then shells out to `sudo iloc set` for the privileged
    part once you've confirmed a point. Windows has no inline sudo
    equivalent, so there it prints the `iloc set` command for you to run
    yourself from an Administrator terminal.
    """
    sim = get_simulation_status()
    center_lat = sim["latitude"] if sim["simulation_active"] else 20.0
    center_lon = sim["longitude"] if sim["simulation_active"] else 0.0

    try:
        latitude, longitude = pick_location_from_map(center_lat, center_lon)
    except MapPickerCancelledError as e:
        raise click.ClickException(str(e))

    click.echo(f"Selected {latitude:.6f}, {longitude:.6f}.")

    if _WINDOWS:
        click.echo("Run this from an Administrator PowerShell or Command Prompt:")
        click.secho(f"  iloc set {latitude} {longitude}", fg="green")
        return

    click.echo("Applying (you may be asked for your password)...")
    result = subprocess.run(
        ["sudo", sys.executable, "-m", "iloc.cli", "set", str(latitude), str(longitude)]
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


@cli.command("status")
def status_command() -> None:
    """Show device connection, Developer Mode, and simulation status."""
    device = get_device_status()
    sim = get_simulation_status()

    if not device["connected"]:
        click.secho("Device: not connected", fg="red")
        if device["error"]:
            click.echo(f"  {device['error']}")
    else:
        click.secho("Device: connected", fg="green")
        click.echo(f"  Name:           {device['name']}")
        click.echo(f"  Model:          {device['product_type']}")
        click.echo(f"  iOS version:    {device['ios_version']}")
        click.echo(f"  UDID:           {device['udid']}")
        dev_mode = device["developer_mode_enabled"]
        click.secho(
            f"  Developer Mode: {'on' if dev_mode else 'off'}",
            fg="green" if dev_mode else "yellow",
        )

    click.echo()
    click.secho(
        f"Tunnel:     {'active' if sim['tunnel_active'] else 'inactive'}",
        fg="green" if sim["tunnel_active"] else "white",
    )
    if sim["simulation_active"]:
        click.secho(f"Simulation: ACTIVE at {sim['latitude']}, {sim['longitude']}", fg="green")
    else:
        click.echo("Simulation: inactive (reporting real GPS)")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
