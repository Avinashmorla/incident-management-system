from datetime import datetime, timedelta, timezone

import pytest

from app.models.schemas import ComponentType, RCARecord, RootCauseCategory, Severity, WorkItem, WorkItemState
from app.services.workflow import WorkItemStateMachine, WorkflowError


def make_item() -> WorkItem:
    now = datetime.now(timezone.utc)
    return WorkItem(
        component_id="RDBMS_PRIMARY_01",
        component_type=ComponentType.RDBMS,
        severity=Severity.P0,
        status=WorkItemState.RESOLVED,
        first_signal_at=now - timedelta(minutes=12),
        last_signal_at=now,
        signal_count=100,
        alert_channel="pagerduty:database-oncall:RDBMS_PRIMARY_01",
    )


def make_rca(item: WorkItem) -> RCARecord:
    return RCARecord(
        incident_start=item.first_signal_at,
        incident_end=datetime.now(timezone.utc),
        root_cause_category=RootCauseCategory.CAPACITY,
        fix_applied="Promoted read replica and increased pool capacity.",
        prevention_steps="Add saturation alerts and replay this scenario in load tests.",
        mttr_seconds=720,
    )


def test_closing_without_rca_is_rejected():
    machine = WorkItemStateMachine()

    with pytest.raises(WorkflowError, match="RCA"):
        machine.transition(make_item(), WorkItemState.CLOSED)


def test_closing_with_complete_rca_is_allowed():
    machine = WorkItemStateMachine()
    item = make_item()

    closed = machine.transition(item, WorkItemState.CLOSED, make_rca(item))

    assert closed.status == WorkItemState.CLOSED
    assert closed.rca is not None
    assert closed.rca.fix_applied.startswith("Promoted")


def test_invalid_state_jump_is_rejected():
    machine = WorkItemStateMachine()
    item = make_item()
    item.status = WorkItemState.OPEN

    with pytest.raises(WorkflowError, match="Cannot transition"):
        machine.transition(item, WorkItemState.CLOSED, make_rca(item))
