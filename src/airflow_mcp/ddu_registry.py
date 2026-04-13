"""Known Delivery Hero DDU codes and their Airflow URL patterns.

This registry maps DDU codes to their Airflow base URLs following
the DH Data Hub convention: airflow-{ddu}.datahub.deliveryhero.net

Add new DDUs here as they're discovered. The install script and
config generation use this as the source of truth for DH instances.
"""

from __future__ import annotations

# URL pattern for DH Airflow instances
DH_URL_PATTERN = "https://airflow-{ddu}.datahub.deliveryhero.net"

# Known DDUs — add more as you discover them.
# Format: code -> human-readable description
# Wex TODO: Verify these and add missing ones from the Data Hub directory.
KNOWN_DDUS: dict[str, str] = {
    # --- APAC ---
    "eiga": "Eiga (Japan)",
    "paa": "PandaApp (APAC)",
    "fpk": "Foodpanda (South Korea)",
    "fpt": "Foodpanda (Thailand)",
    "fps": "Foodpanda (Singapore)",
    "fpm": "Foodpanda (Malaysia)",
    "fpp": "Foodpanda (Philippines)",
    "fpb": "Foodpanda (Bangladesh)",
    "fpl": "Foodpanda (Laos)",
    "fpc": "Foodpanda (Cambodia)",
    "fph": "Foodpanda (Hong Kong)",
    "fpmm": "Foodpanda (Myanmar)",
    # --- MENA ---
    "tlb": "Talabat (MENA)",
    "hun": "Hungerstation (Saudi Arabia)",
    # --- Europe ---
    "mjm": "Mjam (Austria)",
    "gfg": "GFG (Global Fashion Group)",
    "efg": "EFG (Europe)",
    # --- Americas ---
    "ped": "PedidosYa (LatAm)",
    "dmh": "Delivery Much (Brazil)",
    # --- Platform ---
    "dhp": "DH Platform (shared)",
}


def get_dh_url(ddu: str) -> str:
    """Get the Airflow URL for a DH DDU code."""
    return DH_URL_PATTERN.format(ddu=ddu)


def list_known_ddus() -> dict[str, str]:
    """Return all known DDUs with descriptions."""
    return dict(KNOWN_DDUS)
