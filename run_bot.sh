#!/bin/bash
cd /home/z/my-project/repo
while true; do
    python3 -u v948_pullbot.py --loop --interval 2 2>&1
    echo "Bot died, restarting in 3s..."
    sleep 3
done
