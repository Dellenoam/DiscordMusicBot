from discord.ui import Button
import discord


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
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            return await interaction.response.send_message('Трек пропущен')

        await interaction.reponse.send_message('Сейчас ничего не играет')


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
        guild_id = interaction.guild.id

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
        if interaction.user == self.track_info['ctx'].author:
            if (not self.queues[interaction.guild.id]
                    or not [track for track in self.queues[interaction.guild.id]][0] == self.track_info):
                return await interaction.response.send_message(f'Трек {self.track_info["title"]} отсутствует в очереди')
            self.queues[interaction.guild.id].remove(self.track_info)
            await interaction.response.send_message(f'Трек {self.track_info["title"]} был удален из очереди')
        else:
            await interaction.response.send_message('Ты не можешь удалять треки, добавленные другими пользователями')
