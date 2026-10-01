"""Browser dashboard for managing monitored devices and viewing weather context."""

import ipaddress
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

import app.ip_inventory as inventory_module
from app import auth, config, history, settings_store
from app.analysis import correlator
from app.services import servicenow
from app.services.device_monitor import ReachabilityMonitor
from app.services.network_outages import check_network_outage
from app.services.power_outages import check_power_outage
from app.services.reachability import check_devices
from app.services.weather import geocode_location, get_weather


add_device = inventory_module.add_device
assign_location = inventory_module.assign_location
lookup_location_snmp = inventory_module.lookup_location_snmp
remove_device = inventory_module.remove_device
save_devices = inventory_module.save_devices

log = logging.getLogger(__name__)


def _inventory_addresses():
    return [device["ip_address"] for device in inventory_module.load_devices(get_inventory_path())]


def _check_with_config(ip_addresses):
    return check_devices(
        ip_addresses,
        timeout_seconds=config.PING_TIMEOUT_SECONDS,
        max_concurrent=config.PING_CONCURRENCY,
    )


_history = history.HistoryStore()
_PRUNE_INTERVAL_SECONDS = history.HOUR
_last_prune = 0.0


def _record_sweep(results, checked_at):
    """Roll one sweep into the history store and open/close outage episodes.

    Runs from the background sweep rather than /api/device-locations so
    history accrues even when nobody has the dashboard open.
    """
    global _last_prune
    locations = {
        device["ip_address"]: device.get("location", "").strip()
        for device in inventory_module.load_devices(get_inventory_path())
    }
    _history.record_sweep(results, locations, checked_at)

    counts = {}  # casefolded location -> [display name, devices, unreachable]
    for ip, reachable in results.items():
        location = locations.get(ip)
        if not location:
            continue
        entry = counts.setdefault(location.casefold(), [location, 0, 0])
        entry[1] += 1
        entry[2] += not reachable
    _history.update_outages(
        {name: (down / total, total) for name, total, down in counts.values()},
        correlator.OUTAGE_THRESHOLD,
        checked_at,
    )

    if checked_at - _last_prune >= _PRUNE_INTERVAL_SECONDS:
        _history.prune(config.HISTORY_RETENTION_DAYS, now=checked_at)
        _last_prune = checked_at


# Looked up through lambdas so tests patching app.dashboard.check_devices /
# get_inventory_path / _history, and settings reloading app.config, take effect.
_monitor = ReachabilityMonitor(
    get_addresses=lambda: _inventory_addresses(),
    check=lambda ip_addresses: _check_with_config(ip_addresses),
    interval_seconds=lambda: config.REACHABILITY_INTERVAL_SECONDS,
    on_sweep=lambda results, checked_at: _record_sweep(results, checked_at),
)


@asynccontextmanager
async def _lifespan(_app):
    _history.close_stale_episodes()
    _monitor.start()
    try:
        yield
    finally:
        _monitor.stop()
        _history.close()


app = FastAPI(title="SignalWatch Dashboard", docs_url=None, redoc_url=None, lifespan=_lifespan)
_DASHBOARD_FILE = Path(__file__).with_name("dashboard.html")
_SETTINGS_FILE = Path(__file__).with_name("settings.html")
_LOGIN_FILE = Path(__file__).with_name("login.html")
_TRENDS_FILE = Path(__file__).with_name("trends.html")
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


@app.get("/trends", response_class=HTMLResponse)
def trends_page():
    return _TRENDS_FILE.read_text(encoding="utf-8")


# range -> (window, bucket). Hourly points up to a week, daily beyond that.
_TREND_RANGES = {
    "24h": (history.DAY, history.HOUR),
    "7d": (7 * history.DAY, history.HOUR),
    "30d": (30 * history.DAY, history.DAY),
    "90d": (90 * history.DAY, history.DAY),
}


@app.get("/api/trends")
def get_trends(range: str = "24h", utc_offset_minutes: int = 0):
    if range not in _TREND_RANGES:
        raise HTTPException(status_code=422, detail=f"range must be one of {', '.join(_TREND_RANGES)}.")
    if not -14 * 60 <= utc_offset_minutes <= 14 * 60:
        raise HTTPException(status_code=422, detail="utc_offset_minutes is out of range.")

    window, bucket = _TREND_RANGES[range]
    now = time.time()
    return {
        "range": range,
        "since": now - window,
        "until": now,
        "bucket_seconds": bucket,
        "retention_days": config.HISTORY_RETENTION_DAYS,
        **_history.trends(now - window, bucket, now=now, utc_offset_seconds=utc_offset_minutes * 60),
    }


@app.get("/api/devices")
def list_devices():
    return {"devices": inventory_module.load_devices(get_inventory_path())}


def _device_reachability(ip_addresses):
    """Return {ip: True/False/None}, None meaning not checked yet.

    Reads the background monitor's cache when it's running (the normal case
    under uvicorn). Without it (e.g. a TestClient used outside a `with`
    block), falls back to pinging synchronously.
    """
    if _monitor.running:
        return _monitor.snapshot(ip_addresses)
    reachable, _ = _check_with_config(ip_addresses)
    reachable_set = set(reachable)
    return {ip: ip in reachable_set for ip in ip_addresses}


@app.get("/api/devices/status")
def device_status():
    ip_addresses = _inventory_addresses()
    status = _device_reachability(ip_addresses)

    return {
        "devices": [
            {"ip_address": ip, "reachable": status[ip]}
            for ip in ip_addresses
        ]
    }


@app.post("/api/devices/refresh-snmp")
def refresh_device_locations_from_snmp():
    devices = inventory_module.load_devices(get_inventory_path())
    updated_addresses = []

    def lookup(device):
        return lookup_location_snmp(
            device["ip_address"],
            community=config.SNMP_COMMUNITY,
            timeout=config.SNMP_TIMEOUT_SECONDS,
            version=config.SNMP_VERSION,
        )

    # Queried in parallel for the same reason pings are: one at a time, a
    # large inventory of non-responding devices took timeout * N to finish.
    workers = max(1, min(config.PING_CONCURRENCY, len(devices)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="snmp") as pool:
        locations = list(pool.map(lookup, devices))

    for device, location in zip(devices, locations):
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
            status_by_ip = _device_reachability(group["devices"])
            reachable = [ip for ip in group["devices"] if status_by_ip[ip] is True]
            unreachable = [ip for ip in group["devices"] if status_by_ip[ip] is False]
            pending = len(group["devices"]) - len(reachable) - len(unreachable)
            if pending:
                # Don't judge (or ticket) a site on a partial picture right
                # after startup or an add; the next sweep fills it in.
                status = "pending"
            elif not unreachable:
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
            if pending:
                pass
            elif percent_down >= correlator.OUTAGE_THRESHOLD:
                confidence = _assess_location_confidence(coordinates)
                if confidence:
                    marker["confidence"] = confidence

                ticket = _ensure_outage_ticket(
                    group["location"], group["devices"], percent_down, confidence
                )
                if ticket:
                    marker["ticket"] = ticket
                try:
                    _history.annotate_outage(group["location"], confidence, ticket)
                except Exception:
                    log.exception("Could not record outage details for %s", group["location"])
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

    saved = save_devices(updated, get_inventory_path())
    _monitor.request_sweep()
    return {"devices": saved}


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
