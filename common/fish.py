import logging
import requests
from datetime import datetime

from common.config import FISH_SECRET, FISH_MODEL_ID

from fish_audio_sdk import Session, TTSRequest

logger = logging.getLogger()

class FishClient:

    def __init__(self):
        self.session = Session(FISH_SECRET)
        self.cost_per_million_bytes = 15.00
    
    def calculate_cost(self, text: str):
        bytes_count = len(text.encode('utf-8'))
        cost = (bytes_count / 1_000_000) * self.cost_per_million_bytes
        return bytes_count, cost

    def text_to_mp3(self, text: str):
        logger.info(f"Attempting TTS")
        
        bytes_used, cost = self.calculate_cost(text)
        
        logger.info(f"TTS Request - Text: '{text[:50]}...' | Bytes: {bytes_used:,} | Cost: ${cost:.6f}")
        
        file_path = f'media/{text[:5]}_{datetime.now().timestamp()}.wav'

        with open(file_path, 'wb') as f:
            for chunk in self.session.tts(
                TTSRequest(
                    reference_id = FISH_MODEL_ID,
                    text = text
                )
            ):
                f.write(chunk)

        logger.info(f"Successfully wrote audio to {file_path}")
        
        return file_path
