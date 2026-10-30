import unittest
from unittest.mock import MagicMock, patch

from app.main import Handler


class LanAddressTests(unittest.TestCase):
    def socket_for(self, ip):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.getsockname.return_value = (ip, 12345)
        return connection

    def test_only_current_route_is_returned_and_rechecked(self):
        with patch("app.main.socket.socket", side_effect=[
            self.socket_for("192.168.1.100"),
            self.socket_for("192.168.2.20"),
        ]), patch("app.main.socket.getaddrinfo") as adapters:
            self.assertEqual(Handler._lan_addresses(), {"192.168.1.100"})
            self.assertEqual(Handler._lan_addresses(), {"192.168.2.20"})
            adapters.assert_not_called()

    def test_disconnected_network_does_not_keep_previous_address(self):
        with patch("app.main.socket.socket", side_effect=[
            self.socket_for("192.168.1.100"), OSError(), OSError(),
        ]):
            self.assertEqual(Handler._lan_addresses(), {"192.168.1.100"})
            self.assertEqual(Handler._lan_addresses(), set())

    def test_non_shareable_addresses_are_omitted(self):
        for ip in ("127.0.0.1", "169.254.83.107", "0.0.0.0", "224.0.0.1"):
            with self.subTest(ip=ip), patch(
                "app.main.socket.socket", side_effect=[self.socket_for(ip), OSError()]
            ):
                self.assertEqual(Handler._lan_addresses(), set())


if __name__ == "__main__":
    unittest.main()
