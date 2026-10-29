from app.config import settings
from app.providers.voice_interface import VoiceProvider
from app.providers.mock_voice import MockVoiceProvider
from app.providers.bolna_voice import BolnaVoiceProvider

def get_voice_provider() -> VoiceProvider:
    if settings.VOICE_PROVIDER.lower() == "bolna" and settings.BOLNA_API_KEY:
        return BolnaVoiceProvider()
    return MockVoiceProvider()

voice_provider = get_voice_provider()
