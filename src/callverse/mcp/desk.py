"""The CallVerse MCP server for outside apps: Claude Desktop, the MCP Inspector, any MCP client.

It is the Advisor's server (server.py) plus what a person, or another AI, needs at a desk:
- a case: ``open_case`` picks a customer contact, and the order tools then answer "as of" that moment
  (before any case is opened they answer as of the last day of the history);
- the digital twin: list the scenarios, read the contact forecast, simulate a week of the contact centre;
- resources: the policies and the open case;
- prompts: "answer this customer as a CallVerse advisor" and "plan the staffing of a scenario".

Two ways in (transports): stdio (`callverse mcp`: the client starts the server as a program and they talk
through its input and output, which is how Claude Desktop does it) and Streamable HTTP (the /mcp address of
the API while `callverse serve` runs, reachable from this PC only).
"""

# How to read this file:
# - CaseDesk: the open case and the shared resources (keyword search, twin) of an outside client.
# - desk_catalog(): the full menu (advisor tools + case + twin tools, policies + case, two prompts).
# - connection_info(): how Claude Desktop / the MCP Inspector / an HTTP client connect.
# - run_stdio(): `callverse mcp`. HttpEndpoint: the /mcp address of the API.
import json
import os
import sys
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

import anyio
import pandas as pd
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp, StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from callverse.agents.advisor import KeywordRetriever, load_knowledge_base_config
from callverse.agents.advisor.tools import AdvisorTools
from callverse.agents.client.profiles import find_profile
from callverse.config import FORECAST_DIR, PROJECT_ROOT, config_path
from callverse.data.new_customers import contact_date_range
from callverse.mcp.server import (
    ADVISOR_INSTRUCTIONS,
    CatalogPrompt,
    CatalogResource,
    CatalogTool,
    McpCatalog,
    advisor_catalog,
)

CASE_URI = "callverse://case/current"
DESK_INSTRUCTIONS = (
    f"{ADVISOR_INSTRUCTIONS} Start with open_case and a contact id (e.g. SC000014): until a case is open, "
    "the order tools answer as of the last day of the history. list_twin_scenarios, forecast_next_week "
    "and simulate_week run the digital twin of the contact centre (one simulated week takes about a second)."
)
# The KPIs simulate_week returns (the twin computes about 30).
WEEK_KPIS = [
    "offered",
    "service_level",
    "abandon_rate",
    "asa_seconds",
    "mean_wait_seconds",
    "occupancy",
    "agent_hours",
    "overtime_hours",
    "understaffed_hours",
    "total_cost_eur",
    "cost_per_contact_eur",
]


@lru_cache(maxsize=1)
def _own_twin() -> Any:
    """A digital twin for this process (takes about 1.5 s the first time)."""
    from callverse.twin.digital_twin import DigitalTwin

    return DigitalTwin()


