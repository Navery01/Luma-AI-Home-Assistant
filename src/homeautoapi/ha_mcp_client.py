import json
import os
from click.testing import Result
import httpx
from enum import Enum
from pydantic import BaseModel


class RouteResult(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"

class RouteResponse(BaseModel):
    response_speech: str | None = None
    result: RouteResult = RouteResult.SUCCESS


class HAMCPClient:
    def __init__(self, 
                 base_url:str=os.getenv("HA_BASE_URL", "http://homeassistant.local:8123"), 
                 token: str=os.getenv("HA_TOKEN", "")):
        self.base_url = base_url
        self.mcp_url = f"{base_url}/api/mcp"
        self.session_id = None
        self._rpc_id = 0
        self.token = token
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json, text/event-stream",
        }

    async def route_intent(self, utterance: str, language: str = "en") -> RouteResponse:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/conversation/process",
                headers=self.headers,
                json={"text": utterance, "language": language},
            )

            response.raise_for_status()
            data = response.json()
            if data.get("response", {}).get("response_type") == "action_done":
                return RouteResponse(
                    result=RouteResult.SUCCESS,
                    response_speech=data["response"].get("speech", {}).get("plain", {}).get("speech", "")
                )
            else:
                return RouteResponse(result=RouteResult.FAILURE, response_speech=data.get("response", {}).get("speech", {}).get("plain", {}).get("speech", ""))

            
    
    def _next_rpc_id(self):
        """Generate the next RPC ID for JSON-RPC calls."""
        self._rpc_id += 1
        return self._rpc_id
    
    async def _post(self, payload: dict, timeout: int = 10) -> dict | None:
        """Send a POST request to the MCP endpoint with the given payload and handle the response."""
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self.mcp_url,
                headers=self.headers,
                json=payload,
            )

        if "mcp-session-id" in response.headers:
            self.session_id = response.headers["mcp-session-id"]
            self.headers["mcp-session-id"] = self.session_id

        response.raise_for_status()

        text = response.text.strip()
        if not text:
            return None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data: "):
                data_str = line[len("data: "):]
                try:
                    return json.loads(data_str)
                except json.JSONDecodeError:
                    print(f"Failed to decode JSON: {data_str}")
                    return None
        return json.loads(text)
    
    async def _notify(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        payload: dict[str, object] = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(self.mcp_url, headers=self.headers, json=payload)
        response.raise_for_status()


    async def initialize(self) -> dict | None:
        """
        Required first call negotiates protocol version and capabilities.
        Also sends the mandatory notifications/initialized follow-up.
        """
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_rpc_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "HA Agent", "version": "1.0"},
            },
        }
        result = await self._post(payload)

        await self._notify("notifications/initialized")

        return result
    
    async def list_tools(self) -> list[dict]: 
        """List available tools exposed by Home Assistant MCP."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_rpc_id(),
            "method": "tools/list",
            "params":{}
        }
        result = await self._post(payload)
        return (result or {}).get("result", {}).get("tools", [])
    
    async def call_tool(self, name:str, args:dict) -> dict | None:
        """Call a specific tool by name with the provided arguments."""

        print(f"Calling tool {name} with args: {args}")
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_rpc_id(),
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": args or {}
            }
        }
        result = await self._post(payload)
        print(f"Tool call result: {result}")
        return (result or {}).get("result", result)
    
    @staticmethod
    def to_litellm_tools(tools:list[dict]) -> list[dict]:
        """Convert Home Assistant tools to litellm tool format."""
        return [{"type": "function",
                 "function": {
                     "name": tool["name"],
                     "description": tool.get("description", ""),
                     "parameters": tool.get("inputSchema", {"type": "object", "properties": {}})
                 }
        } for tool in tools]
        