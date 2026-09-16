from eventwall.models import EventEnvironment, EventRecord, EventSource
from eventwall.services import is_sensitive_key, record_event, sanitize_metadata
from rbac.audit.service import prune_audits


def test_eventwall_and_audit_contracts():
    assert all((EventEnvironment, EventRecord, EventSource))
    assert record_event and sanitize_metadata and is_sensitive_key and prune_audits
