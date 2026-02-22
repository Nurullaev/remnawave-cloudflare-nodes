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
from ..utils.dns import build_fqdn
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

    def _format_node_stats(self, stats: "NodeStats") -> str:
        line = self._l10n.format_value("node-stats-line", {
            "online": stats.online,
            "total": stats.total,
            "offline": stats.offline,
            "disabled": stats.disabled,
        })

        if stats.zones:
            zone_lines = [
                self._l10n.format_value("node-zone-line", {
                    "zone": z.name,
                    "online": z.online,
                    "total": z.total,
                    "offline": z.offline,
                })
                for z in stats.zones
            ]
            line += "\n" + "\n".join(zone_lines)

        return line

    def format_node_state_change(self, change: NodeStateChange) -> str:
        stats = change.stats or NodeStats(total=0, online=0, offline=0, disabled=0, zones=[])
        stats_str = self._format_node_stats(stats)

        if change.current_healthy:
            return self._l10n.format_value(
                "node-became-healthy",
                {
                    "name": change.node_name,
                    "address": change.node_address,
                    "stats": stats_str,
                },
            )
        else:
            return self._l10n.format_value(
                "node-became-unhealthy",
                {
                    "name": change.node_name,
                    "address": change.node_address,
                    "reason": change.reason or self._label("node-reason-unknown"),
                    "stats": stats_str,
                },
            )

    def format_dns_change(self, change: DNSChange) -> str:
        msg_id = "dns-record-added" if change.action == "added" else "dns-record-removed"
        return self._l10n.format_value(
            msg_id, {"domain": build_fqdn(change.zone_name, change.domain), "ip": change.ip_address}
        )

    def format_dns_error(self, error: DNSError) -> str:
        return self._l10n.format_value(
            "dns-operation-error",
            {
                "domain": build_fqdn(error.zone_name, error.domain),
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

    def _label(self, key: str) -> str:
        return self._l10n.format_value(key)

    def format_service_started(self, event: ServiceStarted) -> str:
        zone_lines = []
        for domain_conf in event.domains:
            domain = domain_conf.get("domain", "")
            for zone in domain_conf.get("zones") or []:
                ips = zone.get("ips", [])
                zone_lines.append(self._l10n.format_value("service-zone-line", {
                    "zone": build_fqdn(zone['name'], domain),
                    "count": len(ips),
                }))

        header = self._label("service-summary-header")
        domains_str = "\n".join(zone_lines) if zone_lines else self._label("service-no-zones")
        summary = f"{header}\n{domains_str}"

        if event.api_enabled:
            summary += "\n\n" + self._l10n.format_value("service-api-info", {
                "host": event.api_host,
                "port": event.api_port,
            })

        return self._l10n.format_value("service-started", {"summary": summary})

    def format_service_stopped(self) -> str:
        return self._l10n.format_value("service-stopped")

    def format_api_config_updated(self, event: ApiConfigUpdated) -> str:
        return self._l10n.format_value(
            "api-config-updated", {"changes": ", ".join(event.changes), "ip": event.client_ip}
        )

    def format_api_domain_added(self, event: ApiDomainAdded) -> str:
        lines = []
        for zone in event.zones:
            name = zone.get("name", "")
            ips = zone.get("ips", [])
            ttl = zone.get("ttl", "")
            proxied = zone.get("proxied", False)
            lines.append(self._l10n.format_value("domain-zone-line", {
                "zone": build_fqdn(name, event.domain),
                "ttl": ttl,
                "proxied": proxied,
            }))
            for ip in ips:
                lines.append("  " + self._l10n.format_value("ip-list-item", {"ip": ip}))
        details = "\n".join(lines)
        return self._l10n.format_value(
            "api-domain-added", {"domain": event.domain, "details": details, "ip": event.client_ip}
        )

    def format_api_domain_removed(self, event: ApiDomainRemoved) -> str:
        return self._l10n.format_value(
            "api-domain-removed", {"domain": event.domain, "ip": event.client_ip}
        )

    def format_api_zone_added(self, event: ApiZoneAdded) -> str:
        ip_list = "\n".join(
            self._l10n.format_value("ip-list-item", {"ip": ip}) for ip in event.ips
        )
        details = self._l10n.format_value("zone-added-details", {
            "ip_list": ip_list,
            "ttl": event.ttl,
            "proxied": event.proxied,
        })
        return self._l10n.format_value(
            "api-zone-added",
            {"fqdn": build_fqdn(event.zone_name, event.domain), "details": details, "ip": event.client_ip},
        )

    def format_api_zone_updated(self, event: ApiZoneUpdated) -> str:
        change_lines = []
        for k, v in event.changes.items():
            if k == "ips":
                ip_list = "\n".join(
                    self._l10n.format_value("ip-list-item", {"ip": ip}) for ip in v
                )
                change_lines.append(self._l10n.format_value("zone-change-ips", {"ip_list": ip_list}))
            elif k == "ttl":
                change_lines.append(self._l10n.format_value("zone-change-ttl", {"value": v}))
            elif k == "proxied":
                change_lines.append(self._l10n.format_value("zone-change-proxied", {"value": v}))
            else:
                change_lines.append(f"{k}={v}")
        return self._l10n.format_value(
            "api-zone-updated",
            {"fqdn": build_fqdn(event.zone_name, event.domain), "changes": "\n".join(change_lines),
             "ip": event.client_ip},
        )

    def format_api_zone_removed(self, event: ApiZoneRemoved) -> str:
        return self._l10n.format_value(
            "api-zone-removed", {"fqdn": build_fqdn(event.zone_name, event.domain), "ip": event.client_ip}
        )
