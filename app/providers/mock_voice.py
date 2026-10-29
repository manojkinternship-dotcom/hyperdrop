import asyncio
import time
import uuid
import logging
from typing import Dict, Any, Optional
import httpx
from app.providers.voice_interface import VoiceProvider

logger = logging.getLogger("hyperdrop.mock_voice")

class MockVoiceProvider(VoiceProvider):
    def __init__(self):
        self.active_calls: Dict[str, Dict[str, Any]] = {}

    async def initiate_call(
        self,
        phone: str,
        role: str,
        language: str,
        context: Dict[str, Any],
        webhook_url: str
    ) -> str:
        call_id = f"mock_{role}_{uuid.uuid4().hex[:8]}"
        self.active_calls[call_id] = {
            "phone": phone,
            "role": role,
            "language": language,
            "context": context,
            "webhook_url": webhook_url,
            "started_at": time.time(),
            "status": "in_progress"
        }
        logger.info(f"[MockVoice] Outbound call started to {role} ({phone}, {language}) -> Call ID: {call_id}")
        return call_id

    async def speak(self, call_id: str, text: str, language: str) -> bool:
        if call_id not in self.active_calls:
            logger.warning(f"[MockVoice] Unknown call_id {call_id}")
            return False
        
        call_info = self.active_calls[call_id]
        logger.info(f"[MockVoice Speak] [{call_info['role'].upper()}] ({language}): {text}")
        # Realistic small delay simulating speech synthesis
        await asyncio.sleep(0.1)
        return True

    async def hangup(self, call_id: str) -> bool:
        if call_id in self.active_calls:
            self.active_calls[call_id]["status"] = "completed"
            logger.info(f"[MockVoice] Call ended: {call_id}")
            return True
        return False
