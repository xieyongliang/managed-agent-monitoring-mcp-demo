"""Read-only BytePlus Cloud Monitor tools using the official SDK."""

from __future__ import annotations

import json
import os
import time


def _client(region: str):
    import byteplussdkcore
    from byteplussdkcloudmonitor import CLOUDMONITORApi

    ak = os.getenv("BYTEPLUS_ACCESS_KEY", "")
    sk = os.getenv("BYTEPLUS_SECRET_KEY", "")
    if not ak or not sk:
        raise ValueError("BytePlus cloud credentials are not configured on the MCP server")
    config = byteplussdkcore.Configuration()
    config.ak = ak
    config.sk = sk
    config.session_token = os.getenv("BYTEPLUS_SESSION_TOKEN", "")
    config.region = region
    config.scheme = "https"
    config.debug = False
    return CLOUDMONITORApi(byteplussdkcore.ApiClient(config))


def _window(minutes: int) -> tuple[int, int]:
    if not 1 <= minutes <= 1440:
        raise ValueError("time_range_minutes must be between 1 and 1440")
    end = int(time.time())
    return end - minutes * 60, end


def _error(exc: Exception, operation: str, region: str) -> dict:
    # Do not expose SDK request headers or arbitrary provider response bodies.
    detail = {"type": type(exc).__name__}
    if isinstance(exc, (ValueError, ModuleNotFoundError)):
        detail["message"] = str(exc)
    else:
        detail["message"] = "BytePlus monitoring query failed; inspect code and request_id"
        try:
            metadata = json.loads(getattr(exc, "body", "") or "{}").get("ResponseMetadata", {})
            detail["code"] = metadata.get("Error", {}).get("Code")
            detail["request_id"] = metadata.get("RequestId")
        except (ValueError, AttributeError, TypeError):
            pass
    return {"ok": False, "provider": "byteplus", "operation": operation, "region": region, "query_error": detail}


def get_byteplus_alert_groups(
    region: str = "ap-southeast-1",
    resource_id: str = "",
    time_range_minutes: int = 60,
    page_number: int = 1,
    page_size: int = 20,
) -> dict:
    """Read alert history. Returned groups are not necessarily active incidents."""
    operation = "ListAlertGroup"
    try:
        start, end = _window(time_range_minutes)
        if page_number < 1 or not 1 <= page_size <= 100:
            raise ValueError("page_number must be positive and page_size must be 1..100")
        from byteplussdkcloudmonitor import ListAlertGroupRequest

        response = _client(region).list_alert_group(
            ListAlertGroupRequest(start_at=start, end_at=end, resource_id=resource_id or None,
                                  page_number=page_number, page_size=page_size),
            _request_timeout=(5, 20),
        ).to_dict()
        return {"ok": True, "provider": "byteplus", "operation": operation, "region": region,
                "resource_id": resource_id, "start_time": start, "end_time": end,
                "result": response,
                "coverage_note": "One page of alert history; inspect states and total_count. Empty data does not prove health."}
    except Exception as exc:
        return _error(exc, operation, region)


def get_byteplus_metric_data(
    namespace: str,
    sub_namespace: str,
    metric_name: str,
    dimensions: dict[str, str],
    region: str = "ap-southeast-1",
    time_range_minutes: int = 30,
    period: str = "60s",
    statistics_method: str = "avg",
) -> dict:
    """Query one resource's metric using its documented namespace and dimensions."""
    operation = "GetMetricData"
    try:
        start, end = _window(time_range_minutes)
        if not namespace or not metric_name or not dimensions:
            raise ValueError("namespace, metric_name and dimensions are required")
        from byteplussdkcloudmonitor import (
            DimensionForGetMetricDataInput,
            GetMetricDataRequest,
            InstanceForGetMetricDataInput,
        )

        request = GetMetricDataRequest(
            namespace=namespace, sub_namespace=sub_namespace, metric_name=metric_name,
            instances=[InstanceForGetMetricDataInput(dimensions=[
                DimensionForGetMetricDataInput(name=k, value=v) for k, v in dimensions.items()
            ])],
            start_time=start, end_time=end, period=period,
            statistics_methods=[statistics_method],
        )
        response = _client(region).get_metric_data(request, _request_timeout=(5, 20)).to_dict()
        return {"ok": True, "provider": "byteplus", "operation": operation, "region": region,
                "namespace": namespace, "sub_namespace": sub_namespace, "metric_name": metric_name,
                "dimensions": dimensions, "start_time": start, "end_time": end,
                "result": response,
                "coverage_note": "One metric query; missing datapoints are not zero and do not prove health."}
    except Exception as exc:
        return _error(exc, operation, region)
