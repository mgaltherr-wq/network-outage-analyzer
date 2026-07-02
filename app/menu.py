from app.ip_inventory import (
    add_ip_address,
    load_ip_addresses,
    remove_ip_address,
    save_ip_addresses,
)


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
        print("5. Quit")

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
            return QUIT
        else:
            print("Invalid option. Choose 1-5.")


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
