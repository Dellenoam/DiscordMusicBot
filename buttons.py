from collections import defaultdict
from discord.ui import Button
import discord

skip_votes = defaultdict(set)


# Кнопка для пропуска трека
class SkipButton(Button):
    def __init__(self):
        super().__init__(label="Пропустить", style=discord.ButtonStyle.gray, emoji='⏭')
        self.callback = self.button_callback

    async def button_callback(self, interaction):
        await self.button_handler(interaction)

    @staticmethod
    async def button_handler(interaction):
        """Пропускает текущий трек"""
        if not interaction.user.voice:
            return await interaction.response.send_message('Ты должен быть в голосовом канале', ephemeral=True)

        guild_id = interaction.guild_id
        voice_client = interaction.guild.voice_client

        if not voice_client:
            return await interaction.response.send_message('Сейчас ничего не играет', ephemeral=True)

        if interaction.user.id in skip_votes[guild_id]:
            return await interaction.response.send_message('Ты уже проголосовал', ephemeral=True)

        skip_votes[guild_id].add(interaction.user.id)
        total_members = len(interaction.user.voice.channel.voice_states.keys()) - 1

        if not len(skip_votes[guild_id]) / total_members >= 0.5:
            return await interaction.response.send_message(
                f'Ты проголосовал за пропуск трека. Осталось голосов '
                f'{round(total_members * 0.5) - len(skip_votes[guild_id])}'
            )

        voice_client.stop()
        skip_votes[guild_id].clear()
        return await interaction.response.send_message('Трек пропущен')


# Кнопка для просмотра очереди треков
class QueueButton(Button):
    def __init__(self, queue_function, queues):
        super().__init__(label="Очередь", style=discord.ButtonStyle.gray, emoji='🎵')
        self.queue_function = queue_function
        self.queues = queues
        self.callback = self.button_callback

    async def button_callback(self, interaction):
        await self.button_handler(interaction, self.queues)

    @staticmethod
    async def button_handler(interaction, queues):
        """Отображает текущую очередь"""
        guild_id = interaction.guild_id

        if queues.get(guild_id):
            formatted_queue = "\n".join(
                [f'{index + 1}. {query["title"]}' for index, query in enumerate(queues[guild_id])])
            message = f'Следующие треки:\n{formatted_queue}'
            return await interaction.response.send_message(message)

        await interaction.response.send_message('Очередь пуста')


# Кнопка для удаления добавленного трека из очереди
class RemoveButton(Button):
    def __init__(self, queues, track_info):
        super().__init__(label='Удалить', style=discord.ButtonStyle.gray, emoji='❌')
        self.queues = queues
        self.track_info = track_info
        self.callback = self.button_callback

    async def button_callback(self, interaction):
        if interaction.user != self.track_info['author']:
            return await interaction.response.send_message(
                'Ты не можешь удалять треки, добавленные другими пользователями', ephemeral=True
            )

        if not self.queues[interaction.guild_id][0] == self.track_info:
            return await interaction.response.send_message(f'Трек {self.track_info["title"]} отсутствует в очереди')

        self.queues[interaction.guild_id].remove(self.track_info)
        return await interaction.response.send_message(f'Трек {self.track_info["title"]} был удален из очереди')
