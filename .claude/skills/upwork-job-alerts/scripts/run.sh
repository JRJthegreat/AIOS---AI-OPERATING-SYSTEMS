#!/bin/zsh
# Unattended upwork-job-alerts run. Launched by ~/Library/LaunchAgents/com.nexam.upwork-job-alerts.plist
# at :07 and :37. Isolated like upwork-followups: no user/project settings, the Upwork MCP from the
# follow-ups mcp.json, guard hooks from headless_settings.json, and a tool allowlist that confines the run.
set -u
REPO="/Users/air/AIOS - AI OPERATING SYSTEMS"
SKILL="$REPO/.claude/skills/upwork-job-alerts"
LOGDIR="$HOME/Library/Logs/upwork-job-alerts"
NOTIFY_FILE="$HOME/.config/upwork-job-alerts/notify_email"
mkdir -p "$LOGDIR" "$REPO/.tmp/upwork_job_alerts/raw"
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"
export PYTHONWARNINGS="ignore"
cd "$REPO" || exit 1
LOG="$LOGDIR/$(date +%Y-%m-%d).log"

# Working hours guard: 15:00 to 02:59 Asia/Taipei (launchd fires on the Mac's local clock).
HOUR=$(TZ=Asia/Taipei date +%H)
if [ "$HOUR" -ge 3 ] && [ "$HOUR" -lt 15 ]; then exit 0; fi

# JOB_ALERTS_NOTIFY overrides the address for a test run (tests go to the test inbox only).
NOTIFY="${JOB_ALERTS_NOTIFY:-$(tr -d ' \n' < "$NOTIFY_FILE" 2>/dev/null)}"
if [ -z "$NOTIFY" ]; then echo "$(date) no notify address in $NOTIFY_FILE" >> "$LOG"; exit 1; fi

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') start"
  claude -p "Unattended scheduled run, nobody is watching and nobody can answer questions. The notify address is $NOTIFY. Read .claude/skills/upwork-job-alerts/SKILL.md and carry out its Run section exactly, then end with the RUN line." \
    --setting-sources "" \
    --mcp-config "$REPO/.claude/skills/upwork-followups/scripts/mcp.json" \
    --settings "$SKILL/scripts/headless_settings.json" \
    --allowedTools \
      "Read" \
      "Edit(.tmp/upwork_job_alerts/**)" \
      "Bash(python3 .claude/skills/upwork-job-alerts/scripts/job_alerts.py:*)" \
      "mcp__upwork__upwork__find_jobs" \
      "mcp__upwork__upwork__save_job" \
      "mcp__claude_ai_Gmail__send_message" \
    --output-format text < /dev/null
  rc=$?
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') exit $rc"
  exit $rc
} >> "$LOG" 2>&1
