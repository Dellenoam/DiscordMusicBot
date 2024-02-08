import asyncio
import os
import dotenv
import discord
import yt_dlp
from discord.ext import commands

import buttons
from buttons import SkipButton, QueueButton, RemoveButton

# Загружаем .env
dotenv.load_dotenv()

# Создаем объект бота
bot = commands.Bot()


# По готовности бота задается статус, активность и выводится сообщение о начале работы
@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.do_not_disturb, activity=discord.Game(name="Detroit: Become Human"))
    print('Bot is online!')


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


@bot.slash_command(name='play')
async def play(ctx, *, query: str):
    """Команда для проигрывания трека и добавления его в очередь"""
    await ctx.defer()

    if not ctx.author.voice:
        return await ctx.respond('Ты должен быть подключен к каналу')

    await enqueue(ctx, query)

    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await play_queue(ctx)


async def enqueue(ctx, query: str):
    """Добавляет трек в очередь"""
    with ydl:
        if 'youtube.com' in query or 'youtu.be' in query:
            info = ydl.extract_info(query, download=False)
            audio_url = info.get('url')
            title = info.get('title')
        else:
            info = ydl.extract_info(f'ytsearch:{query}', download=False)
            if not info.get('entries'):
                return await ctx.respond('Трек не найден')
            audio_url = info['entries'][0].get('url')
            title = info['entries'][0].get('title')

    if audio_url is None:
        return await ctx.respond('Трек не найден')

    guild_id = ctx.guild.id
    track_info = {'url': audio_url, 'title': title, 'ctx': ctx}
    queues.setdefault(guild_id, []).append(
        track_info
    )

    view = discord.ui.View()
    view.add_item(RemoveButton(queues, track_info))
    view.add_item(QueueButton(queue, queues))
    await ctx.respond(f"Трек: {title} добавлен в очередь", view=view)


async def play_queue(ctx):
    """Проигрывает треки из очереди"""
    guild_id = ctx.guild.id

    while queues[guild_id]:
        query = queues[guild_id].pop(0)
        ctx = query['ctx']

        if not ctx.voice_client or not ctx.voice_client.is_connected():
            await ctx.author.voice.channel.connect()

        ctx.voice_client.play(
            discord.FFmpegPCMAudio(
                query['url'],
                before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -vn'
            )
        )

        view = discord.ui.View()
        view.add_item(SkipButton())
        view.add_item(QueueButton(queue, queues))
        await ctx.respond(f"Сейчас играет: {query['title']}", view=view)

        while ctx.voice_client.is_playing():
            await asyncio.sleep(1)

    await ctx.voice_client.disconnect()


@bot.slash_command(name='skip', description='Пропустить текущий трек')
async def skip(interaction):
    """Пропускает текущий трек"""
    await buttons.SkipButton.button_handler(interaction)


@bot.slash_command(name='queue', description='Посмотреть текущую очередь')
async def queue(interaction):
    """Отображает текущую очередь"""
    await buttons.QueueButton.button_handler(interaction, queues)

# Запускаем бота
bot.run(os.getenv('DISCORD_TOKEN'))
