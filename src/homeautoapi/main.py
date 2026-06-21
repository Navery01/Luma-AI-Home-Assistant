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

    AGENT = Agent()
    MCP_CLIENT = HAMCPClient()

    AGENT = Agent()
    MCP_CLIENT = HAMCPClient()
    await MCP_CLIENT.initialize()
    ha_tools = await MCP_CLIENT.list_tools()
    for tool in ha_tools:
        desc = tool.get("description", "(no description)")[:80]
        print(f"  - {tool['name']:<40} {desc}")

    await AGENT.run_agent(
        user_message = request.get("query", ""),
        tools = MCP_CLIENT.to_litellm_tools(ha_tools),
        mcp_client = MCP_CLIENT
    )

    # await _on_final_transcript(TranscriptEvent(text=request.get("query", ""), is_final=True, speech_final=True, raw_result=None))
    
    return {"message": "Request received", "request": request, "result": "OK"}

@app.websocket("/ws/assistant/")
@app.websocket("/ws/assistant/")
async def websocket_endpoint(websocket: WebSocket):
    STT_PROVIDER = STTProvider(app)
    STT_PROVIDER.connect_final_transcript_handler(lambda event: _on_final_transcript(event, websocket=websocket))

    STT_PROVIDER = STTProvider(app)
    STT_PROVIDER.connect_final_transcript_handler(lambda event: _on_final_transcript(event, websocket=websocket))

    await websocket.accept()
    await STT_PROVIDER.transcribe(websocket)

async def _on_final_transcript(event, *, websocket: WebSocket):
    TTS_PROVIDER = TTSProvider(websocket)
async def _on_final_transcript(event, *, websocket: WebSocket):
    TTS_PROVIDER = TTSProvider(websocket)
    pprint(f"Final transcript: {event.text}")
    agent_response = await _dispatch_agent(event.text)

    await TTS_PROVIDER.synthesize(agent_response)

    agent_response = await _dispatch_agent(event.text)

    await TTS_PROVIDER.synthesize(agent_response)



async def _dispatch_agent(user_text: str) -> str:
async def _dispatch_agent(user_text: str) -> str:
    """Initialize the agent with Home Assistant tools and run it with the user's message."""
    AGENT = Agent()
    MCP_CLIENT = HAMCPClient()  
    AGENT = Agent()
    MCP_CLIENT = HAMCPClient()  
    await MCP_CLIENT.initialize()
    ha_tools = await MCP_CLIENT.list_tools()
    try:
        agent_response = await AGENT.run_agent(
        agent_response = await AGENT.run_agent(
        user_message = user_text,
        tools = MCP_CLIENT.to_litellm_tools(ha_tools),
        mcp_client = MCP_CLIENT
    )
        
        return agent_response
        
        return agent_response
    except Exception as exc:
        print(f"RAG pipeline failed: {exc}")
        return "Failed"
    return "OK"

def run():
    logging.info("Starting Home Automation API...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

