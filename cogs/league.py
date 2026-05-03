import discord
from discord.ext import commands
from discord import app_commands
import json, os

# ─── Helpers ────────────────────────────────────────────────────────────────

def load_config():
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(data):
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def parse_color(hex_str: str) -> discord.Color:
    try:
        return discord.Color(int(hex_str.strip().lstrip("#"), 16))
    except Exception:
        return discord.Color.dark_grey()

def has_manager_role(interaction: discord.Interaction) -> bool:
    """Returns True if user is admin OR has the configured manager role."""
    if interaction.user.guild_permissions.administrator:
        return True
    cfg = load_config()
    manager_role_id = cfg.get("manager_role")
    if manager_role_id:
        role = interaction.guild.get_role(manager_role_id)
        if role and role in interaction.user.roles:
            return True
    return False

# ─── Embed builder ───────────────────────────────────────────────────────────

def _league_body(league: dict) -> str:
    """Shared description body used by all league embeds."""
    body = (
        f"> ***Leader:*** *{league.get('leader', 'N/A')}*\n"
        f"> ***Officers:*** *{league.get('officers', 'N/A')}*\n"
        f"> ***League Code:*** *{league.get('code', 'N/A')}*\n"
        f"> ***Minimum Threat:*** *{league.get('min_threat', 'N/A')}*\n"
    )
    if league.get("extra_requirement"):
        body += f"> ***Additional Requirement:*** *{league.get('extra_requirement')}*\n"
    body += (
        f"\n"
        f"> ***Raid Tier:*** *{league.get('raid_tier', 'N/A')}*\n"
        f"> ***Raid Time:*** *{league.get('raid_time', 'N/A')}*\n"
        f"\n"
        f"> ***Invasions Rank:*** *{league.get('invasions_rank', 'N/A')}*\n"
        f"> ***Invasions Division:*** *{league.get('invasions_division', 'N/A')}*\n"
        f"> ***Invasions Time:*** *{league.get('invasions_time', 'N/A')}*"
    )
    return body

def build_league_embed(league: dict, league_id: str) -> discord.Embed:
    is_open = league.get("open", False)

    if league.get("color"):
        color = parse_color(league["color"])
    else:
        color = discord.Color.green() if is_open else discord.Color.red()

    embed = discord.Embed(
        title=league.get("name", "League"),
        description=_league_body(league),
        color=color,
    )

    if league.get("banner"):
        embed.set_image(url=league["banner"])
    if league.get("icon"):
        embed.set_thumbnail(url=league["icon"])

    status_text = "Applications: Open" if is_open else "Applications: Closed"
    embed.set_footer(text=f"{status_text} • League ID: {league_id}")
    return embed

def build_info_embed(league: dict, league_id: str) -> discord.Embed:
    """Info-only embed — no application status, no button."""
    if league.get("color"):
        color = parse_color(league["color"])
    else:
        color = discord.Color.blurple()

    embed = discord.Embed(
        title=league.get("name", "League"),
        description=_league_body(league),
        color=color,
    )

    if league.get("banner"):
        embed.set_image(url=league["banner"])
    if league.get("icon"):
        embed.set_thumbnail(url=league["icon"])

    embed.set_footer(text=f"Injustice 2 Mobile • League ID: {league_id}")
    return embed

def build_control_embed(league: dict, league_id: str) -> discord.Embed:
    """Applications control embed with open/close buttons."""
    is_open = league.get("open", False)
    color = discord.Color.green() if is_open else discord.Color.red()

    embed = discord.Embed(
        title=f"⚙️ Applications Control — {league.get('name', 'League')}",
        description=(
            "Use the buttons below to open or close applications for this league.\n"
            "Only members with the designated manager role can use these buttons."
        ),
        color=color,
    )
    embed.add_field(
        name="Current Status",
        value="🟢 **Open** — Players can apply." if is_open else "🔴 **Closed** — Applications are disabled.",
        inline=False,
    )
    embed.set_footer(text=f"League ID: {league_id}")
    return embed

# ─── Views ───────────────────────────────────────────────────────────────────

