#!/usr/bin/env python3
"""Patch routes.py to add memory hooks.

Usage:
    python -m memory.patch_routes
    python -m memory.patch_routes --restore
"""

import argparse
from pathlib import Path


def patch_routes():
    """Patch api/routes.py with memory hooks."""
    routes_file = Path("api/routes.py")
    if not routes_file.exists():
        print(f"Error: {routes_file} not found")
        return False

    content = routes_file.read_text()

    # Check if already patched
    if "# MEMORY: START" in content:
        print("routes.py is already patched")
        return True

    # Find the create_message function
    marker = '''@router.post("/v1/messages")
async def create_message(
    request_data: MessagesRequest,
    service: ClaudeProxyService = Depends(get_proxy_service),
    _auth=Depends(require_api_key),
):
    """Create a message (always streaming)."""
    return service.create_message(request_data)'''

    if marker not in content:
        print("Error: Could not find create_message function to patch")
        return False

    patched = '''# MEMORY: START
from memory.hooks import before_request, after_response
# MEMORY: END

@router.post("/v1/messages")
async def create_message(
    request_data: MessagesRequest,
    service: ClaudeProxyService = Depends(get_proxy_service),
    settings: Settings = Depends(get_settings),
    _auth=Depends(require_api_key),
):
    """Create a message (always streaming) with memory."""
    # MEMORY: START
    session_id = before_request(request_data, n_context=4)
    model = getattr(request_data, "model", None) or settings.model
    provider = settings.provider_type
    # MEMORY: END
    response = service.create_message(request_data)
    # MEMORY: START
    return after_response(session_id, response, request_data, model, provider)
    # MEMORY: END'''

    new_content = content.replace(marker, patched)

    # Backup
    backup = routes_file.with_suffix(".py.backup")
    backup.write_text(content)
    print(f"Backup created: {backup}")

    # Write
    routes_file.write_text(new_content)
    print(f"Patched: {routes_file}")

    return True


def restore_routes():
    """Restore routes.py from backup."""
    routes_file = Path("api/routes.py")
    backup = routes_file.with_suffix(".py.backup")

    if not backup.exists():
        print("Error: Backup not found")
        return False

    routes_file.write_text(backup.read_text())
    print(f"Restored from: {backup}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Patch routes.py for memory")
    parser.add_argument("--restore", action="store_true", help="Restore from backup")
    args = parser.parse_args()

    if args.restore:
        restore_routes()
    else:
        patch_routes()
