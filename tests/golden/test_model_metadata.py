"""Every catalogued metric must carry title, description, owner and a plain-English formula."""

from __future__ import annotations

import pytest
from build_metric_dictionary import REQUIRED_META, SEMANTICS, load_metrics

METRICS = load_metrics()
REQUIRED_SPEC_METRICS = {
    "active_customers", "new_customers", "churned_customers", "churn_rate", "products_per_customer",
    "cross_sell_rate", "total_deposits", "avg_deposits", "casa_balance", "casa_ratio", "loans_outstanding",
    "loans_disbursed", "npl_balance", "npl_ratio", "provision_coverage", "net_interest_income", "nim", "txn_count",
    "txn_value", "digital_share", "campaign_cost", "campaign_response_rate", "campaign_conversion_rate", "cac",
}


def test_all_spec_metrics_exist():
    assert REQUIRED_SPEC_METRICS <= {m["name"] for m in METRICS}


@pytest.mark.parametrize("metric", METRICS, ids=lambda m: f"{m['cube']}.{m['name']}")
def test_metric_is_fully_documented(metric):
    assert metric.get("title") and metric.get("description")
    meta = metric.get("meta", {})
    for key in REQUIRED_META:
        assert meta.get(key), f"{metric['name']} is missing meta.{key}"
    assert meta["time_semantics"] in SEMANTICS
    assert meta["unit"] in {"bdt", "count", "percent", "ratio"}


def test_metric_names_are_unique():
    names = [m["name"] for m in METRICS]
    assert len(names) == len(set(names))
