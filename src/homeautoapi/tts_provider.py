# TODO
"""
Implement a Text-to-Speech (TTS) provider that connects to a TTS websocket client
and transmits text to be spoken as audio bytes. This will be used to provide voice responses
which will be transmitted back to the client and will be transmitted through a websocket connection. 
The provider should have a subscribable signal for when the audio bytes are ready to be sent to the client. 
"""

from cartesia import Cartesia
from fastapi import WebSocketDisconnect
import os, asyncio

class TTSOutputFormat:
    def __init__(self, container: str = "wav", encoding: str = "pcm_f32le", sample_rate: int = 44100):
        self.container = container
        self.encoding = encoding
        self.sample_rate = sample_rate

    def to_dict(self):        
        return {
            "container": self.container,
            "encoding": self.encoding,
            "sample_rate": self.sample_rate
        }
class TTSVoice:
    def __init__(self, mode: str = "id", id: str = "default"):
        self.mode = mode
        self.id = id

    def to_dict(self):
        return {
            "mode": self.mode,
            "id": self.id
        }


class TTSProvider:
    def __init__(self, api_key: str = os.getenv("CARTESIA_API_KEY", "")):
        self._client = Cartesia(api_key=api_key)
        self._RECONNECT_MAX_ATTEMPTS = 5

    async def synthesize(self, 
                         websocket, 
                         message: str,
                         *,
                         model_id: str = "sonic-3",
                         output_format: TTSOutputFormat = TTSOutputFormat(),
                         voice: TTSVoice = TTSVoice()) -> None:
        """Connect to the TTS websocket client and transmit text to be spoken as audio bytes."""
        with self._client.tts.websocket_connect() as ws:
            ctx = ws.context(
            model_id=model_id,
            voice=voice.to_dict(), # type: ignore
            output_format=output_format.to_dict()
        )
            
            ctx.push(message)

            ctx.no_more_inputs()

            for response in ctx.receive():
                if response.type == "chunk" and response.audio:
                    asyncio.create_task(websocket.send_bytes(response.audio))
        while True:
            try:
                message = await websocket.receive()

                # response = await self._client.tts.generate(
                #     model_id=model_id,
                #     transcript=message,
                #     voice=voice.to_dict(),
                #     output_format=output_format.to_dict()
                # )

            except WebSocketDisconnect:
                break