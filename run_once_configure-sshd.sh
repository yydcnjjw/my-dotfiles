#!/bin/bash

# Configure sshd keep-alive settings
# Requires sudo privileges

SSHD_CONFIG="/etc/ssh/sshd_config"

echo "Configuring sshd keep-alive settings..."

# Check for sudo privileges
if ! sudo -v &> /dev/null; then
    echo "Error: This script requires sudo privileges to modify /etc/ssh/sshd_config."
    exit 1
fi

# Backup original config
sudo cp $SSHD_CONFIG "${SSHD_CONFIG}.bak"
echo "Backed up original config to ${SSHD_CONFIG}.bak"

# Function to update or append config key
update_or_append() {
    local key=$1
    local value=$2
    local file=$3

    if sudo grep -q "^[[:space:]]*${key}" "$file"; then
        sudo sed -i "s/^[[:space:]]*${key}.*/${key} ${value}/" "$file"
    elif sudo grep -q "^[[:space:]]*#[[:space:]]*${key}" "$file"; then
        sudo sed -i "s/^[[:space:]]*#[[:space:]]*${key}.*/${key} ${value}/" "$file"
    else
        echo "${key} ${value}" | sudo tee -a "$file" > /dev/null
    fi
}

update_or_append "ClientAliveInterval" "60" "$SSHD_CONFIG"
update_or_append "ClientAliveCountMax" "3" "$SSHD_CONFIG"

echo "Configuration updated."

# Try to restart SSH service
if systemctl is-active --quiet sshd; then
    sudo systemctl restart sshd
    echo "Restarted sshd service."
elif systemctl is-active --quiet ssh; then
    sudo systemctl restart ssh
    echo "Restarted ssh service."
else
    echo "Failed to automatically detect running SSH service. Please manually restart sshd/ssh service to apply changes."
    echo "Example: sudo systemctl restart sshd"
fi
