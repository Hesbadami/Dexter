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


class TTSBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='!',
            intents=discord.Intents.all()
        )
        self.fish = FishClient()
        
    async def setup_hook(self):
        """Initialize Wavelink connection when bot starts"""
        try:
            # Connect to local Lavalink server
            node = wavelink.Node(
                uri='http://localhost:2333', 
                password=os.environ.get("WAVEPASS")
            )
            await wavelink.Pool.connect(node=node)
            logger.info("Connected to Lavalink server!")
        except Exception as e:
            logger.error(f"Failed to connect to Lavalink: {e}")
            logger.error("Make sure Lavalink server is running on localhost:2333")


bot = TTSBot()

@bot.event
async def on_ready():
    logger.info(f"{bot.user} is ready!")

@bot.event
async def on_message(message):
    
    logger.info(f"Received message")

    if message.author == bot.user:
        return
    
    if message.content and message.content.startswith('!dex'):
        await speak_message_hq(message)

    # Process other commands
    await bot.process_commands(message)
    
# High quality options for TTS
FFMPEG_OPTIONS = {
    'before_options': '-nostdin',
    'options': '-vn -ar 48000 -ac 2 -b:a 320k -af "volume=0.8,highpass=f=200,lowpass=f=8000"'
}

async def speak_message_hq(message):
    """High-quality TTS using Wavelink/Lavalink"""
    try:
        # Extract text after !dex command
        text_to_speak = message.content.replace('!dex', '').strip()
        if not text_to_speak:
            await message.reply("Please provide text to speak! Example: `!dex Hello world`")
            return

        # Check if user is in voice channel
        if not message.author.voice:
            await message.reply("You need to be in a voice channel first!")
            return

        voice_channel = message.author.voice.channel
        
        # Generate TTS audio file
        logger.info(f"Generating TTS for: '{text_to_speak}'")
        audio_file = bot.fish.text_to_mp3(text_to_speak)
        
        # Get or create Wavelink player for this guild
        player: wavelink.Player = message.guild.voice_client
        if not player:
            player = await voice_channel.connect(cls=wavelink.Player)
        elif player.channel != voice_channel:
            await player.move_to(voice_channel)

        # Create track from local file and play with high quality
        track = await wavelink.LocalTrack.search(audio_file)
        if track:
            await player.play(track[0])  # LocalTrack.search returns a list
            await message.add_reaction("🔊")  # React to show it's playing
            logger.info(f"Playing TTS audio: {audio_file}")
        else:
            await message.reply("Failed to load audio file for playback")
            
    except wavelink.NodeException:
        logger.error("Lavalink connection failed - falling back to regular Discord audio")
        await speak_message_fallback(message)
    except Exception as e:
        logger.error(f"Error in speak_message_hq: {e}")
        await message.reply(f"Error playing TTS: {e}")

async def speak_message_fallback(message):
    """Fallback to regular Discord audio if Lavalink fails"""
    text_to_speak = message.content.replace('!dex', '').strip()
    audio_file = bot.fish.text_to_mp3(text_to_speak)

    if message.author.voice:
        vc = await message.author.voice.channel.connect()
        
        # Use best quality FFmpeg options as fallback
        source = discord.FFmpegOpusAudio(
            audio_file,
            before_options='-nostdin',
            options='-ar 48000 -ac 2 -b:a 256k'
        )
        
        vc.play(source)
        await message.add_reaction("🔊")
        
        # Wait for playback to finish
        while vc.is_playing():
            await asyncio.sleep(1)
        await vc.disconnect()

@bot.command(name='join')
async def join_voice(ctx):
    """Join voice channel command"""
    if not ctx.author.voice:
        await ctx.send("You're not in a voice channel!")
        return
    
    channel = ctx.author.voice.channel
    player: wavelink.Player = ctx.guild.voice_client
    
    if not player:
        player = await channel.connect(cls=wavelink.Player)
        await ctx.send(f"Joined {channel.name}")
    else:
        await ctx.send("Already connected to a voice channel!")

@bot.command(name='leave')
async def leave_voice(ctx):
    """Leave voice channel command"""
    player: wavelink.Player = ctx.guild.voice_client
    
    if player:
        await player.disconnect()
        await ctx.send("Disconnected from voice channel")
    else:
        await ctx.send("Not connected to any voice channel!")

@bot.command(name='stop')
async def stop_audio(ctx):
    """Stop current audio playback"""
    player: wavelink.Player = ctx.guild.voice_client
    
    if player and player.playing:
        await player.stop()
        await ctx.send("Stopped audio playback")
    else:
        await ctx.send("Nothing is currently playing!")

# Wavelink event handlers
@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
    logger.info(f"Wavelink node '{payload.node.identifier}' is ready!")

@bot.event  
async def on_wavelink_track_start(payload: wavelink.TrackStartEventPayload):
    logger.info(f"Track started: {payload.track.title}")

@bot.event
async def on_wavelink_track_end(payload: wavelink.TrackEndEventPayload):
    logger.info(f"Track ended: {payload.track.title}")
    
    # Auto-disconnect after TTS finishes (optional)
    player = payload.player
    if player and not player.queue:  # No more tracks in queue
        await asyncio.sleep(2)  # Brief pause
        await player.disconnect()
