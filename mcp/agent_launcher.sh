#!/usr/bin/env bash
# agent_launcher.sh -- reference launcher for an agent host (Claude Code) that follows Kalmido's runtime settings (2.4.1; event mode 2.35.0).
#
# Kalmido never runs an agent. An admin only chooses runtime settings in Settings > Agents > (agent) > Runtime and
# Kalmido hands them to the agent: GET /api/v1/agent -> "runtime" {model, autocompact, autocompact_pct, nightly_reset,
# reset_seq, timezone}. This launcher (2.1394.0, #4068) only loads the env file, finds Python and starts mcp/agent_run.py
# --launch, which applies them -- the same code for this launcher and agent_launcher.ps1:
#   - starts the agent command, ALWAYS in a fresh session (Claude Code starts a new conversation unless it gets
#     --continue / --resume, so never pass those here)
#   - model:            appends `--model <model>` (empty = the command's own default)
#   - auto-compact:     on + percentage -> CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=<pct>; off -> DISABLE_AUTO_COMPACT=1
#   - restarts it (fresh session) when the model / auto-compact settings change, when an admin presses "Reset now"
#     (reset_seq goes up; the agent also gets the event `reset`), once a night at nightly_reset (HH:MM in runtime.timezone),
#     and whenever the command exits by itself (after KALMIDO_RESTART_DELAY seconds)
#   - git author (2.396.0, #3386): GIT_AUTHOR_NAME / _EMAIL and GIT_COMMITTER_NAME / _EMAIL from runtime.git_author (a
#     project with a repository may name its own: data.repo.git_author of a task), KALMIDO_GIT_COAUTHOR=1 when the agent
#     should append a Co-Authored-By line; an older server without git_author: nothing is set
#   - work window (2.236.0, #2905): outside the work window of its work style no new session starts
#   - interim summary (2.233.0, #3189: rotate_size / rotate_runs / rotate_idle_min, sent as rotate_tokens etc.): applied per chat
#     conversation by mcp/agent_run.py in --events mode; without --events the command runs one session (not applicable)
# It polls GET /api/v1/agent every KALMIDO_POLL seconds (default 60): one small request, no events are consumed.
#
# usage: agent_launcher.sh [-e ENV_FILE] [--once] [-- COMMAND ...]
#   ENV_FILE  default ./kalmido-agent.env (chmod 600), shell syntax:
#               KALMIDO_URL=https://tasks.example.com
#               KALMIDO_TOKEN=abk_...            the agent's API token (Settings > Agents); a TEAM agent's run never sees it
#                                                (2.1386.0, #6668): it gets the token of its request only (one person)
#             everything in it is exported to the command too (the MCP server mcp/kalmido_mcp.py reads the same two)
#             optional: KALMIDO_TOOLSETS=tickets,code,office  (only those tool packages in the MCP server; chat is always on)
#   COMMAND   what to start (default: KALMIDO_AGENT_CMD of the env file, else claude; KALMIDO_AGENT_PROFILE claude | codex |
#             generic names the tool, 2.391.0). Example, a headless loop that works through its events:
#               agent_launcher.sh -e ~/.config/kalmido/agent.env -- claude -p "$(cat ~/agent/prompt.md)" --permission-mode acceptEdits
#   --once    print the command line and environment it would use, then exit (a dry run; the token is never printed)
#   --events  event mode (2.35.0, recommended for Claude Code): mcp/agent_run.py waits for the agent's events and starts
#             ONE fresh headless run of COMMAND per event (`-p --output-format stream-json --verbose`, the event as prompt
#             on stdin), like a hosted chat service: steps between tool calls, model and permission mode, typing / status,
#             plan usage ring, reply reference, approval cards; the final text of a chat run is posted as the answer.
#             COMMAND then is the plain agent command without -p, e.g.
#               agent_launcher.sh -e ~/.config/kalmido/agent.env --events -- claude --mcp-config ~/agent/.mcp.json
#             Same as KALMIDO_EVENTS=1 in the env file. Optional keys there: KALMIDO_PROMPT_FILE (text in front of every
#             event), KALMIDO_USAGE_LIMIT (pause new runs at this % of the week), KALMIDO_USAGE_FILE (a status line
#             file {at, rate_limits}), KALMIDO_STATE_DIR (event cursor), KALMIDO_APPROVAL_CHECK=0 (2.40.0: no check of
#             chat answers that ask to decide without an ```approval block), KALMIDO_NOTICE_COMPACTED (2.41.0: the notice
#             in the chat when a run compacts its conversation, {0} = the time). Without --events: the command runs as it is.
#   KALMIDO_HOST  the computer name shown in Kalmido (2.44.0; default: hostname without the domain), sent once at start
#   KALMIDO_PYTHON  the Python to use (default: python3)
#   KALMIDO_POLL / KALMIDO_RESTART_DELAY  seconds between two reads of the settings (60) / before a restart (10)
# Exit codes: 0 stopped (TERM / INT end the command with everything it started, KILL after 30 s), 1 Kalmido not reachable at
# the start, 2 a wrong start (no env file, KALMIDO_URL / KALMIDO_TOKEN missing, no Python 3 or no mcp/agent_run.py).
# Needs: bash (3.2 is enough, the macOS one) and python3 (3.9+). /agent-setup.sh of your Kalmido sets it up with an autostart
# (launchd LaunchAgent / systemd --user); see docs/AGENTS.md "Runtime settings" for a hand-made systemd unit.
# 2.1394.0 (#4068): two steps, the same in agent_launcher.ps1 (tests/launcher_parity_test.py checks the markers); every
# capability of tests/launcher_parity_test.py lives in mcp/agent_run.py.
set -uo pipefail

