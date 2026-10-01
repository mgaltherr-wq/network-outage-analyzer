from getpass import getpass

from app import auth
from app.ip_inventory import (
    add_ip_address,
    load_ip_addresses,
    remove_ip_address,
    save_ip_addresses,
)
from app.settings_store import FIELDS_BY_KEY, SECRET, get_settings, update_settings


CONTINUE = "continue"
QUIT = "quit"


def show_startup_menu():
    ip_addresses = load_ip_addresses()

    while True:
        print("\n=== Network Outage Analyzer ===")
        print("1. Show IP address list")
        print("2. Add IP address")
        print("3. Remove IP address")
        print("4. Continue to outage analysis")
        print("5. Settings")
        print("6. Quit")

        choice = input("Select an option: ").strip()

        if choice == "1":
            _print_ip_addresses(ip_addresses)
        elif choice == "2":
            ip_addresses = _add_ip_address_prompt(ip_addresses)
        elif choice == "3":
            ip_addresses = _remove_ip_address_prompt(ip_addresses)
        elif choice == "4":
            return CONTINUE
        elif choice == "5":
            _show_settings_menu()
        elif choice == "6":
            return QUIT
        else:
            print("Invalid option. Choose 1-6.")


def _print_ip_addresses(ip_addresses):
    if not ip_addresses:
        print("No IP addresses configured.")
        return

    print("\nConfigured IP addresses:")
    for index, ip_address in enumerate(ip_addresses, start=1):
        print(f"{index}. {ip_address}")


def _add_ip_address_prompt(ip_addresses):
    value = input("IP address to add: ").strip()
    try:
        updated, added = add_ip_address(ip_addresses, value)
    except ValueError:
        print("Invalid IP address.")
        return ip_addresses

    if added:
        save_ip_addresses(updated)
        print(f"Added {value}.")
        return updated

    print(f"{value} is already in the list.")
    return ip_addresses


def _remove_ip_address_prompt(ip_addresses):
    value = input("IP address to remove: ").strip()
    try:
        updated, removed = remove_ip_address(ip_addresses, value)
    except ValueError:
        print("Invalid IP address.")
        return ip_addresses

    if removed:
        save_ip_addresses(updated)
        print(f"Removed {value}.")
        return updated

    print(f"{value} is not in the list.")
    return ip_addresses


def _show_settings_menu():
    while True:
        settings = get_settings()

        print("\n=== Settings ===")
        index_to_key = {}
        current_group = None
        for index, setting in enumerate(settings, start=1):
            if setting["group"] != current_group:
                current_group = setting["group"]
                print(f"-- {current_group} --")
            status = setting["value"] if setting["is_set"] else "not set"
            print(f"{index}. {setting['label']} ({status})")
            index_to_key[str(index)] = setting["key"]
        print("-- Dashboard --")
        password_status = "set" if auth.is_password_set() else "not set"
        print(f"P. Dashboard password ({password_status})")
        print("0. Back")

        choice = input("Select a setting to change: ").strip()
        if choice == "0":
            return
        if choice.casefold() == "p":
            _set_dashboard_password_prompt()
            continue

        key = index_to_key.get(choice)
        if not key:
            print("Invalid option.")
            continue

        _update_setting_prompt(key)


def _update_setting_prompt(key):
    field = FIELDS_BY_KEY[key]
    prompt = f"New value for {field.label} (blank to cancel, '-' to clear): "
    value = getpass(prompt) if field.kind == SECRET else input(prompt)
    value = value.strip()

    if not value:
        print("No change made.")
        return

    update_settings({key: "" if value == "-" else value})
    print(f"Updated {field.label}.")


def _set_dashboard_password_prompt():
    password = getpass(f"New dashboard password (min {auth.MIN_PASSWORD_LENGTH} characters, blank to cancel): ")
    if not password:
        print("No change made.")
        return

    try:
        auth.validate_new_password(password)
    except ValueError as exc:
        print(exc)
        return

    if getpass("Confirm new dashboard password: ") != password:
        print("Passwords do not match. No change made.")
        return

    auth.set_password(password)
    print("Dashboard password updated. Existing dashboard sessions have been signed out.")
