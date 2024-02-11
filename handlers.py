from collections import defaultdict

skip_votes = defaultdict(set)


async def skip_handler(interaction):
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
    del skip_votes[guild_id]
    return await interaction.response.send_message('Трек пропущен')


async def queue_handler(interaction, queues):
    """Отображает текущую очередь"""
    guild_id = interaction.guild_id

    if queues.get(guild_id):
        formatted_queue = "\n".join(
            [f'{index + 1}. {query["title"]}' for index, query in enumerate(queues[guild_id])])
        message = f'Следующие треки:\n{formatted_queue}'
        return await interaction.response.send_message(message)

    await interaction.response.send_message('Очередь пуста')
