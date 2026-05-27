import logging, os
import uvicorn, asyncio
from pprint import pprint
from fastapi import FastAPI, WebSocket
from homeautoapi.rag_dispatcher import RAGDispatcher
from homeautoapi.stt_provider import STTProvider, TranscriptEvent
from homeautoapi.home_assistant_provider import HomeAssistantProvider
from homeautoapi.agent_dispatcher import AgentDispatcher
from homeautoapi.tts_provider import TTSProvider
app = FastAPI()

@app.get("/api/")
async def read_root():
    return {"message": "Welcome to the Home Automation API!"}

@app.post("/api/request")
async def handle_request(request: dict):

    await _on_final_transcript(TranscriptEvent(text=request.get("query", ""), is_final=True, speech_final=True, raw_result=None))
    
    return {"message": "Request received", "request": request, "result": "OK"}

@app.websocket("/ws/stt")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await STT_PROVIDER.transcribe(websocket)

async def _on_final_transcript(event):
    pprint(f"Final transcript: {event.text}")
    asyncio.create_task(_dispatch_agent(event.text))


async def _dispatch_agent(user_text: str) -> None:
    try:
        await AgentDispatcher().dispatch(user_text)
    except Exception as exc:
        print(f"RAG pipeline failed: {exc}")



RAG_DISPATCHER = RAGDispatcher()
STT_PROVIDER = STTProvider(app)
TTS_PROVIDER = TTSProvider()
HOMEASSISTANT_PROVIDER = HomeAssistantProvider(os.environ.get("HA_BASE_URL", "http://192.168.0.50:8123"), os.environ.get("HA_TOKEN", ""))
STT_PROVIDER.connect_final_transcript_handler(_on_final_transcript)


def run():
    logging.info("Starting Home Automation API...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

