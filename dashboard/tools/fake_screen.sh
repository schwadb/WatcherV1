#!/usr/bin/env bash
# Stand-in for deploy/screen.sh on a machine without a display (used by the tests):
#   DASHBOARD_SCREEN_CMD=tools/fake_screen.sh
echo "$(date +%T) $1" >> "${FAKE_SCREEN_LOG:-/tmp/fake_screen.log}"
echo "fake screen $1"
