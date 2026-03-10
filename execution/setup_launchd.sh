#!/bin/bash

# Setup USF Job Sniper launchd daemon

PLIST_FILE="com.usfjobsniper.scraper.plist"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"
PROJECT_DIR="/Users/andressabillon/CodingProjects/usf job sniper"

echo "Copying plist to ~/Library/LaunchAgents..."
mkdir -p "$LAUNCHD_DIR"
cp "$PROJECT_DIR/$PLIST_FILE" "$LAUNCHD_DIR/"

echo "Unloading existing service (if any)..."
launchctl unload "$LAUNCHD_DIR/$PLIST_FILE" 2>/dev/null || true

echo "Loading new service..."
launchctl load "$LAUNCHD_DIR/$PLIST_FILE"

echo "Setup complete! The job sniper will now run every 60 minutes in the background."
echo "Logs can be found in .tmp/scraper.log"
