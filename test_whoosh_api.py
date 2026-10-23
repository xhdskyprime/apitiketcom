import unittest
from unittest.mock import MagicMock, patch
import json
from whoosh_api import WhooshAPI

class TestWhooshAPI(unittest.TestCase):
    def setUp(self):
        self.auth_config = {
            "account_id": "36288055",
            "device_id": "test-device-id",
            "cookie": "test-cookie"
        }
        self.api = WhooshAPI(self.auth_config)

    def test_init(self):
        self.assertEqual(self.api.session.headers.get("x-account-id"), "36288055")
        self.assertEqual(self.api.session.headers.get("deviceId"), "test-device-id")

    @patch("whoosh_api.requests.Session.get")
    def test_search_whoosh_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "data": {
                "departJourneys": {
                    "journeys": [
                        {
                            "id": "WHOOSH-123",
                            "originStation": {"code": "IDHMA"},
                            "destinationStation": {"code": "IDTLA"},
                            "departDate": "2026-08-28",
                            "departTime": "06:25:00",
                            "arriveTime": "07:19:00",
                            "segmentSchedules": [
                                {
                                    "trainNumber": "G1003",
                                    "trainName": "Whoosh",
                                    "subClass": {"code": "PE"},
                                    "wagonClass": {"code": "O:123", "detail": "Ekonomi Premium"},
                                    "availableSeats": 50,
                                    "scheduleFares": [{"priceAmount": 300000}]
                                }
                            ]
                        }
                    ]
                }
            }
        }
        mock_get.return_value = mock_response

        results = self.api.search_whoosh("IDHMA", "IDTLA", "2026-08-28")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["trainNumber"], "G1003")
        self.assertEqual(results[0]["price"], 300000)

    @patch("whoosh_api.requests.Session.post")
    def test_add_to_cart_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "data": {
                "cartId": "cart-123",
                "secret": "secret-456"
            }
        }
        mock_post.return_value = mock_response

        item = {
            "id": "WHOOSH-123",
            "originCode": "IDHMA",
            "destinationCode": "IDTLA",
            "departDate": "2026-08-28",
            "subClass": "PE",
            "trainNumber": "G1003",
            "wagonClass": "O:123"
        }
        cart_id, secret = self.api.add_to_cart(item)
        self.assertEqual(cart_id, "cart-123")
        self.assertEqual(secret, "secret-456")

    @patch("whoosh_api.requests.Session.post")
    def test_create_order_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "data": {
                "orderId": "1357633518",
                "orderHash": "HASH123",
                "paymentUrl": "https://www.tiket.com/payment?order_id=1357633518"
            }
        }
        mock_post.return_value = mock_response

        res = self.api.create_order("cart-123", "secret-456")
        self.assertEqual(res["order_id"], "1357633518")
        self.assertEqual(res["order_hash"], "HASH123")

if __name__ == "__main__":
    unittest.main()
