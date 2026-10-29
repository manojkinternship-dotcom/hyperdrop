from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class VoiceProvider(ABC):
    @abstractmethod
    async def initiate_call(
        self,
        phone: str,
        role: str,
        language: str,
        context: Dict[str, Any],
        webhook_url: str
    ) -> str:
        """Initiate an outbound call leg and return call_id."""
        pass

    @abstractmethod
    async def speak(self, call_id: str, text: str, language: str) -> bool:
        """Speak a prompt or message on an active call leg."""
        pass

    @abstractmethod
    async def hangup(self, call_id: str) -> bool:
        """End an active call leg."""
        pass