class LeagueView(discord.ui.View):
    """Apply button shown on the main league embed."""

    def __init__(self, league_id: str):
        super().__init__(timeout=None)
        self.league_id = league_id
        self.update_button()

    def update_button(self):
        self.clear_items()
        cfg = load_config()
        league = cfg.get("leagues", {}).get(self.league_id, {})
        is_open = league.get("open", False)

        btn = discord.ui.Button(
            label="✅ Apply to League" if is_open else "🔒 Applications Closed",
            style=discord.ButtonStyle.success if is_open else discord.ButtonStyle.secondary,
            custom_id=f"apply_{self.league_id}",
            disabled=not is_open,
        )
        btn.callback = self.apply_callback
        self.add_item(btn)

    async def apply_callback(self, interaction: discord.Interaction):
        from cogs.application import ApplicationModal
        cfg = load_config()
        league = cfg.get("leagues", {}).get(self.league_id, {})
        modal = ApplicationModal(league_id=self.league_id, league_name=league.get("name", "League"))
        await interaction.response.send_modal(modal)


class ControlView(discord.ui.View):
    """Open / Close buttons for the control embed."""

    def __init__(self, league_id: str):
        super().__init__(timeout=None)
        self.league_id = league_id

    async def _check_permission(self, interaction: discord.Interaction) -> bool:
        if has_manager_role(interaction):
            return True
        await interaction.response.send_message(
            "❌ You don't have permission to manage applications.", ephemeral=True
        )
        return False

    async def _toggle(self, interaction: discord.Interaction, open_state: bool):
        if not await self._check_permission(interaction):
            return

        cfg = load_config()
        league = cfg.get("leagues", {}).get(self.league_id)
        if not league:
            return await interaction.response.send_message("❌ League not found.", ephemeral=True)

        cfg["leagues"][self.league_id]["open"] = open_state
        save_config(cfg)

        # Update control embed itself
        new_control_embed = build_control_embed(cfg["leagues"][self.league_id], self.league_id)
        await interaction.message.edit(embed=new_control_embed, view=self)

        # Also update the main league embed if it exists
        embed_loc = league.get("embed_message")
        if embed_loc:
            try:
                ch = interaction.guild.get_channel(embed_loc["channel"])
                msg = await ch.fetch_message(embed_loc["message"])
                new_embed = build_league_embed(cfg["leagues"][self.league_id], self.league_id)
                new_view = LeagueView(self.league_id)
                await msg.edit(embed=new_embed, view=new_view)
            except Exception as e:
                print(f"[WARN] Could not update league embed: {e}")

        status = "open 🟢" if open_state else "closed 🔴"
        await interaction.response.send_message(
            f"✅ **{league['name']}** is now **{status}**.", ephemeral=True
        )

    @discord.ui.button(label="🟢 Open Applications", style=discord.ButtonStyle.success, custom_id="ctrl_open")
    async def open_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._toggle(interaction, True)

    @discord.ui.button(label="🔴 Close Applications", style=discord.ButtonStyle.danger, custom_id="ctrl_close")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._toggle(interaction, False)


# ─── Cog ────────────────────────────────────────────────────────────────────

