import logging
import uvicorn, asyncio
from pprint import pprint
from fastapi import FastAPI, WebSocket
from homeautoapi.stt_provider import STTProvider
from homeautoapi.agent import Agent
from homeautoapi.ha_mcp_client import HAMCPClient, RouteResult
from homeautoapi.tts_provider import TTSProvider
app = FastAPI()

@app.get("/api/")
async def read_root():
    return {"message": "Welcome to the Home Automation API!"}

@app.post("/api/request")
async def handle_request(request: dict):
    """Useful for testing with tools like Postman"""
    asyncio.create_task(_dispatch_agent(request.get("query", "")))
    
    return {"message": "Request received", "request": request, "result": "OK"}

@app.websocket("/ws/assistant")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await STT_PROVIDER.transcribe(websocket)

async def _on_final_transcript(event):
    pprint(f"Final transcript: {event.text}")
    asyncio.create_task(_dispatch_agent(event.text))


async def _dispatch_agent(user_text: str) -> None:
    """Initialize the agent with Home Assistant tools and run it with the user's message."""
    await MCP_CLIENT.initialize()
    ha_tools = await MCP_CLIENT.list_tools()

    route_response = await MCP_CLIENT.route_intent(user_text)
    if route_response.result == RouteResult.SUCCESS:
        print(f"Intent routed successfully with response speech: {route_response.response_speech}")
        return
    else:
        try:
            await AGENT.run_agent(
                user_message = user_text,
                tools = MCP_CLIENT.to_litellm_tools(ha_tools),
                mcp_client = MCP_CLIENT
            )
        except Exception as exc:
            print(f"RAG pipeline failed: {exc}")

MCP_CLIENT = HAMCPClient()
AGENT = Agent()

STT_PROVIDER = STTProvider(app)
TTS_PROVIDER = TTSProvider()

STT_PROVIDER.connect_final_transcript_handler(_on_final_transcript)




def run():
    logging.info("Starting Home Automation API...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

