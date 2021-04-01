
import typing as t
import discord
import wavelink
import datetime as dt
import asyncio
import random
import re
from enum import Enum
from discord.ext import commands


tfs = None #twenty-four seven boolean
URL_REGEX = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
OPTIONS = {
    "1️⃣": 0,
    "2⃣": 1,
    "3⃣": 2,
    "4⃣": 3,
    "5⃣": 4,
}

#Error Handling
class AlrConnectedToChannel(commands.CommandError):
    pass

class NoVoiceChannel(commands.CommandError):
    pass

class QueueIsEmpty(commands.CommandError):
    pass

class NoTracksFound(commands.CommandError):
    pass

class PlayerAlrPaused(commands.CommandError):
    pass

class PlayerAlrPlaying(commands.CommandError):
    pass

class NoMoreTracks(commands.CommandError):
    pass

class NoPreviousTracks(commands.CommandError):
    pass

class InvalidRepeatMode(commands.CommandError):
    pass

#Repeat functionality
class RepeatMode(Enum):
    NONE = 0
    ONE = 1
    ALL = 2


#Getters/Setters
class Queue:
    def __init__(self):
        print("queue object made")
        self._queue = []
        self.position = 0
        self.repeat_mode = RepeatMode.NONE

    def add(self, *args):
        self._queue.extend(args)
    
    @property
    def is_empty(self):
        return not self._queue
        
    @property
    def current_track(self):
        if not self._queue: 
            raise QueueIsEmpty

        if self.position <= len(self._queue) - 1:
            return self._queue[self.position]

    @property
    def upcoming(self):
        if not self._queue:
            raise QueueIsEmpty
        else:
            return self._queue[self.position + 1:]

    @property
    def history(self):
        if not self._queue:
            raise QueueIsEmpty
        else:
            return self._queue[:self.position]
            
    @property
    def length(self):
        return len(self._queue)

    def get_next_track(self):
        if not self._queue:
            raise QueueIsEmpty
        
        self.position += 1
        #print(len(self._queue)) debug statement

        if self.position < 0:
            return None
        elif self.position > len(self._queue) - 1:
            if self.repeat_mode == RepeatMode.ALL:
                self.position = 0
            else:
                return None

        return self._queue[self.position]

    def shuffle(self):
        if not self._queue:
            raise QueueIsEmpty

        upcoming = self.upcoming
        random.shuffle(upcoming)
        self._queue = self._queue[:self.position + 1]
        self._queue.extend(upcoming)

    def set_repeat_mode(self, mode):
        if mode == "none":
            self.repeat_mode = RepeatMode.NONE
        if mode == "1" or mode == "one":
            self.repeat_mode = RepeatMode.ONE
        if mode == "all":
            self.repeat_mode = RepeatMode.ALL

    def empty_queue(self):
        self._queue.clear()


#Player object with command definitions
class Player(wavelink.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args,**kwargs)
        self.queue = Queue()

    async def connect(self, ctx, channel=None):
        if self.is_connected:
            raise AlrConnectedToChannel
        
        if (channel := getattr(ctx.author.voice, "channel", channel)) is None:
            raise NoVoiceChannel

        await super().connect(channel.id)
        return channel
    
    async def teardown(self):
        try:
            await self.destroy()
        except KeyError:
            pass
    
    async def add_tracks(self, ctx, tracks):

        if not tracks:
            raise NoTracksFound
        
        if isinstance(tracks, wavelink.TrackPlaylist):
            self.queue.add(*tracks.tracks)
        elif len(tracks) == 1:
            self.queue.add(tracks[0])
            await ctx.send(f"Added {tracks[0].title} to the queue")
        else:
            if(track := await self.choose_track(ctx, tracks)) is not None:
                self.queue.add(track)
                await ctx.send(f"Added {track.title} to the queue")

        if not self.is_playing and not self.queue.is_empty:
            await self.start_playback()

    async def choose_track(self, ctx, tracks):
        def _check(r, u):
            return (
                r.emoji in OPTIONS.keys() # r is reaction, u is user who reacted
                and u == ctx.author
                and r.message.id == msg.id
            )
        
        embed = discord.Embed(
            title="Choose a song",
            description=(
                "\n".join(
                    f"**{i+1}. ** {t.title} ({t.length//60000}:{str(t.length%60).zfill(2)})"
                    for i, t in enumerate(tracks[:5])
                )
            ),
            colour=ctx.author.colour,
            timestamp=dt.datetime.utcnow()
        )
        embed.set_author(name="Query Results")
        embed.set_footer(text=f"Invoked by {ctx.author.display_name}", icon_url=ctx.author.avatar_url)

        msg = await ctx.send(embed=embed)
        for emoji in list(OPTIONS.keys())[:min(len(tracks), len(OPTIONS))]:
            await msg.add_reaction(emoji)
        try:
            reaction, _ = await self.bot.wait_for("reaction_add", timeout=60, check=_check)
        except asyncio.TimeoutError:
            await msg.delete()
            await ctx.message.delete()
        else:
            await msg.delete()
            return tracks[OPTIONS[reaction.emoji]]


    async def start_playback(self):
        await self.play(self.queue.current_track)

    async def advance(self):
        try:
            if (track := self.queue.get_next_track()) is not None:
                await self.play(track)
        except QueueIsEmpty:
            pass

    async def repeat_track(self):
        await self.play(self.queue.current_track)


