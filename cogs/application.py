import discord
from discord.ext import commands
import json, os, asyncio

# ─── Helpers ────────────────────────────────────────────────────────────────

def load_config():
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# ─── Application Modal ───────────────────────────────────────────────────────

class ApplicationModal(discord.ui.Modal):

    ign = discord.ui.TextInput(
        label="In-Game Name (IGN)",
        placeholder="Your exact name in Injustice 2 Mobile",
        max_length=30,
    )
    ttv = discord.ui.TextInput(
        label="Total Threat Value (TTV)",
        placeholder="e.g. 20M",
        max_length=30,
    )
    invasions_time = discord.ui.TextInput(
        label="Invasions Time Suitable?",
        placeholder="Will you be available at this time?",
        max_length=30,
    )
    raid_time = discord.ui.TextInput(
        label="Raid Time Suitable?",
        placeholder="Will you be available at this time?",
        max_length=30,
    )
    cooldown = discord.ui.TextInput(
        label="Cooldown? If yes, when does it end?",
        placeholder="e.g. 12 hours",
        max_length=30,
    )

    def __init__(self, league_id: str, league_name: str):
        super().__init__(title=f"Application — {league_name}")
        self.league_id = league_id
        self.league_name = league_name

    async def on_submit(self, interaction: discord.Interaction):
        from settings import SCREENSHOT_CHANNEL_ID, APPLICANT_ROLE_ID

        self.interaction_data = {
            "ign": self.ign.value,
            "ttv": self.ttv.value,
            "invasions_time": self.invasions_time.value,
            "raid_time": self.raid_time.value,
            "cooldown": self.cooldown.value,
        }

        screenshot_channel = interaction.guild.get_channel(SCREENSHOT_CHANNEL_ID)
        if not screenshot_channel:
            await interaction.response.send_message(
                "❌ Screenshot channel not found. Please contact an administrator.", ephemeral=True
            )
            return

        # Grant applicant role so they can see the screenshot channel
        applicant = interaction.user
        role_granted = False
        if APPLICANT_ROLE_ID:
            role = interaction.guild.get_role(APPLICANT_ROLE_ID)
            if role and role not in applicant.roles:
                try:
                    await applicant.add_roles(role, reason="Applying to league — screenshot access")
                    role_granted = True
                except discord.Forbidden:
                    pass

        await interaction.response.send_message(
            f"✅ Almost done! Head over to {screenshot_channel.mention} and send your screenshot.",
            ephemeral=True,
        )

        prompt_msg = await screenshot_channel.send(
            f"{applicant.mention}\n"
            "• To complete your application, send a screenshot of your roster in this channel right now. "
            "Make sure your **name** and **threat value** are visible.\n"
            "• Your application will be reviewed once we receive your roster image. "
            "You have **10 minutes** to send the image."
        )

        # Collect ALL images sent by the applicant within 10 minutes
        collected_images: list[discord.Message] = []

        def check(m: discord.Message):
            return (
                m.author.id == applicant.id
                and m.channel.id == screenshot_channel.id
                and len(m.attachments) > 0
                and m.attachments[0].content_type
                and m.attachments[0].content_type.startswith("image/")
            )

        # Wait for at least the first image
        try:
            first = await interaction.client.wait_for("message", check=check, timeout=600)
            collected_images.append(first)
        except Exception:
            await prompt_msg.delete()
            await screenshot_channel.send(
                f"{applicant.mention} ⏰ Time expired! Your application was cancelled. "
                "Click the Apply button again to retry."
            )
            # Remove applicant role if it was granted
            if role_granted:
                try:
                    role = interaction.guild.get_role(APPLICANT_ROLE_ID)
                    if role:
                        await applicant.remove_roles(role, reason="Application timed out")
                except Exception:
                    pass
            return

        # Give a short window (15s) to collect any additional screenshots
        try:
            while True:
                extra = await asyncio.wait_for(
                    interaction.client.wait_for("message", check=check),
                    timeout=15,
                )
                collected_images.append(extra)
        except asyncio.TimeoutError:
            pass

        # Collect all image URLs
        image_urls = []
        for m in collected_images:
            for att in m.attachments:
                if att.content_type and att.content_type.startswith("image/"):
                    image_urls.append(att.url)

        await prompt_msg.delete()

        await self._submit_application(interaction, screenshot_channel, image_urls)

    async def _submit_application(
        self,
        interaction: discord.Interaction,
        screenshot_channel: discord.TextChannel,
        image_urls: list[str],
    ):
        cfg = load_config()
        league = cfg.get("leagues", {}).get(self.league_id, {})

        review_channel_id = league.get("review_channel")
        reviewer_role_id = league.get("reviewer_role")

        if not review_channel_id:
            await screenshot_channel.send(
                f"{interaction.user.mention} ❌ Review channel not configured. Contact an administrator."
            )
            return

        review_channel = interaction.guild.get_channel(review_channel_id)
        if not review_channel:
            await screenshot_channel.send(
                f"{interaction.user.mention} ❌ Review channel not found. Contact an administrator."
            )
            return

        applicant = interaction.user
        d = self.interaction_data

        embed = discord.Embed(
            title=f"{self.league_name}",
            description=(
                f"**User:** {applicant.mention}\n"
                f"**IGN:** {d['ign']}\n"
                f"**Threat:** {d['ttv']}\n"
                f"\n"
                f"**Invasions Time Suitable:** {d['invasions_time']}\n"
                f"**Raid Time Suitable:** {d['raid_time']}\n"
                f"**Cooldown:** {d['cooldown']}\n"
                f"\n"
                f"**Decision:**"
            ),
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=applicant.display_avatar.url)
        if image_urls:
            embed.set_image(url=image_urls[0])
        embed.set_footer(text=f"Applicant ID: {applicant.id} • League: {self.league_id}")

        reviewer_mention = f"<@&{reviewer_role_id}>" if reviewer_role_id else ""

        view = ReviewView(
            applicant_id=applicant.id,
            league_id=self.league_id,
            league_name=self.league_name,
            screenshot_channel_id=screenshot_channel.id,
        )

        await review_channel.send(
            content=f"{reviewer_mention} — New application received!",
            embed=embed,
            view=view,
        )

        # Send extra screenshots as follow-up embeds in review channel
        for url in image_urls[1:]:
            extra_embed = discord.Embed(color=discord.Color.gold())
            extra_embed.set_image(url=url)
            extra_embed.set_footer(text=f"Additional screenshot — {applicant.display_name}")
            await review_channel.send(embed=extra_embed)

        # Confirmation in screenshot channel
        await screenshot_channel.send(
            f"{applicant.mention} ✅ Your application to **{self.league_name}** has been submitted! "
            "Please wait for the leaders to review it. You will be notified once a decision is made."
        )


