import json
from ipaddress import ip_address
from pathlib import Path


DEFAULT_IP_LIST_PATH = Path(__file__).resolve().parents[1] / "ip_addresses.json"


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


def remove_ip_address(ip_addresses, ip_address_value):
    normalized = normalize_ip(ip_address_value)
    if normalized not in ip_addresses:
        return ip_addresses, False

    return [item for item in ip_addresses if item != normalized], True
