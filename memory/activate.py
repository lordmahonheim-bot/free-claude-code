"""Activation script to enable memory in routes.py.

Run this to patch routes.py with memory support.
"""

import re
from pathlib import Path


def patch_routes():
    """Patch routes.py to enable memory."""
    routes_path = Path(__file__).parent.parent / "api" / "routes.py"

    if not routes_path.exists():
        print(f"Error: {routes_path} not found")
        return False

    content = routes_path.read_text()

    # Check if already patched
    if "memory_enabled_service" in content or "MemoryEnabledProxyService" in content:
        print("Memory already enabled in routes.py")
        return True

    # Find the imports section and add memory import
    import_section = """from api.services import ClaudeProxyService

router = APIRouter()"""

    new_import_section = """from api.services import ClaudeProxyService

try:
    from memory.integration import create_memory_enabled_service
    MEMORY_ENABLED = True
except ImportError:
    MEMORY_ENABLED = False
    create_memory_enabled_service = None

router = APIRouter()"""

    if import_section not in content:
        print("Error: Could not find import section to patch")
        return False

    content = content.replace(import_section, new_import_section)

    # Find get_proxy_service and replace it
    old_function = '''def get_proxy_service(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ClaudeProxyService:
    """Build the request service for route handlers."""
    return ClaudeProxyService(
        settings,
        provider_getter=lambda provider_type: dependencies.resolve_provider(
            provider_type, app=request.app, settings=settings
        ),
        token_counter=get_token_count,
    )'''

    new_function = '''def get_proxy_service(
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Build the request service for route handlers."""
    provider_getter = lambda provider_type: dependencies.resolve_provider(
        provider_type, app=request.app, settings=settings
    )
    if MEMORY_ENABLED and create_memory_enabled_service:
        return create_memory_enabled_service(
            settings=settings,
            provider_getter=provider_getter,
            token_counter=get_token_count,
        )
    return ClaudeProxyService(
        settings=settings,
        provider_getter=provider_getter,
        token_counter=get_token_count,
    )'''

    if old_function not in content:
        print("Warning: Could not find get_proxy_service to patch, attempting manual edit")
        return False

    content = content.replace(old_function, new_function)

    # Backup original
    backup_path = routes_path.with_suffix(".py.backup")
    backup_path.write_text(routes_path.read_text())
    print(f"Backup saved to: {backup_path}")

    # Write patched version
    routes_path.write_text(content)
    print(f"Patched: {routes_path}")
    print("\nMemory system activated!")
    print("Restart the server to use memory features.")
    return True


def restore_routes():
    """Restore original routes.py from backup."""
    routes_path = Path(__file__).parent.parent / "api" / "routes.py"
    backup_path = routes_path.with_suffix(".py.backup")

    if not backup_path.exists():
        print(f"Error: Backup not found at {backup_path}")
        return False

    routes_path.write_text(backup_path.read_text())
    print(f"Restored: {routes_path}")
    return True


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        restore_routes()
    else:
        patch_routes()
