"""Deterministic services behind the MCP gateway.

Rule: nothing in here imports from agents, api, jobs or llm. They must be able to
live as independent services. Allowed: config, schemas, storage.
"""
