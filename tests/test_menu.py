import unittest
from unittest.mock import patch

from app.menu import CONTINUE, QUIT, show_startup_menu


class ShowStartupMenuTests(unittest.TestCase):
    @patch("app.menu.load_ip_addresses", return_value=["10.0.0.1"])
    @patch("builtins.input", side_effect=["4"])
    def test_option_4_continues_to_analysis(self, _input, _load):
        self.assertEqual(show_startup_menu(), CONTINUE)

    @patch("app.menu.load_ip_addresses", return_value=["10.0.0.1"])
    @patch("builtins.input", side_effect=["5"])
    def test_option_5_quits(self, _input, _load):
        self.assertEqual(show_startup_menu(), QUIT)

    @patch("app.menu.load_ip_addresses", return_value=[])
    @patch("builtins.input", side_effect=["9", "1", "5"])
    def test_invalid_option_reprompts_until_valid_choice(self, _input, _load):
        self.assertEqual(show_startup_menu(), QUIT)

    @patch("app.menu.save_ip_addresses")
    @patch("app.menu.load_ip_addresses", return_value=[])
    @patch("builtins.input", side_effect=["2", "192.168.1.1", "5"])
    def test_add_ip_address_prompt_saves_new_address(self, _input, _load, save):
        show_startup_menu()

        save.assert_called_once_with(["192.168.1.1"])

    @patch("app.menu.save_ip_addresses")
    @patch("app.menu.load_ip_addresses", return_value=["192.168.1.1"])
    @patch("builtins.input", side_effect=["2", "not-an-ip", "5"])
    def test_add_ip_address_prompt_rejects_invalid_address(self, _input, _load, save):
        show_startup_menu()

        save.assert_not_called()

    @patch("app.menu.save_ip_addresses")
    @patch("app.menu.load_ip_addresses", return_value=["192.168.1.1"])
    @patch("builtins.input", side_effect=["3", "192.168.1.1", "5"])
    def test_remove_ip_address_prompt_saves_updated_list(self, _input, _load, save):
        show_startup_menu()

        save.assert_called_once_with([])

    @patch("app.menu.save_ip_addresses")
    @patch("app.menu.load_ip_addresses", return_value=[])
    @patch("builtins.input", side_effect=["3", "192.168.1.1", "5"])
    def test_remove_ip_address_prompt_skips_save_when_not_found(self, _input, _load, save):
        show_startup_menu()

        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
