#!/bin/bash

# Change to the correct directory so it works smoothly from the .desktop launcher
cd "/home/dhruvil/real_estate" || exit

echo "Starting Real Estate Voice Agent services in separate windows..."

# Start Python Backend
x-terminal-emulator -T "Real Estate Voice Agent Backend" -e bash -c "echo 'Starting Backend...'; source .venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8000 --reload; echo -e '\nProcess stopped.'; exec bash" &

# Start Cloudflare Tunnel
x-terminal-emulator -T "Real Estate Voice Agent Tunnel" -e bash -c "echo 'Starting Cloudflare Tunnel...'; cloudflared tunnel run gunivox; echo -e '\nProcess stopped.'; exec bash" &

# Start React Frontend
x-terminal-emulator -T "Real Estate Voice Agent Frontend" -e bash -c "echo 'Starting Frontend...'; npm run dev; echo -e '\nProcess stopped.'; exec bash" &

echo "All windows launched successfully!"
