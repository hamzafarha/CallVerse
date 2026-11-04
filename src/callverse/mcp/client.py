"""The Advisor agent's MCP client: discover the tools, then call them, through the CallVerse MCP server.

At each turn the Advisor opens one connection to the server, asks for the menu (tools/list), gives the
descriptions of the tools allowed at this stage to its LLM (gating stays the agent's decision), and sends
every tool the LLM chooses as a tools/call request. The server runs it and the result comes back as JSON.

The server lives in the same process, so the SDK hands the requests straight to the server's handlers
(no network, about 2 ms per call); outside apps reach the very same handlers over stdio or HTTP
(desk.py).

The MCP library is asynchronous (async/await) while the agents are plain (synchronous) code. The *bridge*
is an event loop running in a background thread: the agent hands it a request and waits for the answer,
like passing a note through a hatch.
"""

# How to read this file:
# - bridge(): the background event loop (one per process).
# - McpToolbox: the Advisor's toolbox over MCP (schemas() and execute(), like DirectToolbox in
#   agents/advisor/tools.py). It connects on first use and disconnects at the end of the turn.
# - read_menu(): everything a server publishes, read through the protocol (the API and `callverse mcp-check`).
import functools
import json
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any

import anyio
from anyio.from_thread import BlockingPortal
from mcp import Client

from callverse.agents.advisor.tools import AdvisorTools
from callverse.mcp.server import SERVER_NAME, advisor_catalog

_portal: BlockingPortal | None = None
_portal_lock = threading.Lock()


def bridge() -> BlockingPortal:
    """The event loop that runs the MCP connections, in a background thread (started on first use)."""
    global _portal
    with _portal_lock:
        if _portal is None:
            ready = threading.Event()
            holder: dict[str, BlockingPortal] = {}

            def loop() -> None:
                async def main() -> None:
                    async with BlockingPortal() as portal:
                        holder["portal"] = portal
                        ready.set()
                        await portal.sleep_until_stopped()

                anyio.run(main)

            # daemon=True: the thread never keeps Python alive when the program ends.
            threading.Thread(target=loop, name="mcp-bridge", daemon=True).start()
            ready.wait()
            _portal = holder["portal"]
        return _portal


def openai_schema(tool: Any) -> dict[str, Any]:
    """An MCP tool description in the "function calling" format the LLM client expects."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema,
        },
    }


class McpToolbox:
    """The Advisor's tools reached through the CallVerse MCP server (the "mcp" transport)."""

    transport = "mcp"

    def __init__(
        self, tools: AdvisorTools, on_event: Callable[[str, dict[str, Any]], None] | None = None
    ) -> None:
        # The server is built around THIS chat's tools: its as_of date, its ticket list, its call log.
        self.tools = tools
        self.on_event = on_event
        self.server = advisor_catalog(lambda: tools).server()
        self.listed: dict[str, dict[str, Any]] = {}
        self.requests = 0
        self._connection: Any = None
        self._client: Client | None = None

    # ------------------------------------------------------------ connection
    def _connected(self) -> Client:
        """Connect (once per turn) and read the menu of tools."""
        if self._client is not None:
            return self._client
        started = time.perf_counter()
        self._connection = bridge().wrap_async_context_manager(Client(self.server))
        self._client = self._connection.__enter__()
        listed = bridge().call(self._client.list_tools)  # tools/list
        self.requests += 1
        self.listed = {tool.name: openai_schema(tool) for tool in listed.tools}
        if self.on_event is not None:
            self.on_event(
                "mcp",
                {
                    "server": SERVER_NAME,
                    "protocol": getattr(self._client.session, "protocol_version", None),
                    "tools": list(self.listed),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
        return self._client

    def close(self) -> None:
        """Disconnect (end of the turn)."""
        if self._connection is not None:
            self._connection.__exit__(None, None, None)
        self._connection, self._client = None, None

    def __enter__(self) -> "McpToolbox":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------- the tools
    def schemas(self, names: Iterable[str]) -> list[dict[str, Any]]:
        """The descriptions of these tools, as the server published them (same order as ``names``)."""
        self._connected()
        return [self.listed[name] for name in names if name in self.listed]

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Send the LLM's choice as a tools/call request; returns the result's JSON text."""
        client = self._connected()
        result = bridge().call(functools.partial(client.call_tool, name, arguments))
        self.requests += 1
        text = "".join(getattr(block, "text", "") for block in result.content)
        return text or json.dumps({"error": f"empty MCP result for {name}"})


# ------------------------------------------------------------------ the menu
async def read_menu(client: Client) -> dict[str, Any]:
    """Everything a connected server publishes: tools, resources, resource templates and prompts."""
    tools = await client.list_tools()
    resources = await client.list_resources()
    templates = await client.list_resource_templates()
    prompts = await client.list_prompts()
    return {
        "protocol": getattr(client.session, "protocol_version", None),
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "arguments": list((t.input_schema or {}).get("properties", {})),
                "required": list((t.input_schema or {}).get("required", [])),
            }
            for t in tools.tools
        ],
        "resources": [
            {"uri": str(r.uri), "name": r.name, "title": r.title, "description": r.description}
            for r in resources.resources
        ],
        "templates": [
            {"uri_template": t.uri_template, "title": t.title} for t in templates.resource_templates
        ],
        "prompts": [
            {
                "name": p.name,
                "title": p.title,
                "description": p.description,
                "arguments": [a.name for a in p.arguments or []],
            }
            for p in prompts.prompts
        ],
    }
