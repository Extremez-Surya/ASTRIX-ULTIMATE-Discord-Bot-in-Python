import os
import sys
import asyncio

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import traceback
from threading import Thread
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands

from core import Context, Cog, Astrix
from utils.Tools import *
from utils.config import *

import jishaku
import cogs

os.environ["JISHAKU_NO_DM_TRACEBACK"] = "False"
os.environ["JISHAKU_HIDE"] = "True"
os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
os.environ["JISHAKU_FORCE_PAGINATOR"] = "True"

from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv("TOKEN")

client = Astrix()
tree = client.tree

@client.event
async def on_ready():
    await client.wait_until_ready()
    
    try:
        print("""
           \033[1;36m
    _   ___ _____ ___ _____  __
   /\\ / __|_   _| _ \\_ _\\ \\/ /
  / _ \\\\__ \\ | | |   /| | >  < 
 /_/ \\_\\___/ |_| |_|_\\___/_/\\_\\
           \033[0m
           """)
    except Exception:
        print("\n=== ASTRIX BOT ===\n")
    print("Loaded & Online!")
    print(f"Logged in as: {client.user}")
    print(f"Connected to: {len(client.guilds)} guilds")
    print(f"Connected to: {len(client.users)} users")
    try:
        synced = await client.tree.sync()
        all_commands = list(client.commands)
        print(f"Synced Total {len(all_commands)} Client Commands and {len(synced)} Slash Commands")
    except Exception as e:
        print(e)

@client.event
async def on_command_completion(context: commands.Context) -> None:
    if context.author.id == 767979794411028491:
        return

    webhook_url = os.getenv("COMMAND_LOG_WEBHOOK")
    if not webhook_url or not webhook_url.strip():
        return

    full_command_name = context.command.qualified_name
    split = full_command_name.split("\n")
    executed_command = str(split[0])
    try:
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(webhook_url, session=session)

            if context.guild is not None:
                embed = discord.Embed(color=0x000000)
                avatar_url = context.author.avatar.url if context.author.avatar else context.author.default_avatar.url
                embed.set_author(
                    name=f"Executed {executed_command} Command By : {context.author}",
                    icon_url=avatar_url
                )
                embed.set_thumbnail(url=avatar_url)
                embed.add_field(name=" Command Name :",
                                value=f"{executed_command}",
                                inline=False)
                embed.add_field(
                    name=" Command Executed By :",
                    value=f"{context.author} | ID: [{context.author.id}](https://discord.com/users/{context.author.id})",
                    inline=False)
                embed.add_field(
                    name=" Command Executed In :",
                    value=f"{context.guild.name} | ID: [{context.guild.id}](https://discord.com/guilds/{context.guild.id})",
                    inline=False)
                embed.add_field(
                    name=" Command Executed In Channel :",
                    value=f"{context.channel.name} | ID: [{context.channel.id}](https://discord.com/channels/{context.guild.id}/{context.channel.id})",
                    inline=False)

                embed.timestamp = discord.utils.utcnow()
                embed.set_footer(text="Astrix • ASTRIXCODE by Vinay Kumar",
                                 icon_url=client.user.display_avatar.url)
                await webhook.send(embed=embed)
            else:
                embed1 = discord.Embed(color=0x000000)
                avatar_url = context.author.avatar.url if context.author.avatar else context.author.default_avatar.url
                embed1.set_author(
                    name=f"Executed {executed_command} Command By : {context.author}",
                    icon_url=avatar_url
                )
                embed1.set_thumbnail(url=avatar_url)
                embed1.add_field(name=" Command Name :",
                                 value=f"{executed_command}",
                                 inline=False)
                embed1.add_field(
                    name=" Command Executed By :",
                    value=f"{context.author} | ID: [{context.author.id}](https://discord.com/users/{context.author.id})",
                    inline=False)
                embed1.set_footer(text="Astrix • ASTRIXCODE by Vinay Kumar",
                                  icon_url=client.user.display_avatar.url)
                await webhook.send(embed=embed1)
    except discord.errors.NotFound:
        pass
    except Exception as e:
        print(f'Webhook log notice: {e}')

from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Astrix Development™ 2026"

def run():
    try:
        app.run(host='0.0.0.0', port=8080)
    except Exception as e:
        print(f"Web server notice: {e}")

def keep_alive():
    server = Thread(target=run, daemon=True)
    server.start()

keep_alive()

async def main():
    if not TOKEN:
        print("ERROR: TOKEN is missing in .env file! Please set TOKEN in .env.")
        return
    async with client:
        if os.name == "nt":
            os.system("cls")
        else:
            os.system("clear")
        await client.load_extension("jishaku")
        await client.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
