import json
import os
import httpx
from enum import Enum
from pydantic import BaseModel


class RouteResult(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"

class RouteResponse(BaseModel):
    response_speech: str | None = None
    result: RouteResult = RouteResult.SUCCESS


class HomeAssistantConversationClient:


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
    @property
    def config(self):
        return {
            "home_assistant": {
                "transport": "streamable_http",
                "url": self.mcp_url,
                "headers": self.headers
            }
        }

    async def route_intent(self, utterance: str, language: str = "en") -> RouteResponse:
        print(f"Routing intent for utterance: {utterance}")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/conversation/process",
                headers=self.headers,
                json={"text": utterance, "language": language},
                timeout=30
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

            
    
        