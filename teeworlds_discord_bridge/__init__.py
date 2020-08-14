import re
import functools
from argparse import ArgumentParser
from asyncio import (
    sleep,
    open_connection,
    Lock,
)

import discord
from ruamel import yaml


CHAT_PATTERN = re.compile(
    r'^\[\S+\]\[chat\]: \d+:\d+:(.+?): (.*)$'
)
JOIN_PATTERN = re.compile(
    r'^\[\S+\]\[game\]: team_join player=\'(.+?)\''
)
LEAVE_PATTERN = re.compile(
    r'^\[\S+\]\[game\]: leave player=\'(.+?)\''
)


def acquire(*modes):
    def outer(f):
        @functools.wraps(f)
        async def inner(self, *args, **kwargs):
            for mode in modes:
                await getattr(self, f'{mode}_lock').acquire()
            try:
                return await f(self, *args, **kwargs)
            finally:
                for mode in modes:
                    getattr(self, f'{mode}_lock').release()
        return inner
    return outer


class TeeworldsECON:

    def __init__(self, host, port, password):
        self.host = host
        self.port = port
        self.password = password
        self.reader = None
        self.writer = None
        self.read_lock = Lock()
        self.write_lock = Lock()

    @acquire('write', 'read')
    async def connect(self):
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()
        try:
            self.reader, self.writer = await open_connection(
                self.host, self.port,
            )
            print(f'Connected to {self.host}:{self.port}')
            self.writer.write(f'{self.password}\n'.encode())
            await self.writer.drain()
            # Skip password prompt
            await self.reader.readline()
            line = await self.reader.readline()
            if 'Authentication successful' \
                    not in line.decode('utf-8'):
                raise Exception(
                    f'Failed to authenticate to {self.host}:{self.port}'
                )
        except Exception as e:
            print(f'Failed to connect to {self.host}:{self.port}')
            raise e

    async def disconnect(self):
        if self.writer is not None:
            self.writer.close()
            return await self.writer.wait_closed()

    def is_closing(self):
        if self.writer is None:
            return True
        else:
            return self.writer.is_closing()

    @acquire('write')
    async def say(self, message):
        message = message[:120]
        # Prevent command injection
        message.replace('\n', ' ')
        self.writer.write(f'say {message}\n'.encode())
        await self.writer.drain()

    @acquire('read')
    async def readline(self):
        r = (await self.reader.readline()).decode('utf-8')
        if r == '':
            self.writer.close()
            raise Exception(
                f'Connection to {self.host}:{self.port} has been closed'
            )
        else:
            return r.replace('\0', '').rstrip()


class TeeworldsDiscordBridge(discord.Client):

    def __init__(self, config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config
        self.connections = {}
        for server_id, discord_server \
                in self.config['discord_servers'].items():
            for channel_id, settings \
                    in discord_server['teeworlds_servers'].items():
                self.loop.create_task(
                    self.watch_econ(server_id, channel_id, settings)
                )

    async def on_ready(self):
        print(f'Logged in successfully as {self.user}')

    async def watch_econ(self, server_id, channel_id, settings):
        await self.wait_until_ready()
        econ = TeeworldsECON(
            settings['econ_host'],
            settings['econ_port'],
            settings['econ_password'],
        )
        self.connections[(server_id, channel_id)] = econ
        while not self.is_closed():
            if econ.is_closing():
                try:
                    await econ.connect()
                except:  # noqa: E722
                    await sleep(5)
                    continue
            try:
                line = await econ.readline()
            except:  # noqa: E722
                continue
            match = re.match(CHAT_PATTERN, line)
            if match:
                name = match.group(1)
                if name in settings.get('blacklist', []):
                    continue
                message = match.group(2)
                await self.get_channel(channel_id).send(
                    f'[chat] {name}: {message}'
                )
                continue
            match = re.match(JOIN_PATTERN, line)
            if match and settings.get('show_joins') is True:
                name = match.group(1)
                await self.get_channel(channel_id).send(
                    f'[game] {name} joined the game'
                )
            match = re.match(LEAVE_PATTERN, line)
            if match and settings.get('show_leaves') is True:
                name = match.group(1).split(':')[1:]
                await self.get_channel(channel_id).send(
                    f'[game] {name} left the game'
                )

    async def on_message(self, message):
        server_id = message.channel.guild.id
        settings = self.config['discord_servers'].get(server_id)
        if settings is None or self.user.id == message.author.id:
            return
        for channel_id, server in settings['teeworlds_servers'].items():
            if message.channel.id == channel_id:
                await self.connections[(server_id, channel_id)].say(
                    f'Discord: {message.author.name}: {message.clean_content}'
                )
                break


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
