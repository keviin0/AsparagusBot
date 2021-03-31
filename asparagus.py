import sys
import os
import logging
import typing
import importlib

import discord
from discord.ext import commands 

env = importlib.__import__("Config.env_" + sys.argv[1], fromlist=("env_" + sys.argv[1]))

intents = discord.Intents.default()
intents.members = True
intents.typing = False
intents.presences = False
intents.messages = True
intents.guilds = True

client = commands.Bot(command_prefix=env.bot_prefix, intents=intents)
client.remove_command('help')


@client.command(aliases=["quit"])
@commands.has_permissions(administrator=True)
async def _close(ctx):
    await client.close()

async def on_error(self):
    raise


for filename in os.listdir('./Commands'):
    if filename.endswith('.py'):
        client.load_extension(f'Commands.{filename[:-3]}')

'''
for filename in os.listdir('./Events'):
    if filename.endswith('.py'):
        client.load_extension(f'Events.{filename[:-3]}')

for filename in os.listdir('./Tasks'):
    if filename.endswith('.py'):
        client.load_extension(f'Tasks.{filename[:-3]}')
'''

@client.event
async def on_ready():
    #print(client.__dict__)
    print("Logged on as " + client.user.name + " #" + client.user.discriminator)

client.run(env.token)
