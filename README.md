# Luma Home Assistant Agent

A real-time voice-controlled home automation backend. Speak a natural-language command, and the system transcribes it, reasons over your device registry, executes the right actions in Home Assistant, and speaks a confirmation back — all over a single persistent WebSocket connection.

---

## Architecture

![Luma Home Assistant Agent architecture diagram](https://github.com/Navery01/Luma-AI-Home-Assistant/blob/main/voice_assistant_architecture_v5.svg)

---

## Components

### `STTProvider` — Speech-to-Text
Manages a streaming connection to **Deepgram** (nova-3) over a WebSocket. Receives raw PCM audio chunks from the client, forwards them to Deepgram, and fires a `speech_final` event when a complete utterance is detected. Implements automatic reconnection with exponential backoff and a keepalive loop to maintain the Deepgram session.

### `Agent` — Agentic Loop
The core reasoning engine. Runs a multi-stage loop (up to 2 iterations) to reliably translate a user utterance into executed Home Assistant actions:

1. **Intent Classification** — Determines whether the utterance is an actionable device command or a conversational query.
2. **RAG Device Retrieval** — Embeds the query with `text-embedding-3-small` and runs cosine similarity against the live HA device registry to retrieve the top-k most relevant devices, keeping the LLM context small.
3. **LLM Action Planning** — Calls `gpt-4o-mini` (or escalates to `gpt-4o` for complex / ambiguous commands) with the device subset and produces a validated `AgentResponseSchema`: a typed list of tool calls and a natural-language `chat_response`.
4. **HA Action Execution** — Dispatches `set_light_state` and `activate_scene` calls concurrently against the Home Assistant REST API.
5. **Status Verification** — Reads back entity state from HA to confirm the action succeeded.
6. **Retry / Clarification** — If `is_complete` is false or a call failed, loops back to re-plan. Escalates model and surfaces a clarification response after 2 failed iterations.

### `RAGDispatcher` — Embedding Retrieval
Computes OpenAI embeddings for the user query and the serialised device registry entries, then ranks devices by cosine similarity. Keeps the LLM prompt focused on the ≤15 most relevant devices rather than the full registry.

### `TTSProvider` — Text-to-Speech
Connects to **Cartesia** (sonic-3) over its WebSocket API, pushes the agent's `chat_response`, and streams returned audio chunks directly back to the client WebSocket as binary frames. Defaults to `wav / pcm_f32le / 44.1kHz`.

### `HAMCPClient` — HA Client
Wraps the Home Assistant REST and WebSocket APIs. Provides:
- `get_light_devices()` / `get_scenes()` — live entity state reads
- `set_light_state()` — controls brightness, color, effects, speed, intensity, and reverse via both the light service and auxiliary `number.*` / `switch.*` entities
- `activate_scene()` — triggers HA scenes
- `refresh_device_registry()` — syncs the full device/entity/effect catalogue into PostgreSQL for caching

---

## WebSocket Protocol

All communication happens on a **single persistent connection** at `/ws/assistant`.

### Client → Server

| Frame type | Content | Description |
|---|---|---|
| Binary | Raw PCM bytes | Audio from the microphone (linear16, 48kHz, mono) |
| Text (JSON) | `{"type": "finalize"}` | Force-flush the current Deepgram utterance |
| Text (JSON) | `{"type": "close"}` | Gracefully close the session |

### Server → Client

| Frame type | Content | Description |
|---|---|---|
| Text (JSON) | `{"type": "transcript", "text": "...", "is_final": true}` | Interim and final STT transcripts |
| Text (JSON) | `{"type": "assistant_message", "text": "..."}` | The agent's text response |
| Binary | PCM audio bytes | TTS audio chunks streamed back in real time |
| Text (JSON) | `{"type": "tts_done"}` | Signals the end of a TTS response |
| Text (JSON) | `{"type": "error", "detail": "..."}` | Error from any pipeline stage |

---

## Setup

### Prerequisites

- Python 3.11+
- A running [Home Assistant](https://www.home-assistant.io/) instance
- PostgreSQL (for device registry caching)

### API Keys Required

| Key | Provider | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | [OpenAI](https://platform.openai.com/) | LLM planning + embeddings |
| `DEEPGRAM_API_KEY` | [Deepgram](https://deepgram.com/) | Speech-to-text |
| `CARTESIA_API_KEY` | [Cartesia](https://cartesia.ai/) | Text-to-speech |
| `HA_TOKEN` | Home Assistant | Long-lived access token |

### Installation

```bash
# Clone the repo
git clone https://github.com/Navery01/HomeAssistantAgent.git
cd HomeAssistantAgent/HomeAutoAPI

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux

# Install the package
pip install -e .
```

### Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```env
# Home Assistant
HA_BASE_URL=http://homeassistant.local:8123
HA_TOKEN=your_ha_long_lived_token

# OpenAI
OPENAI_API_KEY=sk-...
CHAT_MODEL=gpt-4o-mini          # default; escalates to gpt-4o automatically
EMBEDDING_MODEL=text-embedding-3-small

# Deepgram
DEEPGRAM_API_KEY=...

# Cartesia
CARTESIA_API_KEY=...

# Database
POSTGRES_URL=postgresql+asyncpg://postgres:password@localhost:5432/homeautoapi
```

### Seed the Device Registry

On first run (or after adding new devices to HA), populate the PostgreSQL cache:

```bash
python -m homeautoapi.home_assistant_provider
```

### Run the Server

```bash
python -m homeautoapi
```

The API starts on `http://0.0.0.0:8000`. Connect a client to `ws://localhost:8000/ws/assistant` and start speaking.

---

## REST Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/` | Health check |
| `POST` | `/api/request` | Text-only shortcut — bypasses STT, runs the agent directly |
| `WS` | `/ws/assistant` | Full voice session (STT → Agent → TTS) |

### `POST /api/request`

Useful for testing the agent pipeline without audio:

```bash
curl -X POST http://localhost:8000/api/request \
  -H "Content-Type: application/json" \
  -d '{"query": "turn the kitchen lights blue"}'
```

---

## Project Structure

```
src/homeautoapi/
├── main.py                     # FastAPI app, WebSocket session management
├── agent_dispatcher.py         # Multi-stage agentic loop (LLM + HA execution)
├── rag_dispatcher.py           # Embedding-based device retrieval
├── stt_provider.py             # Deepgram streaming STT
├── tts_provider.py             # Cartesia streaming TTS
├── home_assistant_provider.py  # HA REST client + PostgreSQL device cache
├── models/
│   └── models.py               # Pydantic schemas (actions, responses, HA entities)
└── prompts/
    └── intent_classification.txt
```

---

## Roadmap

See [`todo.txt`](todo.txt) for the full prioritised backlog. Key upcoming items:

- [ ] Cache device embeddings in PostgreSQL — eliminates a re-embedding API call on every request
- [ ] Conversation history — pass the last N turns into the LLM for context-aware follow-ups
- [ ] LLM provider abstraction (LiteLLM) — swap between OpenAI, Anthropic Claude, and local models
- [ ] Streaming LLM response — pipe `chat_response` tokens back to the client before TTS starts
- [ ] Evaluation notebook — score correctness across 20+ voice commands
- [ ] Test suite — fixture-based tests that mock the HA API and assert correct tool calls

---

## License

MIT — see `pyproject.toml`.
