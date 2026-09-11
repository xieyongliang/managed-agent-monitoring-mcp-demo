"""Contract and failure tests; these do not substitute for a real API test."""
import os
import unittest
from unittest.mock import Mock, patch

from byteplus_tools import get_byteplus_alert_groups, get_byteplus_metric_data


class BytePlusToolsTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_credentials_returns_error_not_mock_data(self):
        result = get_byteplus_alert_groups()
        self.assertFalse(result["ok"])
        self.assertIn("query_error", result)
        self.assertNotIn("result", result)

    @patch("byteplus_tools._client")
    def test_alert_resource_scope_and_pagination(self, client):
        client.return_value.list_alert_group.return_value = Mock(to_dict=lambda: {"data": [], "total_count": 0})
        result = get_byteplus_alert_groups(resource_id="test-resource", page_number=2)
        request = client.return_value.list_alert_group.call_args.args[0]
        self.assertEqual(request.resource_id, "test-resource")
        self.assertEqual(request.page_number, 2)
        self.assertTrue(result["ok"])
        self.assertIn("does not prove health", result["coverage_note"])

    @patch("byteplus_tools._client")
    def test_metric_sdk_dimensions_and_time_window(self, client):
        client.return_value.get_metric_data.return_value = Mock(to_dict=lambda: {"data": None})
        result = get_byteplus_metric_data("test-ns", "test-sub", "test-metric", {"ResourceId": "test-resource"})
        request = client.return_value.get_metric_data.call_args.args[0]
        self.assertEqual(request.instances[0].dimensions[0].name, "ResourceId")
        self.assertEqual(request.end_time - request.start_time, 1800)
        self.assertTrue(result["ok"])

    @patch("byteplus_tools._client")
    def test_invalid_window_does_not_call_cloud(self, client):
        self.assertFalse(get_byteplus_alert_groups(time_range_minutes=0)["ok"])
        client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
