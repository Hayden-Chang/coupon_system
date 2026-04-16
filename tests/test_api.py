import tempfile
import unittest
from pathlib import Path

import app as app_module
from database import Database


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db = app_module.db
        self.test_db_path = Path(self.temp_dir.name) / "test_coupons.db"
        app_module.db = Database(str(self.test_db_path))
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.db = self.original_db
        self.temp_dir.cleanup()

    def default_config_payload(self, name="测试配置"):
        return {
            "name": name,
            "x": 2,
            "y": 34,
            "m": 15,
            "n": 20,
            "coupons": [
                {"tier": 1, "p": 50, "q": 5},
                {"tier": 2, "p": 70, "q": 8},
            ],
        }

    def create_config(self, payload=None, name=None):
        request_payload = payload or self.default_config_payload(name=name or "测试配置")
        response = self.client.post("/api/configs", json=request_payload)
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["data"]["id"]

    def test_list_configs_initially_empty(self):
        response = self.client.get("/api/configs")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"], [])

    def test_create_and_get_config(self):
        config_id = self.create_config()

        response = self.client.get(f"/api/configs/{config_id}")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()["data"]
        self.assertEqual(body["id"], config_id)
        self.assertEqual(body["name"], "测试配置")
        self.assertEqual(len(body["coupons"]), 2)
        self.assertEqual(body["coupons"][0]["tier"], 1)
        self.assertEqual(body["coupons"][1]["tier"], 2)

    def test_create_config_rejects_invalid_fields(self):
        payload = self.default_config_payload()
        payload["name"] = ""
        payload["x"] = 1

        response = self.client.post("/api/configs", json=payload)

        self.assertEqual(response.status_code, 400)
        body = response.get_json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("name", body["error"]["details"])
        self.assertIn("x", body["error"]["details"])

    def test_create_config_rejects_profit_constraint_violation(self):
        payload = {
            "name": "亏损配置",
            "x": 1.2,
            "y": 0,
            "m": 10,
            "n": 10,
            "coupons": [
                {"tier": 1, "p": 12, "q": 5},
            ],
        }

        response = self.client.post("/api/configs", json=payload)

        self.assertEqual(response.status_code, 422)
        body = response.get_json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "PROFIT_CONSTRAINT_VIOLATION")
        self.assertIn("profit", body["error"]["details"])

    def test_update_config_without_coupons_keeps_existing_coupons(self):
        config_id = self.create_config()

        update_payload = {
            "name": "更新后的配置",
            "x": 2.2,
            "y": 36,
            "m": 15,
            "n": 20,
        }
        update_response = self.client.put(f"/api/configs/{config_id}", json=update_payload)
        self.assertEqual(update_response.status_code, 200, update_response.get_data(as_text=True))

        detail_response = self.client.get(f"/api/configs/{config_id}")
        body = detail_response.get_json()["data"]
        self.assertEqual(body["name"], "更新后的配置")
        self.assertEqual(len(body["coupons"]), 2)
        self.assertEqual([coupon["tier"] for coupon in body["coupons"]], [1, 2])

    def test_coupon_crud_flow(self):
        config_id = self.create_config()
        config = self.client.get(f"/api/configs/{config_id}").get_json()["data"]
        original_coupon_id = config["coupons"][0]["id"]

        add_response = self.client.post(
            f"/api/configs/{config_id}/coupons",
            json={"tier": 3, "p": 90, "q": 12},
        )
        self.assertEqual(add_response.status_code, 201, add_response.get_data(as_text=True))
        added_coupon_id = add_response.get_json()["data"]["id"]

        update_response = self.client.put(
            f"/api/coupons/{original_coupon_id}",
            json={"tier": 1, "p": 52, "q": 6},
        )
        self.assertEqual(update_response.status_code, 200, update_response.get_data(as_text=True))

        delete_response = self.client.delete(f"/api/coupons/{added_coupon_id}")
        self.assertEqual(delete_response.status_code, 200, delete_response.get_data(as_text=True))
        self.assertEqual(delete_response.get_json()["data"]["config_id"], config_id)

        detail_response = self.client.get(f"/api/configs/{config_id}")
        coupons = detail_response.get_json()["data"]["coupons"]
        self.assertEqual(len(coupons), 2)
        self.assertEqual(coupons[0]["p"], 52.0)
        self.assertEqual(coupons[0]["q"], 6.0)
        self.assertEqual([coupon["tier"] for coupon in coupons], [1, 2])

    def test_duplicate_config_name_returns_conflict(self):
        self.create_config(name="重复名称")

        response = self.client.post("/api/configs", json=self.default_config_payload(name="重复名称"))

        self.assertEqual(response.status_code, 409)
        body = response.get_json()
        self.assertEqual(body["error"]["code"], "CONFIG_NAME_CONFLICT")

    def test_chart_endpoint_returns_image_and_summary(self):
        config_id = self.create_config()

        response = self.client.get(f"/api/configs/{config_id}/chart")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()["data"]
        self.assertTrue(payload["image_base64"])
        self.assertGreater(payload["summary"]["min_profit"], 0)
        self.assertGreater(payload["summary"]["max_profit_rate"], 0)


if __name__ == "__main__":
    unittest.main()
