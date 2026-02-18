from fastapi import Depends, FastAPI, HTTPException, status

from ..config import Config
from ..utils.logger import get_logger
from .auth import make_auth_dependency
from .models import ConfigPatch, DomainIn, ZoneIn, ZonePatch

logger = get_logger(__name__)


def create_app(config: Config) -> FastAPI:
    app = FastAPI(
        title="Remnawave Cloudflare DNS Monitor",
        version="1.0.0",
        docs_url="/api/docs" if config.api_docs_enabled else None,
        redoc_url=None,
    )

    auth = make_auth_dependency(config.api_token)

    @app.get("/api/config", dependencies=[Depends(auth)])
    async def get_config():
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
                },
            },
        }

    @app.patch("/api/config", dependencies=[Depends(auth)])
    async def patch_config(body: ConfigPatch):
        if body.check_interval is not None:
            config.update_check_interval(body.check_interval)

        if body.log_level is not None:
            config.update_log_level(body.log_level)

        if body.telegram is not None:
            tg = body.telegram
            kwargs = {}
            if tg.enabled is not None:
                kwargs["enabled"] = tg.enabled
            if tg.locale is not None:
                kwargs["locale"] = tg.locale
            if tg.notify is not None:
                notify = {k: v for k, v in tg.notify.model_dump().items() if v is not None}
                if notify:
                    kwargs["notify"] = notify
            if kwargs:
                config.update_telegram(**kwargs)

        return {"status": "ok"}

    @app.get("/api/config/domains", dependencies=[Depends(auth)])
    async def list_domains():
        return config.domains

    @app.post("/api/config/domains", status_code=status.HTTP_201_CREATED, dependencies=[Depends(auth)])
    async def add_domain(body: DomainIn):
        try:
            config.add_domain(domain=body.domain, zones=[z.model_dump() for z in body.zones])
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        logger.info(f"API: added domain '{body.domain}'")
        return {"status": "ok"}

    @app.delete("/api/config/domains/{domain}", dependencies=[Depends(auth)])
    async def remove_domain(domain: str):
        try:
            config.remove_domain(domain)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        logger.info(f"API: removed domain '{domain}'")
        return {"status": "ok"}

    @app.post(
        "/api/config/domains/{domain}/zones",
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(auth)],
    )
    async def add_zone(domain: str, body: ZoneIn):
        try:
            config.add_zone(domain, body.model_dump())
        except ValueError as e:
            code = status.HTTP_409_CONFLICT if "already exists" in str(e) else status.HTTP_404_NOT_FOUND
            raise HTTPException(status_code=code, detail=str(e))
        logger.info(f"API: added zone '{body.name}' to '{domain}'")
        return {"status": "ok"}

    @app.patch("/api/config/domains/{domain}/zones/{zone_name}", dependencies=[Depends(auth)])
    async def patch_zone(domain: str, zone_name: str, body: ZonePatch):
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            return {"status": "ok"}
        try:
            config.update_zone(domain, zone_name, **updates)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        logger.info(f"API: updated zone '{zone_name}' of '{domain}': {updates}")
        return {"status": "ok"}

    @app.delete("/api/config/domains/{domain}/zones/{zone_name}", dependencies=[Depends(auth)])
    async def remove_zone(domain: str, zone_name: str):
        try:
            config.remove_zone(domain, zone_name)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        logger.info(f"API: removed zone '{zone_name}' from '{domain}'")
        return {"status": "ok"}

    return app
