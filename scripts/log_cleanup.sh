#!/bin/bash

# Log cleanup script for content_generator
# Runs daily to remove logs older than 2 days

LOG_DIR="/home/polat/Desktop/Projects/content_generator/logs"

# Check if log directory exists
if [ ! -d "$LOG_DIR" ]; then
    echo "Log directory $LOG_DIR does not exist"
    exit 1
fi

# Find and delete log files older than 2 days
find "$LOG_DIR" -name "app_*.log" -mtime +2 -delete

# Log the cleanup action
echo "$(date): Cleaned up old log files in $LOG_DIR" >> "$LOG_DIR/cleanup.log"

# Optional: Rotate logs if needed (create new log file for today)
TODAY_LOG="$LOG_DIR/app_$(date +%Y-%m-%d).log"
if [ ! -f "$TODAY_LOG" ]; then
    touch "$TODAY_LOG"
    echo "Created new log file: $TODAY_LOG"
fi