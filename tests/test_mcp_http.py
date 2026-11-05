import asyncio
import socket

import httpx2
import pytest
import uvicorn
from langgraph.checkpoint.memory import InMemorySaver
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from commerce.api import create_app
from commerce.schemas import Actor


@pytest.mark.asyncio
async def test_sdk_real_http_modern_legacy_auth_and_owner_isolation(system):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    system.settings.public_base_url = f"http://127.0.0.1:{port}"
    app = create_app(system.settings, checkpointer=InMemorySaver(), source=system.worker.source)
    token, _ = app.state.identity.issue_session(system.actor)
    session = system.service.create_session(
        system.actor, "Buy water under $3", "mcp-owner-isolation"
    )
    other = system.service.create_session(
        Actor(user_id="sam"), "Buy water under $3", "mcp-other-owner-key"
    )
    runner = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False)
    )
    task = asyncio.create_task(runner.serve())
    try:
        for _ in range(200):
            if runner.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.02)
        assert runner.started
        resource = system.settings.public_base_url + "/mcp"
        for mode in ("auto", "legacy"):
            async with httpx2.AsyncClient(
                headers={"Authorization": "Bearer " + token}, trust_env=False, timeout=10
            ) as http:
                async with Client(
                    streamable_http_client(resource, http_client=http), mode=mode
                ) as client:
                    tools = await client.list_tools()
                    assert {tool.name for tool in tools.tools} == {
                        "search_products",
                        "get_purchase_status",
                    }
                    assert all(tool.output_schema for tool in tools.tools)
                    result = await client.call_tool("get_purchase_status", {"session_id": session})
                    assert result.structured_content["purchase"]["id"] == session
                    denied = await client.call_tool("get_purchase_status", {"session_id": other})
                    assert denied.is_error and other not in str(denied.content)
        async with httpx2.AsyncClient(trust_env=False) as http:
            metadata = await http.get(
                system.settings.public_base_url + "/.well-known/oauth-protected-resource/mcp"
            )
            assert metadata.json()["resource"] == resource
            for bearer in ("", "invalid"):
                response = await http.post(
                    resource,
                    headers={"Authorization": "Bearer " + bearer} if bearer else {},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                )
                assert response.status_code == 401
            oversized = await http.post(resource, content=b"x" * 65537)
            assert oversized.status_code == 413
            # Browser cookies are not an implicit authorization path into MCP.
            http.cookies.set("commerce_session", token)
            assert (await http.post(resource)).status_code == 401
    finally:
        runner.should_exit = True
        await task
