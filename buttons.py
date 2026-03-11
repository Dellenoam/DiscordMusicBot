from typing import Dict, List

import asyncio
import discord
from discord import Interaction
from discord.ui import Button, Select

from handlers import skip_handler, queue_handler
from models import TrackInfo


class SkipButton(Button):
    """
    Класс кнопки для пропуска текущего трека.

    Attributes:
        label (str): Текст кнопки.
        style (discord.ButtonStyle): Стиль кнопки.
        emoji (str): Эмодзи для кнопки.

    Methods:
        button_callback: Обработчик нажатия кнопки для пропуска текущего трека.
    """

    def __init__(self) -> None:
        super().__init__(
            label="Пропустить", style=discord.ButtonStyle.danger, emoji="⏭"
        )
        self.callback = self.button_callback

    @staticmethod
    async def button_callback(interaction: Interaction) -> None:
        """Пропускает текущий трек"""
        await skip_handler(interaction)


class QueueButton(Button):
    """
    Класс кнопки для просмотра текущей очереди.

    Attributes:
        label (str): Текст кнопки.
        style (discord.ButtonStyle): Стиль кнопки.
        emoji (str): Эмодзи для кнопки.
        queues (dict): Словарь очередей.

    Methods:
        button_callback: Обработчик нажатия кнопки для просмотра текущей очереди.
    """

    def __init__(self, queues: Dict[int, List[TrackInfo]]) -> None:
        super().__init__(label="Очередь", style=discord.ButtonStyle.primary, emoji="🎵")
        self.queues = queues
        self.callback = self.button_callback

    async def button_callback(self, interaction: Interaction) -> None:
        await queue_handler(interaction, self.queues)


class RemoveButton(Button):
    """
    Класс кнопки для удаления трека из очереди.

    Attributes:
        label (str): Текст кнопки.
        style (discord.ButtonStyle): Стиль кнопки.
        emoji (str): Эмодзи для кнопки.
        queues (dict): Словарь очередей.
        track_info (TrackInfo): Информация о треке.

    Methods:
        button_callback: Обработчик нажатия кнопки для удаления трека из очереди.
    """

    def __init__(self, queues: Dict[int, List[TrackInfo]], track_info: TrackInfo) -> None:
        super().__init__(label="Удалить", style=discord.ButtonStyle.danger, emoji="❌")
        self.queues = queues
        self.track_info = track_info
        self.callback = self.button_callback

    async def button_callback(self, interaction: Interaction) -> None:
        """
        Удаляет трек из очереди при нажатии кнопки.

        Parameters:
            interaction (Interaction): Взаимодействие с кнопкой.
        """
        if interaction.user != self.track_info.author:
            await interaction.response.send_message(
                "Ты не можешь удалять треки, добавленные другими пользователями",
                ephemeral=True,
            )
            return

        if self.track_info not in self.queues[interaction.guild_id]:
            await interaction.response.send_message(
                f"Трек {self.track_info.title} отсутствует в очереди"
            )
            return

        self.queues[interaction.guild_id].remove(self.track_info)
        await interaction.response.send_message(
            f"Трек {self.track_info.title} был удален из очереди"
        )


class SearchResultSelect(Select):
    """Выпадающий список для выбора трека из результатов поиска."""

    def __init__(self, entries: List[dict], future: asyncio.Future) -> None:
        options = [
            discord.SelectOption(label=entry["title"][:100], value=str(index))
            for index, entry in enumerate(entries)
        ]
        super().__init__(placeholder="Выберите трек", options=options)
        self.future = future
        self.entries = entries

    async def callback(self, interaction: Interaction) -> None:
        await interaction.response.defer()
        index = int(self.values[0])
        if not self.future.done():
            self.future.set_result(self.entries[index])
        try:
            await interaction.message.delete()
        except discord.NotFound:
            pass
