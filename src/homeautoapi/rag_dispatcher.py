import asyncio
import numpy as np
from openai import OpenAI
import os, json
from .models import models
from .home_assistant_provider import *

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "gpt-4o mini")
API_KEY = os.environ.get("OPENAI_API_KEY")


# TODO - error handling for API calls
# TODO - more robust schema validation for LLM output
# TODO - fix the piecemeal class structure
# TODO - add a way to provide HA context


SYSTEM_PROMPT = """
You are a Home Assistant automation assistant.
You will be given a subset of devices from a Home Assistant device registry (JSON) and a user instruction.
Your job is to produce a structured JSON response that lists the exact REST API calls needed to carry out
the instruction.

Rules:
- Use only the devices provided in the context. Do not invent entity_ids.
- Use only listed effects in the device attributes.effects_list (if present). 
- If the user requests an effect not in the list, choose the closest one and manually set colors to match the requested effect.    
- The Authorization header value is the placeholder string "Bearer <HA_TOKEN>" — do not fill in a real token.
- HA service endpoints follow the pattern: POST /api/services/{domain}/{service}
  e.g.  light.turn_on  → POST /api/services/light/turn_on
- The body must always include "entity_id" and any service-specific fields.
- Return ONLY the JSON object matching the schema — no extra prose.
- The top-level JSON tag for the list of API calls must be "actions", and each call must include "method", "endpoint", "headers", and "body" fields.
- populate the "chat_response" field in the output JSON with a natural-language response to the user that confirms the action taken, use non-confirming language e.g. "Ok on it".
- The chat response should be in written as Wheatly from Portal 2 would say it. Specifically, it should be very casual and conversational, and include some light humor.
- The prefix for each device is used to inform which tool to use, for example if the device has "light" in its EntityID, you should use the set_light_state tool with the appropriate parameters to control it. If the device has "scene" in its EntityID, you should use the activate_scene tool to activate it.
""".strip()

class RAGDispatcher:
    def __init__(self):
        self.client = OpenAI(api_key=API_KEY)
        self.corpus_embeddings = np.array([])  # Initialize with your corpus embeddings

    
    def _embed_texts(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts using the OpenAI API.
        
        Args:
            texts: List of strings to embed.
        
        Returns:
            A 2D numpy array of shape (len(texts), embedding_dim) containing the embeddings.
        
        """
        response = self.client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
        return np.array([item.embedding for item in response.data], dtype=np.float32)
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Row-wise cosine similarity between a query vector and a corpus matrix."""
        a_norm = a / (np.linalg.norm(a) + 1e-10)
        b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-10)
        return b_norm @ a_norm


    def _retrieve(self, query: str, device_registry: list[dict], top_k: int = 10) -> list[dict]:
        """Return the top_k most relevant devices for a natural-language query."""
        q_emb = self._embed_texts([query])[0]
        scores = self._cosine_similarity(q_emb, self._embed_texts([json.dumps(device) for device in device_registry]))
        print(f"Similarity scores: {scores}")
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [device_registry[i] for i in top_indices]
    

    def get_relevant_devices(self, query: str, device_registry: list[dict], top_k: int = 10) -> list[dict]:
        """Public method to get relevant devices, can be used for debugging or other purposes."""
        return self._retrieve(query, device_registry, top_k=top_k)
    
    # async def query_rag(self, user_query: str, device_registry: list[dict], top_k: int = 10, execute: bool = False):
    #     parsed = await asyncio.to_thread(
    #         self._query_rag_sync,
    #         user_query,
    #         device_registry,
    #         top_k,
    #     )
    #     if execute:
    #         await HomeAssistantProvider.execute(parsed, HOME_ASSISTANT_BASE_URL)
    #     return parsed.model_dump(exclude_none=True)

    # def _query_rag_sync(self, user_query: str, device_registry: list[dict], top_k: int = 10):
    #     """Retrieve relevant devices and ask the LLM to generate HA API payloads."""
    #     # The full device registry is not large enough to require embedding-based retrieval, but this is where it would happen for larger corpora.
    #     relevant_devices = self._retrieve(user_query, device_registry, top_k=top_k)
    #     context_json = json.dumps(relevant_devices, indent=2)


    #     user_message = (
    #         f"User instruction: {user_query}"
    #         f"\n\nDevice registry (only use these devices to fulfill the instruction):\n{context_json}"
    #     )

    #     response = self.client.chat.completions.parse(
    #         model=CHAT_MODEL,
    #         response_format=models.RagResponseSchema,
    #         messages=[
    #             {"role": "system", "content": SYSTEM_PROMPT},
    #             {"role": "user",   "content": user_message},
    #         ],
    #     )
    #     parsed = response.choices[0].message.parsed
    #     if parsed is None:
    #         raise ValueError("Model returned no parsed response content.")
    #     return parsed
    

# if __name__ == "__main__":
#     dispatcher = RAGDispatcher()
#     device_registry = [
#         {"Device": "WLED-LEDROPE-BACKWALL", "EntityID": "light.wled_ledrope_backwall", "State": "on", "Effects": ["ColorWaves", "Static"]},
#         {"Device": "WLED-LEDROPE-KITCHEN", "EntityID": "light.wled_ledrope_kitchen", "State": "on", "Effects": ["ColorWaves", "Static"]},
#         {"Device": "WLED-LEDROPE-BEDDOOR", "EntityID": "light.wled_ledrope_beddoor", "State": "on", "Effects": ["ColorWaves", "Static"]},
#         {"Device": "WLED-OBELISK-TV_RIGHT", "EntityID": "light.wled_obelisk_tv_right", "State": "on", "Effects": ["ColorWaves", "Static"]},
#         {"Device": "WLED-OBELISK-TV_LEFT", "EntityID": "light.wled_obelisk_tv_left", "State": "on", "Effects": ["ColorWaves", "Static"]},     
#         {"Device": "SCENE-DYNAMIC-OUTWORLD", "EntityID": "scene.dynamic_outworld", "State": "n/a", "Effects": ["n/a"]},
#     ]
#     result = asyncio.run(dispatcher.query_rag("", device_registry=device_registry, execute=True))
#     print(json.dumps(result, indent=2))