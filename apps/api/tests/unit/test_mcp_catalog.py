from app.adapters.mcp_catalog_http import FakeMcpCatalog, HttpMcpCatalog
from app.application.list_mcp_tools import list_mcp_tools


async def test_fake_catalog_lists_expected_tools() -> None:
    catalog = await list_mcp_tools(FakeMcpCatalog())
    names = {tool.name for tool in catalog.tools}
    assert catalog.connected is True
    assert names == {"echo", "time_now", "list_stages"}


async def test_http_catalog_without_token_is_disconnected() -> None:
    catalog = await HttpMcpCatalog("http://mcp:18765", "").fetch()
    assert catalog.connected is False
    assert catalog.error == "MCP_SHARED_TOKEN unset"
