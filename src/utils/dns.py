def build_fqdn(zone_name: str, domain: str) -> str:
    """Return the fully-qualified domain name for a zone.

    zone_name='@' represents the apex/root record, so FQDN equals domain.
    Otherwise FQDN is zone_name.domain.
    """
    return domain if zone_name == "@" else f"{zone_name}.{domain}"
