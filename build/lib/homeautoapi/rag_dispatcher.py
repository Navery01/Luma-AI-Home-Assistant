import numpy as np
from openai import OpenAI
import os, json, requests

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "gpt-4o")
API_KEY = os.environ.get("OPENAI_API_KEY")
HOME_ASSISTANT_TOKEN = os.environ.get("HA_TOKEN", "")
HOME_ASSISTANT_BASE_URL = os.environ.get("HA_BASE_URL", "http://homeassistant.local:8123")

# TODO - error handling for API calls
# TODO - more robust schema validation for LLM output
# TODO - fix the piecemeal class structure
# TODO - add a way to provide HA context

HA_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["intent_summary", "actions"],
    "properties": {
        "intent_summary": {
            "type": "string",
            "description": "One-sentence plain-English summary of what will be done."
        },
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["method", "endpoint", "headers", "body"],
                "properties": {
                    "method":   {"type": "string", "enum": ["GET", "POST"]},
                    "endpoint": {"type": "string", "description": "Full path, e.g. /api/services/light/turn_on"},
                    "headers":  {"type": "object"},
                    "body":     {"type": "object", "description": "JSON payload for the request body"}
                }
            }
        },
        "warnings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional warnings or assumptions made."
        }
    }
}

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
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [device_registry[i] for i in top_indices]
    
    @staticmethod
    def _execute(request: dict, base_url: str) -> None:
        """Execute the generated REST calls against the HA instance."""
        for req in request["actions"]:
            url = f"{req['endpoint']}"
            headers = {"Authorization": req["headers"]["Authorization"].replace("Bearer <HA_TOKEN>", f"Bearer {HOME_ASSISTANT_TOKEN}")}
            body: dict = req["body"]
            method = req["method"]

            print(f"Executing {method} {url} with body {body} …")
            
            requests.request(method, f"{base_url}{url}", headers=headers, json=body)
    
    def query_rag(self, user_query: str, device_registry: list[dict], top_k: int = 10, execute: bool = False):
        """Retrieve relevant devices and ask the LLM to generate HA API payloads."""
        relevant_devices = self._retrieve(user_query, device_registry, top_k=top_k)

        context_json = json.dumps(relevant_devices, indent=2)
        user_message = (
            f"Device context (retrieved from registry):\n```json\n{context_json}\n```\n\n"
            f"User instruction: {user_query}"
        )

        response = self.client.chat.completions.create(
            model=CHAT_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
        )
        raw = str(response.choices[0].message.content)
        if execute:
            self._execute(json.loads(raw), HOME_ASSISTANT_BASE_URL)
        return json.loads(raw)
    

if __name__ == "__main__":
    dispatcher = RAGDispatcher()
    device_registry = [
        {"Device": "WLED-LEDROPE-BACKWALL", "EntityID": "light.wled_led_rope_backwall", "State": "on", "Effects": ["ColorWaves", "Static"]},
        {"Device": "WLED-LEDROPE-KITCHEN", "EntityID": "light.wled_ledrope_kitchen", "State": "on", "Effects": ["ColorWaves", "Static"]},
        {"Device": "WLED-LEDROPE-BEDDOOR", "EntityID": "light.wled_ledrope_beddoor", "State": "on", "Effects": ["ColorWaves", "Static"]},
        {"Device": "SCENE-DYNAMIC-OUTWORLD", "EntityID": "scene.dynamic_outworld", "State": "n/a", "Effects": ["n/a"]},
    ]
    result = dispatcher.query_rag("Activate the outworld scene", device_registry=device_registry, execute=False)
    print(json.dumps(result, indent=2))