"""CallVerse and the Model Context Protocol (MCP).

MCP is an open standard plug between AI applications and tools, a bit like a USB-C port: a *server*
publishes a menu (tools to call, resources to read, prompts to start from) and any *client* (an AI
agent, Claude Desktop, the MCP Inspector...) connects, reads the menu and orders from it.

- server.py: the CallVerse MCP server. It publishes the Advisor's tools (orders, tickets, refunds, the
  rules engine, the bank code check, the knowledge base...) and the company policies.
- client.py: the Advisor agent's MCP client. At each turn the agent connects, asks the server for its
  tools (tools/list), gives their descriptions to the LLM and runs the LLM's choice (tools/call).
- desk.py: the server for outside apps. It adds a "case" (which customer contact you work on), the
  digital twin and forecast tools, and ready-made prompts. It runs over stdio (`callverse mcp`, for
  Claude Desktop) and over HTTP (http://127.0.0.1:8000/mcp while `callverse serve` runs).

This file imports nothing on purpose: the Advisor (agents layer) imports server.py and client.py, which
must never reach the twin (desk.py does).
"""
