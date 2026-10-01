import discord
import psutil
import sys
import os
import time
import aiosqlite
import platform
import datetime
from discord import ui
from discord.ext import commands
from utils.Tools import *
import wavelink


class StatsContainerView(ui.LayoutView):
    def __init__(self, cog, ctx):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.active_tab = "general"
        self.render_tab("general")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ Only the command author can interact with this.", ephemeral=True)
            return False
        return True

    def _get_buttons(self, active: str):
        b_gen = ui.Button(
            label="General",
            emoji="📊",
            style=discord.ButtonStyle.primary if active == "general" else discord.ButtonStyle.secondary
        )
        b_sys = ui.Button(
            label="System",
            emoji="⚙️",
            style=discord.ButtonStyle.primary if active == "system" else discord.ButtonStyle.secondary
        )
        b_ping = ui.Button(
            label="Ping",
            emoji="🏓",
            style=discord.ButtonStyle.primary if active == "ping" else discord.ButtonStyle.secondary
        )
        b_close = ui.Button(label="Close", emoji="🗑️", style=discord.ButtonStyle.danger)

        async def cb_gen(interaction: discord.Interaction):
            self.render_tab("general")
            await interaction.response.edit_message(view=self)

        async def cb_sys(interaction: discord.Interaction):
            self.render_tab("system")
            await interaction.response.edit_message(view=self)

        async def cb_ping(interaction: discord.Interaction):
            await self.render_ping_tab(interaction)

        async def cb_close(interaction: discord.Interaction):
            try:
                await interaction.message.delete()
            except Exception:
                pass

        b_gen.callback = cb_gen
        b_sys.callback = cb_sys
        b_ping.callback = cb_ping
        b_close.callback = cb_close

        return ui.ActionRow(b_gen, b_sys, b_ping, b_close)

    def render_tab(self, tab: str):
        self.clear_items()
        self.active_tab = tab

        if tab == "general":
            guild_count = len(self.cog.bot.guilds)
            user_count = sum(g.member_count for g in self.cog.bot.guilds if g.member_count is not None)
            commands_count = len(set(self.cog.bot.walk_commands()))
            slash_count = len([cmd for cmd in self.cog.bot.tree.get_commands()])

            uptime_seconds = int(round(time.time() - self.cog.start_time))
            up_td = datetime.timedelta(seconds=uptime_seconds)
            uptime_str = f"{up_td.days}d {up_td.seconds // 3600}h {(up_td.seconds // 60) % 60}m {up_td.seconds % 60}s"

            connected_vcs = sum(1 for vc in self.cog.bot.voice_clients if vc)
            playing_tracks = sum(1 for vc in self.cog.bot.voice_clients if vc.playing)

            header = (
                "### 👑 Astrix — General Stats\n"
                f"> **Servers:** `{guild_count:,}` • **Users:** `{user_count:,}` • **Prefix:** `>`"
            )

            body = (
                f"• **Uptime:** `{uptime_str}`\n"
                f"• **Commands:** `{commands_count}` (Slash: `{slash_count}`)\n"
                f"• **Music:** `{playing_tracks}` tracks playing across `{connected_vcs}` VCs\n"
                f"• **Total Streams:** `{self.cog.total_songs_played:,}` songs played"
            )

            footer = "*Astrix • Made by Vinay Kumar (ASTRIXCODE)*"

            container = ui.Container(
                ui.TextDisplay(header),
                ui.Separator(),
                ui.TextDisplay(body),
                ui.Separator(),
                ui.TextDisplay(footer),
                self._get_buttons("general")
            )
            self.add_item(container)

        elif tab == "system":
            mem = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent()
            cpu_cores = psutil.cpu_count(logical=False) or psutil.cpu_count()

            header = (
                "### ⚙️ Astrix — System Information\n"
                f"> **OS:** `{platform.system()} {platform.release()}` ({platform.machine()})"
            )

            body = (
                f"• **Python:** `{platform.python_version()}` | **discord.py:** `{discord.__version__}`\n"
                f"• **CPU Usage:** `{cpu_percent}%` ({cpu_cores} Cores)\n"
                f"• **Memory:** `{mem.used / (1024 ** 2):,.1f} MB` / `{mem.total / (1024 ** 2):,.1f} MB` ({mem.percent}%)\n"
                f"• **Architecture:** `{platform.architecture()[0]}`"
            )

            footer = "*Astrix • Made by Vinay Kumar (ASTRIXCODE)*"

            container = ui.Container(
                ui.TextDisplay(header),
                ui.Separator(),
                ui.TextDisplay(body),
                ui.Separator(),
                ui.TextDisplay(footer),
                self._get_buttons("system")
            )
            self.add_item(container)

    async def render_ping_tab(self, interaction: discord.Interaction):
        self.clear_items()
        self.active_tab = "ping"

        s_id = self.ctx.guild.shard_id if self.ctx.guild else 0
        sh = self.cog.bot.get_shard(s_id)
        shard_ping = round(sh.latency * 1000) if sh else round(self.cog.bot.latency * 1000)
        ws_ping = round(self.cog.bot.latency * 1000)

        db_latency = "N/A"
        try:
            async with aiosqlite.connect("db/stats.db") as db:
                t0 = time.perf_counter()
                await db.execute("SELECT 1")
                t1 = time.perf_counter()
                db_latency = f"{round((t1 - t0) * 1000, 2)} ms"
        except Exception:
            db_latency = "N/A"

        header = "### 🏓 Astrix — Network & Latencies\n> Real-time response times"

        body = (
            f"• **Websocket Latency:** `{ws_ping} ms`\n"
            f"• **Shard Latency:** `{shard_ping} ms`\n"
            f"• **Database Latency:** `{db_latency}`"
        )

        footer = "*Astrix • Made by Vinay Kumar (ASTRIXCODE)*"

        container = ui.Container(
            ui.TextDisplay(header),
            ui.Separator(),
            ui.TextDisplay(body),
            ui.Separator(),
            ui.TextDisplay(footer),
            self._get_buttons("ping")
        )
        self.add_item(container)
        await interaction.response.edit_message(view=self)


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
        self.total_songs_played = 0
        self.bot.loop.create_task(self.setup_database())

    async def setup_database(self):
        os.makedirs("db", exist_ok=True)
        async with aiosqlite.connect("db/stats.db") as db:
            await db.execute("CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value INTEGER)")
            await db.commit()
            async with db.execute("SELECT value FROM stats WHERE key = 'total_songs_played'") as cursor:
                row = await cursor.fetchone()
                self.total_songs_played = row[0] if row else 0
            if row is None:
                await db.execute("INSERT INTO stats (key, value) VALUES ('total_songs_played', 0)")
                await db.commit()

    async def update_total_songs_played(self):
        async with aiosqlite.connect("db/stats.db") as db:
            await db.execute("INSERT OR REPLACE INTO stats (key, value) VALUES ('total_songs_played', ?)", (self.total_songs_played,))
            await db.commit()

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        self.total_songs_played += 1
        await self.update_total_songs_played()

    @commands.hybrid_command(name="stats", aliases=["botinfo", "botstats", "bi", "statistics"], help="Shows the bot's information.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def stats(self, ctx):
        view = StatsContainerView(self, ctx)
        await ctx.reply(view=view, mention_author=False)
