#!/bin/bash

echo "Starting scheduler..."
python scheduler.py &
SCHEDULER_PID=$!

sleep 5

echo "Starting web interface on http://${WEB_HOST}:${WEB_PORT}"
python web.py

trap "kill $SCHEDULER_PID" EXIT
