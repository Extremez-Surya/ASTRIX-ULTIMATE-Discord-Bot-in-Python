import discord
from discord.ext import commands


class _fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    """Fun commands"""
  
    def help_custom(self):
        emoji = '🎉'
        label = "Fun & AI"
        description = "Fun, games, AI commands & social interactions"
        return emoji, label, description

    @commands.group()
    async def __Fun__(self, ctx: commands.Context):
        """`/imagine` , `ship` , `mydog` , `chat` , `translate` , `howgay` , `lesbian` , `cute` , `intelligence`, `chutiya` , `horny` , `tharki` , `gif` , `iplookup` , `weather` , `hug` , `kiss` , `pat` , `cuddle` , `slap` , `tickle` , `spank` ,  `8ball` , `truth` , `dare`"""