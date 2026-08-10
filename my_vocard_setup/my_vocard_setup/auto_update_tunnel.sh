#!/bin/bash
# Auto update settings.json with new Cloudflare Quick Tunnel URL

echo "Checking Cloudflare Tunnel URL..."
for i in {1..15}; do
    URL=$(docker logs vocard-cloudflared 2>&1 | grep -o 'https://[^"]*trycloudflare.com' | tail -n 1)
    if [ -n "$URL" ]; then
        echo "Found Tunnel URL: $URL"
        REDIRECT_URI="${URL}/callback"
        
        # Read current redirect_url in settings.json
        CURRENT_URI=$(grep -o '"redirect_url": "[^"]*"' /home/copter2737/Vocard-Dashboard/settings.json | cut -d'"' -f4)
        
        if [ "$CURRENT_URI" != "$REDIRECT_URI" ]; then
            echo "Updating settings.json to: $REDIRECT_URI"
            sed -i "s|\"redirect_url\": \".*\"|\"redirect_url\": \"$REDIRECT_URI\"|g" /home/copter2737/Vocard-Dashboard/settings.json
            echo "Restarting vocard-dashboard container..."
            docker restart vocard-dashboard
            echo "Done! Dashboard updated with new URL."
        else
            echo "settings.json is already up to date with: $REDIRECT_URI"
        fi
        exit 0
    fi
    sleep 2
done

echo "Could not find trycloudflare.com URL from vocard-cloudflared logs."
exit 1
