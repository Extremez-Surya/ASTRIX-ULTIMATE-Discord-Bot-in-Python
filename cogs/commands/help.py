import discord
from discord.ext import commands
from discord import app_commands, Interaction, ui
from difflib import get_close_matches
from contextlib import suppress
from core import Context
from core.axon import axon
from core.Cog import Cog
from utils.Tools import getConfig
from itertools import chain
import json
from utils import help as vhelp
from utils import Paginator, DescriptionEmbedPaginator, FieldPagePaginator, TextPaginator
import asyncio
from utils.config import serverLink
from utils.Tools import *

color = 0x185fe5
client = axon()

class HelpCommand(commands.HelpCommand):

  async def send_ignore_message(self, ctx, ignore_type: str):

    if ignore_type == "channel":
      await ctx.reply(f"This channel is ignored.", mention_author=False)
    elif ignore_type == "command":
      await ctx.reply(f"{ctx.author.mention} This Command, Channel, or You have been ignored here.", delete_after=6)
    elif ignore_type == "user":
      await ctx.reply(f"You are ignored.", mention_author=False)

  async def on_help_command_error(self, ctx, error):
    errors = [
      commands.CommandOnCooldown, commands.CommandNotFound,
      discord.HTTPException, commands.CommandInvokeError
    ]
    if not type(error) in errors:
      await self.context.reply(f"Unknown Error Occurred\n{error.original}",
                               mention_author=False)
    else:
      if type(error) == commands.CommandOnCooldown:
        return

    return await super().on_help_command_error(ctx, error)

  async def command_not_found(self, string: str) -> None:
    ctx = self.context
    check_ignore = await ignore_check().predicate(ctx)
    check_blacklist = await blacklist_check().predicate(ctx)

    if not check_blacklist or not check_ignore:
      return

    cmds = [str(cmd) for cmd in self.context.bot.walk_commands()]
    matches = get_close_matches(string, cmds, n=3)

    data = await getConfig(self.context.guild.id)
    prefix = data["prefix"]

    content = f"### ⚠️ Command Not Found\nNo command named `{string}` was found."
    if matches:
      match_str = ", ".join(f"`{prefix}{m}`" for m in matches)
      content += f"\n\n**Did you mean:** {match_str}"
    content += f"\n\n*Use `{prefix}help` to view all available commands.*"

    view = ui.LayoutView(timeout=60)
    container = ui.Container(
      ui.TextDisplay(content)
    )
    view.add_item(container)
    await ctx.reply(view=view, mention_author=False)

  async def send_bot_help(self, mapping):
    ctx = self.context
    check_ignore = await ignore_check().predicate(ctx)
    check_blacklist = await blacklist_check().predicate(ctx)

    if not check_blacklist or not check_ignore:
      return

    data = await getConfig(self.context.guild.id)
    prefix = data["prefix"]

    view = vhelp.HelpContainerView(mapping=mapping, ctx=self.context, prefix=prefix)
    await ctx.reply(view=view, mention_author=False)

  async def send_command_help(self, command):
    ctx = self.context
    check_ignore = await ignore_check().predicate(ctx)
    check_blacklist = await blacklist_check().predicate(ctx)

    if not check_blacklist or not check_ignore:
      return

    data = await getConfig(self.context.guild.id)
    prefix = data["prefix"]
    alias = ", ".join(f"`{a}`" for a in command.aliases) if command.aliases else "None"
    help_text = command.help or "No description provided."

    content = (
      f"### 📖 Command: `{command.qualified_name}`\n"
      f"*{help_text}*\n"
    )

    view = ui.LayoutView(timeout=120)
    container = ui.Container(
      ui.TextDisplay(content),
      ui.Separator(),
      ui.TextDisplay(
        f"• **Usage:** `{prefix}{command.qualified_name} {command.signature}`\n"
        f"• **Aliases:** {alias}"
      ),
      ui.Separator(),
      ui.TextDisplay("*Astrix • Developed by Vinay Kumar (ASTRIXCODE)*")
    )
    view.add_item(container)
    await self.context.reply(view=view, mention_author=False)

  def get_command_signature(self, command: commands.Command) -> str:
    parent = command.full_parent_name
    if len(command.aliases) > 0:
      aliases = ' | '.join(command.aliases)
      fmt = f'[{command.name} | {aliases}]'
      if parent:
        fmt = f'{parent}'
      alias = f'[{command.name} | {aliases}]'
    else:
      alias = command.name if not parent else f'{parent} {command.name}'
    return f'{alias} {command.signature}'

  def common_command_formatting(self, embed_like, command):
    embed_like.title = self.get_command_signature(command)
    if command.description:
      embed_like.description = f'{command.description}\n\n{command.help}'
    else:
      embed_like.description = command.help or 'No help found...'

  async def send_group_help(self, group):
    ctx = self.context
    check_ignore = await ignore_check().predicate(ctx)
    check_blacklist = await blacklist_check().predicate(ctx)

    if not check_blacklist or not check_ignore:
      return

    data = await getConfig(self.context.guild.id)
    prefix = data["prefix"]

    subcmds = []
    for cmd in group.commands:
      doc = cmd.short_doc or "No description"
      if len(doc) > 55:
        doc = doc[:52] + "..."
      subcmds.append(f"• `{prefix}{cmd.qualified_name}` — {doc}")

    content = f"### 📂 Group: `{group.qualified_name}` ({len(group.commands)})\n"
    if group.help:
      content += f"*{group.help}*\n"

    view = ui.LayoutView(timeout=120)
    container = ui.Container(
      ui.TextDisplay(content),
      ui.Separator(),
      ui.TextDisplay("\n".join(subcmds) if subcmds else "*No subcommands available.*"),
      ui.Separator(),
      ui.TextDisplay("*Astrix • Developed by Vinay Kumar (ASTRIXCODE)*")
    )
    view.add_item(container)
    await self.context.reply(view=view, mention_author=False)

  async def send_cog_help(self, cog):
    ctx = self.context
    check_ignore = await ignore_check().predicate(ctx)
    check_blacklist = await blacklist_check().predicate(ctx)

    if not check_blacklist or not check_ignore:
      return

    data = await getConfig(self.context.guild.id)
    prefix = data["prefix"]

    cmds = []
    for cmd in cog.get_commands():
      doc = cmd.short_doc or "No description"
      if len(doc) > 55:
        doc = doc[:52] + "..."
      cmds.append(f"• `{prefix}{cmd.qualified_name}` — {doc}")

    view = ui.LayoutView(timeout=120)
    container = ui.Container(
      ui.TextDisplay(f"### 📦 Module: `{cog.qualified_name}` ({len(cog.get_commands())})"),
      ui.Separator(),
      ui.TextDisplay("\n".join(cmds) if cmds else "*No commands available in this module.*"),
      ui.Separator(),
      ui.TextDisplay("*Astrix • Developed by Vinay Kumar (ASTRIXCODE)*")
    )
    view.add_item(container)
    await self.context.reply(view=view, mention_author=False)


class Help(Cog, name="help"):

  def __init__(self, client: axon):
    self._original_help_command = client.help_command
    attributes = {
      'name': "help",
      'aliases': ['h'],
      'cooldown': commands.CooldownMapping.from_cooldown(1, 5, commands.BucketType.user),
      'help': 'Shows help about bot, a command, or a category'
    }
    client.help_command = HelpCommand(command_attrs=attributes)
    client.help_command.cog = self

  async def cog_unload(self):
    self.help_command = self._original_help_command
