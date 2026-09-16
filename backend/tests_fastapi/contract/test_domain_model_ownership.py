from aiops import models as aiops_models
from ops import models as ops_models


AIOPS = {"AIOpsModelProvider", "AIOpsAgentConfig", "AIOpsMCPServer", "AIOpsSkill", "AIOpsChatSession"}
OPS = {"Host", "Deployment", "Alert", "MetricDataSource", "TransactionTicket"}


def test_generated_models_are_exported_by_their_owning_domain():
    assert AIOPS <= set(aiops_models.__all__)
    assert OPS <= set(ops_models.__all__)
    assert AIOPS.isdisjoint(set(ops_models.__all__))
    assert OPS.isdisjoint(set(aiops_models.__all__))
