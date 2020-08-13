import re
from argparse import ArgumentParser
from asyncio import open_unix_connection, sleep, open_connection

import discord
from ruamel import yaml


CHAT_PATTERN = re.compile(r'^\[\S+ \S+\]\[chat\]: (\d+:\d+:.+?): (.*)$')


class TeeworldsDiscordBridge(discord.Client):

    def __init__(self, config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__config = config
        for discord_name, discord_server in config['discord_servers'].items():
            for tw_name, tw_server \
                    in discord_server['teeworlds_servers'].items():
                self.loop.create_task(
                    self.watch_log(discord_name, tw_name, tw_server)
                )

    async def on_ready(self):
        print(f'Logged in successfully as {self.user}')

    async def connect_to_log(self, path):
        reader = None
        while reader is None:
            try:
                reader, _ = await open_unix_connection(path)
            except:
                print(f'Failed to connect to log: {path}')
                await sleep(5)
        print(f'Connected to log: {path}')
        return reader

    async def watch_log(self, discord_server, tw_server, settings):
        await self.wait_until_ready()
        reader = await self.connect_to_log(settings['unix_socket'])
        channel = self.get_channel(settings['channel_id'])
        while not self.is_closed():
            line = (await reader.readline()).decode('utf-8').rstrip()
            if not line:
                reader.close()
                await reader.wait_closed()
                reader = await self.connect_to_log(settings['unix_socket'])
            match = re.match(CHAT_PATTERN, line)
            if not match:
                continue
            await channel.send(
                f'{tw_server}: {match.group(1)}: {match.group(2)}'
            )

    async def on_message(self, message):
        settings = self.__config['discord_servers'].get(
            message.channel.guild.id
        )
        if settings is None or self.user.id == message.author.id:
            return
        for server in settings['teeworlds_servers'].values():
            if message.channel.id == server['channel_id']:
                _, writer = await open_connection(
                    server['econ_address'],
                    server['econ_port'],
                )
                writer.write(f'{server["econ_password"]}\n'.encode('utf-8'))
                content = message.clean_content[:100]
                content.replace('\n', ' ')
                author = message.author.name[:30]
                author.replace('\n', ' ')
                writer.write(
                    f'say Discord: {author}: {content}\n'.encode('utf-8')
                )
                await writer.drain()
                writer.close()


def main():
    parser = ArgumentParser(description='Teeworld to/from Discord chat bridge')
    parser.add_argument(
        '-c', '--config', required=True,
        type=str, action='store', dest='config',
        help='configuration file path',
    )
    args = parser.parse_args()
    with open(args.config, mode='r') as f:
        config = yaml.safe_load(f)
    client = TeeworldsDiscordBridge(config)
    client.run(config['discord_token'])
