#!/usr/bin/env python3


import subprocess
import time
import os
import logging
import signal
import sys
from datetime import datetime
import threading
import json
import psutil
import re
import socket
from dotenv import load_dotenv

load_dotenv()

WAYPOINT_NAME_MAX_LEN = 32
WAYPOINT_NAME_PATTERN = re.compile(r'^[\w\-]+$')
STABLE_UPTIME_THRESHOLD = 300  # seconds before restart_count resets


class MinecraftServer:
    def __init__(self):
        self.setup_logging()
        self.server_process = None
        self.running = False
        self.restart_count = 0
        self.start_time = time.time()
        self.last_tick_time = time.time()
        self.tps = 20.0
        self.player_waypoints = {}
        self.waypoints_file = "waypoints.json"
        self.pending_waypoints = {}
        self.load_waypoints()

        # --- SECURITY MAPPING (DDNS Application Layer) ---
        # Load from PLAYER_DOMAINS env var: "User1=user1.ddns.net,User2=user2.ddns.net"
        self.player_domains = self._load_player_domains()

    def _load_player_domains(self):
        raw = os.getenv('PLAYER_DOMAINS', '')
        domains = {}
        for entry in raw.split(','):
            entry = entry.strip()
            if '=' in entry:
                player, domain = entry.split('=', 1)
                domains[player.strip()] = domain.strip()
        if not domains:
            self.logger.warning("⚠️  PLAYER_DOMAINS not set in .env — no players will be whitelisted.")
        return domains

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('minecraft_server.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)

    def load_waypoints(self):
        try:
            if os.path.exists(self.waypoints_file):
                with open(self.waypoints_file, 'r') as f:
                    self.player_waypoints = json.load(f)
                self.logger.info("📍 Waypoints loaded")
            else:
                self.player_waypoints = {}
        except Exception as e:
            self.logger.error(f"Error loading waypoints: {e}")
            self.player_waypoints = {}

    def save_waypoints(self):
        try:
            with open(self.waypoints_file, 'w') as f:
                json.dump(self.player_waypoints, f, indent=2)
            self.logger.info("📍 Waypoints saved")
        except Exception as e:
            self.logger.error(f"Error saving waypoints: {e}")

    def get_server_stats(self):
        if self.server_process:
            try:
                process = psutil.Process(self.server_process.pid)
                memory = psutil.virtual_memory()
                cpu_percent = process.cpu_percent()
                memory_mb = process.memory_info().rss / 1024 / 1024
                uptime_hours = (time.time() - self.start_time) / 3600

                return {
                    "cpu": cpu_percent,
                    "memory_mb": memory_mb,
                    "memory_percent": process.memory_percent(),
                    "system_memory_free": memory.available / 1024 / 1024,
                    "uptime_hours": uptime_hours,
                    "tps": self.tps
                }
            except Exception as e:
                self.logger.error(f"Error reading server stats: {e}")
                return None
        return None

    def send_chat_message(self, message):
        if self.server_process and self.running:
            payload = json.dumps({"text": message, "color": "yellow"})
            self.send_command(f"tellraw @a {payload}")

    def handle_chat_commands(self, line):
        chat_pattern = r'<(\w+)> (![\w\s]+.*)'
        match = re.search(chat_pattern, line)

        if match:
            player = match.group(1)
            full_command = match.group(2).strip()
            command_parts = full_command.split()
            command = command_parts[0].lower()

            self.logger.info(f"🔍 Command detected: {player} -> {full_command}")

            if command == "!ping":
                self.handle_ping_command(player)
            elif command == "!status":
                self.handle_status_command(player)
            elif command == "!tps":
                self.handle_tps_command(player)
            elif command == "!help":
                self.handle_help_command(player)
            elif command == "!setwaypoint":
                self.handle_setwaypoint_command(player, full_command)
            elif command == "!waypoints":
                self.handle_waypoints_command(player)
            elif command == "!waypoint":
                self.handle_waypoint_command(player, full_command)
            elif command == "!delwaypoint":
                self.handle_delwaypoint_command(player, full_command)

    def handle_ping_command(self, player):
        ping_estimate = "~50ms"
        message = f"🏓 {player}: Estimated Ping {ping_estimate}"
        self.send_chat_message(message)

    def handle_status_command(self, player):
        stats = self.get_server_stats()
        if stats:
            uptime = f"{stats['uptime_hours']:.1f}h"
            cpu = f"{stats['cpu']:.1f}%"
            memory = f"{stats['memory_mb']:.0f}MB"
            tps = f"{stats['tps']:.1f}"
            message = f"📊 CPU: {cpu} | RAM: {memory} | TPS: {tps} | Uptime: {uptime}"
            self.send_chat_message(message)
        else:
            self.send_chat_message("❌ Could not retrieve server stats")

    def handle_tps_command(self, player):
        if self.tps >= 19.5:
            status = "🟢 Excellent"
        elif self.tps >= 18:
            status = "🟡 Good"
        elif self.tps >= 15:
            status = "🟠 Fair"
        else:
            status = "🔴 Lag"
        message = f"⚡ TPS: {self.tps:.2f}/20.0 {status}"
        self.send_chat_message(message)

    def handle_help_command(self, player):
        self.send_chat_message("🔧 Commands: !ping !status !tps !help")
        time.sleep(0.5)
        self.send_chat_message("📍 Waypoints: !setwaypoint <name> !waypoints !waypoint <name> !delwaypoint <name>")

    def _validate_waypoint_name(self, name):
        if not name or len(name) > WAYPOINT_NAME_MAX_LEN:
            return False
        return bool(WAYPOINT_NAME_PATTERN.match(name))

    def handle_setwaypoint_command(self, player, full_command):
        parts = full_command.split(' ', 1)
        if len(parts) < 2:
            self.send_chat_message("📍 Usage: !setwaypoint <name>")
            return
        waypoint_name = parts[1].strip()
        if not waypoint_name:
            return
        if not self._validate_waypoint_name(waypoint_name):
            self.send_chat_message(f"📍 {player}: Invalid waypoint name (max {WAYPOINT_NAME_MAX_LEN} alphanumeric/dash chars)")
            return

        if player not in self.player_waypoints:
            self.player_waypoints[player] = {}

        self.pending_waypoints[player] = waypoint_name
        self.send_command(f"data get entity {player} Pos")
        self.send_chat_message(f"📍 {player}: Saving waypoint '{waypoint_name}'...")

        def waypoint_timeout():
            time.sleep(5)
            if player in self.pending_waypoints and self.pending_waypoints[player] == waypoint_name:
                del self.pending_waypoints[player]
                self.send_chat_message(f"📍 {player}: Timeout fetching coordinates for '{waypoint_name}'")

        timeout_thread = threading.Thread(target=waypoint_timeout)
        timeout_thread.daemon = True
        timeout_thread.start()

    def handle_waypoints_command(self, player):
        if player not in self.player_waypoints or not self.player_waypoints[player]:
            self.send_chat_message(f"📍 {player}: No waypoints saved")
            return
        waypoints = self.player_waypoints[player]
        if len(waypoints) == 1:
            name, coords = list(waypoints.items())[0]
            self.send_chat_message(f"📍 {player}: '{name}' → {coords}")
        else:
            waypoint_list = ", ".join(waypoints.keys())
            self.send_chat_message(f"📍 {player}: Waypoints ({len(waypoints)}): {waypoint_list}")

    def handle_waypoint_command(self, player, full_command):
        parts = full_command.split(' ', 1)
        if len(parts) < 2:
            self.send_chat_message("📍 Usage: !waypoint <name>")
            return
        waypoint_name = parts[1].strip()
        if player not in self.player_waypoints or waypoint_name not in self.player_waypoints[player]:
            self.send_chat_message(f"📍 {player}: Waypoint '{waypoint_name}' not found")
            return
        coords = self.player_waypoints[player][waypoint_name]
        self.send_chat_message(f"📍 {player}: '{waypoint_name}' → {coords}")

    def handle_delwaypoint_command(self, player, full_command):
        parts = full_command.split(' ', 1)
        if len(parts) < 2:
            self.send_chat_message("📍 Usage: !delwaypoint <name>")
            return
        waypoint_name = parts[1].strip()
        if player not in self.player_waypoints or waypoint_name not in self.player_waypoints[player]:
            self.send_chat_message(f"📍 {player}: Waypoint '{waypoint_name}' not found")
            return
        del self.player_waypoints[player][waypoint_name]
        self.save_waypoints()
        self.send_chat_message(f"📍 {player}: Waypoint '{waypoint_name}' deleted")

    def calculate_tps(self, line):
        if "Server thread/INFO" in line:
            current_time = time.time()
            time_diff = current_time - self.last_tick_time
            if time_diff > 0:
                estimated_tps = min(20.0, 1.0 / max(time_diff, 0.05))
                self.tps = (self.tps * 0.9) + (estimated_tps * 0.1)
            self.last_tick_time = current_time

    def verify_identity(self, player, current_ip):
        if player not in self.player_domains:
            self.logger.warning(f"🚨 REJECTED: {player} is not in the DDNS whitelist.")
            self.send_command(f"kick {player} §cYou are not in the authorized players list (DDNS).")
            return

        domain = self.player_domains[player]
        try:
            expected_ip = socket.gethostbyname(domain)
            if current_ip != expected_ip:
                self.logger.warning(f"🚨 ALERT: {player} attempted login from {current_ip} (Expected {expected_ip})")
                msg = f"§c§lSECURITY ERROR!\n§eYour IP does not match your domain:\n§b{domain}\n§7Wait 2 mins if you restarted your router."
                self.send_command(f"kick {player} {msg}")
            else:
                self.logger.info(f"✅ Identity verified: {player}")
        except Exception as e:
            self.logger.error(f"❌ DNS resolution error for {player}: {e}")

    def start_server(self):
        try:
            self.logger.info("🚀 Starting server...")
            self.start_time = time.time()
            command = [
                "java", "-Xms900M", "-Xmx900M", "-Xss256k", "-XX:+UseG1GC",
                "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=200",
                "-XX:+UnlockExperimentalVMOptions", "-XX:+DisableExplicitGC",
                "-XX:+AlwaysPreTouch", "-XX:G1NewSizePercent=30",
                "-XX:G1MaxNewSizePercent=40", "-XX:G1HeapRegionSize=8M",
                "-XX:G1MixedGCCountTarget=4", "-XX:InitiatingHeapOccupancyPercent=15",
                "-XX:G1MixedGCLiveThresholdPercent=90", "-XX:G1RSetUpdatingPauseTimePercent=5",
                "-XX:SurvivorRatio=32", "-XX:+PerfDisableSharedMem",
                "-XX:MaxTenuringThreshold=1", "-Dusing.aikars.flags=true",
                "-Daikars.new.flags=true", "-jar", "paper-1.21.11-99.jar", "nogui"
            ]

            self.server_process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1
            )

            self.running = True
            self.logger.info(f"✅ Server started (PID: {self.server_process.pid})")
            return True

        except Exception as e:
            self.logger.error(f"❌ Error starting server: {e}")
            return False

    def monitor_server(self):
        try:
            for line in iter(self.server_process.stdout.readline, ''):
                if line:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"[{timestamp}] {line.strip()}")

                    login_match = re.search(r': (\w+)\[/([0-9\.]+):\d+\] logged in', line)
                    if login_match:
                        player_name = login_match.group(1)
                        player_ip = login_match.group(2)
                        threading.Thread(target=self.verify_identity, args=(player_name, player_ip)).start()

                    data_match = re.search(r'(\w+) has the following entity data: \[(-?\d+\.?\d*)d, (-?\d+\.?\d*)d, (-?\d+\.?\d*)d\]', line)
                    if data_match:
                        player_from_data = data_match.group(1)
                        x, y, z = data_match.group(2), data_match.group(3), data_match.group(4)
                        if player_from_data in self.pending_waypoints:
                            waypoint_name = self.pending_waypoints[player_from_data]
                            coords = f"X:{float(x):.1f} Y:{float(y):.1f} Z:{float(z):.1f}"
                            if player_from_data not in self.player_waypoints:
                                self.player_waypoints[player_from_data] = {}
                            self.player_waypoints[player_from_data][waypoint_name] = coords
                            self.save_waypoints()
                            self.send_chat_message(f"📍 {player_from_data}: Waypoint '{waypoint_name}' saved at {coords}")
                            del self.pending_waypoints[player_from_data]

                    self.calculate_tps(line)
                    self.handle_chat_commands(line)

                    if "Done (" in line:
                        self.logger.info("🎮 Server fully loaded")
                    elif "joined the game" in line:
                        player_match = re.search(r'(\w+) joined the game', line)
                        if player_match:
                            self.logger.info(f"👤 Player connected: {player_match.group(1)}")
                    elif "left the game" in line:
                        pass
                    elif "Stopping server" in line:
                        self.logger.info("🛑 Server stopping...")

                if self.server_process.poll() is not None:
                    break
        except Exception as e:
            self.logger.error(f"Error monitoring: {e}")

    def send_command(self, command):
        if self.server_process and self.running:
            try:
                self.server_process.stdin.write(f"{command}\n")
                self.server_process.stdin.flush()
                return True
            except Exception as e:
                self.logger.error(f"Error sending command: {e}")
        return False

    def stop_server(self):
        if self.server_process and self.running:
            self.logger.info("🛑 Stopping server...")
            self.send_command("stop")
            try:
                self.server_process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.server_process.terminate()
            self.running = False

    def backup_world(self):
        if os.path.exists("world"):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}.tar.gz"
            try:
                subprocess.run(["tar", "-czf", backup_name, "world", "world_nether", "world_the_end"], check=True)
                self.logger.info(f"💾 Backup created: {backup_name}")
                backups = sorted([f for f in os.listdir('.') if f.startswith('backup_') and f.endswith('.tar.gz')])
                if len(backups) > 5:
                    for old_backup in backups[:-5]:
                        os.remove(old_backup)
                return True
            except Exception as e:
                self.logger.error(f"💾 Backup failed: {e}")
        return False

    def run_24_7(self):
        self.logger.info("🌟 Starting 24/7 mode...")

        def signal_handler(signum, frame):
            self.stop_server()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        INTERVAL_STATS = 1800
        INTERVAL_BACKUP = 7200

        while True:
            try:
                if self.start_server():
                    monitor_thread = threading.Thread(target=self.monitor_server)
                    monitor_thread.daemon = True
                    monitor_thread.start()

                    last_stats = time.time()
                    last_backup = time.time()

                    server_start_time = time.time()
                    while self.server_process.poll() is None:
                        now = time.time()
                        if now - last_stats > INTERVAL_STATS:
                            last_stats = now
                        if now - last_backup > INTERVAL_BACKUP:
                            self.backup_world()
                            last_backup = now
                        # Reset crash counter if the server has been stable long enough
                        if self.restart_count > 0 and (now - server_start_time) > STABLE_UPTIME_THRESHOLD:
                            self.restart_count = 0
                        time.sleep(1)

                    self.logger.warning("⚠️ Server process has terminated.")
                    if self.restart_count < 10:
                        self.restart_count += 1
                        self.logger.info(f"🔄 Restarting in 30s (attempt {self.restart_count}/10)...")
                        time.sleep(30)
                    else:
                        self.logger.error("❌ Max restart attempts reached. Exiting.")
                        break
                else:
                    time.sleep(30)
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in run loop: {e}")
                time.sleep(30)
        self.stop_server()

def main():
    server = MinecraftServer()
    server.run_24_7()

if __name__ == "__main__":
    main()