log() { printf '%s agent_launcher: %s\n' "$(date '+%F %T')" "$*" >&2; }
ENV_FILE=./kalmido-agent.env
FLAGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -e|--env) [[ $# -ge 2 ]] || { log "-e needs a file"; exit 2; }; ENV_FILE=$2; shift 2 ;;
    --once|--events) FLAGS+=("$1"); shift ;;
    --) shift; break ;;
    -h|--help) awk 'NR > 1 && !/^#/ { exit } NR > 1' "$0"; exit 0 ;;
    *) break ;;
  esac
done

# kalmido-starter-step: env_file -- every line of the env file into the environment (KALMIDO_ENV_FILE = its full path: the
# model's process never gets KALMIDO_TOKEN, the MCP server, the hooks and agent_job.py read the token from the file, #6457)
[[ -r "$ENV_FILE" ]] || { log "cannot read $ENV_FILE"; exit 2; }
[[ "$ENV_FILE" == */* ]] || ENV_FILE=./$ENV_FILE  # "." would search PATH for a bare name
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
KALMIDO_ENV_FILE="$(cd "$(dirname "$ENV_FILE")" && pwd)/$(basename "$ENV_FILE")"
export KALMIDO_ENV_FILE

# kalmido-starter-step: python -- KALMIDO_PYTHON or python3, and mcp/agent_run.py next to this file
PY=${KALMIDO_PYTHON:-python3}
command -v "$PY" >/dev/null 2>&1 || { log "needs Python 3 ($PY not found; set KALMIDO_PYTHON)"; exit 2; }
RUNNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/agent_run.py"
[[ -r "$RUNNER" ]] || { log "$RUNNER missing"; exit 2; }

# kalmido-starter-step: run -- agent_run.py --launch does the rest (same process: TERM / INT reach it directly); without
# KALMIDO_TOKEN in its environment: it reads the token from KALMIDO_ENV_FILE (#6457)
export KALMIDO_LAUNCHER_PID=$$
exec env -u KALMIDO_TOKEN "$PY" "$RUNNER" --launch ${FLAGS[@]+"${FLAGS[@]}"} -- "$@"
