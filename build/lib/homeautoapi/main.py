import fastapi, uvicorn, asyncio, logging, openapi
import numpy as np

from .rag_dispatcher import RAGDispatcher

app = fastapi.FastAPI()

RAG_DISPATCHER = RAGDispatcher()


@app.get("/api/")
async def read_root():
    return {"message": "Welcome to the Home Automation API!"}

@app.post("/api/request")
async def handle_request(request: dict):

    result = RAG_DISPATCHER.query_rag(request.get("query", ""), device_registry=request.get("device_registry", []), execute=request.get("execute", False))
    return {"message": "Request received", "request": request, "result": result}

def run():
    logging.info("Starting Home Automation API...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
