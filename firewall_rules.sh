#!/bin/bash
# Automated script for UFW rule updates based on DDNS resolution

MINECRAFT_PORT=25565
LOG_FILE="/var/log/minecraft_firewall_update.log"

# Associative array with DDNS domains (Example for GitHub)
declare -A DOMAINS=(
    ["User1"]="user1.ddns.net" 
    ["User2"]="user2.ddns.net"
)  

echo "$(date): Starting smart firewall update..." >> $LOG_FILE

# Function to extract IP from DDNS domain
get_ip_from_domain() {
    local domain=$1
    local ip=$(nslookup $domain | grep -A1 "Name:" | grep "Address:" | tail -1 | cut -d' ' -f2)

    # Regex to verify valid IPv4 format
    if [[ $ip =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        echo $ip
    else
        echo "ERROR"
    fi
}

declare -a DETECTED_VALID_IPS

# ---------------------------------------------------------
# STEP 1: Ensure access for current IPs (No deletions yet)
# ---------------------------------------------------------
for name in "${!DOMAINS[@]}"; do
    domain="${DOMAINS[$name]}"
    
    if [ ! -z "$domain" ]; then
        ip=$(get_ip_from_domain $domain)
        
        if [ "$ip" != "ERROR" ]; then
            DETECTED_VALID_IPS+=("$ip")
            
            # UFW will skip if rule already exists, or add it instantly if new
            sudo ufw allow from $ip to any port $MINECRAFT_PORT > /dev/null 2>&1
            echo "$(date): Verified/Added IP for $name: $ip" >> $LOG_FILE
        else
            echo "$(date): ERROR getting IP for $domain ($name)" >> $LOG_FILE
        fi
    fi
done

# ---------------------------------------------------------
# STEP 2: Surgical Cleanup (Delete only obsolete rules)
# ---------------------------------------------------------
echo "$(date): Checking for obsolete rules..." >> $LOG_FILE

FIREWALL_IPS=$(sudo ufw status | grep "$MINECRAFT_PORT" | grep -v "(v6)" | awk '{print $3}' | sort | uniq)

for firewall_ip in $FIREWALL_IPS; do
    is_valid=false
    
    for valid_ip in "${DETECTED_VALID_IPS[@]}"; do
        if [ "$firewall_ip" == "$valid_ip" ]; then
            is_valid=true
            break
        fi
    done

    # If the firewall IP does not match any current valid IP -> DELETE
    if [ "$is_valid" = false ]; then
        if [ "$firewall_ip" != "Anywhere" ]; then 
            sudo ufw delete allow from $firewall_ip to any port $MINECRAFT_PORT > /dev/null 2>&1
            echo "$(date): REMOVED obsolete IP: $firewall_ip" >> $LOG_FILE
        fi
    fi
done

echo "$(date): Update completed." >> $LOG_FILE
echo "----------------------------------------" >> $LOG_FILE
