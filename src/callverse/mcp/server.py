"""The CallVerse MCP server: the Advisor's tools and the company policies, published with MCP.

Think of a restaurant. The *catalog* is the menu: each line is a tool (something to do), a resource
(something to read) or a prompt (a ready-made instruction), with the Python function behind it. The
*server* is the waiter: a client asks for the menu (tools/list, resources/list, prompts/list) and orders
from it (tools/call, resources/read, prompts/get); the waiter passes each order to the kitchen (the
function) and brings the result back.

The tool descriptions are not rewritten here: they are the ones the Advisor already gives its LLM
(SCHEMAS_BY_NAME in agents/advisor/tools.py), so there is one source of truth. Every tool call still
ends in AdvisorTools, which records it (success, time, who chose it) exactly as before, with via="mcp".
"""

# How to read this file:
# - CatalogTool / CatalogResource / CatalogPrompt: one line of the menu and the function behind it.
# - McpCatalog: the menu. McpCatalog.server() builds the low-level MCP server: one handler per protocol
#   method, all reading the menu.
# - advisor_catalog(): the menu every CallVerse server starts from: the 9 tools an LLM may call and the 10
#   policy documents. The Advisor connects to it (client.py); desk.py adds more for outside apps.
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any

import anyio.to_thread
import mcp_types as types
from mcp.server import Server
from mcp.shared.exceptions import MCPError

from callverse import __version__
from callverse.agents.advisor.indexing import DocumentMeta, load_knowledge_base_config, parse_document
from callverse.agents.advisor.tools import LLM_TOOL_NAMES, SCHEMAS_BY_NAME, AdvisorTools
from callverse.config import PROJECT_ROOT, config_path

SERVER_NAME = "callverse"
POLICY_URI = "callverse://policies/{doc_id}"
# JSON-RPC error code for a request with a wrong parameter (unknown resource or prompt, missing argument).
INVALID_PARAMS = -32602
# What every client reads when it connects (the server's "instructions").
ADVISOR_INSTRUCTIONS = (
    "CallVerse customer-service tools on the Olist e-commerce data (Brazil, 2016-2018). The order tools "
    "answer 'as of' the moment the customer wrote: the digital twin replays history, so later events are "
    "not visible yet. Open the order with lookup_order before answering about it, then call "
    "recommend_resolution: the company rules engine decides the action, and you put its approved answer "
    "into words without changing any fact. Never ask for bank account numbers in a chat."
)


def server_version() -> str:
    """The installed CallVerse version (what the server announces to clients)."""
    try:
        return metadata.version("callverse")
    except metadata.PackageNotFoundError:
        return __version__


# ---------------------------------------------------------------- the menu
@dataclass
class CatalogTool:
    """A tool: its name, description and JSON Schema (what the LLM reads), and the function behind it."""

    name: str
    description: str
    input_schema: dict[str, Any]
    run: Callable[[dict[str, Any]], dict[str, Any]]
    group: str = "advisor"  # for the UI: advisor (customer service), case (outside apps) or twin


@dataclass
class CatalogResource:
    """A document a client can read, by its address (URI)."""

    uri: str
    name: str
    title: str
    description: str
    read: Callable[[], str]
    mime_type: str = "text/markdown"


@dataclass
class CatalogPrompt:
    """A ready-made instruction a client can start from, filled with its arguments."""

    name: str
    title: str
    description: str
    arguments: list[tuple[str, str]]  # (name, description); all required
    render: Callable[[dict[str, str]], str]


def tool_result(result: dict[str, Any]) -> types.CallToolResult:
    """A tool's answer in MCP form: the JSON as text (every client reads it) and as structured data."""
    text = json.dumps(result, default=str, ensure_ascii=False)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structured_content=json.loads(text),
        # is_error tells the client (and its LLM) that the tool could not do it, e.g. an unknown order.
        is_error="error" in result,
    )


