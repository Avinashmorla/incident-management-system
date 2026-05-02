from app.models.schemas import RCARecord, WorkItem, WorkItemState


ALLOWED_TRANSITIONS: dict[WorkItemState, set[WorkItemState]] = {
    WorkItemState.OPEN: {WorkItemState.INVESTIGATING},
    WorkItemState.INVESTIGATING: {WorkItemState.RESOLVED},
    WorkItemState.RESOLVED: {WorkItemState.CLOSED, WorkItemState.INVESTIGATING},
    WorkItemState.CLOSED: set(),
}


class WorkflowError(ValueError):
    pass


class WorkItemStateMachine:
    def transition(self, item: WorkItem, target: WorkItemState, rca: RCARecord | None = None) -> WorkItem:
        if target == item.status:
            return item

        if target not in ALLOWED_TRANSITIONS[item.status]:
            raise WorkflowError(f"Cannot transition work item from {item.status} to {target}")

        if target == WorkItemState.CLOSED and rca is None and item.rca is None:
            raise WorkflowError("A complete RCA is required before closing an incident")

        item.status = target
        if rca is not None:
            item.rca = rca
        return item