class Music(commands.Cog, wavelink.WavelinkMixin):
    def __init__(self, bot):
        self.bot = bot
        self.wavelink = wavelink.Client(bot=bot)
        self.bot.loop.create_task(self.start_nodes())

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.bot and after.channel is None:
            if not [m for m in before.channel.members if not m.bot]:
                await self.get_player(member.guild).teardown()

    @wavelink.WavelinkMixin.listener()
    async def on_node_ready(self, node):
        print(f"Wavelink node `{node.identifier}` ready.")

    @wavelink.WavelinkMixin.listener("on_track_stuck")
    @wavelink.WavelinkMixin.listener("on_track_end")
    @wavelink.WavelinkMixin.listener("on_track_exception")
    async def on_player_stop(self, node, payload):
        if payload.player.queue.repeat_mode == RepeatMode.ONE:
            await payload.player.repeat_track()
        else:
            await payload.player.advance()

    async def cog_check(self, ctx):
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("Music commands are not available in DMs")
            return False
        
        
        return True

    async def start_nodes(self):
        await self.bot.wait_until_ready()

        nodes = {
            "MAIN": {
                "host": "127.0.0.1",
                "port": 2333,
                "rest_uri": "http://127.0.0.1:2333",
                "password": "youshallnotpass",
                "identifier": "Main",
                "region": "us_west"
            }
        }

        for node in nodes.values():
            await self.wavelink.initiate_node(**node)

    def get_player(self, obj):
        if isinstance(obj, commands.Context):
            return self.wavelink.get_player(obj.guild.id, cls=Player, context=obj)
        elif isinstance(obj, discord.Guild):
            return self.wavelink.get_player(obj.id, cls=Player)

    @commands.command(name="connect", aliases=['join'])
    async def _connect(self, ctx, *, channel: t.Optional[discord.VoiceChannel]):
        player = self.get_player(ctx)
        channel = await player.connect(ctx, channel)
        await ctx.send(f"Connected to {channel.name}")

    @_connect.error
    async def conn_error(self, ctx, exc):
        if isinstance(exc, AlrConnectedToChannel):
            await ctx.send("Already connected to a voice channel")
        elif isinstance(exc, NoVoiceChannel):
            await ctx.send("No suitable VC found or provided")

    @commands.command(name="disconnect", aliases=["leave"])
    async def _disconnect(self, ctx):
        player = self.get_player(ctx)
        await player.disconnect()
        await ctx.send("Disconnected")

    @commands.command(name="play", aliases=["p"])
    async def _play(self, ctx, *, query: t.Optional[str]):
        player = self.get_player(ctx)

        if ctx.message.author.id == 330375924325416961:
            return

        if not player.is_connected:
            await player.connect(ctx)

        if query is None:
            if player.is_playing:
                raise PlayerAlrPlaying
            elif player.queue.is_empty:
                raise QueueIsEmpty

            await player.set_pause(False)
            await ctx.send("Resumed")

        else: 
            query = query.strip("<>")
            print("query is " + query)
            if not re.match(URL_REGEX, query):
                query = f"ytsearch:{query}"
            
            await player.add_tracks(ctx, await self.wavelink.get_tracks(query))

    @_play.error
    async def _play_error(self, ctx, exc):
        if isinstance(exc, NoVoiceChannel):
            await ctx.send("No suitable VC found or provided")
        elif isinstance(exc, QueueIsEmpty):
            await ctx.send("No songs to play as the queue is empty")


    @commands.command(name="queue", aliases=["q"])
    async def _queue(self, ctx, show: t.Optional[int] = 10):
        player = self.get_player(ctx)
        
        if player.queue.is_empty:
            raise QueueIsEmpty

        embed = discord.Embed(
            title = "Queue",
            description = f"Showing up to {show} tracks",
            colour = ctx.author.colour,
            timestamp=dt.datetime.utcnow()
        )
        embed.set_author(name="Query Results")
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.avatar_url)
        embed.add_field(
            name="Currently playing", 
            value = getattr(player.queue.current_track, "title", "No tracks currently playing"), 
            inline=False
        )
        if upcoming := player.queue.upcoming:
            embed.add_field(
                name="Next up",
                value="\n".join(t.title for t in player.queue.upcoming[:show])
            )
        msg = await ctx.send(embed=embed)

    @_queue.error
    async def _queue_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
            await ctx.send("The queue is currently empty")

    @commands.command(name="pause")
    async def _pause(self, ctx):
        player = self.get_player(ctx)

        if player.is_paused:
            raise PlayerAlrPaused
        
        await player.set_pause(True)
        await ctx.send("Paused")

    @_pause.error
    async def _pause_error(self, ctx, exc):
        if isinstance(exc, PlayerAlrPaused):
            await ctx.send("Already paused")

    @commands.command(name="resume", aliases = ["continue"])
    async def _resume(self, ctx):
        player = self.get_player(ctx)

        if not player.is_paused:
            raise PlayerAlrPlaying
        
        await player.set_pause(False)
        await ctx.send("Resumed")
        
    @_resume.error
    async def _resume_error(self, ctx, exc):
        if isinstance(exc, PlayerAlrPlaying):
            await ctx.send("Already playing")
    
    @commands.command(name="stop", aliases = ["s"])
    async def _stop(self, ctx):
        player = self.get_player(ctx)
        player.queue.empty_queue()
        await player.stop()
        await ctx.send("Playback stopped")

    @commands.command(name="next", aliases = ["skip"])
    async def _next(self, ctx):
        player = self.get_player(ctx)
        
        if not player.queue.upcoming:
            raise NoMoreTracks

        await player.stop()
        await ctx.send("Skipped current track")
    
    @_next.error
    async def _next_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
            await ctx.send("Queue is currently empty so track could not be skipped")
        elif isinstance(exc, NoMoreTracks):
            await ctx.send("There are no more tracks in the queue")
            
    @commands.command(name="previous", aliases = ["back"])
    async def _previous(self, ctx):
        player = self.get_player(ctx)
        
        if not player.queue.history:
            raise NoPreviousTracks

        player.queue.position -= 2
        await player.stop()
        await ctx.send("Playing previous track")

    @_previous.error
    async def _previous_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
            await ctx.send("Queue is a empty so track could not be skipped")
        elif isinstance(exc, NoPreviousTracks):
            await ctx.send("There are no more tracks in the queue")

    @commands.command(name="shuffle")
    async def _shuffle(self, ctx):
        player = self.get_player(ctx)
        player.queue.shuffle()
        await ctx.send("Queue shuffled")
    
    @_shuffle.error
    async def _shuffle_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
            await ctx.send("Could not shuffle as there are no tracks in queue")

    @commands.command(name="loop", aliases = ["repeat"])
    async def _loop(self, ctx, mode: t.Optional[str]):
        if mode.lower() not in ("none", "1", "all", "one"):
            raise InvalidRepeatMode
        
        if not mode:
            player.queue.set_repeat_mode("all")
        await ctx.send(f"The repeat mode has been set to all")
        
        player = self.get_player(ctx)
        player.queue.set_repeat_mode(mode.lower())
        await ctx.send(f"The repeat mode has been set to {mode}")
    
    @commands.command(name="debug")
    async def _debug(self, ctx):
        player = self.get_player(ctx)
        await ctx.send(f"The position is {player.position}")
                
    


def setup(client):
    client.add_cog(Music(client))
        