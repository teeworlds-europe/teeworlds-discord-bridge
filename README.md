# teeworlds-discord-bridge

Bridge chat messages between Teeworlds and Discord. See `config.yml` for example
configuration.

Inspired by [teeworlds-discord-bot](https://github.com/pure-luck-999/teeworlds-discord-bot)

## Features

- Mapping Discord channels to Teeworlds servers
- Automatically reconnecting to external console
- Optionally sending notifications about joins and leaves

## Bugs

- Script doesn't terminate properly. It needs to be shutted down with SIGKILL.
