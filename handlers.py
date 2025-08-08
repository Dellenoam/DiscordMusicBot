import os
from collections import defaultdict
from typing import Dict, List, Tuple

from discord.interactions import Interaction

from models import TrackInfo

skip_votes = defaultdict(set)


def _get_skip_settings() -> Tuple[float, bool]:
    """Возвращает порог голосов и флаг мгновенного пропуска администратором."""
    percent = float(os.getenv("SKIP_VOTE_PERCENT", 0.5))
    admin_instant = os.getenv("ADMIN_INSTANT_SKIP", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    return percent, admin_instant


async def skip_handler(interaction: Interaction) -> None:
    """
    Обработчик команды пропуска текущего трека.

    Parameters:
        interaction (Interaction): Взаимодействие с кнопкой.
    """
    if not interaction.user.voice:
        await interaction.response.send_message(
            "Ты должен быть в голосовом канале", ephemeral=True
        )
        return

    guild_id = interaction.guild_id
    voice_client = interaction.guild.voice_client

    if not voice_client:
        await interaction.response.send_message(
            "Сейчас ничего не играет", ephemeral=True
        )
        return

    vote_percent, admin_instant = _get_skip_settings()

    if admin_instant and interaction.user.guild_permissions.administrator:
        voice_client.stop()
        skip_votes.pop(guild_id, None)
        await interaction.response.send_message("Трек пропущен администратором")
        return

    if interaction.user.id in skip_votes[guild_id]:
        await interaction.response.send_message(
            "Ты уже проголосовал", ephemeral=True
        )
        return

    skip_votes[guild_id].add(interaction.user.id)
    total_members = len(interaction.user.voice.channel.voice_states.keys()) - 1

    if total_members == 0:
        voice_client.stop()
        del skip_votes[guild_id]
        await interaction.response.send_message(
            "Недостаточно участников для голосования. Трек остановлен."
        )
        return

    required_votes = round(total_members * vote_percent)
    if len(skip_votes[guild_id]) < required_votes:
        await interaction.response.send_message(
            "Ты проголосовал за пропуск трека. Осталось голосов "
            f"{required_votes - len(skip_votes[guild_id])}"
        )
        return

    voice_client.stop()
    del skip_votes[guild_id]
    await interaction.response.send_message("Трек пропущен")


async def queue_handler(interaction: Interaction, queues: Dict[int, List[TrackInfo]]) -> None:
    """
    Обработчик команды для просмотра текущей очереди.

    Parameters:
        interaction (Interaction): Взаимодействие с кнопкой.
        queues (Dict[int, List[TrackInfo]]): Словарь очередей.
    """
    guild_id = interaction.guild_id

    if queues.get(guild_id):
        formatted_queue = "\n".join(
            [
                f"{index + 1}. {track.title}"
                for index, track in enumerate(queues[guild_id])
            ]
        )
        message = f"Следующие треки:\n{formatted_queue}"
        await interaction.response.send_message(message)
        return

    await interaction.response.send_message("Очередь пуста")