# ─── Review View (Accept / Reject) ──────────────────────────────────────────

class ReviewView(discord.ui.View):
    def __init__(
        self,
        applicant_id: int,
        league_id: str,
        league_name: str,
        screenshot_channel_id: int,
    ):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.league_id = league_id
        self.league_name = league_name
        self.screenshot_channel_id = screenshot_channel_id

    async def _has_permission(self, interaction: discord.Interaction) -> bool:
        cfg = load_config()
        league = cfg.get("leagues", {}).get(self.league_id, {})
        reviewer_role_id = league.get("reviewer_role")
        if not reviewer_role_id:
            return interaction.user.guild_permissions.administrator
        role = interaction.guild.get_role(reviewer_role_id)
        return role in interaction.user.roles or interaction.user.guild_permissions.administrator

    def _build_decided_embed(self, original_embed: discord.Embed, decision_text: str, color: discord.Color) -> discord.Embed:
        new_desc = original_embed.description.replace(
            "**Decision:**",
            f"**Decision:** {decision_text}"
        )
        original_embed.description = new_desc
        original_embed.color = color
        return original_embed

    async def _remove_applicant_role(self, guild: discord.Guild, applicant: discord.Member):
        """Remove applicant role after decision is made."""
        from settings import APPLICANT_ROLE_ID
        if not APPLICANT_ROLE_ID:
            return
        role = guild.get_role(APPLICANT_ROLE_ID)
        if role and role in applicant.roles:
            try:
                await applicant.remove_roles(role, reason="Application decided")
            except Exception as e:
                print(f"[WARN] Could not remove applicant role: {e}")

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success, custom_id="review_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._has_permission(interaction):
            return await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)

        cfg = load_config()
        league = cfg.get("leagues", {}).get(self.league_id, {})
        league_code = league.get("code", "N/A")
        league_role_id = league.get("league_role")

        applicant = interaction.guild.get_member(self.applicant_id)
        if not applicant:
            return await interaction.response.send_message("❌ Applicant not found in the server.", ephemeral=True)

        # Add league role, skip if already has it
        role_warning = ""
        if league_role_id:
            role = interaction.guild.get_role(league_role_id)
            if role:
                if role in applicant.roles:
                    role_warning = f"\nℹ️ Member already has the **{role.name}** role."
                else:
                    bot_member = interaction.guild.get_member(interaction.client.user.id)
                    bot_top_role = bot_member.top_role if bot_member else None
                    if bot_top_role and bot_top_role > role:
                        try:
                            await applicant.add_roles(role, reason=f"Accepted into {self.league_name}")
                        except discord.Forbidden:
                            role_warning = "\n⚠️ Could not add role — check bot permissions in Server Settings."
                    else:
                        role_warning = f"\n⚠️ Could not add role **{role.name}** — move the bot's role above it in Server Settings → Roles."

        # Update embed
        decided_embed = self._build_decided_embed(
            interaction.message.embeds[0],
            f"Accepted by {interaction.user.mention}",
            discord.Color.green(),
        )
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(embed=decided_embed, view=self)

        # Remove applicant role
        await self._remove_applicant_role(interaction.guild, applicant)

        # Notify in screenshot channel
        screenshot_channel = interaction.guild.get_channel(self.screenshot_channel_id)
        accept_msg = (
            f"{applicant.mention} Your application to **{self.league_name}** has been **accepted**!\n"
            f"📋 League Code: `{league_code}`\n"
            "• Welcome to the team! An officer will introduce you to the league channels very soon. "
            "If you need help, contact the leader."
        )
        if screenshot_channel:
            await screenshot_channel.send(accept_msg)

        await interaction.response.send_message(
            f"✅ Application accepted.{role_warning}", ephemeral=True
        )

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger, custom_id="review_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._has_permission(interaction):
            return await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)

        await interaction.response.send_modal(RejectModal(
            applicant_id=self.applicant_id,
            league_name=self.league_name,
            league_id=self.league_id,
            screenshot_channel_id=self.screenshot_channel_id,
            parent_view=self,
        ))


