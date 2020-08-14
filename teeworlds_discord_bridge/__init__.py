import re
import sys
from argparse import ArgumentParser
from asyncio import (
    sleep,
    open_connection,
    Event,
)

import discord
from ruamel import yaml


CHAT_PATTERN = re.compile(r'^\[\S+\]\[chat\]: \d+:\d+:(.+?): (.*)$')


class TeeworldsECON:

    def __init__(self, host, port, password):
        self.host = host
        self.port = port
        self.password = password
        self.reader = None
        self.writer = None
        self.connected = Event()
        self.waiting = Event()
        self.waiting.set()

    async def connect(self):
        while True:
            if self.writer is not None:
                self.writer.close()
                await self.writer.wait_closed()
                self.writer = None
                self.reader = None
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
                if not 'Authentication successful' \
                        in line.decode('utf-8'):
                    print(f'Failed to authenticate to {self.host}:{self.port}')
                    await sleep(10)
                    continue
                break
            except Exception as e:
                print(f'Failed to connect to {self.host}:{self.port}: {e!s}')
                await sleep(5)
        self.connected.set()

    async def say(self, message):
        await self.connected.wait()
        await self.waiting.wait()
        self.waiting.clear()
        message = message[:120]
        # Prevent command injection
        message.replace('\n', ' ')
        try:
            self.writer.write(f'say {message}\n'.encode())
            await self.writer.drain()
        except Exception as e:
            print(f'Failed to send command to {self.host}:{self.port}')
            self.connected.clear()
            await self.connect()
        finally:
            self.waiting.set()

    async def readline(self):
        # It's not safe to call this method, before previous call returns
        await self.connected.wait()
        while True:
            try:
                return (await self.reader.readline()).decode('utf-8')\
                    .replace('\0', '').rstrip()
            except Exception as e:
                print(f'Failed to read line from {self.host}:{self.port}')
                self.connected.clear()
                await self.connect()


class TeeworldsDiscordBridge(discord.Client):

    def __init__(self, config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config
        self.connections = {}
        for server_id, discord_server in self.config['discord_servers'].items():
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
        await econ.connect()
        while True:
            line = await econ.readline()
            match = re.match(CHAT_PATTERN, line)
            if not match:
                continue
            name = match.group(1)
            message = match.group(2)
            await self.get_channel(channel_id).send(
                f'[chat] {name}: {message}'
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
