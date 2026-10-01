import discord
from discord import ui
from typing import Dict, List, Optional
from utils.Tools import *


class HelpDropdown(ui.Select):
    def __init__(self, options: List[discord.SelectOption], placeholder: str = "Choose a Module for Help..."):
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view: HelpContainerView = self.view  # type: ignore
        val = self.values[0]
        if val == "Home":
            view.render_home()
        else:
            view.render_category(val)
        await interaction.response.edit_message(view=view)


class HelpContainerView(ui.LayoutView):
    def __init__(self, mapping: dict, ctx, prefix: str = ">"):
        super().__init__(timeout=180)
        self.mapping = mapping
        self.ctx = ctx
        self.prefix = prefix
        self.categories: Dict[str, dict] = {}

        self._parse_categories()
        self.render_home()

    def _parse_categories(self):
        cogs_to_process = []
        if hasattr(self.mapping, "items"):
            for k, v in self.mapping.items():
                if hasattr(k, "help_custom"):
                    cogs_to_process.append((k, v if isinstance(v, list) else (k.get_commands() if hasattr(k, "get_commands") else [])))
                elif hasattr(v, "help_custom"):
                    cogs_to_process.append((v, v.get_commands() if hasattr(v, "get_commands") else []))
        elif self.ctx and getattr(self.ctx, "bot", None):
            for cog in self.ctx.bot.cogs.values():
                if hasattr(cog, "help_custom"):
                    cogs_to_process.append((cog, cog.get_commands() if hasattr(cog, "get_commands") else []))

        for cog, cmd_list in cogs_to_process:
            try:
                emoji, label, desc = cog.help_custom()
                cmds = [c for c in cmd_list if not getattr(c, "hidden", False)]
                self.categories[label] = {
                    "emoji": emoji,
                    "label": label,
                    "description": desc,
                    "commands": cmds
                }
            except Exception:
                pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ Only the command author can interact with this menu.", ephemeral=True)
            return False
        return True

    def _get_dropdown_options(self, selected: Optional[str] = None) -> List[discord.SelectOption]:
        options = [
            discord.SelectOption(
                label="Home",
                emoji="🏠",
                description="Return to main help overview",
                value="Home",
                default=(selected is None or selected == "Home")
            )
        ]
        for label, data in self.categories.items():
            options.append(
                discord.SelectOption(
                    label=label,
                    emoji=data["emoji"],
                    description=data["description"][:100],
                    value=label,
                    default=(selected == label)
                )
            )
        return options[:25]

    def render_home(self):
        self.clear_items()

        bot_name = self.ctx.bot.user.name if (self.ctx and getattr(self.ctx, "bot", None) and self.ctx.bot.user) else "Astrix"
        total_commands = len(set(self.ctx.bot.walk_commands())) if (self.ctx and getattr(self.ctx, "bot", None)) else 450
        bot_id = self.ctx.bot.user.id if (self.ctx and getattr(self.ctx, "bot", None) and self.ctx.bot.user) else 1526109358474264686
        module_count = len(self.categories)

        header_text = (
            f"### 👑 {bot_name} — Control & Help Center\n"
            f"> Fast, modern & all-in-one Discord bot for Security, Moderation, Music & Management."
        )

        instructions_text = (
            f"**Information & Configuration**\n"
            f"• **Command Prefix:** `{self.prefix}` • **Slash Commands:** Enabled\n"
            f"• **Commands Available:** `{total_commands}` across `{module_count}` modules\n"
            f"• **Bot Developer:** Vinay Kumar (`ASTRIXCODE`)\n"
            f"• **Core Engine:** Astrix Development\n\n"
            f"**How To Navigate**\n"
            f"• Choose any category from the select menu below to view its commands.\n"
            f"• For detailed command syntax & options: `{self.prefix}help <command>`"
        )

        select = HelpDropdown(options=self._get_dropdown_options(selected="Home"))

        home_btn = ui.Button(label="Home", emoji="🏠", style=discord.ButtonStyle.secondary, disabled=True)
        close_btn = ui.Button(label="Close", emoji="🗑️", style=discord.ButtonStyle.danger)

        async def on_close(interaction: discord.Interaction):
            try:
                await interaction.message.delete()
            except Exception:
                pass
        close_btn.callback = on_close

        support_btn = ui.Button(label="Support", style=discord.ButtonStyle.link, url="https://discord.gg/FR9pXG2Mwb")
        invite_btn = ui.Button(
            label="Invite",
            style=discord.ButtonStyle.link,
            url=f"https://discord.com/oauth2/authorize?client_id={bot_id}&permissions=8&scope=bot%20applications.commands"
        )

        container = ui.Container(
            ui.TextDisplay(header_text),
            ui.Separator(),
            ui.TextDisplay(instructions_text),
            ui.ActionRow(select),
            ui.ActionRow(home_btn, close_btn, support_btn, invite_btn)
        )
        self.add_item(container)

    def render_category(self, category_name: str):
        self.clear_items()
        cat_data = self.categories.get(category_name)
        if not cat_data:
            self.render_home()
            return

        emoji = cat_data["emoji"]
        label = cat_data["label"]
        desc = cat_data["description"]
        commands_list = cat_data["commands"]

        header_text = (
            f"### {emoji} {label} Commands\n"
            f"*{desc}*\n"
            f"> Prefix: `{self.prefix}` • Total: `{len(commands_list)}`"
        )

        parts = []
        for cmd in commands_list:
            if cmd.help:
                lines = [l.strip() for l in cmd.help.strip().split("\n") if l.strip()]
                cleaned = []
                for l in lines:
                    c_line = l.replace(" , ", " • ").replace("` , `", "` • `")
                    cleaned.append(c_line)
                parts.append("\n".join(cleaned))
            else:
                clean_name = cmd.name.strip("_")
                parts.append(f"`{self.prefix}{clean_name}`")

        cmd_text = "\n\n".join(parts) if parts else "*No commands available in this module.*"

        footer_text = "*Astrix • Made by Vinay Kumar (ASTRIXCODE)*"

        select = HelpDropdown(options=self._get_dropdown_options(selected=category_name))

        home_btn = ui.Button(label="Home", emoji="🏠", style=discord.ButtonStyle.secondary, disabled=False)
        async def on_home(interaction: discord.Interaction):
            self.render_home()
            await interaction.response.edit_message(view=self)
        home_btn.callback = on_home

        close_btn = ui.Button(label="Close", emoji="🗑️", style=discord.ButtonStyle.danger)
        async def on_close(interaction: discord.Interaction):
            try:
                await interaction.message.delete()
            except Exception:
                pass
        close_btn.callback = on_close

        support_btn = ui.Button(label="Support", style=discord.ButtonStyle.link, url="https://discord.gg/FR9pXG2Mwb")

        container = ui.Container(
            ui.TextDisplay(header_text),
            ui.Separator(),
            ui.TextDisplay(cmd_text),
            ui.Separator(),
            ui.TextDisplay(footer_text),
            ui.ActionRow(select),
            ui.ActionRow(home_btn, close_btn, support_btn)
        )
        self.add_item(container)


# Backwards compatibility alias
View = HelpContainerView
