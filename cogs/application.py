import discord
from discord.ext import commands
import json, os

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
        from settings import SCREENSHOT_CHANNEL_ID

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

        await interaction.response.send_message(
            f"✅ Almost done! Head over to {screenshot_channel.mention} and send your screenshot.",
            ephemeral=True,
        )

        prompt_msg = await screenshot_channel.send(
            f"{interaction.user.mention}\n"
            "• To complete your application, send a screenshot of your roster in this channel right now. "
            "Make sure your **name** and **threat value** are visible.\n"
            "• Your application will be reviewed once we receive your roster image. "
            "You have **10 minutes** to send the image.\n"
            "• This message will be deleted after you send the screenshot."
        )

        # Collect ALL images sent by the applicant within 10 minutes
        collected_images: list[discord.Message] = []

        def check(m: discord.Message):
            return (
                m.author.id == interaction.user.id
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
                f"{interaction.user.mention} ⏰ Time expired! Your application was cancelled. "
                "Click the Apply button again to retry.",
                delete_after=15,
            )
            return

        # Give a short window (15s) to collect any additional screenshots
        import asyncio
        try:
            while True:
                extra = await asyncio.wait_for(
                    interaction.client.wait_for("message", check=check),
                    timeout=15,
                )
                collected_images.append(extra)
        except asyncio.TimeoutError:
            pass  # No more images, proceed

        # Collect all image URLs before deleting the messages
        image_urls = []
        for m in collected_images:
            for att in m.attachments:
                if att.content_type and att.content_type.startswith("image/"):
                    image_urls.append(att.url)

        await prompt_msg.delete()

        await self._submit_application(interaction, screenshot_channel, collected_images, image_urls)

    async def _submit_application(
        self,
        interaction: discord.Interaction,
        screenshot_channel: discord.TextChannel,
        screenshot_messages: list[discord.Message],
        image_urls: list[str],
    ):
        cfg = load_config()
        league = cfg.get("leagues", {}).get(self.league_id, {})

        review_channel_id = league.get("review_channel")
        reviewer_role_id = league.get("reviewer_role")

        if not review_channel_id:
            for m in screenshot_messages:
                await m.delete()
            await screenshot_channel.send(
                f"{interaction.user.mention} ❌ Review channel not configured. Contact an administrator.",
                delete_after=15,
            )
            return

        review_channel = interaction.guild.get_channel(review_channel_id)
        if not review_channel:
            for m in screenshot_messages:
                await m.delete()
            await screenshot_channel.send(
                f"{interaction.user.mention} ❌ Review channel not found. Contact an administrator.",
                delete_after=15,
            )
            return

        applicant = interaction.user
        d = self.interaction_data

        # Main application embed — first image as embed image
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

        # Store screenshot message IDs so they can be deleted after decision
        screenshot_msg_ids = [
            {"channel": screenshot_channel.id, "message": m.id}
            for m in screenshot_messages
        ]

        view = ReviewView(
            applicant_id=applicant.id,
            league_id=self.league_id,
            league_name=self.league_name,
            screenshot_channel_id=screenshot_channel.id,
            screenshot_msg_ids=screenshot_msg_ids,
        )

        review_msg = await review_channel.send(
            content=f"{reviewer_mention} — New application received!",
            embed=embed,
            view=view,
        )

        # Send any extra screenshots as follow-up messages in the review channel
        for url in image_urls[1:]:
            extra_embed = discord.Embed(color=discord.Color.gold())
            extra_embed.set_image(url=url)
            extra_embed.set_footer(text=f"Additional screenshot — {applicant.display_name}")
            await review_channel.send(embed=extra_embed)

        # Confirmation in screenshot channel — screenshots remain visible until decision
        await screenshot_channel.send(
            f"{applicant.mention} ✅ Your application to **{self.league_name}** has been submitted!\n"
            "• Please wait for the leaders to review it. You will be notified once a decision is made.\n"
            "• This message will be deleted in 30 seconds.",
            delete_after=30,
        )


# ─── Review View (Accept / Reject) ──────────────────────────────────────────

class ReviewView(discord.ui.View):
    def __init__(
        self,
        applicant_id: int,
        league_id: str,
        league_name: str,
        screenshot_channel_id: int,
        screenshot_msg_ids: list[dict],
    ):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.league_id = league_id
        self.league_name = league_name
        self.screenshot_channel_id = screenshot_channel_id
        self.screenshot_msg_ids = screenshot_msg_ids  # [{"channel": id, "message": id}, ...]

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

    async def _delete_screenshots(self, guild: discord.Guild):
        """Delete all applicant screenshots from the screenshot channel."""
        for loc in self.screenshot_msg_ids:
            try:
                ch = guild.get_channel(loc["channel"])
                if ch:
                    msg = await ch.fetch_message(loc["message"])
                    await msg.delete()
            except Exception as e:
                print(f"[WARN] Could not delete screenshot message: {e}")

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

        # Delete screenshots now that decision is made
        await self._delete_screenshots(interaction.guild)

        # Notify applicant in screenshot channel
        screenshot_channel = interaction.guild.get_channel(self.screenshot_channel_id)
        accept_msg = (
            f"{applicant.mention}, your application to **{self.league_name}** has been **accepted**!\n"
            f"• Welcome to the team! An officer will introduce you the league channels very soon. If you need help, contact the leader."
            f"📋 League Code: `{league_code}`\n"
        )
        if screenshot_channel:
            await screenshot_channel.send(accept_msg)
        else:
            try:
                await applicant.send(accept_msg)
            except discord.Forbidden:
                pass

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
            screenshot_msg_ids=self.screenshot_msg_ids,
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
        screenshot_msg_ids: list[dict],
        parent_view: ReviewView,
    ):
        super().__init__()
        self.applicant_id = applicant_id
        self.league_name = league_name
        self.league_id = league_id
        self.screenshot_channel_id = screenshot_channel_id
        self.screenshot_msg_ids = screenshot_msg_ids
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

        # Delete screenshots now that decision is made
        await self.parent_view._delete_screenshots(interaction.guild)

        reject_msg = (
            f"{applicant.mention if applicant else 'Applicant'} "
            f"Unfortunately your application to **{self.league_name}** has been **rejected**.\n"
            + (f"• **Reason:** {reason_text}\n" if reason_text else "")
            + "• You may try for another league or try again in the future!"
        )

        # Try DM first, fall back to screenshot channel
        dm_sent = False
        if applicant:
            try:
                await applicant.send(reject_msg)
                dm_sent = True
            except discord.Forbidden:
                pass

        if not dm_sent:
            screenshot_channel = interaction.guild.get_channel(self.screenshot_channel_id)
            if screenshot_channel:
                await screenshot_channel.send(reject_msg, delete_after=30)

        await interaction.response.send_message("❌ Application rejected.", ephemeral=True)


# ─── Cog ────────────────────────────────────────────────────────────────────

class Application(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


async def setup(bot):
    await bot.add_cog(Application(bot))
