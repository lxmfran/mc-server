## Automated MC Server with DDNS and Firewall Handling

## Project Description
This project implements a dynamic perimeter security architecture for Linux servers (VPS).
It combines a Python server wrapper, an asynchronous Discord bot, and a UFW firewall script
to restrict Minecraft access exclusively to whitelisted players whose current IP matches their
registered DDNS domain.

---

## Architecture

```
Discord Bot (bot.py)
    |
    +-- !ip       -> runs firewall_rules.sh -> updates UFW allow rules
    +-- !status   -> polls Minecraft server via mcstatus
    +-- !restart  -> systemctl restart minecraft
    +-- !help     -> lists available commands

Minecraft Wrapper (minecraft_server.py)
    |
    +-- Starts PaperMC with Aikar JVM flags
    +-- Monitors stdout in a background thread
    +-- Verifies player identity on login (DDNS -> IP check)
    +-- Handles in-game chat commands: !ping !status !tps !help
    +-- Manages a per-player waypoint system (saved to waypoints.json)
    +-- Auto-restarts on crash (up to 10 times; resets after stable uptime)
    +-- Periodic world backups (keeps last 5)

Firewall Script (firewall_rules.sh)
    |
    +-- Resolves each DDNS domain with dig
    +-- Adds UFW allow rules for current IPs
    +-- Removes obsolete rules for IPs no longer in use
```

---

## Tech Stack
* **Cloud Infrastructure:** Linux (Ubuntu VPS)
* **Security & Networking:** UFW, TCP/IP, DDNS, socket-based IP verification
* **Automation:** Python (discord.py, mcstatus, psutil, python-dotenv), Bash
* **Architecture:** Threaded stdout monitoring; async Discord bot

---

## Installation & Deployment

1. Clone this repository.
2. Install Python dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in all values.
4. Configure allowed DDNS domains in the `PLAYER_DOMAINS` env var (see `.env.example`).
5. Ensure `dnsutils` is installed for the firewall script: `apt install dnsutils`
6. Run the bot and server wrapper independently, or as systemd services (recommended).

### Environment Variables (.env)

| Variable            | Required | Description                                      |
|---------------------|----------|--------------------------------------------------|
| DISCORD_TOKEN       | yes      | Discord bot token                                |
| SCRIPT_PATH         | yes      | Absolute path to firewall_rules.sh               |
| PLAYER_DOMAINS      | yes      | Player=their.ddns.net,Other=other.ddns.net       |
| ALLOWED_CHANNEL_ID  | optional | Discord channel ID for bot commands (0 = any)    |
| ADMIN_ROLE_NAME     | optional | Discord role name required to run commands        |

### Recommended: Run as systemd services

Create `/etc/systemd/system/minecraft.service` and `/etc/systemd/system/mc-bot.service`,
enable them with `systemctl enable --now` and both will auto-restart on failure.

---

## In-Game Commands

| Command                | Description                          |
|------------------------|--------------------------------------|
| !ping                  | Shows estimated ping                 |
| !status                | Shows CPU, RAM, TPS, uptime          |
| !tps                   | Shows TPS with a quality label       |
| !help                  | Lists all commands                   |
| !setwaypoint <name>    | Saves your current position          |
| !waypoints             | Lists your saved waypoints           |
| !waypoint <name>       | Shows coordinates of a waypoint      |
| !delwaypoint <name>    | Deletes a waypoint                   |

Waypoint names must be alphanumeric or dashes, max 32 characters.

---

## Discord Bot Commands

| Command   | Description                                  |
|-----------|----------------------------------------------|
| !ip       | Resolves DDNS and updates UFW rules          |
| !status   | Shows server online status and player list   |
| !restart  | Restarts the minecraft systemd service       |
| !help     | Lists available Discord commands             |

Commands are restricted to `ALLOWED_CHANNEL_ID` and `ADMIN_ROLE_NAME` if configured.

---

## Copilot Analysis & Opinion

### What this project does well

- **Smart security model.** Using DDNS + UFW to create a dynamic allowlist is genuinely
  clever for a small private server. It avoids exposing the server to the public internet
  without requiring a VPN, and the firewall operates at the OS kernel level.
- **Self-contained.** Everything runs on one VPS with no external dependencies beyond
  Discord and DDNS providers.
- **Aikar JVM flags.** The chosen JVM flags are the community-standard G1GC tuning for
  PaperMC. Good choice.
- **Waypoint system.** A nice quality-of-life feature built entirely in Python by parsing
  server output — no mods required.

### Issues that were fixed in this revision

1. **JSON injection in tellraw** (`minecraft_server.py`): The original code manually
   escaped only double-quotes in chat messages before embedding them in a raw JSON string.
   A player message containing backslashes or other special characters could corrupt the
   JSON sent to the server. Fixed by using `json.dumps()`.

2. **Shell injection via subprocess.getoutput** (`bot.py`): The original bot used
   `subprocess.getoutput(f"tail -n 2 /path/to/file")` which runs through `/bin/sh` and
   accepts a format string. Replaced with `subprocess.run(['tail', '-n', '2', path])`.

3. **No Discord authorization** (`bot.py`): Any user in any channel could trigger `!ip`,
   which runs a privileged script with `sudo`. Added `ALLOWED_CHANNEL_ID` and
   `ADMIN_ROLE_NAME` guards.

4. **Hardcoded player list** (`minecraft_server.py`): `player_domains` was a Python dict
   literal. Now loaded from the `PLAYER_DOMAINS` env var — no code changes needed to add
   or remove players.

5. **restart_count never resets** (`minecraft_server.py`): If the server crashed once
   early on, the counter would stay at 1 forever, eating into the budget of 10 restarts.
   Now resets to 0 after the server has been stable for 5 minutes.

6. **Bare except clauses** (`minecraft_server.py`): Several `except: pass` blocks silently
   swallowed errors. Now all exceptions are logged.

7. **Fragile nslookup parsing** (`firewall_rules.sh`): The original used a brittle grep
   pipeline on `nslookup` output that varies across DNS server types and OS versions.
   Replaced with `dig +short` which outputs only the IP address.

### Remaining suggestions (not implemented — bigger scope changes)

- **TPS measurement is inaccurate.** The current approach estimates TPS from how often
  log lines appear, which is not the actual tick rate. Consider using a Paper plugin
  (e.g. Spark) or parsing the `Cannot keep up!` warning lines for a real measurement.
- **The Discord bot and server wrapper are fully disconnected.** The bot cannot start,
  stop, or communicate with the Python wrapper directly. For a tighter integration,
  consider a shared socket or a simple HTTP API on localhost.
- **No rate limiting on Discord commands.** A user (or bot) spamming `!ip` will run the
  firewall script repeatedly.
- **Backup runs silently in background.** Players are not notified before a backup starts
  (which causes a brief lag spike). A `say` command before backup would be friendly.
- **`python-dotenv` not imported in `minecraft_server.py` originally.** The server wrapper
  read env vars but never called `load_dotenv()`. This is now fixed.
