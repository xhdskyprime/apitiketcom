import unittest
from unittest.mock import MagicMock, patch
import json
from tiket_api import TiketAPI

class TestTiketAPI(unittest.TestCase):
    def setUp(self):
        self.auth_config = {
            "account_id": "36288055",
            "device_id": "test-device-id",
            "cookie": "test-cookie"
        }
        self.api = TiketAPI(self.auth_config)

    def test_init(self):
        self.assertEqual(self.api.session.headers.get("x-account-id"), "36288055")
        self.assertEqual(self.api.session.headers.get("deviceId"), "test-device-id")

    @patch("tiket_api.requests.Session.post")
    def test_add_to_cart_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "message": "SUCCESS",
            "data": {"cartId": "mock-cart-id-123"}
        }
        mock_post.return_value = mock_response

        cart_id = self.api.add_to_cart("flight-1", "supplier-1", 500000)
        self.assertEqual(cart_id, "mock-cart-id-123")

    @patch("tiket_api.requests.Session.post")
    def test_create_booking_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "message": "SUCCESS",
            "data": {
                "successData": {
                    "orderId": "123456789",
                    "orderHash": "HASH123",
                    "paymentUrl": "https://www.tiket.com/payment?order_id=123456789"
                }
            }
        }
        mock_post.return_value = mock_response

        contact = {"fullName": "TEST USER", "email": "test@test.com", "phone": "08123456789"}
        adults = [{"fullName": "TEST USER"}]
        result = self.api.create_booking("mock-cart-id", contact, adults)
        
        self.assertEqual(result["order_id"], "123456789")
        self.assertEqual(result["order_hash"], "HASH123")

    @patch("tiket_api.requests.Session.post")
    def test_create_booking_null_data(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "message": "SUCCESS",
            "errors": ["Expired session"],
            "data": None
        }
        mock_post.return_value = mock_response

        contact = {"fullName": "TEST USER", "email": "test@test.com", "phone": "08123456789"}
        adults = [{"fullName": "TEST USER"}]
        with self.assertRaises(Exception) as ctx:
            self.api.create_booking("mock-cart-id", contact, adults)
        self.assertIn("Booking gagal", str(ctx.exception))

    @patch("tiket_api.requests.Session.post")
    def test_add_to_cart_null_data(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "message": "FAILED",
            "data": None
        }
        mock_post.return_value = mock_response

        with self.assertRaises(Exception) as ctx:
            self.api.add_to_cart("flight-1", "supplier-1", 500000)
        self.assertIn("Gagal add to cart", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
