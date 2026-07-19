"""Browser dashboard for managing monitored devices and viewing weather context."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.ip_inventory import add_ip_address, load_ip_addresses, remove_ip_address, save_ip_addresses


app = FastAPI(title="SignalWatch Dashboard", docs_url=None, redoc_url=None)
_DASHBOARD_FILE = Path(__file__).with_name("dashboard.html")


class DeviceRequest(BaseModel):
    ip_address: str


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return _DASHBOARD_FILE.read_text(encoding="utf-8")


@app.get("/api/devices")
def list_devices():
    return {"devices": load_ip_addresses()}


@app.post("/api/devices", status_code=201)
def create_device(device: DeviceRequest):
    try:
        devices = load_ip_addresses()
        updated, added = add_ip_address(devices, device.ip_address)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Enter a valid IPv4 or IPv6 address.") from exc

    if not added:
        raise HTTPException(status_code=409, detail="That device is already monitored.")

    return {"devices": save_ip_addresses(updated)}


@app.delete("/api/devices/{ip_address}")
def delete_device(ip_address: str):
    try:
        devices = load_ip_addresses()
        updated, removed = remove_ip_address(devices, ip_address)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid device address.") from exc

    if not removed:
        raise HTTPException(status_code=404, detail="Device was not found.")

    return {"devices": save_ip_addresses(updated)}
