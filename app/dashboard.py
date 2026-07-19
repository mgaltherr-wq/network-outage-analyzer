"""Browser dashboard for managing monitored devices and viewing weather context."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import app.ip_inventory as inventory_module


add_device = inventory_module.add_device
assign_location = inventory_module.assign_location
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


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return _DASHBOARD_FILE.read_text(encoding="utf-8")


@app.get("/api/devices")
def list_devices():
    return {"devices": inventory_module.load_devices(get_inventory_path())}


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
