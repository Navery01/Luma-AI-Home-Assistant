# TODO:
#   1. Fix the client_facts bug and the chat history placement
#   2. Clean up rag_dispatcher.py and the pyproject.toml dependencies

import logging
import uvicorn, asyncio
from pprint import pprint
from fastapi import FastAPI, WebSocket
from homeautoapi.stt_provider import STTProvider
from homeautoapi.agent import Agent
from homeautoapi.ha_mcp_client import HAMCPClient, RouteResult
from homeautoapi.tts_provider import TTSProvider
from homeautoapi.db_helper import add_chat_log, get_client_facts, get_recent_chat_logs
app = FastAPI()

@app.get("/api/")
async def read_root():
    return {"message": "Welcome to the Home Automation API!"}

@app.post("/api/request")
async def handle_request(request: dict):
    """Useful for testing with tools like Postman"""

    agent_response = await _dispatch_agent(request.get("message", ""))

    await add_chat_log(client_id="default_client", message=request.get("message", ""), response=agent_response)

    return {"message": "Request received", "request": request, "result": agent_response}

@app.websocket("/ws/assistant/")
async def websocket_endpoint(websocket: WebSocket):
    STT_PROVIDER = STTProvider(app)
    STT_PROVIDER.connect_final_transcript_handler(lambda event: _on_final_transcript(event, websocket=websocket))

    await websocket.accept()
    await STT_PROVIDER.transcribe(websocket)

# TODO: multi-client
async def _on_final_transcript(event, *, websocket: WebSocket):
    TTS_PROVIDER = TTSProvider(websocket)
    pprint(f"Final transcript: {event.text}")
    agent_response = await _dispatch_agent(event.text)

    await add_chat_log(client_id="default_client", message=event.text, response=agent_response)

    await TTS_PROVIDER.synthesize(agent_response)


# TODO: multi-client
async def _dispatch_agent(user_text: str) -> str:
    """Initialize the agent with Home Assistant tools and run it with the user's message."""
    AGENT = Agent()
    MCP_CLIENT = HAMCPClient()  
    await MCP_CLIENT.initialize()
    ha_tools = await MCP_CLIENT.list_tools()
    route_response = await MCP_CLIENT.route_intent(user_text)
    if route_response.result == RouteResult.SUCCESS:
        print(f"Intent routed successfully with response speech: {route_response.response_speech}")
        return route_response.response_speech or "OK"
    else:
        try:
            client_facts = await get_client_facts("default_client", limit=5)
            chat_history = await get_recent_chat_logs("default_client", limit=2)

            agent_response = await AGENT.run_agent(
                user_message = user_text,
                tools = MCP_CLIENT.to_litellm_tools(ha_tools),
                mcp_client = MCP_CLIENT,
                client_facts = client_facts,
                chat_history = chat_history
            )
            return agent_response
        except Exception as exc:
            print(f"RAG pipeline failed: {exc}")
            return "Failed"


def run():
    logging.info("Starting Home Automation API...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

