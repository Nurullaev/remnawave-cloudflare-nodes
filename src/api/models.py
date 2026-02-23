from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class NodeIn(BaseModel):
    ip: str                         # IP to write into Cloudflare DNS
    address: Optional[str] = None  # node.address to match in Remnawave (e.g. Tailscale IP); defaults to ip


class ZoneIn(BaseModel):
    name: str
    ttl: int = Field(default=120, ge=1)
    proxied: bool = False
    ips: Optional[List[str]] = None
    nodes: Optional[List[NodeIn]] = None

    @model_validator(mode="after")
    def validate_has_entries(self) -> "ZoneIn":
        if not self.ips and not self.nodes:
            raise ValueError("At least one of 'ips' or 'nodes' must be provided")
        return self


class ZonePatch(BaseModel):
    ttl: Optional[int] = Field(default=None, ge=1)
    proxied: Optional[bool] = None
    ips: Optional[List[str]] = Field(default=None, min_length=1)
    nodes: Optional[List[NodeIn]] = None


class DomainIn(BaseModel):
    domain: str
    zones: List[ZoneIn] = Field(min_length=1)


class TelegramNotifyPatch(BaseModel):
    dns_changes: Optional[bool] = None
    node_changes: Optional[bool] = None
    errors: Optional[bool] = None
    critical: Optional[bool] = None
    api_changes: Optional[bool] = None


class TelegramPatch(BaseModel):
    enabled: Optional[bool] = None
    locale: Optional[str] = Field(default=None, pattern="^(en|ru)$")
    notify: Optional[TelegramNotifyPatch] = None


class ConfigPatch(BaseModel):
    check_interval: Optional[int] = Field(default=None, ge=5)
    log_level: Optional[str] = Field(default=None, pattern="^(DEBUG|INFO|WARNING|ERROR)$")
    telegram: Optional[TelegramPatch] = None
