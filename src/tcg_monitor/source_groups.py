from __future__ import annotations

from tcg_monitor.models import SourceConfig

ALWAYS_ON_GROUP = "always"
ADDITIONAL_GROUP = "additional"


def active_source_filter(
    sources: list[SourceConfig],
    requested_source_ids: set[str] | None,
    *,
    additional_monitoring_enabled: bool,
) -> set[str]:
    """Return source IDs that may reach the network in this run."""

    allowed = {
        source.id
        for source in sources
        if source.enabled
        and (
            source.activation_group == ALWAYS_ON_GROUP
            or (
                additional_monitoring_enabled
                and source.activation_group == ADDITIONAL_GROUP
            )
        )
    }
    if requested_source_ids is None:
        return allowed
    return requested_source_ids & allowed