class RejectModal(discord.ui.Modal, title="Reason for Rejection"):
    reason = discord.ui.TextInput(
        label="Reason (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="e.g. Threat value below the minimum requirement...",
        required=False,
        max_length=300,
    )

    def __init__(
        self,
        applicant_id: int,
        league_name: str,
        league_id: str,
        screenshot_channel_id: int,
        parent_view: ReviewView,
    ):
        super().__init__()
        self.applicant_id = applicant_id
        self.league_name = league_name
        self.league_id = league_id
        self.screenshot_channel_id = screenshot_channel_id
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        applicant = interaction.guild.get_member(self.applicant_id)
        reason_text = self.reason.value.strip() if self.reason.value else None

        # Update embed
        decided_embed = self.parent_view._build_decided_embed(
            interaction.message.embeds[0],
            f"Rejected by {interaction.user.mention}" + (f" — *{reason_text}*" if reason_text else ""),
            discord.Color.red(),
        )
        for child in self.parent_view.children:
            child.disabled = True
        await interaction.message.edit(embed=decided_embed, view=self.parent_view)

        # Remove applicant role
        if applicant:
            await self.parent_view._remove_applicant_role(interaction.guild, applicant)

        # Send rejection message in screenshot channel
        reject_msg = (
            f"{applicant.mention if applicant else 'Applicant'} "
            f"Unfortunately your application to **{self.league_name}** has been **rejected**."
            + (f"\n**Reason:** {reason_text}" if reason_text else "")
            + "\nYou may try another league or try again in the future!"
        )
        screenshot_channel = interaction.guild.get_channel(self.screenshot_channel_id)
        if screenshot_channel:
            await screenshot_channel.send(reject_msg)

        await interaction.response.send_message("❌ Application rejected.", ephemeral=True)


# ─── Cog ────────────────────────────────────────────────────────────────────

class Application(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


async def setup(bot):
    await bot.add_cog(Application(bot))
