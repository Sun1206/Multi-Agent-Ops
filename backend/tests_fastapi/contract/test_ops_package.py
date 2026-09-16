from ops.alerts.api import router as alerts_router
from ops.alerts.config_api import router as alert_config_router
from ops.modules.api import router as modules_router
from ops.observability.metrics.api import router as metrics_router
from ops.observability.metrics.runtime import execute_metric_query


def test_ops_router_and_runtime_contracts():
    assert alerts_router and alert_config_router and modules_router and metrics_router
    assert execute_metric_query
