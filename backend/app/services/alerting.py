from abc import ABC, abstractmethod

from app.models.schemas import ComponentType, Severity


class AlertingStrategy(ABC):
    @abstractmethod
    def classify(self, component_id: str) -> tuple[Severity, str]:
        raise NotImplementedError


class PagerDutyP0Strategy(AlertingStrategy):
    def classify(self, component_id: str) -> tuple[Severity, str]:
        return Severity.P0, f"pagerduty:database-oncall:{component_id}"


class PlatformP1Strategy(AlertingStrategy):
    def classify(self, component_id: str) -> tuple[Severity, str]:
        return Severity.P1, f"slack:platform-critical:{component_id}"


class CacheP2Strategy(AlertingStrategy):
    def classify(self, component_id: str) -> tuple[Severity, str]:
        return Severity.P2, f"slack:cache-ops:{component_id}"


class DefaultP3Strategy(AlertingStrategy):
    def classify(self, component_id: str) -> tuple[Severity, str]:
        return Severity.P3, f"email:service-owner:{component_id}"


class AlertingStrategyFactory:
    def __init__(self) -> None:
        self._strategies: dict[ComponentType, AlertingStrategy] = {
            ComponentType.RDBMS: PagerDutyP0Strategy(),
            ComponentType.NOSQL: PlatformP1Strategy(),
            ComponentType.QUEUE: PlatformP1Strategy(),
            ComponentType.MCP_HOST: PlatformP1Strategy(),
            ComponentType.CACHE: CacheP2Strategy(),
            ComponentType.API: DefaultP3Strategy(),
        }

    def for_component(self, component_type: ComponentType) -> AlertingStrategy:
        return self._strategies.get(component_type, DefaultP3Strategy())
