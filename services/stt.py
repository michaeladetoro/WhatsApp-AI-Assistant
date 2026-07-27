import io
import logging

from openai import AsyncOpenAI

from brain.config import OPENAI_API_KEY

logger = logging.getLogger("WhatsApp_Bot.STT")


class SpeechToText:
    """Transcribe audio using OpenAI's Whisper API."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    async def transcribe(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
        """
        Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw audio file bytes.
            filename: Filename hint for the API (affects format detection).

        Returns:
            Transcribed text string, or empty string on failure.
        """
        try:
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = filename

            transcript = await self._client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
            text = transcript.text.strip()
            logger.info(f"STT transcribed: '{text[:60]}...'")
            return text
        except Exception as e:
            logger.error(f"STT transcription failed: {e}")
            return ""