class League(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── Error handler for missing admin ──────────────────────────────────────
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You need **Administrator** permission to use this command.", ephemeral=True
            )

    # ── /set-manager-role ─────────────────────────────────────────────────────
    @app_commands.command(name="set-manager-role", description="Set the role that can open/close applications via the control embed.")
    @app_commands.describe(role="The role to grant application management access")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_manager_role(self, interaction: discord.Interaction, role: discord.Role):
        cfg = load_config()
        cfg["manager_role"] = role.id
        save_config(cfg)
        await interaction.response.send_message(
            f"✅ Manager role set to **{role.name}**. Members with this role can use the control embed.",
            ephemeral=True,
        )

    # ── /configure-league ─────────────────────────────────────────────────────
    @app_commands.command(name="configure-league", description="Create or edit a league configuration.")
    @app_commands.describe(
        league_id="Unique league ID (e.g. end)",
        name="League display name (e.g. [END] THE ENDLESS)",
        leader="Leader mention or name",
        officers="Officers role mention or name",
        code="League code in the game",
        min_threat="Minimum Threat requirement (e.g. 50M)",
        raid_tier="Raid Tier (e.g. 10)",
        raid_time="Raid Time (e.g. 09:00)",
        invasions_rank="Invasions Rank (e.g. LEGENDARY)",
        invasions_division="Invasions Division (e.g. 1/2)",
        invasions_time="Invasions Time (e.g. back-to-back at REFRESH TIME)",
        review_channel="Channel where applications will be sent",
        reviewer_role="Role that can accept or reject applications",
        league_role="Role granted to accepted members",
        color="Embed color in hex (e.g. FF0000). Leave blank for auto.",
        banner="Banner image URL (optional)",
        icon="Icon/logo image URL (optional)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def configure_league(
        self,
        interaction: discord.Interaction,
        league_id: str,
        name: str,
        leader: str,
        officers: str,
        code: str,
        min_threat: str,
        raid_tier: str,
        raid_time: str,
        invasions_rank: str,
        invasions_division: str,
        invasions_time: str,
        review_channel: discord.TextChannel,
        reviewer_role: discord.Role,
        league_role: discord.Role,
        color: str = None,
        banner: str = None,
        icon: str = None,
    ):
        cfg = load_config()
        existing = cfg.get("leagues", {}).get(league_id, {})
        cfg.setdefault("leagues", {})[league_id] = {
            "name": name,
            "leader": leader,
            "officers": officers,
            "code": code,
            "min_threat": min_threat,
            "raid_tier": raid_tier,
            "raid_time": raid_time,
            "invasions_rank": invasions_rank,
            "invasions_division": invasions_division,
            "invasions_time": invasions_time,
            "open": existing.get("open", False),
            "review_channel": review_channel.id,
            "reviewer_role": reviewer_role.id,
            "league_role": league_role.id,
            "color": color,
            "banner": banner,
            "icon": icon,
            "embed_message": existing.get("embed_message", None),
            "control_message": existing.get("control_message", None),
            "info_message": existing.get("info_message", None),
        }
        save_config(cfg)
        await interaction.response.send_message(
            f"✅ League **{name}** (`{league_id}`) configured successfully!", ephemeral=True
        )

    # ── /edit-league ──────────────────────────────────────────────────────────
    @app_commands.command(name="edit-league", description="Edit a single field of an existing league.")
    @app_commands.describe(
        league_id="League ID to edit",
        field="Field to edit",
        value="New value for the field",
    )
    @app_commands.choices(field=[
        app_commands.Choice(name="Name",               value="name"),
        app_commands.Choice(name="Leader",             value="leader"),
        app_commands.Choice(name="Officers",           value="officers"),
        app_commands.Choice(name="League Code",        value="code"),
        app_commands.Choice(name="Minimum Threat",     value="min_threat"),
        app_commands.Choice(name="Raid Tier",          value="raid_tier"),
        app_commands.Choice(name="Raid Time",          value="raid_time"),
        app_commands.Choice(name="Invasions Rank",     value="invasions_rank"),
        app_commands.Choice(name="Invasions Division", value="invasions_division"),
        app_commands.Choice(name="Invasions Time",     value="invasions_time"),
        app_commands.Choice(name="Color (hex)",        value="color"),
        app_commands.Choice(name="Banner URL",         value="banner"),
        app_commands.Choice(name="Icon URL",           value="icon"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def edit_league(
        self,
        interaction: discord.Interaction,
        league_id: str,
        field: app_commands.Choice[str],
        value: str,
    ):
        cfg = load_config()
        league = cfg.get("leagues", {}).get(league_id)
        if not league:
            return await interaction.response.send_message("❌ League not found.", ephemeral=True)

        cfg["leagues"][league_id][field.value] = value
        save_config(cfg)

        # Refresh all posted embeds automatically
        updated = cfg["leagues"][league_id]

        embed_loc = updated.get("embed_message")
        if embed_loc:
            try:
                ch = interaction.guild.get_channel(embed_loc["channel"])
                msg = await ch.fetch_message(embed_loc["message"])
                await msg.edit(embed=build_league_embed(updated, league_id), view=LeagueView(league_id))
            except Exception as e:
                print(f"[WARN] Could not update league embed: {e}")

        info_loc = updated.get("info_message")
        if info_loc:
            try:
                ch = interaction.guild.get_channel(info_loc["channel"])
                msg = await ch.fetch_message(info_loc["message"])
                await msg.edit(embed=build_info_embed(updated, league_id))
            except Exception as e:
                print(f"[WARN] Could not update info embed: {e}")

        ctrl_loc = updated.get("control_message")
        if ctrl_loc:
            try:
                ch = interaction.guild.get_channel(ctrl_loc["channel"])
                msg = await ch.fetch_message(ctrl_loc["message"])
                await msg.edit(embed=build_control_embed(updated, league_id), view=ControlView(league_id))
            except Exception as e:
                print(f"[WARN] Could not update control embed: {e}")

        await interaction.response.send_message(
            f"✅ **{field.name}** updated to `{value}` for league `{league_id}`.\n"
            f"All posted embeds have been refreshed automatically.",
            ephemeral=True,
        )

    # ── /delete-league ────────────────────────────────────────────────────────
    @app_commands.command(name="delete-league", description="Permanently delete a league and remove its posted embeds.")
    @app_commands.describe(league_id="League ID to delete")
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_league(self, interaction: discord.Interaction, league_id: str):
        cfg = load_config()
        league = cfg.get("leagues", {}).get(league_id)
        if not league:
            return await interaction.response.send_message("❌ League not found.", ephemeral=True)

        league_name = league.get("name", league_id)

        # Try to delete all posted messages
        for key in ("embed_message", "info_message", "control_message"):
            loc = league.get(key)
            if loc:
                try:
                    ch = interaction.guild.get_channel(loc["channel"])
                    msg = await ch.fetch_message(loc["message"])
                    await msg.delete()
                except Exception as e:
                    print(f"[WARN] Could not delete message ({key}): {e}")

        del cfg["leagues"][league_id]
        save_config(cfg)

        await interaction.response.send_message(
            f"🗑️ League **{league_name}** (`{league_id}`) has been permanently deleted.\n"
            f"All associated embeds have been removed.",
            ephemeral=True,
        )

    # ── /transfer-league-id ───────────────────────────────────────────────────
    @app_commands.command(name="transfer-league-id", description="Rename a league's ID to a new one.")
    @app_commands.describe(
        old_id="Current league ID",
        new_id="New league ID to use",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def transfer_league_id(self, interaction: discord.Interaction, old_id: str, new_id: str):
        cfg = load_config()
        league = cfg.get("leagues", {}).get(old_id)
        if not league:
            return await interaction.response.send_message("❌ League not found.", ephemeral=True)
        if new_id in cfg.get("leagues", {}):
            return await interaction.response.send_message(
                f"❌ A league with ID `{new_id}` already exists.", ephemeral=True
            )

        # Move data to new key
        cfg["leagues"][new_id] = cfg["leagues"].pop(old_id)
        save_config(cfg)

        updated = cfg["leagues"][new_id]

        # Refresh all embeds with new league_id in footer
        embed_loc = updated.get("embed_message")
        if embed_loc:
            try:
                ch = interaction.guild.get_channel(embed_loc["channel"])
                msg = await ch.fetch_message(embed_loc["message"])
                await msg.edit(embed=build_league_embed(updated, new_id), view=LeagueView(new_id))
            except Exception as e:
                print(f"[WARN] Could not update league embed: {e}")

        info_loc = updated.get("info_message")
        if info_loc:
            try:
                ch = interaction.guild.get_channel(info_loc["channel"])
                msg = await ch.fetch_message(info_loc["message"])
                await msg.edit(embed=build_info_embed(updated, new_id))
            except Exception as e:
                print(f"[WARN] Could not update info embed: {e}")

        ctrl_loc = updated.get("control_message")
        if ctrl_loc:
            try:
                ch = interaction.guild.get_channel(ctrl_loc["channel"])
                msg = await ch.fetch_message(ctrl_loc["message"])
                await msg.edit(embed=build_control_embed(updated, new_id), view=ControlView(new_id))
            except Exception as e:
                print(f"[WARN] Could not update control embed: {e}")

        await interaction.response.send_message(
            f"✅ League ID changed from `{old_id}` → `{new_id}` successfully.\n"
            f"All posted embeds have been updated.",
            ephemeral=True,
        )

    # ── /post-league ──────────────────────────────────────────────────────────
    @app_commands.command(name="post-league", description="Post the league embed (with apply button) in this channel.")
    @app_commands.describe(league_id="League ID to post")
    @app_commands.checks.has_permissions(administrator=True)
    async def post_league(self, interaction: discord.Interaction, league_id: str):
        cfg = load_config()
        league = cfg.get("leagues", {}).get(league_id)
        if not league:
            return await interaction.response.send_message("❌ League not found.", ephemeral=True)

        embed = build_league_embed(league, league_id)
        view = LeagueView(league_id)
        await interaction.response.send_message("📤 Posting embed...", ephemeral=True)
        msg = await interaction.channel.send(embed=embed, view=view)

        cfg["leagues"][league_id]["embed_message"] = {"channel": interaction.channel.id, "message": msg.id}
        save_config(cfg)

    # ── /post-all-leagues ─────────────────────────────────────────────────────
    @app_commands.command(name="post-all-leagues", description="Post all configured leagues in this channel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def post_all_leagues(self, interaction: discord.Interaction):
        cfg = load_config()
        leagues = cfg.get("leagues", {})
        if not leagues:
            return await interaction.response.send_message("❌ No leagues configured yet.", ephemeral=True)

        await interaction.response.send_message(
            f"📤 Posting **{len(leagues)}** league(s)...", ephemeral=True
        )

        for league_id, league in leagues.items():
            embed = build_league_embed(league, league_id)
            view = LeagueView(league_id)
            msg = await interaction.channel.send(embed=embed, view=view)
            cfg["leagues"][league_id]["embed_message"] = {"channel": interaction.channel.id, "message": msg.id}

        save_config(cfg)

    # ── /post-info ────────────────────────────────────────────────────────────
    @app_commands.command(name="post-info", description="Post a league info embed (no apply button).")
    @app_commands.describe(league_id="League ID to post")
    @app_commands.checks.has_permissions(administrator=True)
    async def post_info(self, interaction: discord.Interaction, league_id: str):
        cfg = load_config()
        league = cfg.get("leagues", {}).get(league_id)
        if not league:
            return await interaction.response.send_message("❌ League not found.", ephemeral=True)

        embed = build_info_embed(league, league_id)
        await interaction.response.send_message("📤 Posting info embed...", ephemeral=True)
        msg = await interaction.channel.send(embed=embed)

        cfg["leagues"][league_id]["info_message"] = {"channel": interaction.channel.id, "message": msg.id}
        save_config(cfg)

    # ── /post-control ─────────────────────────────────────────────────────────
    @app_commands.command(name="post-control", description="Post the applications control embed for a league.")
    @app_commands.describe(league_id="League ID")
    @app_commands.checks.has_permissions(administrator=True)
    async def post_control(self, interaction: discord.Interaction, league_id: str):
        cfg = load_config()
        league = cfg.get("leagues", {}).get(league_id)
        if not league:
            return await interaction.response.send_message("❌ League not found.", ephemeral=True)

        embed = build_control_embed(league, league_id)
        view = ControlView(league_id)
        await interaction.response.send_message("📤 Posting control embed...", ephemeral=True)
        msg = await interaction.channel.send(embed=embed, view=view)

        cfg["leagues"][league_id]["control_message"] = {"channel": interaction.channel.id, "message": msg.id}
        save_config(cfg)

    # ── /open-league & /close-league (admin fallback via slash) ───────────────
    @app_commands.command(name="open-league", description="Open applications for a league.")
    @app_commands.describe(league_id="League ID")
    @app_commands.checks.has_permissions(administrator=True)
    async def open_league(self, interaction: discord.Interaction, league_id: str):
        await self._toggle_league(interaction, league_id, True)

    @app_commands.command(name="close-league", description="Close applications for a league.")
    @app_commands.describe(league_id="League ID")
    @app_commands.checks.has_permissions(administrator=True)
    async def close_league(self, interaction: discord.Interaction, league_id: str):
        await self._toggle_league(interaction, league_id, False)

    async def _toggle_league(self, interaction: discord.Interaction, league_id: str, open_state: bool):
        cfg = load_config()
        league = cfg.get("leagues", {}).get(league_id)
        if not league:
            return await interaction.response.send_message("❌ League not found.", ephemeral=True)

        cfg["leagues"][league_id]["open"] = open_state
        save_config(cfg)

        # Update main embed
        embed_loc = league.get("embed_message")
        if embed_loc:
            try:
                ch = interaction.guild.get_channel(embed_loc["channel"])
                msg = await ch.fetch_message(embed_loc["message"])
                await msg.edit(embed=build_league_embed(cfg["leagues"][league_id], league_id), view=LeagueView(league_id))
            except Exception as e:
                print(f"[WARN] Could not update league embed: {e}")

        # Update control embed
        ctrl_loc = league.get("control_message")
        if ctrl_loc:
            try:
                ch = interaction.guild.get_channel(ctrl_loc["channel"])
                msg = await ch.fetch_message(ctrl_loc["message"])
                await msg.edit(embed=build_control_embed(cfg["leagues"][league_id], league_id), view=ControlView(league_id))
            except Exception as e:
                print(f"[WARN] Could not update control embed: {e}")

        status = "open 🟢" if open_state else "closed 🔴"
        await interaction.response.send_message(
            f"✅ League **{league['name']}** is now **{status}**.", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(League(bot))
