from aiops.agent_registry import CATALOG, action_catalog
from aiops.services.chat_jobs import ChatJobs, recover_interrupted
from aiops.services.mcp_runtime import diagnose_mcp
from aidevops.restricted_http import PinnedBackend


def test_aiops_runtime_public_contract():
    assert CATALOG and callable(action_catalog)
    assert ChatJobs and recover_interrupted and diagnose_mcp and PinnedBackend
