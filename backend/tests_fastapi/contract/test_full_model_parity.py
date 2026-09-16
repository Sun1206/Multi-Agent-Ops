from aidevops import model_registry as models
from aidevops.database import Base


EXPECTED_EVENTWALL = {"EventRecord", "EventSource", "EventEnvironment"}
EXPECTED_AIOPS = {
    "AIOpsModelProvider", "AIOpsAgentConfig", "AIOpsMCPServer", "AIOpsSkill",
    "AIOpsKnowledgeEnvironment", "AIOpsChatSession", "AIOpsChatMessage",
    "AIOpsPendingAction", "AIOpsToolInvocation", "AIOpsModelInvocation",
    "AIOpsExternalTask", "AIOpsRunbook", "AIOpsRunbookVersion", "AIOpsReviewKnowledge",
}
EXPECTED_OPS = {
    "Host", "TaskResourceGroup", "TaskResource", "HostTask", "HostTaskTemplate",
    "HostTaskSchedule", "HostTaskScheduleExecution", "HostTaskExecution", "Deployment",
    "DeploymentApprovalFlow", "DeploymentApprovalNode", "DeploymentApprovalStep", "Alert",
    "AlertClaim", "AlertIntegration", "AlertRecipient", "AlertRecipientGroup",
    "AlertNotificationChannel", "AlertAggregationRule", "AlertInhibitionRule", "AlertMuteRule",
    "AlertEscalationPolicy", "AlertNotificationRule", "AlertNotificationLog", "AlertAction",
    "AlertInteractionToken", "LogEntry", "LogDataSource", "TracingDataSource",
    "MetricDataSource", "ObservabilityDataSourceLink", "GrafanaSetting", "K8sCluster",
    "K8sConfigRevision", "DockerHost", "NginxEnvironment", "NginxCertificate",
    "NginxDomain", "NginxRoute", "TransactionTicket",
}


def test_every_current_domain_model_is_exported() -> None:
    exported = set(models.__all__)
    assert EXPECTED_EVENTWALL | EXPECTED_AIOPS | EXPECTED_OPS <= exported


def test_each_exported_domain_model_has_real_columns() -> None:
    for name in EXPECTED_EVENTWALL | EXPECTED_AIOPS | EXPECTED_OPS:
        table = getattr(models, name).__table__
        assert len(table.primary_key.columns) == 1
        assert len(table.c) > 2


def test_all_foreign_keys_reference_registered_tables() -> None:
    registered = set(Base.metadata.tables)
    missing = {
        foreign_key.target_fullname.rsplit(".", 1)[0]
        for table in Base.metadata.tables.values()
        for foreign_key in table.foreign_keys
        if foreign_key.target_fullname.rsplit(".", 1)[0] not in registered
    }
    assert missing == set()
    assert len(Base.metadata.sorted_tables) == len(Base.metadata.tables)


def test_decimal_precision_and_domain_uniqueness_are_preserved() -> None:
    provider = models.AIOpsModelProvider.__table__
    assert provider.c.input_token_price_per_1m.type.precision == 10
    assert provider.c.input_token_price_per_1m.type.scale == 6

    domain = models.NginxDomain.__table__
    unique_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in domain.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("environment_id", "domain", "listen_port") in unique_sets


def test_declared_domain_indexes_are_preserved() -> None:
    ticket = models.TransactionTicket.__table__
    index_sets = {tuple(column.name for column in index.columns) for index in ticket.indexes}
    assert ("status", "priority", "updated_at") in index_sets
    assert ("business_line", "environment") in index_sets


def test_domain_state_constants_and_symbolic_defaults_are_preserved() -> None:
    assert models.HostTask.STRATEGY_CONTINUE == "continue"
    assert models.HostTask.__table__.c.status.default.arg == "pending"
    assert models.HostTaskTemplate.__table__.c.execution_strategy.default.arg == "continue"


def test_callable_defaults_and_update_timestamps_are_preserved() -> None:
    assert models.AlertInteractionToken.__table__.c.token.default is not None
    assert models.AIOpsExternalTask.__table__.c.public_id.default is not None
    assert models.AIOpsChatSession.__table__.c.last_message_at.default is not None
    assert models.Host.__table__.c.updated_at.onupdate is not None
