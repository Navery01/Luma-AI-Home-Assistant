# TODO:
#   1. Fix the client_facts bug and the chat history placement
#   2. Clean up rag_dispatcher.py and the pyproject.toml dependencies

import logging
import uvicorn, asyncio
from fastapi import FastAPI, WebSocket
from homeautoapi.agent import Agent
from homeautoapi.database_provider import add_chat_log
app = FastAPI()

@app.get("/api/v1")
async def read_root():
    return {"message": "Welcome to the Home Automation API!"}

@app.post("/api/v1/chat")
async def handle_request(request: dict):
    """Useful for testing with tools like Postman"""

    agent_response = await _dispatch_agent(request.get("message", ""))

    # await add_chat_log(client_id="default_client", message=request.get("message", ""), response=agent_response)

    return {"message": "Request received", "request": request, "result": agent_response}


# TODO: multi-client
async def _dispatch_agent(user_text: str):
    """Initialize the agent with Home Assistant tools and run it with the user's message."""
    AGENT = Agent()
    return await AGENT.run_agent(user_message=user_text)


def run():
    logging.info("Starting Home Automation API...")
    uvicorn.run(app, host="0.0.0.0", port=8080)

