import os
import random
import discord
from discord.ext import commands, tasks
import datetime
import time
from discord import ui
from discord.ui import Button, View
import wavelink
from wavelink.enums import TrackSource
from utils import Paginator, DescriptionEmbedPaginator
from core import Cog, axon, Context
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
import io
import aiohttp
from typing import cast
import asyncio
from utils.Tools import *
track_histories = {}
import base64
import asyncio
import re

SPOTIFY_TRACK_REGEX = r"https?://open\.spotify\.com/track/([a-zA-Z0-9]+)"
SPOTIFY_PLAYLIST_REGEX = r"https?://open\.spotify\.com/playlist/([a-zA-Z0-9]+)"
SPOTIFY_ALBUM_REGEX = r"https?://open\.spotify\.com/album/([a-zA-Z0-9]+)"

class SpotifyAPI:
    BASE_URL = "https://api.spotify.com/v1"

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None

    async def get_token(self):
        auth_url = "https://accounts.spotify.com/api/token"
        auth_value = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode('utf-8')).decode('utf-8')
        headers = {"Authorization": f"Basic {auth_value}"}
        data = {"grant_type": "client_credentials"}
        async with aiohttp.ClientSession() as session:
            async with session.post(auth_url, headers=headers, data=data) as response:
                text = await response.text()
                if response.status != 200:
                    raise Exception(f"Failed to fetch token: {response.status}, response: {text}")
                self.token = (await response.json()).get("access_token")

    async def get(self, endpoint, params=None):
        retries = 2
        for attempt in range(retries):
            if not self.token or attempt > 0:
                await self.get_token()

            url = f"{self.BASE_URL}/{endpoint}"
            headers = {"Authorization": f"Bearer {self.token}"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 401 and attempt < retries - 1:
                        continue
                    elif response.status != 200:
                        raise Exception(f"Failed to fetch data from Spotify: {response.status}")
                    return await response.json()
        raise Exception("Exceeded max retries to fetch Spotify data")

    
    async def get_track(self, track_id):
        return await self.get(f"tracks/{track_id}")

    async def get_playlist(self, playlist_id):
        return await self.get(f"playlists/{playlist_id}")

spotify_api = SpotifyAPI(client_id="ac2b614ca5ce46a18dfd1d3475fd6fd9", client_secret="df7bec95ae88438e8286db597bac8621")

class PlatformSelectView(View):
    def __init__(self, ctx, query):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.query = query

        platforms = [
            ("YouTube", "ytsearch", discord.ButtonStyle.red),
            ("JioSaavn", "jssearch", discord.ButtonStyle.green),
            ("SoundCloud", "scsearch", discord.ButtonStyle.grey),
        ]

        for name, source, style in platforms:
            button = Button(label=name, style=style)
            button.callback = self.create_callback(source)
            self.add_item(button)

    def create_callback(self, source):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.ctx.author:
                await interaction.response.send_message("Only the command author can select a platform.", ephemeral=True)
                return

            await interaction.response.send_message(f"Searching on {interaction.data['custom_id']}...", ephemeral=True)
            await self.perform_search(source)
            await interaction.message.delete()
        return callback

    async def perform_search(self, source):
        results = await wavelink.Playable.search(self.query, source=source)
        if not results:
            return await self.ctx.send(embed=discord.Embed(description="No results found.", color=0xFF0000))

        top_results = results[:5]
        embed = discord.Embed(
            title=f"Top 5 Results for '{self.query}' ({source})",
            color=0x1DB954
        )
        for i, track in enumerate(top_results, start=1):
            embed.add_field(name=f"{i}. {track.title}", value=f"Duration: {track.length // 1000 // 60}:{track.length // 1000 % 60} | [Link]({track.uri})", inline=False)

        await self.ctx.send(embed=embed, view=SearchResultView(self.ctx, top_results))

    

class SearchResultView(View):
    def __init__(self, ctx, results):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.results = results

        for i in range(5):
            button = Button(label=str(i + 1), style=discord.ButtonStyle.primary)
            button.callback = self.create_callback(i)
            self.add_item(button)

    def create_callback(self, index):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.ctx.author:
                await interaction.response.send_message("Only the command author can select a track.", ephemeral=True)
                return

            track = self.results[index]
            vc = self.ctx.voice_client or await self.ctx.author.voice.channel.connect(cls=wavelink.Player)
            vc.ctx = self.ctx


            if not vc.playing:
                await vc.play(track)
                await interaction.response.send_message(f"Started playing `{track.title}`.")
                await self.ctx.cog.display_player_embed(vc, track, self.ctx)

            else:
                await vc.queue.put_wait(track)
                await interaction.response.send_message(f"Added `{track.title}` to the queue.")

        return callback



def create_spotify_card(track_title: str, artist_name: str, artwork_img: Image.Image = None, duration_ms: int = 0, position_ms: int = 0) -> io.BytesIO:
    W, H = 960, 300
    base = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    card = Image.new('RGBA', (W, H), (18, 18, 18, 255))
    
    # Ambient Spotify green glow
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse((W - 350, -80, W + 80, 320), fill=(29, 185, 84, 45))
    glow = glow.filter(ImageFilter.GaussianBlur(60))
    card = Image.alpha_composite(card, glow)
    
    # Rounded corners for the whole card
    mask = Image.new('L', (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W, H), radius=22, fill=255)
    
    b_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(b_layer).rounded_rectangle((0, 0, W - 1, H - 1), radius=22, outline=(45, 45, 45, 255), width=2)
    card = Image.alpha_composite(card, b_layer)
    base.paste(card, (0, 0), mask)
    
    draw = ImageDraw.Draw(base)
    
    # Artwork dimensions
    art_size = (220, 220)
    art_pos = (40, 40)
    
    art = None
    if artwork_img:
        try:
            art = ImageOps.fit(artwork_img.convert('RGBA'), art_size, centering=(0.5, 0.5))
        except Exception:
            art = None
            
    if not art:
        art = Image.new('RGBA', art_size, (28, 28, 28, 255))
        adraw = ImageDraw.Draw(art)
        adraw.ellipse((30, 30, 190, 190), fill=(18, 18, 18, 255), outline=(29, 185, 84, 255), width=4)
        adraw.ellipse((80, 80, 140, 140), fill=(29, 185, 84, 255))
        
    art_mask = Image.new('L', art_size, 0)
    ImageDraw.Draw(art_mask).rounded_rectangle((0, 0, art_size[0], art_size[1]), radius=16, fill=255)
    
    # Shadow for album art
    shadow = Image.new('RGBA', (art_size[0] + 30, art_size[1] + 30), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle((10, 10, art_size[0] + 10, art_size[1] + 10), radius=20, fill=(0, 0, 0, 160))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    base.paste(shadow, (art_pos[0] - 5, art_pos[1] - 5), shadow)
    
    base.paste(art, art_pos, art_mask)
    
    art_border = Image.new('RGBA', art_size, (0, 0, 0, 0))
    ImageDraw.Draw(art_border).rounded_rectangle((0, 0, art_size[0]-1, art_size[1]-1), radius=16, outline=(255, 255, 255, 35), width=1)
    base.paste(art_border, art_pos, art_border)
    
    font_bold = 'utils/arial.ttf'
    try:
        f_badge = ImageFont.truetype(font_bold, 14)
        f_title = ImageFont.truetype(font_bold, 32)
        f_artist = ImageFont.truetype(font_bold, 20)
        f_time = ImageFont.truetype(font_bold, 14)
        f_footer = ImageFont.truetype(font_bold, 13)
    except Exception:
        f_badge = f_title = f_artist = f_time = f_footer = ImageFont.load_default()
        
    content_x = 295
    # Spotify Badge with dot
    draw.ellipse((content_x, 46, content_x + 8, 54), fill=(29, 185, 84, 255))
    draw.text((content_x + 16, 43), 'SPOTIFY MUSIC PLAYER', font=f_badge, fill=(29, 185, 84, 255))
    
    # Equalizer wave bars
    eq_x = content_x + 230
    bar_heights = [8, 14, 20, 12, 18, 10, 16, 22, 14, 8]
    for i, bh in enumerate(bar_heights):
        bx = eq_x + (i * 5)
        by = 54 - bh
        draw.line([(bx, by), (bx, 54)], fill=(29, 185, 84, 200), width=3)

    # Title & Artist
    def truncate_text(text, max_w, font):
        w = draw.textlength(text, font=font)
        if w <= max_w:
            return text
        while len(text) > 3 and draw.textlength(text + '...', font=font) > max_w:
            text = text[:-1]
        return text + '...'

    clean_title = truncate_text(track_title or 'Unknown Track', 600, f_title)
    clean_artist = truncate_text(artist_name or 'Unknown Artist', 600, f_artist)
    
    draw.text((content_x, 75), clean_title, font=f_title, fill=(255, 255, 255, 255))
    draw.text((content_x, 122), clean_artist, font=f_artist, fill=(175, 175, 175, 255))
    
    # Progress Bar
    bar_x = content_x
    bar_y = 180
    bar_w = 600
    bar_h = 6
    draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=3, fill=(55, 55, 55, 255))
    
    progress = 0.0
    if duration_ms > 0:
        progress = max(0.0, min(1.0, position_ms / duration_ms))
    else:
        progress = 0.35
        
    fill_w = int(bar_w * progress)
    if fill_w > 0:
        draw.rounded_rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), radius=3, fill=(29, 185, 84, 255))
        thumb_x = bar_x + fill_w
        thumb_y = bar_y + (bar_h // 2)
        draw.ellipse((thumb_x - 6, thumb_y - 6, thumb_x + 6, thumb_y + 6), fill=(255, 255, 255, 255))
        
    cur_sec = max(0, (position_ms or 0) // 1000)
    tot_sec = max(0, (duration_ms or 0) // 1000)
    cur_str = f"{cur_sec // 60:02d}:{cur_sec % 60:02d}"
    tot_str = f"{tot_sec // 60:02d}:{tot_sec % 60:02d}"
    
    draw.text((bar_x, bar_y + 14), cur_str, font=f_time, fill=(175, 175, 175, 255))
    tot_w = draw.textlength(tot_str, font=f_time)
    draw.text((bar_x + bar_w - tot_w, bar_y + 14), tot_str, font=f_time, fill=(175, 175, 175, 255))
    
    # Bottom details row
    bot_y = 236
    draw.rounded_rectangle((content_x, bot_y, content_x + 120, bot_y + 24), radius=12, fill=(35, 35, 35, 255), outline=(50, 50, 50, 255))
    draw.text((content_x + 16, bot_y + 4), 'LOSSLESS HQ', font=f_footer, fill=(29, 185, 84, 255))
    
    draw.rounded_rectangle((content_x + 130, bot_y, content_x + 240, bot_y + 24), radius=12, fill=(35, 35, 35, 255), outline=(50, 50, 50, 255))
    draw.text((content_x + 146, bot_y + 4), 'STEREO 320k', font=f_footer, fill=(180, 180, 180, 255))
    
    branding = 'Made by Vinay Kumar  •  ASTRIXCODE'
    b_w = draw.textlength(branding, font=f_footer)
    draw.text((bar_x + bar_w - b_w, bot_y + 5), branding, font=f_footer, fill=(130, 130, 130, 255))
    
    image_bytes = io.BytesIO()
    base.save(image_bytes, format='PNG')
    image_bytes.seek(0)
    return image_bytes


class MusicControlView(View):
    def __init__(self, player, ctx):
        super().__init__(timeout=None)
        self.player = player
        self.ctx = ctx
        self._prev_vol = 100

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.ctx.voice_client or not self.player.playing:
            await interaction.response.send_message("❌ Player is no longer active.", ephemeral=True)
            return False
        if not interaction.user.voice or interaction.user.voice.channel != self.ctx.voice_client.channel:
            await interaction.response.send_message(
                embed=discord.Embed(description="❌ You must be connected to the same voice channel to control the player.", color=0xFF0000),
                ephemeral=True
            )
            return False
        return True

    # --- ROW 0: Track Seek & Skip Navigation (5 Buttons) ---
    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, row=0)
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        guild_id = interaction.guild.id
        if guild_id in track_histories and len(track_histories[guild_id]) > 1:
            track_histories[guild_id].pop()
            previous_track = track_histories[guild_id][-1]
            if self.player.playing:
                await self.player.stop()
            await self.ctx.voice_client.queue.put_wait(previous_track)
            await interaction.response.send_message(f"⏮️ Playing previous track: **{previous_track.title}**.", ephemeral=True)
        else:
            await interaction.response.send_message("No previous track found in history.", ephemeral=True)

    @discord.ui.button(emoji="⏪", style=discord.ButtonStyle.secondary, row=0)
    async def rewind_button(self, interaction: discord.Interaction, button: Button):
        if self.player.playing:
            new_position = max(self.player.position - 10000, 0)
            await self.player.seek(new_position)
            await interaction.response.send_message("⏪ Rewound 10 seconds.", ephemeral=True)
        else:
            await interaction.response.send_message("No track is currently playing.", ephemeral=True)

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.success, row=0)
    async def pause_button(self, interaction: discord.Interaction, button: Button):
        if self.player.paused:
            await self.player.pause(False)
            try:
                if self.player.channel and hasattr(self.player.channel, 'edit'):
                    await self.player.channel.edit(status=f"Playing: {self.player.current.title}")
            except Exception:
                pass
            button.emoji = "⏸️"
            button.style = discord.ButtonStyle.success
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"▶️ Resumed by **{interaction.user.display_name}**.", ephemeral=True)
        elif self.player.playing:
            await self.player.pause(True)
            try:
                if self.player.channel and hasattr(self.player.channel, 'edit'):
                    await self.player.channel.edit(status=f"Paused: {self.player.current.title}")
            except Exception:
                pass
            button.emoji = "▶️"
            button.style = discord.ButtonStyle.primary
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"⏸️ Paused by **{interaction.user.display_name}**.", ephemeral=True)
        else:
            await interaction.response.send_message("No track is currently playing.", ephemeral=True)

    @discord.ui.button(emoji="⏩", style=discord.ButtonStyle.secondary, row=0)
    async def forward_button(self, interaction: discord.Interaction, button: Button):
        if self.player.playing:
            new_position = min(self.player.position + 10000, self.player.current.length)
            await self.player.seek(new_position)
            await interaction.response.send_message("⏩ Forwarded 10 seconds.", ephemeral=True)
        else:
            await interaction.response.send_message("No track is currently playing.", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        if self.player and self.player.playing:
            await self.player.stop()
            await interaction.response.send_message(f"⏭️ Skipped track by **{interaction.user.display_name}**.", ephemeral=True)
        else:
            await interaction.response.send_message("No track is currently playing to skip.", ephemeral=True)

    # --- ROW 1: Playback Modes & Actions (5 Buttons) ---
    @discord.ui.button(emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
    async def replay_button(self, interaction: discord.Interaction, button: Button):
        if self.player.playing:
            await self.player.seek(0)
            await interaction.response.send_message("🔄 Replaying current track from start.", ephemeral=True)
        else:
            await interaction.response.send_message("No track is currently playing.", ephemeral=True)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, row=1)
    async def shuffle_button(self, interaction: discord.Interaction, button: Button):
        if self.player.queue and len(self.player.queue) > 1:
            random.shuffle(self.player.queue)
            await interaction.response.send_message(f"🔀 Queue shuffled ({len(self.player.queue)} tracks) by **{interaction.user.display_name}**.", ephemeral=True)
        else:
            await interaction.response.send_message("Queue has fewer than 2 tracks to shuffle.", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, row=1)
    async def stop_button(self, interaction: discord.Interaction, button: Button):
        if self.player:
            guild_id = interaction.guild.id if interaction.guild else None
            voice_channel = getattr(self.player, "channel", None)
            if voice_channel:
                try:
                    await voice_channel.edit(status=None)
                except Exception:
                    pass
            try:
                await self.player.disconnect()
            except Exception:
                pass

            music_cog = interaction.client.get_cog("Music")
            if music_cog and hasattr(music_cog, "controller_messages") and guild_id:
                music_cog.controller_messages.pop(guild_id, None)

            await interaction.response.send_message(f"⏹️ Player stopped and disconnected by **{interaction.user.display_name}**.", ephemeral=True)
        else:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary, row=1)
    async def loop_button(self, interaction: discord.Interaction, button: Button):
        if self.player.queue.mode != wavelink.QueueMode.loop:
            self.player.queue.mode = wavelink.QueueMode.loop
            button.style = discord.ButtonStyle.success
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"🔁 Looping **enabled** by **{interaction.user.display_name}**.", ephemeral=True)
        else:
            self.player.queue.mode = wavelink.QueueMode.normal
            button.style = discord.ButtonStyle.secondary
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"🔁 Looping **disabled** by **{interaction.user.display_name}**.", ephemeral=True)

    @discord.ui.button(emoji="📻", style=discord.ButtonStyle.secondary, row=1)
    async def autoplay_button(self, interaction: discord.Interaction, button: Button):
        if self.player.autoplay != wavelink.AutoPlayMode.enabled:
            self.player.autoplay = wavelink.AutoPlayMode.enabled
            button.style = discord.ButtonStyle.success
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"📻 Autoplay **enabled** by **{interaction.user.display_name}**.", ephemeral=True)
        else:
            self.player.autoplay = wavelink.AutoPlayMode.disabled
            button.style = discord.ButtonStyle.secondary
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"📻 Autoplay **disabled** by **{interaction.user.display_name}**.", ephemeral=True)

    # --- ROW 2: Volume & Queue Management (5 Buttons) ---
    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.secondary, row=2)
    async def vol_down_button(self, interaction: discord.Interaction, button: Button):
        current_vol = getattr(self.player, "volume", 100) or 100
        new_vol = max(current_vol - 10, 10)
        try:
            await self.player.set_volume(new_vol)
            await interaction.response.send_message(f"🔉 Volume decreased to **{new_vol}%** by **{interaction.user.display_name}**.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Could not change volume: {e}", ephemeral=True)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, row=2)
    async def vol_up_button(self, interaction: discord.Interaction, button: Button):
        current_vol = getattr(self.player, "volume", 100) or 100
        new_vol = min(current_vol + 10, 150)
        try:
            await self.player.set_volume(new_vol)
            await interaction.response.send_message(f"🔊 Volume increased to **{new_vol}%** by **{interaction.user.display_name}**.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Could not change volume: {e}", ephemeral=True)

    @discord.ui.button(emoji="🔇", style=discord.ButtonStyle.secondary, row=2)
    async def mute_button(self, interaction: discord.Interaction, button: Button):
        current_vol = getattr(self.player, "volume", 100) or 100
        if current_vol > 0:
            self._prev_vol = current_vol
            try:
                await self.player.set_volume(0)
                button.style = discord.ButtonStyle.danger
                await interaction.response.edit_message(view=self)
                await interaction.followup.send(f"🔇 Player **muted** by **{interaction.user.display_name}**.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"Could not mute: {e}", ephemeral=True)
        else:
            restore_vol = getattr(self, "_prev_vol", 100) or 100
            try:
                await self.player.set_volume(restore_vol)
                button.style = discord.ButtonStyle.secondary
                await interaction.response.edit_message(view=self)
                await interaction.followup.send(f"🔊 Player **unmuted** ({restore_vol}%) by **{interaction.user.display_name}**.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"Could not unmute: {e}", ephemeral=True)

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.secondary, row=2)
    async def queue_button(self, interaction: discord.Interaction, button: Button):
        queue = getattr(self.player, "queue", None)
        if not queue or len(queue) == 0:
            await interaction.response.send_message("📜 The queue is currently empty.", ephemeral=True)
            return

        q_lines = []
        for idx, track in enumerate(list(queue)[:10], 1):
            dur = f"{track.length // 60000:02d}:{(track.length % 60000) // 1000:02d}" if hasattr(track, 'length') else ""
            dur_str = f" `[{dur}]`" if dur else ""
            q_lines.append(f"`{idx}.` **{track.title}**{dur_str}")

        msg = f"### 📜 Current Queue ({len(queue)} tracks)\n" + "\n".join(q_lines)
        if len(queue) > 10:
            msg += f"\n\n*...and {len(queue) - 10} more tracks in queue.*"
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(emoji="🗑️", style=discord.ButtonStyle.secondary, row=2)
    async def clear_queue_button(self, interaction: discord.Interaction, button: Button):
        queue = getattr(self.player, "queue", None)
        if not queue or len(queue) == 0:
            await interaction.response.send_message("The queue is already empty.", ephemeral=True)
            return

        count = len(queue)
        queue.clear()
        await interaction.response.send_message(f"🗑️ Cleared **{count}** tracks from the queue by **{interaction.user.display_name}**.", ephemeral=True)




class Music(commands.Cog):
    def __init__(self, client: axon):
        self.client = client
        self.client.loop.create_task(self.connect_nodes())
        self.client.loop.create_task(self.monitor_inactivity())
        
        self.inactivity_timeout = 120 
        self.player_inactivity = {}  
        self.controller_messages = {}

    async def monitor_inactivity(self):
        await self.client.wait_until_ready()
        while True:
            for guild in self.client.guilds:
                await self.check_inactivity(guild.id) 
            await asyncio.sleep(60) 

    async def check_inactivity(self, guild_id):
        guild = self.client.get_guild(guild_id)
        if not guild:
            return

        player = None
        for vc in self.client.voice_clients:
            if vc.guild.id == guild.id:
                player = vc
                break

        if player and player.playing and len(player.channel.members) == 1:
            await self.inactivity_timer(guild)

    async def inactivity_timer(self, guild):
        await asyncio.sleep(self.inactivity_timeout)
        if len(guild.voice_channels[0].members) == 1:
            player = None
            for vc in self.client.voice_clients:
                if vc.guild.id == guild.id:
                    player = vc
                    break
            if player:
                await player.disconnect(force=True)
                try:
                    ended = discord.Embed(description="Bot has been disconnected due to inactivity (being idle in Voice Channel) for more than 2 minutes." , color=0xFF0000)
                    ended.set_author(name="Inactive Timeout", icon_url=self.client.user.avatar.url)
                    ended.set_footer(text="Thanks for choosing Astrix!")
                    support = Button(label='Support',
                                 style=discord.ButtonStyle.link,
                        url=f'https://discord.gg/FR9pXG2Mwb')
                    vote = Button(label='Vote',
                                 style=discord.ButtonStyle.link,
                        url=f'https://top.gg/bot/11441796597355772640/vote')
                    view = View()
                    view.add_item(support)
                    view.add_item(vote)
                    await player.ctx.channel.send(embed=ended, view=view)
                except:
                    pass

    async def connect_nodes(self) -> None:
        await self.client.wait_until_ready()
        lavalink_uri = os.getenv("LAVALINK_URI", "https://lavalinkv4.serenetia.com:443")
        lavalink_password = os.getenv("LAVALINK_PASSWORD", "https://seretia.link/discord")
        try:
            nodes = [wavelink.Node(uri=lavalink_uri, password=lavalink_password)]
            await wavelink.Pool.connect(nodes=nodes, client=self.client, cache_capacity=None)
            print("Lavalink music node connected successfully.")
        except Exception as e:
            print(f"Music module Lavalink notice: {e}")




    async def display_player_embed(self, player, track, ctx, autoplay=False):
        track_img = None
        if track.artwork:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(track.artwork, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            img_data = io.BytesIO(await resp.read())
                            track_img = Image.open(img_data)
            except Exception:
                track_img = None

        image_bytes = create_spotify_card(
            track_title=track.title,
            artist_name=track.author,
            artwork_img=track_img,
            duration_ms=track.length,
            position_ms=getattr(player, "position", 0) or 0
        )

        filename = f"spotify_player_{int(time.time())}.png"
        file = discord.File(image_bytes, filename=filename)
        sec = max(0, track.length // 1000)
        duration = f"{sec // 60:02d}:{sec % 60:02d}"

        embed = discord.Embed(
            title=f"🎶 {track.title}"
        )
        embed.add_field(name="Author", value=f"`{track.author}`", inline=True)
        embed.add_field(name="Duration", value=f"`{duration}`", inline=True)

        if "spotify" in track.source:
            source_link = f"🟢 [Spotify]({track.uri})"
        elif "jiosaavn" in track.source:
            source_link = f"🎶 [JioSaavn]({track.uri})"
        elif "soundcloud" in track.source:
            source_link = f"🟠 [SoundCloud]({track.uri})"
        elif "youtube" in track.source:
            source_link = f"🔴 [YouTube]({track.uri})"
        else:
            source_link = f"🎵 [Stream Link]({track.uri})"

        embed.add_field(name="Source", value=source_link, inline=True)
        embed.set_image(url=f"attachment://{filename}")

        footer_text = f"Requested by {ctx.author.display_name}"
        if autoplay:
            footer_text += " • Autoplay Mode"
        footer_text += " • ASTRIXCODE by Vinay Kumar"

        avatar_url = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
        embed.set_footer(text=footer_text, icon_url=avatar_url)

        guild_id = player.guild.id if hasattr(player, "guild") and player.guild else (ctx.guild.id if ctx and ctx.guild else None)
        existing_msg = getattr(player, "controller_message", None) or (self.controller_messages.get(guild_id) if guild_id else None)

        if existing_msg:
            try:
                await existing_msg.edit(embed=embed, attachments=[file], view=MusicControlView(player, ctx))
                player.controller_message = existing_msg
                if guild_id:
                    self.controller_messages[guild_id] = existing_msg
                return
            except Exception:
                pass

        new_msg = await ctx.send(embed=embed, file=file, view=MusicControlView(player, ctx))
        player.controller_message = new_msg
        if guild_id:
            self.controller_messages[guild_id] = new_msg


    async def on_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = getattr(payload, "player", None)
        if not player or getattr(player, "queue", None) is None:
            return

        queue = player.queue
        if len(queue) == 0:
            if getattr(queue, "mode", None) == wavelink.QueueMode.loop:
                await player.play(payload.track)
            elif getattr(player, "autoplay", None) == wavelink.AutoPlayMode.enabled:
                await asyncio.sleep(5)
                if player.current:
                    ctx = getattr(player, "ctx", None)
                    if ctx:
                        await self.display_player_embed(player, player.current, ctx, autoplay=True)
                else:
                    if hasattr(player, "ctx") and player.ctx:
                        await player.ctx.send("No suitable track found for autoplay.")
            else:
                try:
                    await player.disconnect()
                except Exception:
                    pass
                ended = discord.Embed(description="All tracks have been played, leaving the voice channel.", color=0xFF0000)
                avatar_url = self.client.user.avatar.url if (self.client.user and self.client.user.avatar) else None
                if avatar_url:
                    ended.set_author(name="Queue Ended", icon_url=avatar_url)
                else:
                    ended.set_author(name="Queue Ended")

                support = Button(label='Support', style=discord.ButtonStyle.link, url='https://discord.gg/FR9pXG2Mwb')
                vote = Button(label='Vote', style=discord.ButtonStyle.link, url='https://top.gg/bot/1144179659735572640/vote')
                view = View()
                view.add_item(support)
                view.add_item(vote)

                guild_id = player.guild.id if hasattr(player, "guild") and player.guild else None
                ctrl_msg = self.controller_messages.pop(guild_id, None) if guild_id else None
                if ctrl_msg:
                    try:
                        await ctrl_msg.edit(embed=ended, attachments=[], view=view)
                        return
                    except Exception:
                        pass

                if hasattr(player, "ctx") and player.ctx:
                    try:
                        await player.ctx.send(embed=ended, view=view)
                    except Exception:
                        pass
        else:
            next_track = await player.queue.get_wait()
            await player.play(next_track)
            ctx = getattr(player, "ctx", None)
            if ctx:
                await self.display_player_embed(player, next_track, ctx)



    async def play_source(self, ctx, query):
        if not ctx.author.voice:
            await ctx.send(embed=discord.Embed(description="⚠️ you need to be in a voice channel to use this command.", color=0x000000))
            return

        vc = ctx.voice_client or await ctx.author.voice.channel.connect(cls=wavelink.Player)
        vc.ctx = ctx
        
        
        if vc.playing:
            if ctx.voice_client and ctx.voice_client.channel != ctx.author.voice.channel:
                await ctx.send(embed=discord.Embed(description=f"You must be connected to {ctx.voice_client.channel.mention} to play.", color=0x000000))
                return
        vc.autoplay = wavelink.AutoPlayMode.disabled

        """if re.match(SPOTIFY_TRACK_REGEX, query):
            await self.handle_spotify_link(ctx, vc, query, "track")
        elif re.match(SPOTIFY_PLAYLIST_REGEX, query):
            await self.handle_spotify_link(ctx, vc, query, "playlist")
        elif re.match(SPOTIFY_ALBUM_REGEX, query):
            await self.handle_spotify_link(ctx, vc, query, "album")
        
            return"""
            
        tracks = await wavelink.Playable.search(query)
        if not tracks:
            await ctx.send(embed=discord.Embed(description="No results found.", color=0x000000))
            return

        if isinstance(tracks, wavelink.Playlist):
            await vc.queue.put_wait(tracks.tracks)
            await ctx.send(embed=discord.Embed(description=f"➕ Added playlist [{tracks.name}](https://discord.gg/mZBtu84xGH) with **{len(tracks.tracks)} songs** to the queue.", color=0x000000))
            if not vc.playing:
                track = await vc.queue.get_wait()
                await vc.play(track)
                await self.display_player_embed(vc, track, ctx)
        else:
            track = tracks[0]
            await vc.queue.put_wait(track)
            await ctx.send(embed=discord.Embed(description=f"➕  Added [{track.title}](https://discord.gg/mZBtu84xGH) to the queue.", color=0x000000))
            if not vc.playing:
                await vc.play(await vc.queue.get_wait())
                await self.display_player_embed(vc, track, ctx)
            self.client.loop.create_task(self.check_inactivity(ctx.guild.id))
           # await interaction.response.defer()


    
    async def handle_spotify_link(self, ctx, vc, link, type_):
        try:
            if type_ == "track":
                track_id = re.search(SPOTIFY_TRACK_REGEX, link).group(1)
                track_info = await spotify_api.get_track(track_id)

                
                title = track_info['name']
                author = ', '.join(artist['name'] for artist in track_info['artists'])

                
                search_query = f"{title} by {author}"
                search_results = await wavelink.Playable.search(search_query, source=wavelink.enums.TrackSource.YouTube)

                if not search_results:
                    await ctx.send("Can't play this track from Spotify, please try with another track.")
                    return

                track = search_results[0]
                await vc.queue.put_wait(track)
                await ctx.send(embed=discord.Embed(description=f"➕ Added [{track.title}](https://discord.gg/mZBtu84xGH) to the queue.", color=0x000000))
                if not vc.playing:
                    await vc.play(track)
                    await self.display_player_embed(vc, track, ctx)

                #await self.display_player_embed(vc, track, ctx)
                
            elif type_ == "playlist":
                lmao = await ctx.send("⏳ Processing to add tracks from the playlist, this may take a while...")
                
                playlist_id = re.search(SPOTIFY_PLAYLIST_REGEX, link).group(1)
                playlist_info = await spotify_api.get(f"playlists/{playlist_id}")
                tracks = playlist_info.get("tracks", {}).get("items", [])
                playlist_length = len(tracks)

                if not tracks:
                    await ctx.send("No tracks found in the playlist.")
                    return

                c = 0
                for track in tracks:
                    title = track['track']['name']
                    author = ', '.join(artist['name'] for artist in track['track']['artists'])
                    search_query = f"{title} {author}"

                    track_results = await wavelink.Playable.search(search_query, source=wavelink.enums.TrackSource.YouTube)
                    if track_results:
                        await vc.queue.put_wait(track_results[0])
                        c += 1
                        await ctx.message.add_reaction("✅")

                await ctx.send(embed=discord.Embed(description=f"➕ Added **{c}** of **{playlist_length}** tracks from **playlist** **[{playlist_info['name']}](https://discord.gg/mZBtu84xGH)** to the queue.", color=0x000000))
                await lmao.delete()
                
                if not vc.playing:
                    next_track = await vc.queue.get_wait()
                    await vc.play(next_track)
                    await self.display_player_embed(vc, next_track, ctx)


            elif type_ == "album":
                await ctx.message.add_reaction("⌛")
                album_id = re.search(SPOTIFY_ALBUM_REGEX, link).group(1)
                album_info = await spotify_api.get(f"albums/{album_id}")
                tracks = album_info.get("tracks", {}).get("items", [])

                if not tracks:
                    await ctx.send("No tracks found in the album.")
                    return

                for track in tracks:
                    title = track['name']
                    author = ', '.join(artist['name'] for artist in track['artists'])
                    search_query = f"{title} {author}"

                    track_results = await wavelink.Playable.search(search_query, source=wavelink.enums.TrackSource.YouTube)
                    if track_results:
                        await vc.queue.put_wait(track_results[0])

                await ctx.send(embed=discord.Embed(description=f"➕ Added all tracks from album **[{album_info['name']}](https://discord.gg/mZBtu84xGH)** to the queue.", color=0x000000))
                if not vc.playing:
                    next_track = await vc.queue.get_wait()
                    await vc.play(next_track)
                    await self.display_player_embed(vc, next_track, ctx)

                
        except Exception as e:
            await ctx.send(f"An error occurred while processing the Spotify link: {e}")



    def create_progress_bar(self, completed, total, length=10):
        filled_length = int(length * (completed / total))
        bar = '█' * filled_length + '░' * (length - filled_length)
        return bar

    @commands.hybrid_command(name="play", aliases=['p'], usage="play <query>", help="Plays a song or playlist.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def play(self, ctx: commands.Context, *, query: str):
        
        await self.play_source(ctx, query)


    @commands.hybrid_command(name="search", usage="search <query>", help="Searches music from multiple platforms.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def search2(self, ctx: commands.Context, *, query: str):
        if not ctx.author.voice:
            await ctx.send(embed=discord.Embed(description="⚠️ You need to be in a voice channel to use this command.", color=0x000000))
            return

        embed = discord.Embed(
            title="Select a platform to search from:",
            description="Click a button below to choose.",
            color=0xff0000
        )
        await ctx.send(embed=embed, view=PlatformSelectView(ctx, query))


    @commands.hybrid_command(name="nowplaying", aliases=["nop"], usage="nowplaying", help="Shows the info about current playing song.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def nowplaying(self, ctx: commands.Context):
        vc = ctx.voice_client
        if not vc or not vc.playing:
            await ctx.send(embed=discord.Embed(description="No song is currently playing.", color=0xFF0000))
            return

        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=discord.Embed(description="You need to be in the same voice channel as me to use this command.", color=0xFF0000))
            return

        track = vc.current
        position = vc.position / 1000  
        length = track.length / 1000  

        progress_bar = self.create_progress_bar(position, length, length=10)
        position_str = f"{int(position // 60)}:{int(position % 60):02}"
        length_str = f"{int(length // 60)}:{int(length % 60):02}"


        queue_length = len(vc.queue) if vc.queue else 0


        if "spotify" in track.uri:
            source_name = "Spotify"
        elif "youtube" in track.uri:
            source_name = "YouTube"
        elif "soundcloud" in track.uri:
            source_name = "SoundCloud"
        elif "jiosaavn" in track.uri:
            source_name = "JioSaavn"
        else:
            source_name = "Unknown Source"


        view = ui.LayoutView(timeout=120)
        link_btn = ui.Button(label=f"Listen on {source_name}", style=discord.ButtonStyle.link, url=track.uri)
        close_btn = ui.Button(label="Close", emoji="🗑️", style=discord.ButtonStyle.danger)
        async def on_close(interaction: discord.Interaction):
            if interaction.user == ctx.author:
                try:
                    await interaction.message.delete()
                except Exception:
                    pass
        close_btn.callback = on_close

        header = f"### 🎶 Now Playing: [{track.title}]({track.uri})\n> **Artist:** `{track.author}` • **Source:** `{source_name}`"
        progress_text = f"`{position_str}` [{progress_bar}] `{length_str}`\n• **Queue Remaining:** `{queue_length}` tracks"
        footer = f"*Requested by {ctx.author.display_name} • Astrix Music by Vinay Kumar*"

        container = ui.Container(
            ui.TextDisplay(header),
            ui.Separator(),
            ui.TextDisplay(progress_text),
            ui.Separator(),
            ui.TextDisplay(footer),
            ui.ActionRow(link_btn, close_btn)
        )
        view.add_item(container)
        await ctx.send(view=view)

    @commands.hybrid_command(name="autoplay", usage="autoplay", help="Toggles autoplay mode.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def autoplay(self, ctx: commands.Context):
        vc = ctx.voice_client
        if not vc or not vc.playing:
            await ctx.send(embed=discord.Embed(description="⚠️ No song is currently playing.", color=0x000000))
            return

        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=discord.Embed(description="⚠️ You need to be in the same voice channel as me to use this command.", color=0xFF0000))
            return

        if vc:
            vc.autoplay = (
                wavelink.AutoPlayMode.enabled if vc.autoplay != wavelink.AutoPlayMode.enabled else wavelink.AutoPlayMode.disabled
            )
            await ctx.send(embed=discord.Embed(description=f"✅ Autoplay {'enabled' if vc.autoplay == wavelink.AutoPlayMode.enabled else 'disabled'} by {ctx.author.mention}.", color=0x000000))

    @commands.hybrid_command(name="loop", usage="loop", help="Toggles loop mode.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def loop(self, ctx: commands.Context):
        vc = ctx.voice_client
        if not vc or not vc.playing:
            await ctx.send(embed=discord.Embed(description="⚠️ No song is currently playing.", color=0x000000))
            return

        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=discord.Embed(description="⚠️ You need to be in the same voice channel as me to use this command.", color=0xFF0000))
            return

        if vc:
            vc.queue.mode = wavelink.QueueMode.loop if vc.queue.mode != wavelink.QueueMode.loop else wavelink.QueueMode.normal
            await ctx.send(embed=discord.Embed(description=f"✅ Loop {'enabled' if vc.queue.mode == wavelink.QueueMode.loop else 'disabled'} by {ctx.author.mention}.", color=0x000000))
        else:
            await ctx.send(embed=discord.Embed(description="I'm not connected to a voice channel.", color=0xFF0000))


    @commands.hybrid_command(name="pause", usage="pause", help="Pauses the current song.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def pause(self, ctx: commands.Context):
        vc = ctx.voice_client
        if not vc or not vc.playing:
            await ctx.send(embed=discord.Embed(description="⚠️ No song is currently playing.", color=0x000000))
            return

        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=discord.Embed(description="⚠️ You need to be in the same voice channel as me to use this command.", color=0xFF0000))
            return

        if vc and vc.playing and not vc.paused:
            await vc.pause(True)
            await vc.channel.edit(status=f"⏸️ Paused: {vc.current.title}")
            await ctx.send(embed=discord.Embed(description=f"Paused by {ctx.author.mention}.", color=0x000000))
        else:
            await ctx.send(embed=discord.Embed(description="⚠️   Nothing is playing or already paused.", color=0xFF0000))

    @commands.hybrid_command(name="resume", usage="resume", help="Resumes the paused song.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def resume(self, ctx: commands.Context):
        vc = ctx.voice_client
        if not vc or not vc.playing:
            await ctx.send(embed=discord.Embed(description="⚠️ No song is currently playing.", color=0x000000))
            return

        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=discord.Embed(description="⚠️ You need to be in the same voice channel as me to use this command.", color=0xFF0000))
            return

        if vc and vc.paused:
            await vc.pause(False)
            await vc.channel.edit(status=f"🎶 Playing: {vc.current.title}")
            await ctx.send(embed=discord.Embed(description=f"Resumed by {ctx.author.mention}.", color=0x000000))
        else:
            await ctx.send(embed=discord.Embed(description="Player is not paused.", color=0xFF0000))

    @commands.hybrid_command(name="skip", usage="skip", help="Skips the current song.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def skip(self, ctx: commands.Context):
        vc = ctx.voice_client
        if not vc or not vc.playing:
            await ctx.send(embed=discord.Embed(description="No song is currently playing.", color=0x000000))
            return

        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=discord.Embed(description="⚠️ You need to be in the same voice channel as me to use this command.", color=0xFF0000))
            return

        if vc.autoplay == wavelink.AutoPlayMode.enabled:
            await vc.stop()
            return await ctx.send(embed=discord.Embed(description=f"Skipped by {ctx.author.mention}.", color=0x000000))


        if vc and vc.playing and not vc.queue.is_empty:
            await vc.stop()
            await ctx.send(embed=discord.Embed(description=f"Skipped by {ctx.author.mention}.", color=0x000000))
        else:
            await ctx.send(embed=discord.Embed(description="⚠️ No song is playing or in the queue to skip.", color=0xFF0000))

    @commands.hybrid_command(name="shuffle", usage="shuffle", help="Shuffles the queue.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def shuffle(self, ctx: commands.Context):
        vc = ctx.voice_client
        if not vc or not vc.playing:
            await ctx.send(embed=discord.Embed(description="⚠️  No song is currently playing.", color=0x000000))
            return

        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=discord.Embed(description="⚠️ You need to be in the same voice channel as me to use this command.", color=0xFF0000))
            return

        if vc and vc.queue:
            random.shuffle(vc.queue)
            await ctx.send(embed=discord.Embed(description=f"Queue shuffled by {ctx.author.mention}.", color=0x000000))
        else:
            await ctx.send(embed=discord.Embed(description="Queue is empty.", color=0xFF0000))

    @commands.hybrid_command(name="stop", usage="stop", help="Stops the current song and clears the queue.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def stop(self, ctx: commands.Context):
        player: wavelink.Player = cast(wavelink.Player, ctx.voice_client)
        vc = ctx.voice_client
        if not vc or not vc.playing:
            await ctx.send(embed=discord.Embed(description="⚠️ No song is currently playing.", color=0x000000))
            return

        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=discord.Embed(description="⚠️  You need to be in the same voice channel as me to use this command.", color=0xFF0000))
            return

        if vc and player:
            await vc.channel.edit(status=None)
            vc.queue.clear()
            await vc.disconnect(force=True)
            await ctx.send(embed=discord.Embed(description=f"Stopped and queue cleared by {ctx.author.mention}.", color=0x000000))
        else:
            await ctx.send(embed=discord.Embed(description="Nothing is playing to stop.", color=0xFF0000))

    @commands.hybrid_command(name="volume", aliases=["vol"], usage="volume <level>", help="Sets the volume of the player.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def volume(self, ctx: commands.Context, level: int):
        vc = ctx.voice_client

        if not vc:
            await ctx.send(embed=discord.Embed(description="⚠️ I'm not connected to a voice channel.", color=0xFF0000))
            return

        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=discord.Embed(description="⚠️ You need to be in the same voice channel as me to use this command.", color=0xFF0000))
            return

        if vc:
            if 1 <= level <= 150:
                await vc.set_volume(level)
                await ctx.send(embed=discord.Embed(description=f"🔊 Volume set to {level}% by {ctx.author.mention}.", color=0x000000))
            else:
                await ctx.send(embed=discord.Embed(description="⚠️ Volume must be between 1 and 150.", color=0xFF0000))
        else:
            await ctx.send(embed=discord.Embed(description="Bot is not connected to a voice channel.", color=0xFF0000))

    @commands.hybrid_command(name="queue", usage="queue", help="Shows the current queue.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def queue(self, ctx: commands.Context):
        vc = ctx.voice_client

        if not vc or not vc.queue or vc.queue.is_empty:
            await ctx.send(embed=discord.Embed(description="⚠️  The queue is currently empty.", color=0x000000))
            return

        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=discord.Embed(description="⚠️ you need to be in the same voice channel as me to use this command.", color=0xFF0000))
            return


        entries = [f"{index + 1}. [{track.title} - {track.author}]({track.uri})" for index, track in enumerate(vc.queue)]
        paginator = Paginator(source=DescriptionEmbedPaginator(
            entries=entries,
            title="Current Queue",
            description="List of upcoming songs.",
            per_page=10,
            color=0x000000),
            ctx=ctx)
        await paginator.paginate()

    @commands.hybrid_command(name="clearqueue", usage="clearqueue", help="Clears the queue.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def clearqueue(self, ctx: commands.Context):
        vc = ctx.voice_client

        if not vc or not vc.queue or vc.queue.is_empty:
            await ctx.send(embed=discord.Embed(description="⚠️  No Queue to clear.", color=0xFF0000))
            return

        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=discord.Embed(description="⚠️  You need to be in the same voice channel as me to use this command.", color=0xFF0000))
            return

        if vc and vc.queue:
            vc.queue.clear()
            await ctx.send(embed=discord.Embed(description="Queue has been cleared.", color=0x1DB954))
        else:
            await ctx.send(embed=discord.Embed(description="No queue to clear.", color=0xFF0000))

    @commands.hybrid_command(name="replay", usage="replay", help="Replays the current song.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def replay(self, ctx: commands.Context):
        vc = ctx.voice_client

        if not vc or not vc.playing:
            await ctx.send(embed=discord.Embed(description="⚠️  I'm not connected to any voice channel.", color=0xFF0000))
            return

        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=discord.Embed(description="⚠️  You need to be in the same voice channel as me to use this command.", color=0xFF0000))
            return

        if vc and vc.playing:
            await vc.seek(0)
            await ctx.send(embed=discord.Embed(description="Replaying the current track.", color=0x1DB954))
        else:
            await ctx.send(embed=discord.Embed(description="No track is currently playing.", color=0xFF0000))

    @commands.hybrid_command(name="join", aliases=["connect"], usage="join", help="Joins the voice channel.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def join(self, ctx: commands.Context):
        if ctx.author.voice:
            await ctx.author.voice.channel.connect(cls=wavelink.Player)
            await ctx.send(embed=discord.Embed(description="Joined the voice channel.", color=0x1DB954))
        else:
            await ctx.send(embed=discord.Embed(description="You need to join a voice channel first.", color=0xFF0000))

    @commands.hybrid_command(name="disconnect", aliases=["dc", "leave"], usage="disconnect", help="Disconnects the bot from the voice channel.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def disconnect(self, ctx: commands.Context):
        vc = ctx.voice_client
        if not vc:
            await ctx.send(embed=discord.Embed(description="⚠️  I'm not connected to any voice channel.", color=0xFF0000))
            return

        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=discord.Embed(description="⚠️  You need to be in the same voice channel as me to use this command.", color=0xFF0000))
            return

        if vc:
            await vc.disconnect()
            await ctx.send(embed=discord.Embed(description="Disconnected from the voice channel.", color=0x1DB954))
        else:
            await ctx.send(embed=discord.Embed(description="Bot is not connected to any voice channel.", color=0xFF0000))

    @commands.hybrid_command(name="seek", usage="seek <percentage>", help="Seeks to a specific percentage of the song.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def seek(self, ctx: commands.Context, percentage: int):
        if not 1 <= percentage <= 100:
            await ctx.send(embed=discord.Embed(description="Please provide a percentage between 1 and 100.", color=0xFF0000))
            return

        vc = ctx.voice_client
        if not vc or not vc.playing:
            await ctx.send(embed=discord.Embed(description="No song is currently playing.", color=0xFF0000))
            return

        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=discord.Embed(description="You need to be in the same voice channel as me to use this command.", color=0xFF0000))
            return

        track = vc.current
        target_position = int(track.length * (percentage / 100))  
        await vc.seek(target_position)

        await ctx.send(embed=discord.Embed(description=f"Seeked to {percentage}% of the current track.", color=0x1DB954))

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = getattr(payload, "player", None)
        if not player:
            return

        track = getattr(player, "current", None) or getattr(payload, "track", None)
        if not track:
            return

        guild = getattr(player, "guild", None)
        guild_id = guild.id if guild else None

        voice_channel = getattr(player, "channel", None)
        if voice_channel:
            try:
                await voice_channel.edit(status=f"🎶 Playing: {track.title}")  # type: ignore
            except Exception:
                pass

        if guild_id:
            if guild_id not in track_histories:
                track_histories[guild_id] = []

            if not track_histories[guild_id] or track_histories[guild_id][-1] != track:
                track_histories[guild_id].append(track)

            if len(track_histories[guild_id]) > 10:
                track_histories[guild_id].pop(0)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = getattr(payload, "player", None)
        if not player:
            return

        voice_channel = getattr(player, "channel", None)
        if voice_channel:
            try:
                await voice_channel.edit(status=None)  # type: ignore
            except Exception:
                pass

        await self.on_track_end(payload)