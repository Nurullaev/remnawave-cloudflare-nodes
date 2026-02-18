from typing import List, Optional
from pydantic import BaseModel, Field


class ZoneIn(BaseModel):
    name: str
    ttl: int = Field(default=120, ge=1)
    proxied: bool = False
    ips: List[str] = Field(min_length=1)


class ZonePatch(BaseModel):
    ttl: Optional[int] = Field(default=None, ge=1)
    proxied: Optional[bool] = None
    ips: Optional[List[str]] = Field(default=None, min_length=1)


class DomainIn(BaseModel):
    domain: str
    zones: List[ZoneIn] = Field(min_length=1)


class TelegramNotifyPatch(BaseModel):
    dns_changes: Optional[bool] = None
    node_changes: Optional[bool] = None
    errors: Optional[bool] = None
    critical: Optional[bool] = None


class TelegramPatch(BaseModel):
    enabled: Optional[bool] = None
    locale: Optional[str] = Field(default=None, pattern="^(en|ru)$")
    notify: Optional[TelegramNotifyPatch] = None


class ConfigPatch(BaseModel):
    check_interval: Optional[int] = Field(default=None, ge=5)
    log_level: Optional[str] = Field(default=None, pattern="^(DEBUG|INFO|WARNING|ERROR)$")
    telegram: Optional[TelegramPatch] = None
