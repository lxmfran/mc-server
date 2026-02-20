## Automated mc server with ddns and firewall handling


## Project Description
This project implements a dynamic perimeter security architecture for Linux servers (VPS). It uses an asynchronous Discord bot integrated with a Python script to remotely manage whitelists using ufw, blocking all unauthorized traffic by default.

## Implemented Solution
A system was designed to allow authenticated users to authorize their dynamic IPs (via DDNS resolution) through a Discord interface. The system updates the Linux kernel firewall rules in real-time, allowing TCP connections exclusively to validated users.

## Tech Stack 🛠️
* **Cloud Infrastructure:** Linux (Ubuntu VPS)
* **Security & Networking:** UFW, TCP/IP, DDNS
* **Automation:** Python (`discord.py`, `sockets`, `psutil`), system services and Bash scripting.
* **Architecture:** Threading execution for real-time log monitoring without blocking the main server process.

## Installation & Deployment
1. Clone this repository.
2. Install Python dependencies: `pip install -r requirements.txt`
3. Rename `.env.example` to `.env` and add your Discord API Token.
4. Configure the allowed DDNS domains in `firewall_rules.sh` and `minecraft_server.py`.
5. Run the bot and the server independently.
6. **Highly Recommended:** Configure the bot and server to run as a systemd service for background execution, automatic restarts, and proper log management
