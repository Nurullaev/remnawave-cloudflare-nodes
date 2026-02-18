from pathlib import Path
from typing import Optional

from fluent.runtime import FluentLocalization, FluentResourceLoader

from .events import (
    NodeStateChange, NodeStats, DNSChange, DNSError,
    CriticalState, CriticalStateRecovered, HealthCheckError,
    ServiceStarted,
    ApiConfigUpdated, ApiDomainAdded, ApiDomainRemoved,
    ApiZoneAdded, ApiZoneUpdated, ApiZoneRemoved,
)
from ..utils.logger import get_logger


class MessageFormatter:
    SUPPORTED_LOCALES = ["en", "ru"]
    DEFAULT_LOCALE = "en"

    def __init__(self, locale: str = "en", locales_dir: Optional[Path] = None):
        self.logger = get_logger(__name__)
        self.locale = locale if locale in self.SUPPORTED_LOCALES else self.DEFAULT_LOCALE

        if locales_dir is None:
            locales_dir = Path(__file__).parent.parent / "locales"

        self.locales_dir = locales_dir
        self._loader = FluentResourceLoader(str(locales_dir / "{locale}"))
        self._l10n = FluentLocalization(
            locales=[self.locale, self.DEFAULT_LOCALE],
            resource_ids=["messages.ftl"],
            resource_loader=self._loader,
        )

    def format_node_state_change(self, change: NodeStateChange) -> str:
        stats = change.stats or NodeStats(total=0, online=0, disabled=0)

        if change.current_healthy:
            return self._l10n.format_value(
                "node-became-healthy",
                {
                    "name": change.node_name,
                    "address": change.node_address,
                    "total": stats.total,
                    "online": stats.online,
                    "disabled": stats.disabled,
                },
            )
        else:
            return self._l10n.format_value(
                "node-became-unhealthy",
                {
                    "name": change.node_name,
                    "address": change.node_address,
                    "reason": change.reason or "unknown",
                    "total": stats.total,
                    "online": stats.online,
                    "disabled": stats.disabled,
                },
            )

    def format_dns_change(self, change: DNSChange) -> str:
        msg_id = "dns-record-added" if change.action == "added" else "dns-record-removed"
        return self._l10n.format_value(
            msg_id, {"domain": f"{change.zone_name}.{change.domain}", "ip": change.ip_address}
        )

    def format_dns_error(self, error: DNSError) -> str:
        return self._l10n.format_value(
            "dns-operation-error",
            {
                "domain": f"{error.zone_name}.{error.domain}",
                "ip": error.ip_address,
                "action": error.action,
                "error": error.error_message,
            },
        )

    def format_critical_state(self, state: CriticalState) -> str:
        return self._l10n.format_value(
            "all-nodes-down", {"total": state.total_nodes, "nodes": ", ".join(state.down_nodes)}
        )

    def format_critical_recovered(self, state: CriticalStateRecovered) -> str:
        return self._l10n.format_value(
            "all-nodes-recovered", {"total": state.total_nodes, "online": state.online_nodes}
        )

    def format_health_check_error(self, error: HealthCheckError) -> str:
        return self._l10n.format_value("health-check-error", {"error": error.error_message})

    def format_service_started(self, event: ServiceStarted) -> str:
        if self.locale == "ru":
            domains_label = "📡 Домены"
            api_label = "🔌 API"
        else:
            domains_label = "📡 Domains"
            api_label = "🔌 API"

        zone_lines = []
        for domain_conf in event.domains:
            domain = domain_conf.get("domain", "")
            for zone in domain_conf.get("zones", []):
                ip_count = len(zone.get("ips", []))
                zone_lines.append(f"• {zone['name']}.{domain} — {ip_count} IP(s)")

        domains_str = "\n".join(zone_lines) if zone_lines else "—"
        summary = f"{domains_label}:\n{domains_str}"

        if event.api_enabled:
            summary += f"\n\n{api_label}: {event.api_host}:{event.api_port}"

        return self._l10n.format_value("service-started", {"summary": summary})

    def format_service_stopped(self) -> str:
        return self._l10n.format_value("service-stopped")

    def format_api_config_updated(self, event: ApiConfigUpdated) -> str:
        return self._l10n.format_value(
            "api-config-updated", {"changes": ", ".join(event.changes), "ip": event.client_ip}
        )

    def format_api_domain_added(self, event: ApiDomainAdded) -> str:
        return self._l10n.format_value(
            "api-domain-added", {"domain": event.domain, "zones": event.zone_count, "ip": event.client_ip}
        )

    def format_api_domain_removed(self, event: ApiDomainRemoved) -> str:
        return self._l10n.format_value(
            "api-domain-removed", {"domain": event.domain, "ip": event.client_ip}
        )

    def format_api_zone_added(self, event: ApiZoneAdded) -> str:
        return self._l10n.format_value(
            "api-zone-added",
            {"zone": event.zone_name, "domain": event.domain, "ips": event.ip_count, "ip": event.client_ip},
        )

    def format_api_zone_updated(self, event: ApiZoneUpdated) -> str:
        return self._l10n.format_value(
            "api-zone-updated",
            {"zone": event.zone_name, "domain": event.domain, "changes": ", ".join(event.changes), "ip": event.client_ip},
        )

    def format_api_zone_removed(self, event: ApiZoneRemoved) -> str:
        return self._l10n.format_value(
            "api-zone-removed", {"zone": event.zone_name, "domain": event.domain, "ip": event.client_ip}
        )
