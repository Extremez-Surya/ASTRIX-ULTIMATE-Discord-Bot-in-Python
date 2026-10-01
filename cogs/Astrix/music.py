import discord
from discord.ext import commands


class _music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    """Music commands"""

    def help_custom(self):
        emoji = '🎵'
        label = "Music"
        description = "Play, pause, skip, queue, loop & audio filters"
        return emoji, label, description

    @commands.group()
    async def __Music__(self, ctx: commands.Context):
        """`play` , `search` , `loop` , `autoplay` , `nowplaying` , `shuffle` , `stop` , `skip` , `seek` , `join` , `disconnect` , `replay` , `queue` , `clearqueue` , `pause` , `resume` , `volume` , `filter` , `filter enable` , `filter disable`"""