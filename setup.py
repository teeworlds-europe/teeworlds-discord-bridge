from setuptools import setup

setup(
    name='teeworlds-discord-bridge',
    author='Jakub Pieńkowski',
    author_email='jakub@jakski.name',
    url='https://github.com/Jakski/teeworlds-discord-bridge',
    license='MIT',
    version='0.0.1',
    description='Chat bridge between Teeworlds and Discord',
    install_requires=[
        'discord.py',
        'ruamel.yaml',
    ],
    entry_points={
        'console_scripts': [
            'teeworlds-discord-bridge=teeworlds_discord_bridge:main',
        ],
    },
)
