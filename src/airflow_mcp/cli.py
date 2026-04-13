"""CLI entry points for airflow-mcp-server."""

from __future__ import annotations

import asyncio
import sys

import httpx

from .config import Config, ConfigError, get_version


def validate() -> None:
    """Validate config and test connectivity to all configured Airflow instances."""
    print(f"airflow-mcp-server v{get_version()}")
    print("=" * 50)

    # Step 1: Load config
    print("\n[Config]")
    try:
        config = Config()
        print(f"  Config loaded successfully")
        print(f"  Default DDU: {config.default_ddu}")
        print(f"  Instances: {', '.join(config.available_ddus)}")
    except FileNotFoundError as e:
        print(f"  FAIL: {e}")
        sys.exit(1)
    except ConfigError as e:
        print(f"  FAIL: {e}")
        sys.exit(1)

    # Step 2: Test connectivity to each instance
    print("\n[Connectivity]")
    results = asyncio.run(_check_all_instances(config))

    failed = sum(1 for ok in results.values() if not ok)
    print(f"\n[Summary]")
    print(f"  {len(results) - failed}/{len(results)} instances reachable")

    if failed:
        sys.exit(1)
    else:
        print("  All checks passed.")


async def _check_all_instances(config: Config) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for ddu in config.available_ddus:
        instance = config.resolve(ddu)
        url = f"{instance.base_url}/api/v2/version"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=instance.auth.get_headers())
                resp.raise_for_status()
                data = resp.json()
                version = data.get("version", "?")
                print(f"  {ddu}: OK (Airflow {version}) — {instance.base_url}")
                results[ddu] = True
        except httpx.ConnectError:
            print(f"  {ddu}: FAIL (connection refused) — {instance.base_url}")
            results[ddu] = False
        except httpx.HTTPStatusError as e:
            print(f"  {ddu}: FAIL (HTTP {e.response.status_code}) — {instance.base_url}")
            if e.response.status_code in (401, 403):
                print(f"         Auth issue. Check your credentials/cookie for '{ddu}'.")
            results[ddu] = False
        except Exception as e:
            print(f"  {ddu}: FAIL ({type(e).__name__}: {e}) — {instance.base_url}")
            results[ddu] = False

    return results


def main() -> None:
    """Main CLI entry point. Dispatches subcommands."""
    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        validate()
    else:
        # Default: run the MCP server
        from .server import main as serve
        serve()
