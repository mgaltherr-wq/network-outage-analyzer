"""Browser dashboard for managing monitored devices and viewing weather context."""

import ipaddress
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

import app.ip_inventory as inventory_module
from app import auth, config, settings_store
from app.analysis import correlator
from app.services import servicenow
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
_SETTINGS_FILE = Path(__file__).with_name("settings.html")
_LOGIN_FILE = Path(__file__).with_name("login.html")
_INVENTORY_PATH = None


def get_inventory_path():
    return _INVENTORY_PATH or inventory_module.DEFAULT_IP_LIST_PATH


class DeviceRequest(BaseModel):
    ip_address: str
    location: str | None = None


class SettingsUpdateRequest(BaseModel):
    values: dict[str, str]


class PasswordRequest(BaseModel):
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


# Everything else requires a valid session cookie; see require_login below.
_PUBLIC_PATHS = {"/login", "/api/auth/status", "/api/auth/login", "/api/auth/setup"}
_login_throttle = auth.LoginThrottle()


def _client_host(request):
    return request.client.host if request.client else ""


def _is_loopback_client(request):
    try:
        return ipaddress.ip_address(_client_host(request)).is_loopback
    except ValueError:
        return False


def _is_authenticated(request):
    return auth.verify_session_token(request.cookies.get(auth.SESSION_COOKIE))


def _set_session_cookie(request, response):
    response.set_cookie(
        auth.SESSION_COOKIE,
        auth.create_session_token(),
        max_age=auth.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )
    return response


@app.middleware("http")
async def require_login(request: Request, call_next):
    if request.url.path in _PUBLIC_PATHS or _is_authenticated(request):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Not authenticated."}, status_code=401)
    return RedirectResponse("/login", status_code=303)


@lru_cache(maxsize=256)
def _cached_geocode(location: str):
    return geocode_location(location)


# Tracks which locations already have an open ServiceNow ticket for the
# outage currently in progress, so a location crossing OUTAGE_THRESHOLD only
# triggers one search-or-create + comment per episode, not one every poll.
# Cleared when a location's percent_down drops back below the threshold.
_active_outage_tickets = {}


def _ensure_outage_ticket(location, ip_addresses, percent_down, confidence):
    key = location.casefold()
    if key in _active_outage_tickets:
        return _active_outage_tickets[key]

    try:
        ticket = servicenow.search_or_create_outage_incident(
            location, ip_addresses, percent_down, confidence
        )
    except Exception:
        return None

    _active_outage_tickets[key] = ticket
    return ticket


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return _DASHBOARD_FILE.read_text(encoding="utf-8")


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return _LOGIN_FILE.read_text(encoding="utf-8")


@app.get("/api/auth/status")
def auth_status(request: Request):
    password_set = auth.is_password_set()
    return {
        "password_set": password_set,
        # First-run setup is only offered to the machine the dashboard runs on,
        # so nobody else on the network can claim an unconfigured instance.
        "setup_allowed": not password_set and _is_loopback_client(request),
        "authenticated": _is_authenticated(request),
    }


@app.post("/api/auth/setup")
def setup_password(payload: PasswordRequest, request: Request):
    if auth.is_password_set():
        raise HTTPException(status_code=409, detail="A password is already set.")
    if not _is_loopback_client(request):
        raise HTTPException(
            status_code=403,
            detail="Set the first password from the machine running the dashboard, "
                   "or from the CLI settings menu.",
        )
    try:
        auth.set_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _set_session_cookie(request, JSONResponse({"ok": True}))


@app.post("/api/auth/login")
def login(payload: PasswordRequest, request: Request):
    client = _client_host(request)
    retry_after = _login_throttle.retry_after(client)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
    if not auth.verify_password(payload.password):
        _login_throttle.record_failure(client)
        raise HTTPException(status_code=401, detail="Incorrect password.")

    _login_throttle.reset(client)
    return _set_session_cookie(request, JSONResponse({"ok": True}))


@app.post("/api/auth/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.SESSION_COOKIE)
    return response


@app.post("/api/auth/password")
def change_password(payload: PasswordChangeRequest, request: Request):
    if not auth.verify_password(payload.current_password):
        raise HTTPException(status_code=403, detail="Current password is incorrect.")
    try:
        auth.set_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Changing the password invalidates every session, including this one.
    return _set_session_cookie(request, JSONResponse({"ok": True}))


@app.get("/settings", response_class=HTMLResponse)
def settings_page():
    return _SETTINGS_FILE.read_text(encoding="utf-8")


@app.get("/api/settings")
def get_settings():
    return {"settings": settings_store.get_settings()}


@app.put("/api/settings")
def update_settings(payload: SettingsUpdateRequest):
    try:
        updated = settings_store.update_settings(payload.values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"settings": updated}


@app.get("/api/devices")
def list_devices():
    return {"devices": inventory_module.load_devices(get_inventory_path())}


@app.get("/api/devices/status")
def device_status():
    devices = inventory_module.load_devices(get_inventory_path())
    ip_addresses = [device["ip_address"] for device in devices]
    reachable, _ = check_devices(ip_addresses)
    reachable_set = set(reachable)

    return {
        "devices": [
            {"ip_address": ip, "reachable": ip in reachable_set}
            for ip in ip_addresses
        ]
    }


@app.post("/api/devices/refresh-snmp")
def refresh_device_locations_from_snmp():
    devices = inventory_module.load_devices(get_inventory_path())
    updated_addresses = []
    for device in devices:
        location = lookup_location_snmp(
            device["ip_address"],
            community=config.SNMP_COMMUNITY,
            timeout=config.SNMP_TIMEOUT_SECONDS,
            version=config.SNMP_VERSION,
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

                ticket = _ensure_outage_ticket(
                    group["location"], group["devices"], percent_down, confidence
                )
                if ticket:
                    marker["ticket"] = ticket
            else:
                _active_outage_tickets.pop(group["location"].casefold(), None)

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
