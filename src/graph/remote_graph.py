"""Neo4jGraph target selection for local pipeline scripts.

Neo4j has no external Bolt ingress in Azure (see infra/modules/neo4j.bicep)
-- it's only reachable directly over Bolt from inside the Container Apps
environment, which is how the deployed app itself (src/graph/query.py,
src/graph/major_events.py's get_timeline()) talks to it. Local scripts
(extract.py, dedupe.py, timeline.py, major_events.py's main(),
illustrations/generate.py) instead default to the local Docker Neo4j at
NEO4J_URI, same as always -- but can be pointed at the deployed graph by
setting ADMIN_API_URL, which routes every query through the app's
authenticated POST /admin/cypher proxy over HTTPS instead of a direct Bolt
connection.
"""

from typing import Any

import httpx
from langchain_neo4j import Neo4jGraph

from src.config import ADMIN_API_KEY, ADMIN_API_URL, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME


class RemoteNeo4jGraph(Neo4jGraph):
    """Neo4jGraph that proxies .query() over HTTPS instead of opening a
    direct Bolt connection. Deliberately skips Neo4jGraph.__init__ (which
    opens a real driver) -- add_graph_documents() and every script here only
    ever call .query(), so overriding just that method is enough for both to
    work unchanged against the remote proxy.
    """

    def __init__(self, base_url: str, api_key: str):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._driver = object()  # satisfies Neo4jGraph._check_driver_state(); never dereferenced
        self._database = "neo4j"
        self.timeout = None
        self.sanitize = False
        self._enhanced_schema = False
        self.schema = ""
        self.structured_schema: dict[str, Any] = {}

    def refresh_schema(self) -> None:
        # No live driver to introspect with apoc.meta.data() -- callers here
        # all pass refresh_schema=False already; this only exists because
        # add_graph_documents() calls it unconditionally after creating its
        # base-entity constraint.
        pass

    def query(self, query: str, params: dict | None = None, session_params: dict | None = None) -> list[dict]:
        response = httpx.post(
            f"{self._base_url}/admin/cypher",
            json={"query": query, "params": params or {}},
            headers={"X-Admin-Key": self._api_key},
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["records"]

    def close(self) -> None:
        pass


def get_graph(refresh_schema: bool = False) -> Neo4jGraph:
    """The Neo4jGraph local scripts should use: the deployed graph via the
    admin proxy when ADMIN_API_URL is set, otherwise a direct Bolt
    connection to NEO4J_URI (the local Docker Neo4j by default).
    """
    if ADMIN_API_URL:
        return RemoteNeo4jGraph(base_url=ADMIN_API_URL, api_key=ADMIN_API_KEY)
    return Neo4jGraph(
        url=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD, refresh_schema=refresh_schema
    )
