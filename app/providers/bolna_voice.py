import logging
from typing import Dict, Any, Optional
import httpx
from app.config import settings
from app.providers.voice_interface import VoiceProvider

logger = logging.getLogger("hyperdrop.bolna_voice")

class BolnaVoiceProvider(VoiceProvider):
    def __init__(self):
        self.api_key = settings.BOLNA_API_KEY
        self.base_url = settings.BOLNA_BASE_URL.rstrip("/")
        self.agent_id = settings.BOLNA_AGENT_ID

    async def initiate_call(
        self,
        phone: str,
        role: str,
        language: str,
        context: Dict[str, Any],
        webhook_url: str
    ) -> str:
        if not self.api_key:
            raise ValueError("BOLNA_API_KEY is not configured in .env. Please set it or use VOICE_PROVIDER=mock.")

        # Ensure Indian country code format if missing
        formatted_phone = phone if phone.startswith("+") else f"+91{phone.lstrip('0')}"
        
        url = f"{self.base_url}/agent/{self.agent_id}" if self.agent_id else f"{self.base_url}/call"
        payload = {
            "recipient_phone_number": formatted_phone,
            "agent_id": self.agent_id,
            "user_data": {
                "role": role,
                "language": language,
                "context": context,
                "webhook_url": webhook_url
            }
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                call_id = data.get("call_id") or data.get("id") or f"bolna_{role}_{formatted_phone}"
                logger.info(f"[BolnaVoice] Call dispatched: {call_id}")
                return call_id
            except Exception as e:
                logger.error(f"[BolnaVoice] Failed to initiate call to {phone}: {e}")
                raise

    async def speak(self, call_id: str, text: str, language: str) -> bool:
        # In Bolna, real-time prompts during an active call can be triggered via agent message/injection API
        url = f"{self.base_url}/call/{call_id}/message"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {"message": text, "language": language}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                return res.status_code == 200
        except Exception as e:
            logger.warning(f"[BolnaVoice] speak API failed: {e}")
            return False

    async def hangup(self, call_id: str) -> bool:
        url = f"{self.base_url}/call/{call_id}/stop"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, headers=headers)
                return res.status_code == 200
        except Exception as e:
            logger.warning(f"[BolnaVoice] hangup API failed: {e}")
            return False
