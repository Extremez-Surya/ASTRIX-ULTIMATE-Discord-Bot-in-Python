import discord

from discord.ext import commands

class _ticket(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

    """Ticket"""

    def help_custom(self):

              emoji = '🎫'

              label = "Ticket"

              description = "Support ticket system and transcripts"

              return emoji, label, description

    @commands.group()

    async def __Ticket__(self, ctx: commands.Context):

        """`/ticket-panel`"""