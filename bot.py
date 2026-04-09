import discord
import subprocess
import os
from dotenv import load_dotenv
from mcstatus import JavaServer

# --- SECURE CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
SCRIPT_PATH = os.getenv('SCRIPT_PATH', '/home/minecraft/firewall_rules.sh')
try:
    ALLOWED_CHANNEL_ID = int(os.getenv('ALLOWED_CHANNEL_ID', '0'))
except ValueError:
    print("WARNING: ALLOWED_CHANNEL_ID is not a valid integer — defaulting to 0 (all channels)")
    ALLOWED_CHANNEL_ID = 0
ADMIN_ROLE_NAME = os.getenv('ADMIN_ROLE_NAME', '')
# ----------------------------

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


def _has_permission(message):
    """Returns True if the message comes from the allowed channel and author has the admin role."""
    if ALLOWED_CHANNEL_ID and message.channel.id != ALLOWED_CHANNEL_ID:
        return False
    if ADMIN_ROLE_NAME:
        role_names = [r.name for r in getattr(message.author, 'roles', [])]
        if ADMIN_ROLE_NAME not in role_names:
            return False
    return True


@client.event
async def on_ready():
    print(f'🤖 Zero-Trust Gatekeeper activated as {client.user}')


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    msg = message.content.lower()

    if not msg.startswith('!'):
        return

    if not _has_permission(message):
        return

    # --- COMMAND 1: !IP ---
    if msg == '!ip':
        await message.channel.send("🕵️‍♂️ Checking IPs and updating firewall... Please wait.")
        try:
            result = subprocess.run(
                ['/bin/bash', SCRIPT_PATH],
                capture_output=True, text=True, timeout=30
            )
            log_result = subprocess.run(
                ['tail', '-n', '2', '/var/log/minecraft_firewall_update.log'],
                capture_output=True, text=True
            )
            log_output = log_result.stdout.strip()
            await message.channel.send(f"✅ **Done!** Firewall rules updated.\n```{log_output}```")
        except subprocess.TimeoutExpired:
            await message.channel.send("❌ Firewall script timed out.")
        except Exception as e:
            await message.channel.send(f"❌ Error executing firewall script: {e}")

    # --- COMMAND 2: !STATUS ---
    elif msg == '!status':
        async with message.channel.typing():
            try:
                server = JavaServer.lookup("localhost:25565")
                status = server.status()

                if status.players.sample:
                    player_names = [p.name for p in status.players.sample]
                    names_str = "**" + ", ".join(player_names) + "**"
                else:
                    names_str = "Nobody online"

                await message.channel.send(
                    f"🟢 **ONLINE**\n"
                    f"👥 Players: `{status.players.online}/{status.players.max}`\n"
                    f"📜 List: {names_str}\n"
                    f"📶 Local Latency: `{round(status.latency)}ms`"
                )
            except Exception:
                await message.channel.send("🔴 **OFFLINE** (Server in maintenance or restarting)")

    # --- COMMAND 3: !RESTART ---
    elif msg == '!restart':
        await message.channel.send("🔄 Sending restart signal to the Minecraft server...")
        try:
            result = subprocess.run(
                ['systemctl', 'restart', 'minecraft'],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                await message.channel.send("✅ **Restart command sent.** Server should be back shortly.")
            else:
                await message.channel.send(f"❌ Restart failed:\n```{result.stderr.strip()}```")
        except subprocess.TimeoutExpired:
            await message.channel.send("❌ Restart command timed out.")
        except Exception as e:
            await message.channel.send(f"❌ Error sending restart: {e}")

    # --- COMMAND 4: !HELP ---
    elif msg == '!help':
        await message.channel.send(
            "**Available commands:**\n"
            "`!ip` — Resolve DDNS and update firewall rules\n"
            "`!status` — Check if the server is online\n"
            "`!restart` — Restart the Minecraft systemd service\n"
            "`!help` — Show this message"
        )


if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN not found in .env file")
    else:
        client.run(TOKEN)
