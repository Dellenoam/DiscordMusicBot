import asyncio
import os
import dotenv
import discord
import yt_dlp
from discord.ext import commands
from discord.ui import View

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
            else:
                audio_url = info['entries'][0].get('url')
                title = info['entries'][0].get('title')

    if audio_url is None:
        return await ctx.respond('Трек не найден')

    guild_id = ctx.guild.id

    queues.setdefault(guild_id, []).append(
        {'url': audio_url, 'title': title}
    )

    await ctx.respond(f"Трек: {title} добавлен в очередь")


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
        await ctx.respond(f"Сейчас играет: {query['title']}", view=SkipQueueView())

        while ctx.voice_client.is_playing():
            await asyncio.sleep(1)

    await ctx.voice_client.disconnect()


# Класс View с кнопками "Пропустить" и "Очередь"
class SkipQueueView(View):
    @discord.ui.button(label="Пропустить", style=discord.ButtonStyle.primary, emoji='⏭')
    async def skip_button(self, button, interaction):
        """Пропускает текущий трек"""
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            return await interaction.response.send_message('Трек пропущен')

        await interaction.reponse.send_message('Сейчас ничего не играет')

    @discord.ui.button(label="Очередь", style=discord.ButtonStyle.primary, emoji='🎵')
    async def queue_button(self, button, interaction):
        """Отображает текущую очередь"""
        guild_id = interaction.guild.id

        if queues.get(guild_id):
            formatted_queue = "\n".join(
                [f'{index + 1}. {query["title"]}' for index, query in enumerate(queues[guild_id])])
            message = f'Следующие треки:\n{formatted_queue}'
            return await interaction.response.send_message(message)

        await interaction.response.send_message('Очередь пуста')


# Запускаем бота
bot.run(os.getenv('DISCORD_TOKEN'))
