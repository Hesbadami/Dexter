import tempfile
import os 
import logging
import asyncio

from common.fish import FishClient
from common.config import DISCORD_TOKEN

import discord
from discord.ext import commands
import wavelink

logger = logging.getLogger()

bot = commands.Bot(
    command_prefix = '!',
    intents = discord.Intents.all()
)
fish = FishClient()

@bot.event
async def on_ready():
    logger.info(f"{bot.user} is ready!")

@bot.event
async def on_message(message):
    
    logger.info(f"Received message")

    if message.author == bot.user:
        return
    
    if message.content and message.content.startswith('!dex'):
        await speak_message(message)

# High quality options for TTS
FFMPEG_OPTIONS = {
    'before_options': '-nostdin',
    'options': '-vn -ar 48000 -ac 2 -b:a 320k -af "volume=0.8,highpass=f=200,lowpass=f=8000"'
}

async def speak_message(message):
    audio_file = fish.text_to_mp3(message.content.strip('!dex '))

    if message.author.voice:
        vc = await message.author.voice.channel.connect()
        #audio_source = await discord.FFmpegOpusAudio.from_probe(audio_file, **FFMPEG_OPTIONS)

        source = discord.FFmpegPCMAudio(
            audio_file,
            before_options='-nostdin',
            options='-ar 48000 -ac 2 -b:a 320k'
        )

        vc.play(source)

        while vc.is_playing():
            await asyncio.sleep(1)
        await vc.disconnect()

        #os.remove(audio_file)