@dataclass
class McpCatalog:
    """What a CallVerse MCP server publishes."""

    instructions: str = ADVISOR_INSTRUCTIONS
    tools: dict[str, CatalogTool] = field(default_factory=dict)
    resources: dict[str, CatalogResource] = field(default_factory=dict)
    templates: list[types.ResourceTemplate] = field(default_factory=list)
    prompts: dict[str, CatalogPrompt] = field(default_factory=dict)
    # Called for a tool name that is not on the menu (an LLM can invent one): the Advisor records it as a
    # failed call, so the tool-success metric stays honest.
    unknown_tool: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None

    def add_tool(self, tool: CatalogTool) -> None:
        self.tools[tool.name] = tool

    def add_resource(self, resource: CatalogResource) -> None:
        self.resources[resource.uri] = resource

    def add_prompt(self, prompt: CatalogPrompt) -> None:
        self.prompts[prompt.name] = prompt

    # ------------------------------------------------------------ the waiter
    def server(self) -> Server:
        """The low-level MCP server: each handler answers one protocol method by reading this catalog."""

        # tools/list: the menu of tools (name, description, JSON Schema of the arguments).
        async def list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
            return types.ListToolsResult(
                tools=[
                    types.Tool(name=t.name, description=t.description, input_schema=t.input_schema)
                    for t in self.tools.values()
                ]
            )

        # tools/call: run one tool with the client's arguments.
        async def call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
            arguments = dict(params.arguments or {})
            tool = self.tools.get(params.name)
            if tool is None and self.unknown_tool is None:
                return tool_result({"error": f"Unknown tool {params.name}."})

            def run() -> dict[str, Any]:
                if tool is None:
                    assert self.unknown_tool is not None
                    return self.unknown_tool(params.name, arguments)
                return tool.run(arguments)

            try:
                # The tools read SQLite or simulate a week: they run in a worker thread, so the server keeps
                # answering other requests meanwhile.
                result = await anyio.to_thread.run_sync(run)
            except Exception as error:  # a broken tool must not break the connection
                result = {"error": f"{type(error).__name__}: {error}"}
            return tool_result(result)

        # resources/list and resources/templates/list: the documents, and the address pattern to read one.
        async def list_resources(ctx: Any, params: Any) -> types.ListResourcesResult:
            return types.ListResourcesResult(
                resources=[
                    types.Resource(
                        uri=r.uri,
                        name=r.name,
                        title=r.title,
                        description=r.description,
                        mime_type=r.mime_type,
                    )
                    for r in self.resources.values()
                ]
            )

        async def list_templates(ctx: Any, params: Any) -> types.ListResourceTemplatesResult:
            return types.ListResourceTemplatesResult(resource_templates=self.templates)

        # resources/read: one document's text.
        async def read_resource(
            ctx: Any, params: types.ReadResourceRequestParams
        ) -> types.ReadResourceResult:
            uri = str(params.uri)
            resource = self.resources.get(uri)
            if resource is None:
                raise MCPError(INVALID_PARAMS, f"Unknown resource {uri}.")
            text = await anyio.to_thread.run_sync(resource.read)
            return types.ReadResourceResult(
                contents=[types.TextResourceContents(uri=uri, mime_type=resource.mime_type, text=text)]
            )

        # prompts/list and prompts/get: ready-made instructions, filled with the client's arguments.
        async def list_prompts(ctx: Any, params: Any) -> types.ListPromptsResult:
            return types.ListPromptsResult(
                prompts=[
                    types.Prompt(
                        name=p.name,
                        title=p.title,
                        description=p.description,
                        arguments=[
                            types.PromptArgument(name=name, description=text, required=True)
                            for name, text in p.arguments
                        ],
                    )
                    for p in self.prompts.values()
                ]
            )

        async def get_prompt(ctx: Any, params: types.GetPromptRequestParams) -> types.GetPromptResult:
            prompt = self.prompts.get(params.name)
            if prompt is None:
                raise MCPError(INVALID_PARAMS, f"Unknown prompt {params.name}.")
            arguments = {k: str(v) for k, v in (params.arguments or {}).items()}
            missing = [name for name, _ in prompt.arguments if not arguments.get(name)]
            if missing:
                raise MCPError(INVALID_PARAMS, f"Missing argument(s): {', '.join(missing)}.")
            text = prompt.render(arguments)
            return types.GetPromptResult(
                description=prompt.description,
                messages=[
                    types.PromptMessage(role="user", content=types.TextContent(type="text", text=text))
                ],
            )

        return Server(
            SERVER_NAME,
            version=server_version(),
            title="CallVerse",
            description="Customer-service digital twin: order tools, rules engine, policies and the twin.",
            instructions=self.instructions,
            on_list_tools=list_tools,
            on_call_tool=call_tool,
            on_list_resources=list_resources,
            on_list_resource_templates=list_templates,
            on_read_resource=read_resource,
            on_list_prompts=list_prompts,
            on_get_prompt=get_prompt,
        )


# ----------------------------------------------------------- the Advisor's part
@lru_cache(maxsize=1)
def policy_documents() -> tuple[tuple[DocumentMeta, Path], ...]:
    """The knowledge-base documents (data/knowledge_base/docs) with their front matter."""
    docs_dir = load_knowledge_base_config(config_path("agents"), PROJECT_ROOT).docs_dir
    documents = []
    for path in sorted(Path(docs_dir).glob("*.md")):
        meta, _ = parse_document(path.read_text(encoding="utf-8"), str(path))
        documents.append((meta, path))
    return tuple(documents)


def read_policy(path: Path) -> str:
    """A policy document without its front matter (the Markdown the advisor reads)."""
    return parse_document(path.read_text(encoding="utf-8"), str(path))[1].strip()


def add_policy_resources(catalog: McpCatalog) -> None:
    """Publish each policy document as a resource: callverse://policies/<doc_id>."""
    for meta, path in policy_documents():
        catalog.add_resource(
            CatalogResource(
                uri=POLICY_URI.format(doc_id=meta.doc_id),
                name=meta.doc_id,
                title=meta.title,
                description=f"Company {meta.doc_type}: {meta.title}.",
                read=lambda path=path: read_policy(path),
            )
        )
    catalog.templates.append(
        types.ResourceTemplate(
            uri_template=POLICY_URI,
            name="policy",
            title="Company policy",
            description="One policy document of the knowledge base, by its id (e.g. refund_policy).",
            mime_type="text/markdown",
        )
    )


def advisor_catalog(
    tools_for: Callable[[], AdvisorTools], instructions: str = ADVISOR_INSTRUCTIONS
) -> McpCatalog:
    """The 9 tools an LLM may call and the policy documents.

    ``tools_for`` returns the AdvisorTools to use: the chat's own (the Advisor agent) or the open case's
    (desk.py). Each call runs ``AdvisorTools.call(..., via="mcp")``, which records it as usual.
    """
    catalog = McpCatalog(instructions)
    for name in LLM_TOOL_NAMES:
        function = SCHEMAS_BY_NAME[name]["function"]

        def run(arguments: dict[str, Any], name: str = name) -> dict[str, Any]:
            return tools_for().call(name, arguments, via="mcp")

        catalog.add_tool(CatalogTool(name, function["description"], function["parameters"], run))
    catalog.unknown_tool = lambda name, arguments: tools_for().call(name, arguments, via="mcp")
    add_policy_resources(catalog)
    return catalog
