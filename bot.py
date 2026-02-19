import discord
import subprocess
import os
from dotenv import load_dotenv
from mcstatus import JavaServer

# --- SECURE CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
SCRIPT_PATH = os.getenv('SCRIPT_PATH', '/home/minecraft/firewall_rules.sh')
# ----------------------------

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'🤖 Zero-Trust Gatekeeper activated as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    msg = message.content.lower()

    # --- COMMAND 1: !IP ---
    if msg == '!ip':
        await message.channel.send("🕵️‍♂️ Checking IPs and updating firewall... Please wait.")
        try:
            subprocess.run(['/bin/bash', SCRIPT_PATH], capture_output=True, text=True)
            log_output = subprocess.getoutput(f"tail -n 2 /var/log/minecraft_firewall_update.log")
            await message.channel.send(f"✅ **Done!** Firewall rules updated.\n```{log_output}```")
        except Exception as e:
            await message.channel.send(f"❌ Error executing Bash script: {e}")

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
            except Exception as e:
                await message.channel.send("🔴 **OFFLINE** (Server in maintenance or restarting)")

if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN not found in .env file")
    else:
        client.run(TOKEN)
