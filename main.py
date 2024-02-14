import asyncio
import os
import re
import dotenv
import discord
import yt_dlp
from buttons import SkipButton, QueueButton, RemoveButton
from handlers import skip_handler, queue_handler, skip_votes
from discord.ext import commands

# Загружаем .env
dotenv.load_dotenv()

# Создаем объект бота
bot = commands.Bot()


# По готовности бота задается статус, активность и выводится сообщение о начале работы
@bot.event
async def on_ready():
    activity = discord.Game(name="Detroit: Become Human")
    await bot.change_presence(status=discord.Status.do_not_disturb, activity=activity)
    print('Bot is online!')


# Создаем объект для загрузки видео с YouTube
ydl_opts = {
    'quiet': True,
    'noplaylist': True,
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

# Семафоры для каждого сервера
guild_semaphore = dict()


@bot.slash_command(name='play')
async def play(ctx, *, query: str):
    """Команда для проигрывания трека и добавления его в очередь"""
    if not ctx.author.voice:
        return await ctx.respond('Ты должен быть в голосовом канале', ephemeral=True)

    await ctx.respond('Думаю над ответом 🤔')

    try:
        message_to_reply = await enqueue(ctx, query)
    except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError):
        return await ctx.respond('Введена некорректная ссылка')

    semaphore = guild_semaphore.get(ctx.guild_id)
    if semaphore is None:
        semaphore = asyncio.Semaphore(1)
        guild_semaphore[ctx.guild_id] = semaphore
    async with semaphore:
        if not queues.get(ctx.guild_id):
            return
        await play_queue(ctx, message_to_reply)


async def enqueue(ctx, query: str):
    """Добавляет трек в очередь"""
    with ydl:
        not_video_url_regex = re.compile(r'^(?:https?://)?(?:www\.)?(youtube.com|youtu.be)/?$')
        video_url_regex = re.compile(
            r'^(?:https?://)?(?:www\.)?(?:youtu\.be/|youtube\.com/(?:embed/|v/|watch\?v=|watch\?.+&v=))([\w-]{11})$'
        )
        if bool(not_video_url_regex.match(query)):
            raise yt_dlp.utils.ExtractorError('ERROR: Введена ссылка на YouTube, а не на видео с него')
        if bool(video_url_regex.match(query)):
            info = await asyncio.to_thread(lambda: ydl.extract_info(query, download=False))
            audio_url = info['url']
            title = info['title']
        else:
            info = await asyncio.to_thread(lambda: ydl.extract_info(f'ytsearch:{query}', download=False))
            if not info['entries']:
                return await ctx.respond('Ничего не нашел по твоему запросу')
            audio_url = info['entries'][0]['url']
            title = info['entries'][0]['title']

    guild_id = ctx.guild_id
    track_info = {'url': audio_url, 'title': title, 'author': ctx.author}
    queues.setdefault(guild_id, []).append(track_info)

    view = discord.ui.View(timeout=None)
    view.add_item(RemoveButton(queues, track_info))
    return await ctx.respond(f"Трек: {title} добавлен в очередь", view=view)


async def play_queue(ctx, message_to_reply):
    """Проигрывает треки из очереди"""
    guild_id = ctx.guild.id

    query = queues[guild_id].pop(0)

    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    ctx.voice_client.play(
        discord.FFmpegPCMAudio(
            query['url'],
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -vn'
        )
    )

    view = discord.ui.View(timeout=None)
    view.add_item(SkipButton())
    view.add_item(QueueButton(queues))
    await message_to_reply.reply(f"Сейчас играет: {query['title']}", view=view)

    while ctx.voice_client.is_playing():
        await asyncio.sleep(1)

    if skip_votes.get(guild_id):
        del skip_votes[guild_id]

    if not queues[guild_id]:
        del guild_semaphore[guild_id]
        await ctx.voice_client.disconnect()


@bot.slash_command(name='skip', description='Пропустить текущий трек')
async def skip(ctx):
    """Пропускает текущий трек"""
    await skip_handler(ctx)


@bot.slash_command(name='queue', description='Посмотреть текущую очередь')
async def queue(ctx):
    """Отображает текущую очередь"""
    await queue_handler(ctx, queues)


# Запускаем бота
bot.run(os.getenv('DISCORD_TOKEN'))
