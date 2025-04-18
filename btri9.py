import discord
from discord.ext import commands
import yt_dlp
import asyncio
import urllib.parse

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

queues = {}
playing_now = {}  # {guild_id: {"url": str, "time": int}}

def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = asyncio.Queue()
    return queues[guild_id]

def search_spotify(spotify_url):
    # Convertiamo il link di Spotify in una ricerca su YouTube
    spotify_url = spotify_url.strip()
    if "spotify.com" not in spotify_url:
        return None

    # Estraiamo il nome del brano dal link
    query = urllib.parse.quote(spotify_url)
    return f"ytsearch:{query}"

@bot.event
async def on_ready():
    print(f"✅ Bot connesso come {bot.user}")

@bot.command()
async def helpme(ctx):
    help_text = """
📖 **Comandi disponibili**:

🎧 **Musica:**
- `!join` → Entra nel tuo canale vocale
- `!play <url>` → Riproduce musica da YouTube o Spotify
- `!pause` → Mette in pausa la musica
- `!resume` → Riprende la musica
- `!stop` → Ferma la musica
- `!skip` → Salta la traccia attuale
- `!seekforward <secondi>` → Avanza nel brano
- `!seekback <secondi>` → Torna indietro nel brano
- `!queue` → Mostra la coda dei brani
- `!leave` → Esce dal canale vocale

ℹ️ **Altro:**
- `!helpme` → Mostra questo messaggio di aiuto

🎶 Scrivi `!play <link>` per iniziare subito!
"""
    await ctx.send(help_text)

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send("🎧 Connesso al canale vocale!")
    else:
        await ctx.send("❌ Devi essere in un canale vocale!")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Uscito dal canale vocale.")
    else:
        await ctx.send("❌ Non sono in un canale vocale.")

@bot.command()
async def play(ctx, url):
    guild_id = ctx.guild.id
    queue = get_queue(guild_id)

    # Se il link è di Spotify, cerchiamo il brano su YouTube
    if 'spotify.com' in url:
        await ctx.send("🔍 Cercando su YouTube...")
        search_url = search_spotify(url)
        if search_url is None:
            await ctx.send("❌ Impossibile trovare il brano.")
            return
        url = search_url  # Cerca su YouTube

    await queue.put(url)
    await ctx.send(f"🎶 Aggiunto in coda: {url}")

    if not ctx.voice_client:
        await ctx.invoke(join)

    if not getattr(ctx.voice_client, "is_playing_music", False):
        await play_next(ctx)

async def play_next(ctx, seek_time=0):
    guild_id = ctx.guild.id
    queue = get_queue(guild_id)

    if queue.empty() and guild_id not in playing_now:
        await ctx.send("🚫 Coda finita.")
        return

    if guild_id in playing_now:
        url = playing_now[guild_id]["url"]
        seek_time = playing_now[guild_id].get("time", 0)
    else:
        url = await queue.get()
        playing_now[guild_id] = {"url": url, "time": 0}

    ydl_opts = {
        'format': 'bestaudio',
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch',
        'noplaylist': True,
        'extract_flat': False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        audio_url = info['url']
        title = info.get('title', 'Sconosciuto')

    ffmpeg_opts = {
        'before_options': f'-ss {seek_time}',
        'options': '-vn'
    }

    ctx.voice_client.is_playing_music = True
    playing_now[guild_id]["time"] = seek_time
    ctx.voice_client.play(
        discord.FFmpegPCMAudio(audio_url, **ffmpeg_opts),
        after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
    )

    await ctx.send(f"🎵 In riproduzione: **{title}** (da {seek_time} sec)")

@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Pausa.")
    else:
        await ctx.send("❌ Nessuna musica in riproduzione.")

@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Ripresa.")
    else:
        await ctx.send("❌ Nessuna musica in pausa.")

@bot.command()
async def stop(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏹️ Fermato.")
    else:
        await ctx.send("❌ Nessuna musica da fermare.")

@bot.command()
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Traccia saltata.")
    else:
        await ctx.send("❌ Nessuna musica da saltare.")

@bot.command()
async def seekforward(ctx, seconds: int):
    guild_id = ctx.guild.id
    if guild_id in playing_now:
        playing_now[guild_id]["time"] += seconds
        ctx.voice_client.stop()
        await ctx.send(f"⏩ Avanzato di {seconds} secondi.")
    else:
        await ctx.send("❌ Nessuna traccia in riproduzione.")

@bot.command()
async def seekback(ctx, seconds: int):
    guild_id = ctx.guild.id
    if guild_id in playing_now:
        playing_now[guild_id]["time"] = max(0, playing_now[guild_id]["time"] - seconds)
        ctx.voice_client.stop()
        await ctx.send(f"⏪ Tornato indietro di {seconds} secondi.")
    else:
        await ctx.send("❌ Nessuna traccia in riproduzione.")

@bot.command()
async def queue(ctx):
    queue = get_queue(ctx.guild.id)
    items = list(queue._queue)
    if items:
        response = "\n".join([f"{i+1}. {url}" for i, url in enumerate(items)])
        await ctx.send(f"📃 Coda attuale:\n{response}")
    else:
        await ctx.send("📭 La coda è vuota.")

bot.run()
