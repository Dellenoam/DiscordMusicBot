import asyncio
from collections import defaultdict
import os
import re
from typing import Optional
import dotenv
import discord
from discord.ext import commands
from discord.commands.context import ApplicationContext
from discord.webhook import WebhookMessage
import yt_dlp
from buttons import SkipButton, QueueButton, RemoveButton, SearchResultSelect
from handlers import skip_handler, queue_handler, skip_votes
from models import TrackInfo

# Загружаем .env
dotenv.load_dotenv()

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise ValueError("DISCORD_TOKEN environment variable is not set or empty.")

# Создаем объект бота
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(intents=intents)

# Создаем объект для загрузки видео с YouTube
ydl_opts = {
    "quiet": True,
    "noplaylist": True,
    "format": "bestaudio/best",
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }
    ],
}

# Объект YoutubeDL с настройками
ydl = yt_dlp.YoutubeDL(ydl_opts)

# Очередь музыки
queues = defaultdict(list)

# Семафоры для каждого сервера создаются по мере необходимости
guild_semaphore = defaultdict(lambda: asyncio.Semaphore(1))

# Предварительно компилированные регулярные выражения
NOT_VIDEO_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(youtube.com|youtu.be)/?$"
)
VIDEO_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:youtu\.be/|youtube\.com/(?:embed/|v/|watch\?v=|watch\?.+&v=))([\w-]{11})$"
)


@bot.event
async def on_ready() -> None:
    """
    Обработчик события on_ready для бота.

    Устанавливает активность и статус бота при его запуске.
    """
    activity = discord.Game(name="Detroit: Become Human")
    await bot.change_presence(status=discord.Status.do_not_disturb, activity=activity)
    print("Bot is online!")


@bot.slash_command(name="play")
async def play(ctx: ApplicationContext, *, query: str) -> None:
    """
    Обработка команды play для бота.

    Parameters:
        ctx (ApplicationContext): Контекст команды.
        query (str): Запрос для поиска или воспроизведения трека.
    """
    if not ctx.author.voice:
        await ctx.respond("Ты должен быть в голосовом канале", ephemeral=True)
        return

    await ctx.respond("Думаю над ответом 🤔")

    try:
        track_added_message = await enqueue(ctx, query)
        if not track_added_message:
            return
    except (
        yt_dlp.utils.DownloadError,
        yt_dlp.utils.ExtractorError,
        yt_dlp.utils.UnsupportedError,
    ):
        await ctx.respond("Введена некорректная ссылка")
        return

    guild_id = ctx.guild_id
    semaphore = guild_semaphore[guild_id]
    async with semaphore:
        if not queues[guild_id]:
            return
        await play_queue(ctx, track_added_message)


async def enqueue(ctx: ApplicationContext, query: str) -> Optional[WebhookMessage]:
    """
    Добавляет трек в очередь для воспроизведения.

    Parameters:
        ctx (ApplicationContext): Контекст вызова команды.
        query (str): Запрос для поиска или воспроизведения трека.

    Returns:
        Optional[WebhookMessage]: Сообщение о добавлении трека в очередь, если что-то найдено. None, если ничего не найдено.

    Raises:
        yt_dlp.utils.UnsupportedError: Если введена ссылка на YouTube, а не на видео.
    """
    with ydl:
        if bool(NOT_VIDEO_URL_RE.match(query)):
            raise yt_dlp.utils.UnsupportedError(
                "ERROR: Введена ссылка на YouTube, а не на видео с него"
            )
        if bool(VIDEO_URL_RE.match(query)):
            info = await asyncio.to_thread(
                lambda: ydl.extract_info(query, download=False)
            )
            audio_url = info["url"]
            title = info["title"]
        else:
            info = await asyncio.to_thread(
                lambda: ydl.extract_info(f"ytsearch5:{query}", download=False)
            )
            entries = info.get("entries") or []
            if not entries:
                await ctx.followup.send("Ничего не нашел по твоему запросу")
                return

            future: asyncio.Future = asyncio.get_running_loop().create_future()
            select = SearchResultSelect(entries[:5], future)
            view = discord.ui.View()
            view.add_item(select)
            await ctx.followup.send("Выберите трек:", view=view, ephemeral=True)
            try:
                choice = await asyncio.wait_for(future, timeout=30)
            except asyncio.TimeoutError:
                await ctx.followup.send("Время выбора истекло", ephemeral=True)
                return

            audio_url = choice["url"]
            title = choice["title"]

    track_info = TrackInfo(url=audio_url, title=title, author=ctx.author)
    queues[ctx.guild_id].append(track_info)

    view = discord.ui.View(timeout=None)
    view.add_item(RemoveButton(queues, track_info))
    return await ctx.followup.send(f"Трек: {title} добавлен в очередь", view=view)


async def play_queue(
    ctx: ApplicationContext, track_added_message: WebhookMessage
) -> None:
    """
    Воспроизводит трек из очереди.

    Parameters:
        ctx (ApplicationContext): Контекст вызова команды.
        track_added_message (WebhookMessage): Сообщение, на которое нужно ответить с информацией о воспроизводимом треке.
    """
    guild_id = ctx.guild.id

    track = queues[guild_id].pop(0)

    if not ctx.voice_client:
        try:
            await ctx.author.voice.channel.connect()
        except (discord.ClientException, discord.Forbidden):
            await track_added_message.reply(
                "Не удалось подключиться к голосовому каналу. Проверьте права бота. Трек не будет добавлен в очередь."
            )
            if ctx.voice_client:
                await ctx.voice_client.disconnect()
            if not queues[guild_id] and guild_id in guild_semaphore:
                del guild_semaphore[guild_id]
            return

    ctx.voice_client.play(
        discord.FFmpegPCMAudio(
            track.url,
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -vn",
        )
    )

    view = discord.ui.View(timeout=None)
    view.add_item(SkipButton())
    view.add_item(QueueButton(queues))
    await track_added_message.reply(f"Сейчас играет: {track.title}", view=view)

    while ctx.voice_client.is_playing():
        await asyncio.sleep(1)

    if skip_votes[guild_id]:
        del skip_votes[guild_id]

    if not queues[guild_id]:
        await ctx.send("Воспроизведение завершено. Выход из канала")
        await ctx.voice_client.disconnect()
        del guild_semaphore[guild_id]


@bot.slash_command(name="skip", description="Пропустить текущий трек")
async def skip(ctx: ApplicationContext) -> None:
    """
    Команда для пропуска текущего трека.

    Parameters:
        ctx (ApplicationContext): Контекст приложения.
    """
    await skip_handler(ctx.interaction)


@bot.slash_command(name="queue", description="Посмотреть текущую очередь")
async def queue(ctx: ApplicationContext) -> None:
    """
    Команда для просмотра текущей очереди.

    Parameters:
        ctx (ApplicationContext): Контекст приложения.
    """
    await queue_handler(ctx.interaction, queues)


# Запускаем бота, если токен присутствует
bot.run(token)
