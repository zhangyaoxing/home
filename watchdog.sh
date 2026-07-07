#!/usr/bin/env bash
# Watchdog: restarts the app when git changes are detected in the working tree.

CHECK_INTERVAL=3
RETRY_DELAY=30

app_pid=""

cleanup() {
    if [ -n "$app_pid" ] && kill -0 "$app_pid" 2>/dev/null; then
        kill "$app_pid" 2>/dev/null
        wait "$app_pid" 2>/dev/null
    fi
    exit 0
}
trap cleanup SIGINT SIGTERM

has_changes() {
    ! git diff --quiet || ! git diff --cached --quiet
}

start_app() {
    PYTHONPATH=src python -m home_control_panel.app &
    echo $!
}

restart_app() {
    echo "$(date '+%H:%M:%S') Changes detected, restarting..."
    if [ -n "$app_pid" ] && kill -0 "$app_pid" 2>/dev/null; then
        kill "$app_pid" 2>/dev/null
        wait "$app_pid" 2>/dev/null
    fi
    while true; do
        app_pid=$(start_app)
        sleep 2
        if kill -0 "$app_pid" 2>/dev/null; then
            echo "$(date '+%H:%M:%S') App started (PID: $app_pid)."
            return 0
        fi
        echo "$(date '+%H:%M:%S') Start failed, retrying in ${RETRY_DELAY}s..."
        sleep "$RETRY_DELAY"
    done
}

app_pid=$(start_app)
echo "$(date '+%H:%M:%S') App started (PID: $app_pid)."

while true; do
    sleep "$CHECK_INTERVAL"

    if ! kill -0 "$app_pid" 2>/dev/null; then
        wait "$app_pid" 2>/dev/null
        exit_code=$?
        if [ "$exit_code" -eq 0 ]; then
            echo "$(date '+%H:%M:%S') App exited normally. Stopping."
            exit 0
        fi
        echo "$(date '+%H:%M:%S') App crashed (exit $exit_code)."
        if has_changes; then
            restart_app
        else
            echo "$(date '+%H:%M:%S') Waiting for changes..."
            while ! has_changes; do
                sleep "$CHECK_INTERVAL"
            done
            restart_app
        fi
        continue
    fi

    if has_changes; then
        restart_app
    fi
done
