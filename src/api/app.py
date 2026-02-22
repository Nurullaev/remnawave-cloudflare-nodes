from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, HTTPException, Request, status

from ..config import Config
from ..telegram import (
    TelegramNotifier,
    ApiConfigUpdated,
    ApiDomainAdded,
    ApiDomainRemoved,
    ApiZoneAdded,
    ApiZoneUpdated,
    ApiZoneRemoved,
)
from ..utils.logger import get_logger
from .auth import make_auth_dependency
from .models import ConfigPatch, DomainIn, ZoneIn, ZonePatch

if TYPE_CHECKING:
    from ..monitoring_service import MonitoringService

logger = get_logger(__name__)


def _client_ip(request: Request) -> str:
    if forwarded_for := request.headers.get("X-Forwarded-For"):
        return forwarded_for.split(",")[0].strip()
    if real_ip := request.headers.get("X-Real-IP"):
        return real_ip
    if request.client:
        return request.client.host
    return "unknown"


def create_app(config: Config, notifier: TelegramNotifier, monitoring_service: "MonitoringService") -> FastAPI:
    app = FastAPI(
        title="Remnawave Cloudflare DNS Monitor",
        version="1.0.0",
        docs_url="/api/docs" if config.api_docs_enabled else None,
        redoc_url=None,
    )

    auth = make_auth_dependency(config.api_token)

    @app.get("/api/config", dependencies=[Depends(auth)])
    async def get_config(request: Request):
        logger.debug(f"API: GET config [from {_client_ip(request)}]")
        return {
            "check_interval": config.check_interval,
            "log_level": config.log_level,
            "domains": config.domains,
            "telegram": {
                "enabled": config.telegram_enabled,
                "locale": config.telegram_locale,
                "notify": {
                    "dns_changes": config.telegram_notify_dns_changes,
                    "node_changes": config.telegram_notify_node_changes,
                    "errors": config.telegram_notify_errors,
                    "critical": config.telegram_notify_critical,
                    "api_changes": config.telegram_notify_api_changes,
                },
            },
        }

    @app.patch("/api/config", dependencies=[Depends(auth)])
    async def patch_config(request: Request, body: ConfigPatch):
        ip = _client_ip(request)
        changes = []

        if body.check_interval is not None:
            config.update_check_interval(body.check_interval)
            changes.append(f"check_interval={body.check_interval}")

        if body.log_level is not None:
            config.update_log_level(body.log_level)
            changes.append(f"log_level={body.log_level}")

        if body.telegram is not None:
            tg = body.telegram
            kwargs = {}
            if tg.enabled is not None:
                kwargs["enabled"] = tg.enabled
                changes.append(f"telegram.enabled={tg.enabled}")
            if tg.locale is not None:
                kwargs["locale"] = tg.locale
                changes.append(f"telegram.locale={tg.locale}")
            if tg.notify is not None:
                notify = {k: v for k, v in tg.notify.model_dump().items() if v is not None}
                if notify:
                    kwargs["notify"] = notify
                    for k, v in notify.items():
                        changes.append(f"telegram.notify.{k}={v}")
            if kwargs:
                config.update_telegram(**kwargs)

        if changes:
            logger.info(f"API: updated config [{', '.join(changes)}] [from {ip}]")
            notifier.notify_api_config_updated(ApiConfigUpdated(changes=changes, client_ip=ip))
        return {"status": "ok"}

    @app.get("/api/config/domains", dependencies=[Depends(auth)])
    async def list_domains(request: Request):
        domains = config.domains
        logger.debug(f"API: GET domains — {len(domains)} domain(s) [from {_client_ip(request)}]")
        return domains

    @app.post("/api/config/domains", status_code=status.HTTP_201_CREATED, dependencies=[Depends(auth)])
    async def add_domain(request: Request, body: DomainIn):
        ip = _client_ip(request)
        try:
            config.add_domain(domain=body.domain, zones=[z.model_dump() for z in body.zones])
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        logger.info(f"API: added domain '{body.domain}' with {len(body.zones)} zone(s) [from {ip}]")
        notifier.notify_api_domain_added(
            ApiDomainAdded(domain=body.domain, zones=[z.model_dump() for z in body.zones], client_ip=ip)
        )
        return {"status": "ok"}

    @app.delete("/api/config/domains/{domain}", dependencies=[Depends(auth)])
    async def remove_domain(request: Request, domain: str):
        ip = _client_ip(request)
        if not any(d.get("domain") == domain for d in config.domains):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Domain '{domain}' not found")
        # Cleanup DNS before removing from config so zones are still readable
        await monitoring_service.cleanup_domain(domain)
        config.remove_domain(domain)
        logger.info(f"API: removed domain '{domain}' [from {ip}]")
        notifier.notify_api_domain_removed(ApiDomainRemoved(domain=domain, client_ip=ip))
        return {"status": "ok"}

    @app.post(
        "/api/config/domains/{domain}/zones",
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(auth)],
    )
    async def add_zone(request: Request, domain: str, body: ZoneIn):
        ip = _client_ip(request)
        try:
            config.add_zone(domain, body.model_dump())
        except ValueError as e:
            code = status.HTTP_409_CONFLICT if "already exists" in str(e) else status.HTTP_404_NOT_FOUND
            raise HTTPException(status_code=code, detail=str(e))
        logger.info(
            f"API: added zone '{body.name}' to '{domain}' "
            f"[{len(body.ips)} IP(s), ttl={body.ttl}, proxied={body.proxied}] "
            f"[from {ip}]"
        )
        notifier.notify_api_zone_added(
            ApiZoneAdded(
                domain=domain, zone_name=body.name, ips=body.ips,
                ttl=body.ttl, proxied=body.proxied, client_ip=ip,
            )
        )
        return {"status": "ok"}

    @app.patch("/api/config/domains/{domain}/zones/{zone_name}", dependencies=[Depends(auth)])
    async def patch_zone(request: Request, domain: str, zone_name: str, body: ZonePatch):
        ip = _client_ip(request)
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            return {"status": "ok"}
        try:
            config.update_zone(domain, zone_name, **updates)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        log_parts = [f"ips={', '.join(v)}" if k == "ips" else f"{k}={v}" for k, v in updates.items()]
        logger.info(f"API: updated zone '{zone_name}' of '{domain}' [{', '.join(log_parts)}] [from {ip}]")
        notifier.notify_api_zone_updated(
            ApiZoneUpdated(domain=domain, zone_name=zone_name, changes=updates, client_ip=ip)
        )
        return {"status": "ok"}

    @app.delete("/api/config/domains/{domain}/zones/{zone_name}", dependencies=[Depends(auth)])
    async def remove_zone(request: Request, domain: str, zone_name: str):
        ip = _client_ip(request)
        # Validate before cleanup
        try:
            config.remove_zone(domain, zone_name)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        await monitoring_service.cleanup_zone(domain, zone_name)
        logger.info(f"API: removed zone '{zone_name}' from '{domain}' [from {ip}]")
        notifier.notify_api_zone_removed(ApiZoneRemoved(domain=domain, zone_name=zone_name, client_ip=ip))
        return {"status": "ok"}

    return app
