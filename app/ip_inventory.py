import asyncio
import json
from ipaddress import ip_address
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.paths import migrate_legacy_file, user_data_dir

migrate_legacy_file("ip_addresses.json")
DEFAULT_IP_LIST_PATH = user_data_dir() / "ip_addresses.json"


def normalize_ip(value):
    return str(ip_address(value.strip()))


def load_ip_addresses(path=DEFAULT_IP_LIST_PATH):
    path = Path(path)
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list of IP addresses.")

    if all(isinstance(item, dict) for item in data):
        return [normalize_ip(item.get("ip_address")) for item in data if item.get("ip_address")]

    return [normalize_ip(item) for item in data]


def save_ip_addresses(ip_addresses, path=DEFAULT_IP_LIST_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    normalized = sorted({normalize_ip(item) for item in ip_addresses})
    with path.open("w", encoding="utf-8") as file:
        json.dump(normalized, file, indent=2)
        file.write("\n")

    return normalized


def add_ip_address(ip_addresses, ip_address_value):
    normalized = normalize_ip(ip_address_value)
    if normalized in ip_addresses:
        return ip_addresses, False

    return sorted([*ip_addresses, normalized]), True


def add_device(devices: List[Dict], ip_address_value: str, location: str = "") -> Tuple[List[Dict], bool, Dict]:
    normalized = normalize_ip(ip_address_value)
    for device in devices:
        if device.get("ip_address") == normalized:
            return devices, False, device

    new_device = {"ip_address": normalized, "location": location, "location_source": "manual"}
    updated = sorted([*devices, new_device], key=lambda item: item["ip_address"])
    return updated, True, new_device


def remove_ip_address(ip_addresses, ip_address_value):
    normalized = normalize_ip(ip_address_value)
    if normalized not in ip_addresses:
        return ip_addresses, False

    return [item for item in ip_addresses if item != normalized], True


def remove_device(devices: List[Dict], ip_address_value: str) -> Tuple[List[Dict], bool]:
    normalized = normalize_ip(ip_address_value)
    updated = [device for device in devices if device.get("ip_address") != normalized]
    return updated, len(updated) != len(devices)


# --- Device records with locations ---
def load_devices(path=DEFAULT_IP_LIST_PATH) -> List[Dict]:
    path = Path(path)
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list) and data and all(isinstance(item, str) for item in data):
        return [{"ip_address": normalize_ip(item), "location": "", "location_source": "manual"} for item in data]

    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        devices = []
        for item in data:
            ip_value = item.get("ip_address")
            if not ip_value:
                continue
            ip = normalize_ip(ip_value)
            devices.append({
                "ip_address": ip,
                "location": item.get("location", ""),
                "location_source": item.get("location_source", "manual"),
            })
        return devices

    raise ValueError(f"{path} must contain a JSON list of IP addresses or device records.")


def save_devices(devices: List[Dict], path=DEFAULT_IP_LIST_PATH) -> List[Dict]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    normalized = []
    for device in devices:
        normalized.append({
            "ip_address": normalize_ip(device["ip_address"]),
            "location": device.get("location", ""),
            "location_source": device.get("location_source", "manual"),
        })

    with path.open("w", encoding="utf-8") as file:
        json.dump(normalized, file, indent=2)
        file.write("\n")

    return normalized


def assign_location(devices: List[Dict], ip_address_value: str, location: str) -> Tuple[List[Dict], bool]:
    normalized_ip = normalize_ip(ip_address_value)
    changed = False
    updated = []
    for device in devices:
        if device.get("ip_address") == normalized_ip:
            if device.get("location") != location or device.get("location_source") != "manual":
                device["location"] = location
                device["location_source"] = "manual"
                changed = True
        updated.append(device)

    return updated, changed


def lookup_location_snmp(ip_address_value: str, community: str = "public", oid: str = "1.3.6.1.2.1.1.6.0", timeout: float = 2, version: str = "2c") -> Optional[str]:
    """Attempt to query sysLocation via SNMP. Returns a string or None."""
    try:
        from pysnmp.hlapi.v3arch.asyncio import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            UdpTransportTarget,
            get_cmd,
        )
    except Exception:
        return None

    async def query():
        engine = SnmpEngine()
        try:
            target = await UdpTransportTarget.create(
                (ip_address_value, 161), timeout=timeout, retries=0
            )
            error_indication, error_status, _, var_binds = await get_cmd(
                engine,
                CommunityData(community, mpModel=0 if version == "1" else 1),
                target,
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
            if error_indication or error_status or not var_binds:
                return None
            location = var_binds[0][1].prettyPrint().strip()
            return location or None
        finally:
            engine.close_dispatcher()

    try:
        return asyncio.run(query())
    except Exception:
        return None
