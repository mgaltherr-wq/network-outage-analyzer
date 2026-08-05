"""Browser dashboard for managing monitored devices and viewing weather context."""

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import app.ip_inventory as inventory_module
from app.analysis import correlator
from app.config import SNMP_COMMUNITY, SNMP_TIMEOUT_SECONDS, SNMP_VERSION
from app.services.network_outages import check_network_outage
from app.services.power_outages import check_power_outage
from app.services.reachability import check_devices
from app.services.weather import geocode_location, get_weather


add_device = inventory_module.add_device
assign_location = inventory_module.assign_location
lookup_location_snmp = inventory_module.lookup_location_snmp
remove_device = inventory_module.remove_device
save_devices = inventory_module.save_devices


app = FastAPI(title="SignalWatch Dashboard", docs_url=None, redoc_url=None)
_DASHBOARD_FILE = Path(__file__).with_name("dashboard.html")
_INVENTORY_PATH = None


def get_inventory_path():
    return _INVENTORY_PATH or inventory_module.DEFAULT_IP_LIST_PATH


class DeviceRequest(BaseModel):
    ip_address: str
    location: str | None = None


@lru_cache(maxsize=256)
def _cached_geocode(location: str):
    return geocode_location(location)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return _DASHBOARD_FILE.read_text(encoding="utf-8")


@app.get("/api/devices")
def list_devices():
    return {"devices": inventory_module.load_devices(get_inventory_path())}


@app.post("/api/devices/refresh-snmp")
def refresh_device_locations_from_snmp():
    devices = inventory_module.load_devices(get_inventory_path())
    updated_addresses = []
    for device in devices:
        location = lookup_location_snmp(
            device["ip_address"],
            community=SNMP_COMMUNITY,
            timeout=SNMP_TIMEOUT_SECONDS,
            version=SNMP_VERSION,
        )
        if not location:
            continue
        if device.get("location") != location or device.get("location_source") != "snmp":
            device["location"] = location
            device["location_source"] = "snmp"
            updated_addresses.append(device["ip_address"])

    if updated_addresses:
        devices = save_devices(devices, get_inventory_path())
        _cached_geocode.cache_clear()

    return {"devices": devices, "updated": updated_addresses}


def _assess_location_confidence(coordinates):
    """Best-effort weather/network/power confidence breakdown for a location.

    Each external check is isolated so one flaky source doesn't take down the
    others; returns None only if weather (the one source we already depend
    on elsewhere) is unavailable.
    """
    try:
        weather = get_weather(coordinates["latitude"], coordinates["longitude"])
    except Exception:
        return None

    try:
        network_result = check_network_outage(coordinates.get("country"))
    except Exception:
        network_result = {"checked": False, "detected": False, "detail": "Network outage check failed"}

    try:
        power_result = check_power_outage(coordinates["latitude"], coordinates["longitude"])
    except Exception:
        power_result = {"checked": False, "detected": False, "detail": "Power outage check failed"}

    return correlator.assess_outage_sources(weather, network_result, power_result)


@app.get("/api/device-locations")
def list_device_locations():
    grouped = {}
    for device in inventory_module.load_devices(get_inventory_path()):
        location = device.get("location", "").strip()
        if not location:
            continue
        group = grouped.setdefault(
            location.casefold(),
            {"location": location, "devices": []},
        )
        group["devices"].append(device["ip_address"])

    markers = []
    for group in grouped.values():
        try:
            coordinates = _cached_geocode(group["location"])
        except Exception:
            coordinates = None
        if coordinates:
            reachable, unreachable = check_devices(group["devices"])
            if not unreachable:
                status = "up"
            elif not reachable:
                status = "down"
            else:
                status = "partial"

            marker = {
                **group,
                **coordinates,
                "status": status,
                "reachable": len(reachable),
                "unreachable": len(unreachable),
            }

            percent_down = len(unreachable) / len(group["devices"])
            if percent_down >= correlator.OUTAGE_THRESHOLD:
                confidence = _assess_location_confidence(coordinates)
                if confidence:
                    marker["confidence"] = confidence

            markers.append(marker)

    return {"locations": markers}


@app.post("/api/devices", status_code=201)
def create_device(device: DeviceRequest):
    try:
        devices = inventory_module.load_devices(get_inventory_path())
        updated, added, _ = add_device(devices, device.ip_address, device.location or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Enter a valid IPv4 or IPv6 address.") from exc

    if not added:
        raise HTTPException(status_code=409, detail="That device is already monitored.")

    return {"devices": save_devices(updated, get_inventory_path())}


@app.delete("/api/devices/{ip_address}")
def delete_device(ip_address: str):
    try:
        devices = inventory_module.load_devices(get_inventory_path())
        updated, removed = remove_device(devices, ip_address)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid device address.") from exc

    if not removed:
        raise HTTPException(status_code=404, detail="Device was not found.")

    return {"devices": save_devices(updated, get_inventory_path())}
