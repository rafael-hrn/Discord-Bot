import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")


intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

def load_config():
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(data):
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

@bot.event
async def on_ready():
    await bot.load_extension("cogs.league")
    await bot.load_extension("cogs.application")
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync()
    guild = discord.Object(id=600172398045560842)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)
    print(f"✅ Bot online as {bot.user} (ID: {bot.user.id})")

bot.run(TOKEN)
