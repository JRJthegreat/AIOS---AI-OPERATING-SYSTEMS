#!/bin/zsh
# Unattended email follow-up run. Launched by ~/Library/LaunchAgents/com.nexam.email-followups.plist.
# Same isolation as run.sh. The only Gmail writes allowed: reply (pinned by guard_email_reply.py to the
# exact follow-up `email_followups.py plan` queued) and send_message (pinned by guard_email.py to Jude).
set -u
REPO="/Users/air/AIOS - AI OPERATING SYSTEMS"
SKILL="$REPO/.claude/skills/upwork-followups"
LOGDIR="$HOME/Library/Logs/upwork-followups"
mkdir -p "$LOGDIR" "$REPO/.tmp/upwork_followups"
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"
export PYTHONWARNINGS="ignore"
cd "$REPO" || exit 1
LOG="$LOGDIR/email-$(date +%Y-%m-%d).log"
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') start"
  claude -p "Unattended scheduled run, nobody is watching and nobody can answer questions. Read .claude/skills/upwork-followups/SKILL.md and carry out its 'Email follow-ups' section exactly, then end with the EMAIL RUN line." \
    --setting-sources "" \
    --mcp-config "$SKILL/scripts/mcp.json" \
    --settings "$SKILL/scripts/headless_settings.json" \
    --allowedTools \
      "Read" \
      "Edit(.tmp/upwork_followups/**)" \
      "Bash(python3 .claude/skills/upwork-followups/scripts/email_followups.py:*)" \
      "mcp__claude_ai_Gmail__get_thread" \
      "mcp__claude_ai_Gmail__reply" \
      "mcp__claude_ai_Gmail__send_message" \
    --output-format text < /dev/null
  rc=$?
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') exit $rc"
  exit $rc
} >> "$LOG" 2>&1
