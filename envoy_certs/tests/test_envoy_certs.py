import json
import os
from typing import Any, Dict

import mock
import pytest

from datadog_checks.base.stubs.aggregator import AggregatorStub
from datadog_checks.dev.utils import get_metadata_metrics
from datadog_checks.envoy_certs import EnvoyCertsCheck

from .common import MockResponse

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DIR = os.path.join(HERE, 'fixtures')


@pytest.mark.unit
def test_check(aggregator, instance):
    # type: (AggregatorStub, Dict[str, Any]) -> None
    with open(os.path.join(FIXTURE_DIR, 'response.json')) as f:
        response = json.load(f)

    with mock.patch('requests.get', return_value=MockResponse(json.dumps(response), 200)):
        check = EnvoyCertsCheck('envoy_certs', {}, [instance])
        check.check(instance)

    check.check(instance)
    trust_domain = "some.trust.domain"
    namespace = "istio-system"
    service_account = "istio-ingressgateway-service-account"
    aggregator.assert_metric(
        "envoy_certs.days_until_expiration",
        tags=[
            "name:spiffe://{}/ns/{}/sa/{}".format(trust_domain, namespace, service_account),
            "san:spiffe://{}/ns/{}/sa/{}".format(trust_domain, namespace, service_account),
        ],
        value=0.0,
    )
    aggregator.assert_metric(
        "envoy_certs.days_until_expiration",
        tags=['san:*.example.com', 'name:*.example.com'],
        value=105.0,
    )
    aggregator.assert_metric(
        "envoy_certs.days_until_expiration",
        tags=['san:*.dev.example.com', 'name:*.dev.example.com'],
        value=52.0,
    )
    aggregator.assert_metric(
        "envoy_certs.days_until_expiration",
        tags=['name:None'],  # CACert doesn't get a name (for now)
        value=2619.0,
    )
    aggregator.assert_all_metrics_covered()
    aggregator.assert_metrics_using_metadata(get_metadata_metrics())
