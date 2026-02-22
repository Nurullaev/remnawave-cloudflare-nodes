from typing import TYPE_CHECKING, Dict, Optional, Set

from .config import Config
from .remnawave import NodeMonitor
from .cloudflare_dns import CloudflareClient, DNSManager
from .utils.logger import get_logger

if TYPE_CHECKING:
    from .telegram import TelegramNotifier


class MonitoringService:
    def __init__(
        self,
        config: Config,
        node_monitor: NodeMonitor,
        cloudflare_client: CloudflareClient,
        dns_manager: DNSManager,
        notifier: Optional["TelegramNotifier"] = None,
    ):
        self.config = config
        self.node_monitor = node_monitor
        self.cloudflare_client = cloudflare_client
        self.dns_manager = dns_manager
        self.notifier = notifier
        self.logger = get_logger(__name__)
        self._zone_id_cache: Dict[str, str] = {}
        self._previous_node_states: Dict[str, bool] = {}
        self._previous_all_down: bool = False

    async def initialize_and_print_zones(self) -> None:
        self.logger.info("Initializing zones")

        current_domain = None
        current_zone_id: Optional[str] = None
        for zone in self.config.get_all_zones():
            domain = zone["domain"]

            if domain != current_domain:
                current_zone_id = await self._get_zone_id(domain)
                current_domain = domain
                if not current_zone_id:
                    self.logger.warning(f"Could not find zone_id for domain {domain}")
                    continue
                self.logger.info(f"Domain: {domain}, Zone ID: {current_zone_id}")

            if not current_zone_id:
                continue

            full_domain = f"{zone['name']}.{domain}"
            self.logger.info(f"  Zone: {full_domain}, TTL: {zone['ttl']}, Proxied: {zone['proxied']}")
            self.logger.info(f"  Configured IPs: {', '.join(zone['ips'])}")

            existing_records = await self.cloudflare_client.get_dns_records(current_zone_id, name=full_domain, record_type="A")
            if existing_records:
                existing_ips = [record["content"] for record in existing_records]
                self.logger.info(f"  Existing DNS records: {', '.join(existing_ips)}")
            else:
                self.logger.info("  Existing DNS records: None")

        self.logger.info("Initialization complete")

    async def perform_health_check(self) -> None:
        self.logger.info("Starting health check cycle")

        try:
            configured_ips = self._get_all_configured_ips()

            all_nodes = await self.node_monitor.check_all_nodes()
            configured_nodes = [node for node in all_nodes if node.address in configured_ips]

            healthy_nodes = [node for node in configured_nodes if node.is_healthy]
            unhealthy_nodes = [node for node in configured_nodes if not node.is_healthy]
            healthy_addresses = {node.address for node in healthy_nodes}

            self.logger.info(
                f"Nodes: {len(healthy_nodes)}/{len(configured_nodes)} online, {len(unhealthy_nodes)} unhealthy"
            )

            if unhealthy_nodes:
                unhealthy_info = []
                for node in unhealthy_nodes:
                    reason = []
                    if not node.is_connected:
                        reason.append("disconnected")
                    if node.is_disabled:
                        reason.append("disabled")
                    if not node.xray_version:
                        reason.append("no xray")
                    unhealthy_info.append(f"{node.address} ({', '.join(reason)})")
                self.logger.info(f"Unhealthy nodes: {'; '.join(unhealthy_info)}")

            self._check_node_transitions(configured_nodes)
            self._check_critical_state(configured_nodes, unhealthy_nodes)

            await self._sync_all_zones(healthy_addresses)

            self.logger.info("Health check cycle completed")

        except Exception as e:
            self.logger.error(f"Error during health check: {e}", exc_info=True)
            if self.notifier and self.config.telegram_notify_errors:
                from .telegram import HealthCheckError

                self.notifier.notify_health_check_error(HealthCheckError(error_message=str(e)))
            raise

    def _get_all_configured_ips(self) -> Set[str]:
        configured_ips = set()
        for zone in self.config.get_all_zones():
            configured_ips.update(zone["ips"])
        return configured_ips

    async def _sync_all_zones(self, healthy_addresses: Set[str]) -> None:
        for zone in self.config.get_all_zones():
            domain = zone["domain"]

            zone_id = await self._get_zone_id(domain)
            if not zone_id:
                self.logger.warning(f"Could not find zone_id for domain {domain}, skipping")
                continue

            await self.dns_manager.sync_dns_records(
                zone_id=zone_id,
                zone_name=zone["name"],
                domain=domain,
                configured_ips=zone["ips"],
                healthy_ips=healthy_addresses,
                ttl=zone["ttl"],
                proxied=zone["proxied"],
            )

    async def _get_zone_id(self, domain: str) -> Optional[str]:
        if domain in self._zone_id_cache:
            return self._zone_id_cache[domain]

        zone_id = await self.cloudflare_client.get_zone_id_by_domain(domain)
        if zone_id:
            self._zone_id_cache[domain] = zone_id

        return zone_id

    def _check_node_transitions(self, nodes) -> None:
        if not self.notifier or not self.config.telegram_notify_node_changes:
            return

        from .telegram import NodeStateChange, NodeStats, ZoneStats

        total = len(nodes)
        disabled = sum(1 for n in nodes if n.is_disabled)

        # Build zone → IPs mapping from config
        zone_ip_map: Dict[str, Set[str]] = {}
        for zone in self.config.get_all_zones():
            key = f"{zone['name']}.{zone['domain']}"
            zone_ip_map[key] = set(zone["ips"])

        # Group nodes by zone
        zone_nodes: Dict[str, list] = {
            key: [n for n in nodes if n.address in ips]
            for key, ips in zone_ip_map.items()
        }

        # Start global and per-zone online counts from the *previous* known states.
        # New nodes (not seen before) fall back to their current state so they don't
        # fire a transition on first sight.
        online = sum(1 for n in nodes if self._previous_node_states.get(n.address, n.is_healthy))
        zone_online: Dict[str, int] = {
            key: sum(1 for n in znodes if self._previous_node_states.get(n.address, n.is_healthy))
            for key, znodes in zone_nodes.items()
        }

        for node in nodes:
            prev_healthy = self._previous_node_states.get(node.address)
            curr_healthy = node.is_healthy

            if prev_healthy is None:
                self._previous_node_states[node.address] = curr_healthy
                continue

            if prev_healthy == curr_healthy:
                continue

            # Apply this node's transition to the running counters before notifying,
            # so each notification reflects the state after exactly this change.
            delta = 1 if curr_healthy else -1
            online += delta

            node_zone: Optional[ZoneStats] = None
            for key, ips in zone_ip_map.items():
                if node.address in ips:
                    zone_online[key] += delta
                    node_zone = ZoneStats(
                        name=key,
                        total=len(zone_nodes[key]),
                        online=zone_online[key],
                        offline=len(zone_nodes[key]) - zone_online[key],
                    )
                    break

            zones_stats = [node_zone] if node_zone else []

            stats = NodeStats(
                total=total,
                online=online,
                offline=total - online,
                disabled=disabled,
                zones=zones_stats,
            )

            reason = None
            if not curr_healthy:
                reasons = []
                if not node.is_connected:
                    reasons.append("disconnected")
                if node.is_disabled:
                    reasons.append("disabled")
                if not node.xray_version:
                    reasons.append("no xray")
                reason = ", ".join(reasons) if reasons else "unknown"

            self.notifier.notify_node_state_change(
                NodeStateChange(
                    node_name=node.name,
                    node_address=node.address,
                    previous_healthy=prev_healthy,
                    current_healthy=curr_healthy,
                    stats=stats,
                    reason=reason,
                )
            )

            self._previous_node_states[node.address] = curr_healthy

    async def cleanup_zone(self, domain: str, zone_name: str) -> None:
        zone_id = await self._get_zone_id(domain)
        if not zone_id:
            self.logger.warning(f"Cannot cleanup {zone_name}.{domain}: zone_id not found")
            return
        await self.dns_manager.cleanup_zone(zone_id, zone_name, domain)

    async def cleanup_domain(self, domain: str) -> None:
        zone_id = await self._get_zone_id(domain)
        if not zone_id:
            self.logger.warning(f"Cannot cleanup domain {domain}: zone_id not found")
            return
        for domain_conf in self.config.domains:
            if domain_conf.get("domain") == domain:
                for zone in domain_conf.get("zones") or []:
                    await self.dns_manager.cleanup_zone(zone_id, zone["name"], domain)
                return

    def _check_critical_state(self, configured_nodes, unhealthy_nodes) -> None:
        if not self.notifier or not self.config.telegram_notify_critical:
            return

        all_down = 0 < len(configured_nodes) == len(unhealthy_nodes)

        if all_down and not self._previous_all_down:
            from .telegram import CriticalState

            self.notifier.notify_critical_state(
                CriticalState(total_nodes=len(configured_nodes), down_nodes=[n.address for n in unhealthy_nodes])
            )
        elif not all_down and self._previous_all_down:
            from .telegram import CriticalStateRecovered

            online_count = len(configured_nodes) - len(unhealthy_nodes)
            self.notifier.notify_critical_recovered(
                CriticalStateRecovered(total_nodes=len(configured_nodes), online_nodes=online_count)
            )

        self._previous_all_down = all_down
