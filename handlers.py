from collections import defaultdict
from typing import Dict
from discord.interactions import Interaction

skip_votes = defaultdict(set)


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

    if interaction.user.id in skip_votes[guild_id]:
        await interaction.response.send_message("Ты уже проголосовал", ephemeral=True)
        return

    skip_votes[guild_id].add(interaction.user.id)
    total_members = len(interaction.user.voice.channel.voice_states.keys()) - 1

    if not len(skip_votes[guild_id]) / total_members >= 0.5:
        await interaction.response.send_message(
            f"Ты проголосовал за пропуск трека. Осталось голосов "
            f"{round(total_members * 0.5) - len(skip_votes[guild_id])}"
        )
        return

    voice_client.stop()
    del skip_votes[guild_id]
    await interaction.response.send_message("Трек пропущен")


async def queue_handler(interaction: Interaction, queues: Dict[int, list]) -> None:
    """
    Обработчик команды для просмотра текущей очереди.

    Parameters:
        interaction (Interaction): Взаимодействие с кнопкой.
        queues (Dict[int, list]): Словарь очередей.
    """
    guild_id = interaction.guild_id

    if queues.get(guild_id):
        formatted_queue = "\n".join(
            [
                f'{index + 1}. {query["title"]}'
                for index, query in enumerate(queues[guild_id])
            ]
        )
        message = f"Следующие треки:\n{formatted_queue}"
        await interaction.response.send_message(message)
        return

    await interaction.response.send_message("Очередь пуста")