class CaseDesk:
    """What an outside client works on: one open case, plus the keyword search and the twin."""

    def __init__(self, retriever: Any = None, twin: Callable[[], Any] | None = None) -> None:
        # retriever: the knowledge-base search (default: TF-IDF, instant and silent). twin: a function that
        # returns the digital twin (the API passes its own, already loaded).
        self._retriever = retriever
        self.twin = twin or _own_twin
        self._tools: AdvisorTools | None = None
        self.case: dict[str, Any] | None = None
        self._lock = threading.Lock()

    def retriever(self) -> Any:
        if self._retriever is None:
            self._retriever = KeywordRetriever.from_config(
                load_knowledge_base_config(config_path("agents"), PROJECT_ROOT)
            )
        return self._retriever

    def tools(self) -> AdvisorTools:
        """The advisor tools of the open case (no case: as of the last day of the history)."""
        with self._lock:
            if self._tools is None:
                last_day = contact_date_range()[1]
                self._tools = AdvisorTools(
                    as_of=last_day + pd.Timedelta(hours=23, minutes=59), retriever=self.retriever()
                )
            return self._tools

    # ---------------------------------------------------------------- tools
    def open_case(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Pick the customer contact to work on: the tools now answer as of that moment."""
        contact_id = str(arguments.get("contact_id", "")).strip().upper()
        try:
            profile = find_profile(contact_id)
        except KeyError:
            return {
                "error": f"No contact {contact_id}. Contact ids look like SC000014 (history) or NC000001 "
                "(a customer created in the portal)."
            }
        tools = AdvisorTools(as_of=profile.contact_timestamp, retriever=self.retriever())
        # What the advisor's screen shows: the message, the order of the logged-in customer and the tone. The
        # true problem type stays hidden (it is the answer key of the Quality agent).
        case = {
            "contact_id": profile.contact_id,
            "contact_time": str(profile.contact_timestamp),
            "customer_message": profile.opening_message,
            "order_id": profile.order_id,
            "customer_tone": profile.tone,
            "repeat_contact": bool(profile.is_repeat_contact),
            "next_step": "The order tools now answer as of this moment: lookup_order, then "
            "recommend_resolution.",
        }
        with self._lock:
            self._tools, self.case = tools, case
        return case

    def list_twin_scenarios(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """The what-if weeks of the twin, the staffing plans and the routers."""
        described = self.twin().describe()
        return {
            "scenarios": {
                name: {"label": s["label"], "description": s["description"], "week_start": s["week_start"]}
                for name, s in described["scenarios"].items()
            },
            "plans": described["plans"],
            "routers": described["routers"],
            "service_level_target": described["service_level_target"],
            "answered_within_seconds": described["threshold_seconds"],
            "opening_hours": described["opening_hours"],
        }

    def forecast_next_week(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """The LightGBM forecast of daily contacts for the week after the history, by problem group."""
        path = FORECAST_DIR / "contact_forecast_next_week.csv"
        if not path.exists():
            return {"error": "No forecast yet: run `callverse forecast` first."}
        frame = pd.read_csv(path)
        by_day = frame.pivot_table(index="date", columns="intent_group", values="contacts", aggfunc="sum")
        by_day["total"] = by_day.sum(axis=1)
        return {
            "unit": "contacts per day (sample scale of the twin)",
            "days": [
                {"date": str(date), **{k: round(float(v), 1) for k, v in row.items()}}
                for date, row in by_day.iterrows()
            ],
        }

    def simulate_week(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Simulate one week of the contact centre with a staffing plan and a router."""
        from callverse.twin.digital_twin import PLAN_KINDS, ROUTERS

        scenario = str(arguments.get("scenario") or "baseline")
        plan = str(arguments.get("plan") or "cpsat")
        router = str(arguments.get("router") or "fifo")
        seeds = int(arguments.get("seeds") or 1)
        if plan not in PLAN_KINDS or router not in ROUTERS or not 1 <= seeds <= 5:
            return {"error": f"plan in {PLAN_KINDS}, router in {ROUTERS}, seeds from 1 to 5."}
        try:
            runs = self.twin().run(scenario, plan, router, seeds, True)
        except (KeyError, FileNotFoundError) as error:  # unknown scenario, or a model not trained yet
            return {"error": str(error).strip("'\"")}
        kpis = pd.DataFrame([run.kpis for run in runs])[WEEK_KPIS].mean()
        return {
            "scenario": scenario,
            "plan": plan,
            "router": router,
            "seeds": seeds,
            "kpis": {name: round(float(value), 3) for name, value in kpis.items()},
            "reading": "service_level = share of live contacts answered in time; abandon_rate = share who "
            "hung up while waiting; costs in euros; hours over the whole week.",
        }


# ---------------------------------------------------------------- the menu
def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


ANSWER_CUSTOMER = """You are a customer advisor at CallVerse, the customer service of a Brazilian online
store.
1. Call open_case with contact_id "{contact_id}" and read the customer's message.
2. Call lookup_order with the case's order_id, then recommend_resolution with that order and the problem
   type that fits the message. The rules engine decides; you do not change its decision.
3. If a policy question remains, call search_knowledge_base or read a resource callverse://policies/<id>.
4. Write the reply to the customer in English: warm, short and faithful to the approved answer (keep every
   date, amount and next step; add nothing). Never ask for bank account numbers in a chat.
5. Below the reply, list the tools you used and what each one told you."""

PLAN_STAFFING = """You are the workforce manager of the CallVerse contact centre.
1. Call list_twin_scenarios and read the scenario "{scenario}".
2. Call simulate_week for that scenario with the plans cpsat, rules_erlang and fixed (router fifo, seeds 2).
3. Compare them in one table: service level, abandon rate, mean wait, agent hours, overtime, total cost.
4. Recommend one plan and explain the trade-off in two sentences, against the service-level target."""


def desk_catalog(desk: CaseDesk | None = None) -> McpCatalog:
    """The full menu for outside apps: 9 advisor tools + open_case + 3 twin tools, the policies and the
    open case, and two prompts."""
    from callverse.twin.digital_twin import PLAN_KINDS, ROUTERS

    desk = desk or CaseDesk()
    catalog = advisor_catalog(desk.tools, DESK_INSTRUCTIONS)
    catalog.add_tool(
        CatalogTool(
            "open_case",
            "Open a customer contact (the case you work on). Returns the customer's message, the order "
            "number and the contact time; the order tools then answer as of that moment.",
            _schema(
                {
                    "contact_id": {
                        "type": "string",
                        "description": "e.g. SC000014 (history) or NC000001 (new)",
                    }
                },
                ["contact_id"],
            ),
            desk.open_case,
            "case",
        )
    )
    catalog.add_tool(
        CatalogTool(
            "list_twin_scenarios",
            "The what-if weeks of the digital twin (baseline, promo spike, delivery delays...), the staffing "
            "plans and the routers it can simulate.",
            _schema({}),
            desk.list_twin_scenarios,
            "twin",
        )
    )
    catalog.add_tool(
        CatalogTool(
            "forecast_next_week",
            "Forecast of customer contacts per day for the week after the history, by problem group.",
            _schema({}),
            desk.forecast_next_week,
            "twin",
        )
    )
    catalog.add_tool(
        CatalogTool(
            "simulate_week",
            "Simulate one week of the contact centre (digital twin) with a staffing plan and a router; "
            "returns the KPIs: service level, abandon rate, waits, agent hours, overtime and costs.",
            _schema(
                {
                    "scenario": {"type": "string", "description": "A scenario of list_twin_scenarios"},
                    "plan": {"type": "string", "enum": PLAN_KINDS},
                    "router": {"type": "string", "enum": ROUTERS},
                    "seeds": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Repetitions"},
                },
                ["scenario"],
            ),
            desk.simulate_week,
            "twin",
        )
    )
    catalog.add_resource(
        CatalogResource(
            CASE_URI,
            "current_case",
            "The open case",
            "The customer contact opened with open_case (JSON).",
            lambda: json.dumps(desk.case or {"case": None, "next_step": "Call open_case first."}, indent=2),
            "application/json",
        )
    )
    catalog.add_prompt(
        CatalogPrompt(
            "answer_customer",
            "Answer a customer as a CallVerse advisor",
            "Open a contact, check the order with the tools and write the policy-correct reply.",
            [("contact_id", "A contact id, e.g. SC000014")],
            lambda arguments: ANSWER_CUSTOMER.format(**arguments),
        )
    )
    catalog.add_prompt(
        CatalogPrompt(
            "plan_staffing",
            "Plan the staffing of a week",
            "Compare staffing plans on a twin scenario and recommend one.",
            [("scenario", "A twin scenario, e.g. promo_spike")],
            lambda arguments: PLAN_STAFFING.format(**arguments),
        )
    )
    return catalog


# ----------------------------------------------------------- the transports
def stdio_command() -> str:
    """The `callverse` program of this Python environment (what Claude Desktop must start)."""
    name = "callverse.exe" if os.name == "nt" else "callverse"
    return str(Path(sys.executable).with_name(name))


def connection_info(http_url: str = "http://127.0.0.1:8000/mcp") -> dict[str, Any]:
    """How an outside app connects: Claude Desktop's config, the MCP Inspector command, the HTTP address."""
    command = stdio_command()
    return {
        "stdio": {"command": command, "args": ["mcp"]},
        "http_url": http_url,
        # Claude Desktop: Settings > Developer > Edit Config, then paste this into claude_desktop_config.json.
        "claude_desktop_config": {"mcpServers": {"callverse": {"command": command, "args": ["mcp"]}}},
        # The MCP Inspector: a web page that connects to any MCP server and lets you try every tool by hand.
        "inspector": f'npx @modelcontextprotocol/inspector "{command}" mcp',
    }


def run_stdio(desk: CaseDesk | None = None) -> None:
    """Serve over stdio until the client closes the connection (`callverse mcp`)."""
    server = desk_catalog(desk).server()

    async def main() -> None:
        # While serving, stray prints go to stderr, so they never mix with the protocol messages.
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(main)


# The /mcp address answers this PC only (DNS-rebinding protection: a web page on another site cannot use it).
LOCAL_ONLY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
    allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
)


class HttpEndpoint:
    """The /mcp address of the API: MCP over Streamable HTTP (JSON-RPC messages in HTTP requests)."""

    def __init__(self, make_server: Callable[[], Server]) -> None:
        # The server is built when the API starts (not when Python imports the API).
        self.make_server = make_server
        self.server: Server | None = None
        self._app: StreamableHTTPASGIApp | None = None

    @asynccontextmanager
    async def running(self) -> AsyncIterator[None]:
        """Run the connection manager while the API runs (a new one at each start)."""
        self.server = self.server or self.make_server()
        manager = StreamableHTTPSessionManager(app=self.server, security_settings=LOCAL_ONLY)
        async with manager.run():
            self._app = StreamableHTTPASGIApp(manager)
            try:
                yield
            finally:
                self._app = None

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if self._app is None:
            response = JSONResponse(
                {"detail": "The MCP endpoint runs with `callverse serve`."}, status_code=503
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)
