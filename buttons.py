from discord.ui import Button
from handlers import skip_handler, queue_handler
import discord


# Кнопка для пропуска трека
class SkipButton(Button):
    def __init__(self):
        super().__init__(label="Пропустить", style=discord.ButtonStyle.gray, emoji='⏭')
        self.callback = self.button_callback

    @staticmethod
    async def button_callback(interaction):
        """Пропускает текущий трек"""
        await skip_handler(interaction)


# Кнопка для просмотра очереди треков
class QueueButton(Button):
    def __init__(self, queues):
        super().__init__(label="Очередь", style=discord.ButtonStyle.gray, emoji='🎵')
        self.queues = queues
        self.callback = self.button_callback

    async def button_callback(self, interaction):
        await queue_handler(interaction, self.queues)


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

        if self.queues.get(interaction.guild_id) and self.track_info not in self.queues[interaction.guild_id]:
            return await interaction.response.send_message(f'Трек {self.track_info["title"]} отсутствует в очереди')

        self.queues[interaction.guild_id].remove(self.track_info)
        return await interaction.response.send_message(f'Трек {self.track_info["title"]} был удален из очереди')
