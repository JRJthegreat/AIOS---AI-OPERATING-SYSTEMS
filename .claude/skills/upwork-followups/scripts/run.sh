#!/bin/zsh
# Unattended upwork-followups run. Launched by ~/Library/LaunchAgents/com.nexam.upwork-followups.plist.
# Isolated on purpose: no user/project settings (their broad python3 allow rules don't apply), the Upwork MCP
# from mcp.json, and the email guard hook from headless_settings.json. Other MCP servers (claude.ai connectors)
# still load, so the tool allowlist below is what actually confines the run: anything not listed is denied.
set -u
REPO="/Users/air/AIOS - AI OPERATING SYSTEMS"
SKILL="$REPO/.claude/skills/upwork-followups"
LOGDIR="$HOME/Library/Logs/upwork-followups"
mkdir -p "$LOGDIR" "$REPO/.tmp/upwork_followups"
# /usr/bin first: the repo's deps (gspread, google-auth) live on the system Python 3.9, not Homebrew's.
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"
export PYTHONWARNINGS="ignore"
cd "$REPO" || exit 1
LOG="$LOGDIR/$(date +%Y-%m-%d).log"
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') start"
  claude -p "Unattended scheduled run, nobody is watching and nobody can answer questions. Read .claude/skills/upwork-followups/SKILL.md and carry out its Run section exactly, then end with the RUN line." \
    --setting-sources "" \
    --mcp-config "$SKILL/scripts/mcp.json" \
    --settings "$SKILL/scripts/headless_settings.json" \
    --allowedTools \
      "Read" \
      "Edit(.tmp/upwork_followups/**)" \
      "Bash(python3 .claude/skills/upwork-followups/scripts/followups.py:*)" \
      "mcp__upwork__upwork__get_messages" \
      "mcp__upwork__upwork__list_freelancer_proposals" \
      "mcp__upwork__upwork__get_tool_help" \
      "mcp__claude_ai_Gmail__send_message" \
    --output-format text < /dev/null
  rc=$?
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') exit $rc"
  exit $rc
} >> "$LOG" 2>&1
