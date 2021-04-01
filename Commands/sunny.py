import discord
import os, random
from discord.ext import commands

class People(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.command(name="sunny", aliases = ["sexy"])
    async def _sunny(self, ctx):
        f = discord.File('./resources/' + random.choice(os.listdir('./resources')))
        await ctx.send(f"Invoked by {ctx.message.author.name}",file=f)

def setup(client):
    client.add_cog(People(client))