# Music Bot

This is a simple music bot written in Python using the Pycord library and yt_dlp to search and retrieve audio tracks from YouTube.
Users can add tracks to the queue, skip the current track, remove track from queue and view the queue.

## Getting Started

### Installation

1. Clone the repository:

    ```bash
    git clone https://github.com/Dellenoam/DiscordMusicBot.git
    ```

2. Change into the project directory:

    ```bash
    cd DiscordMusicBot
    ```
3. Set up a virtual environment
   
   For Windows
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
   For Linux/MacOS
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

4. Install dependencies:

    ```bash
    pip install -r requirements.txt
    ```
5. Install ffmpeg:
   
    You also need ffmpeg to work, you can download it from ffmpeg.org or using a package manager. 

6. Create a `.env` file in the project root and add your Discord bot token:

    ```
    DISCORD_TOKEN=your_discord_token_here
    # Optional: percentage of votes required to skip
    SKIP_VOTE_PERCENT=0.5
    # Optional: allow administrators to skip instantly
    ADMIN_INSTANT_SKIP=true
    ```

7. Run the bot:

    ```bash
    python main.py
    ```

## Usage

- To play a track and add it to the queue, use the /play command.
- To view the current queue, use the /queue command or click on the 'Очередь' button that is sent along with the message about the playing track.
- To skip the current track, use the /skip command or click on the 'Пропустить' button that is sent along with the message about the playing track.
- If you want to remove a track from the queue, click on the 'Удалить' button that is sent along with the message about the added track.

Feel free to customize and extend the functionality as needed!

## Contributing

Contributions are welcome. Please fork the repository, make your changes, and submit a pull request.

## License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.
