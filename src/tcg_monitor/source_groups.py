from __future__ import annotations

from tcg_monitor.models import SourceConfig

ALWAYS_ON_GROUP = "always"
EXPEDITION_SENDAI_GROUP = "expedition_sendai"
EXPEDITION_TOKYO_ROUTE_GROUP = "expedition_tokyo_route"
EXPEDITION_TOKYO_GROUP = "expedition_tokyo"
EXPEDITION_GROUPS = frozenset(
    {
        EXPEDITION_SENDAI_GROUP,
        EXPEDITION_TOKYO_ROUTE_GROUP,
        EXPEDITION_TOKYO_GROUP,
    }
)


def active_source_filter(
    sources: list[SourceConfig],
    requested_source_ids: set[str] | None,
    *,
    enabled_expedition_groups: frozenset[str] | set[str],
) -> set[str]:
    """Return source IDs that may reach the network in this run."""

    allowed = {
        source.id
        for source in sources
        if source.enabled
        and (
            source.activation_group == ALWAYS_ON_GROUP
            or source.activation_group in enabled_expedition_groups
        )
    }
    if requested_source_ids is None:
        return allowed
    return requested_source_ids & allowed
