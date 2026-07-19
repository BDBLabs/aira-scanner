import unittest
from urllib import request


class NetworkGuardTests(unittest.TestCase):
    def test_unmocked_network_is_blocked_by_test_fixture(self):
        with self.assertRaisesRegex(AssertionError, "unmocked network"):
            request.urlopen("https://example.com")


if __name__ == "__main__":
    unittest.main()
