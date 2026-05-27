import asyncio
import json
import os
from pydantic import BaseModel
from typing import Any, Awaitable, Callable

from websockets.exceptions import ConnectionClosedError

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types.listen_v1results import ListenV1Results
from deepgram.listen.v1.types.listen_v1keep_alive import ListenV1KeepAlive
from fastapi import FastAPI, WebSocket, WebSocketDisconnect


class TranscriptEvent(BaseModel):
    text: str
    is_final: bool
    speech_final: bool
    raw_result: ListenV1Results | None


FinalTranscriptHandler = Callable[[TranscriptEvent], Awaitable[None] | None]


class STTProvider:
    _KEEPALIVE_INTERVAL_SECONDS = 5
    _RECONNECT_MAX_ATTEMPTS = 5
    _RECONNECT_BASE_DELAY_SECONDS = 1.0
    _RECONNECT_MAX_DELAY_SECONDS = 10.0

    def __init__(self, app: FastAPI):
        self.app = app
        self._client: AsyncDeepgramClient | None = None
        self._final_transcript_handlers: list[FinalTranscriptHandler] = []

    def connect_final_transcript_handler(self, handler: FinalTranscriptHandler) -> None:
        self._final_transcript_handlers.append(handler)

    async def transcribe(
        self,
        websocket: WebSocket,
        *,
        model: str = "nova-3",
        language: str = "en",
        encoding: str = "linear16",
        sample_rate: int = 48000,
    ) -> None:
        client = self._get_client()
        reconnect_attempt = 0
        should_stop = False

        while not should_stop:
            try:
                async with client.listen.v1.connect(
                    model=model,
                    language=language,
                    interim_results="true",
                    encoding=encoding,
                    sample_rate=sample_rate,
                    channels=1,
                    endpointing=800,
                    utterance_end_ms=1000,
                ) as deepgram_socket:
                    deepgram_socket.on(EventType.MESSAGE, lambda message: asyncio.create_task(self._handle_transcript(message)))
                    deepgram_socket.on(EventType.ERROR, lambda exc: asyncio.create_task(websocket.send_json({"type": "error", "detail": str(exc)})))

                    listener_task = asyncio.create_task(deepgram_socket.start_listening())
                    keepalive_task = asyncio.create_task(self._run_keepalive(deepgram_socket))
                    reconnect_attempt = 0
                    print("Started Deepgram listening session")
                    try:
                        while True:
                            message = await websocket.receive()
                            # print(f"Received message from client: {message}")

                            if message["type"] == "websocket.disconnect":
                                should_stop = True
                                break

                            audio_bytes = message.get("bytes")
                            if audio_bytes:
                                await deepgram_socket.send_media(audio_bytes)
                                continue

                            text_message = message.get("text")
                            if not text_message:
                                continue

                            command = self._parse_command(text_message)
                            if command == "finalize":
                                await deepgram_socket.send_finalize()
                            elif command == "close":
                                should_stop = True
                                await deepgram_socket.send_close_stream()
                                break
                            else:
                                print(f"Received unrecognized message: {text_message}")

                    except WebSocketDisconnect:
                        should_stop = True
                    finally:
                        keepalive_task.cancel()
                        listener_task.cancel()
                        await asyncio.gather(keepalive_task, listener_task, return_exceptions=True)
                        try:
                            await deepgram_socket.send_close_stream()
                        except Exception:
                            pass

            except ConnectionClosedError as exc:
                if should_stop:
                    break

                reconnect_attempt += 1
                if reconnect_attempt > self._RECONNECT_MAX_ATTEMPTS:
                    print(f"Deepgram reconnect attempts exhausted: {exc}")
                    await websocket.send_json(
                        {
                            "type": "error",
                            "detail": "Deepgram connection lost and retries were exhausted.",
                        }
                    )
                    break

                backoff_seconds = min(
                    self._RECONNECT_BASE_DELAY_SECONDS * (2 ** (reconnect_attempt - 1)),
                    self._RECONNECT_MAX_DELAY_SECONDS,
                )
                print(
                    f"Deepgram connection lost ({exc}). Reconnecting in {backoff_seconds:.1f}s "
                    f"(attempt {reconnect_attempt}/{self._RECONNECT_MAX_ATTEMPTS})"
                )
                await asyncio.sleep(backoff_seconds)
            except Exception as exc:
                # Retry unknown transient socket failures using the same reconnect strategy.
                if should_stop:
                    break

                reconnect_attempt += 1
                if reconnect_attempt > self._RECONNECT_MAX_ATTEMPTS:
                    print(f"Unexpected Deepgram stream failure after retries: {exc}")
                    await websocket.send_json(
                        {
                            "type": "error",
                            "detail": "Deepgram stream failed after retries.",
                        }
                    )
                    break

                backoff_seconds = min(
                    self._RECONNECT_BASE_DELAY_SECONDS * (2 ** (reconnect_attempt - 1)),
                    self._RECONNECT_MAX_DELAY_SECONDS,
                )
                print(
                    f"Unexpected Deepgram stream error ({exc}). Reconnecting in {backoff_seconds:.1f}s "
                    f"(attempt {reconnect_attempt}/{self._RECONNECT_MAX_ATTEMPTS})"
                )
                await asyncio.sleep(backoff_seconds)

    def _get_client(self) -> AsyncDeepgramClient:
        if self._client is None:
            if not os.getenv("DEEPGRAM_API_KEY"):
                raise RuntimeError("DEEPGRAM_API_KEY is required for websocket transcription.")
            self._client = AsyncDeepgramClient()
        return self._client

    
    async def _handle_transcript(self, message: Any) -> None:
        if not isinstance(message, ListenV1Results):
            return

        alternative = message.channel.alternatives[0] if message.channel.alternatives else None
        transcript = alternative.transcript.strip() if alternative else ""
        if not transcript:
            return

        event = TranscriptEvent(
            text=transcript,
            is_final=bool(message.is_final),
            speech_final=bool(message.speech_final),
            raw_result=message,
        )

        if event.is_final:
            await self._emit_final_transcript(event)
        else:
            print(f"Interim transcript: {event.text}", end="\n")


    async def _emit_final_transcript(self, event: TranscriptEvent) -> None:
        for handler in self._final_transcript_handlers:
            result: Any = handler(event)
            if hasattr(result, "__await__"):
                await result

    async def _run_keepalive(self, deepgram_socket: Any) -> None:
        while True:
            try:
                await asyncio.sleep(self._KEEPALIVE_INTERVAL_SECONDS)
                await deepgram_socket.send_keep_alive(message=ListenV1KeepAlive(type="KeepAlive"))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"Failed to send Deepgram keepalive: {exc}")
                return

    @staticmethod
    def _parse_command(message: str) -> str | None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return None

        command = payload.get("type")
        if command in {"finalize", "close"}:
            return command
        return None