import asyncio
import os
import dotenv
import discord
import yt_dlp
from discord.ext import commands

# Загружаем .env
dotenv.load_dotenv()

# События для обработки ботом
intents = discord.Intents.all()

# Создаем объект бота
bot = commands.Bot(command_prefix='!', intents=intents)

# Создаем объект для загрузки видео с YouTube
ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

# Объект YoutubeDL с настройками
ydl = yt_dlp.YoutubeDL(ydl_opts)

# Очередь музыки
queues = dict()


@bot.command(name='play')
async def play(ctx, *, track):
    """Команда для проигрывания трека и добавления его в очередь"""
    if not ctx.author.voice:
        await ctx.send('Ты должен быть подключен к каналу')
        return

    await enqueue(ctx, track)

    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await play_queue(ctx)


async def enqueue(ctx, query):
    """Добавляет трек в очередь"""
    with ydl:
        if 'youtube.com' in query or 'youtu.be' in query:
            info = ydl.extract_info(query, download=False)
            audio_url = info.get('url')
            title = info.get('title')
        else:
            info = ydl.extract_info(f'ytsearch:{query}', download=False)
            if not info.get('entries'):
                return await ctx.send('Трек не найден')
            else:
                audio_url = info['entries'][0].get('url')
                title = info['entries'][0].get('title')

    if audio_url is None:
        return await ctx.send('Трек не найден')

    guild_id = ctx.guild.id

    queues.setdefault(guild_id, []).append(
        {'url': audio_url, 'title': title}
    )

    await ctx.send(f"Трек: {title} добавлен в очередь")


async def play_queue(ctx):
    """Проигрывает треки из очереди"""
    guild_id = ctx.guild.id

    while queues[guild_id]:
        query = queues[guild_id].pop(0)

        if not ctx.voice_client or not ctx.voice_client.is_connected():
            await ctx.author.voice.channel.connect()

        ctx.voice_client.play(
            discord.FFmpegPCMAudio(
                query['url'],
                before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -vn'
            )
        )
        await ctx.send(f"Сейчас играет: {query['title']}")

        while ctx.voice_client.is_playing():
            await asyncio.sleep(1)

    await ctx.voice_client.disconnect()


@bot.command(name='queue')
async def queue(ctx):
    """Отображает текущую очередь"""
    guild_id = ctx.guild.id

    if queues.get(guild_id):
        formatted_queue = "\n".join([f'{index + 1}. {query["title"]}' for index, query in enumerate(queues[guild_id])])
        message = f'Следующие треки:\n{formatted_queue}'
        return await ctx.send(message)

    await ctx.send('Очередь пуста')


@bot.command(name='skip')
async def skip(ctx):
    """Пропускает текущий трек"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send('Трек пропущен')
        return

    await ctx.send('Сейчас ничего не играет')


# Запускаем бота
bot.run(os.getenv('DISCORD_TOKEN'))
