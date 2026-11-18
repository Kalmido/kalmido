<#
agent_launcher.ps1 -- the PowerShell port of agent_launcher.sh (Windows; also runs with PowerShell 7 on macOS / Linux).
A reference launcher for an agent host (Claude Code) that follows Kalmido's runtime settings (2.4.1; event mode 2.35.0).

Kalmido never runs an agent. An admin only chooses runtime settings in Settings > Agents > (agent) > Runtime and Kalmido
hands them to the agent: GET /api/v1/agent -> "runtime" {model, autocompact, autocompact_pct, nightly_reset, reset_seq,
timezone}. This launcher (2.1394.0, #4068) only loads the env file, finds Python and starts mcp/agent_run.py --launch,
which applies them -- the same code for this launcher and agent_launcher.sh:
  - starts the agent command, ALWAYS in a fresh session (never pass --continue / --resume here)
  - model:         appends `--model <model>` (empty = the command's own default)
  - auto-compact:  on + percentage -> CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=<pct>; off -> DISABLE_AUTO_COMPACT=1
  - restarts it (fresh session) when the model / auto-compact settings change, when an admin presses "Reset now"
    (reset_seq goes up), once a night at nightly_reset (HH:MM in runtime.timezone), and whenever the command exits by
    itself (after KALMIDO_RESTART_DELAY seconds)
  - git author (2.396.0, #3386): GIT_AUTHOR_NAME / _EMAIL and GIT_COMMITTER_NAME / _EMAIL from runtime.git_author (a
    project with a repository may name its own: data.repo.git_author of a task), KALMIDO_GIT_COAUTHOR=1 when the agent
    should append a Co-Authored-By line; an older server without git_author: nothing is set
  - work window (2.236.0, #2905): outside the work window of its work style no new session starts
  - interim summary (2.233.0, #3189: rotate_size / rotate_runs / rotate_idle_min, sent as rotate_tokens etc.): applied per chat
    conversation by mcp/agent_run.py in --events mode; without --events the command runs one session (not applicable)
It polls GET /api/v1/agent every KALMIDO_POLL seconds (default 60): one small request, no events are consumed.

usage: pwsh -File agent_launcher.ps1 [-e ENV_FILE] [--once] [-- COMMAND ...]
  -e ENV_FILE    default .\kalmido-agent.env (readable only by the agent's account), lines KEY=VALUE:
                   KALMIDO_URL=https://tasks.example.com
                   KALMIDO_TOKEN=abk_...          the agent's API token (Settings > Agents); a TEAM agent's run never sees it
                                                  (2.1386.0, #6668): it gets the token of its request only (one person)
                 every variable in it is passed to the command too (the MCP server mcp/kalmido_mcp.py reads the same two)
  COMMAND        what to start (default: KALMIDO_AGENT_CMD of the env file, else claude; KALMIDO_AGENT_PROFILE claude |
                 codex | generic names the tool, 2.391.0). Example:
                   pwsh -File agent_launcher.ps1 -e $HOME\.config\kalmido\agent.env -- claude -p "Work through your Kalmido events"
  --once         print the command line and environment it would use, then exit (a dry run; the token is never printed)
  --events       event mode (2.35.0, recommended for Claude Code): starts mcp/agent_run.py (Python 3), which waits for the
                 agent's events and runs COMMAND once per event, headless with stream-json: steps, model, permission
                 mode, typing / status, plan usage ring, reply reference, approval cards; the final text of a chat run
                 is posted as the answer. COMMAND is then the plain agent command without -p. Same as KALMIDO_EVENTS=1.
                 Optional keys there: KALMIDO_PROMPT_FILE (text in front of every event), KALMIDO_USAGE_LIMIT (pause new
                 runs at this % of the week), KALMIDO_USAGE_FILE (a status line file {at, rate_limits}), KALMIDO_STATE_DIR
                 (event cursor), KALMIDO_APPROVAL_CHECK=0 (2.40.0: no check of chat answers that ask to decide without an
                 approval block), KALMIDO_NOTICE_COMPACTED (2.41.0: the notice in the chat when a run compacts its
                 conversation, {0} = the time). Without --events: the command runs as it is.
  -EnvFile, -Once, -Events  the same as -e, --once, --events (PowerShell spelling, this script only)
  KALMIDO_HOST   the computer name shown in Kalmido (2.44.0; default: the computer name), sent once at start
  KALMIDO_PYTHON the Python to use (default: py / python / python3 on Windows, python3 / python elsewhere)
  KALMIDO_POLL / KALMIDO_RESTART_DELAY  seconds between two reads of the settings (60) / before a restart (10)
  KALMIDO_TOOLSETS only these MCP tool packages, e.g. tickets,code,office (2.391.0; chat is always on, default: all)
Exit codes: 0 stopped (TERM / INT end the command with everything it started, KILL after 30 s; Windows: taskkill /T, /F after
30 s), 1 Kalmido not reachable at the start, 2 a wrong start (no env file, KALMIDO_URL / KALMIDO_TOKEN missing, no Python 3 or
no mcp/agent_run.py).
Needs: Windows PowerShell 5.1 or PowerShell 7+ and Python 3.9+ (Windows: with the tzdata package for the time zone of the
nightly restart, else the computer's local time). See docs/AGENTS.md "Set up an agent" for a scheduled task.
2.1394.0 (#4068): two steps, the same in agent_launcher.sh (tests/launcher_parity_test.py checks the markers); every capability
of tests/launcher_parity_test.py lives in mcp/agent_run.py.
#>
# arguments by hand (no param block): everything after "--" (or the first unknown word) is the command, as in the .sh
$OnWindows = ($env:OS -eq 'Windows_NT')
# 2.443.0 (#2940): a run from the scheduled task writes with *>> into agent.log, which never sees [Console]::Error: there the
# line goes to the information stream
function Log([string]$m) {
  $l = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') agent_launcher: $m"
  if ([Console]::IsErrorRedirected) { [Console]::Error.WriteLine($l) } else { Write-Information -MessageData $l -InformationAction Continue }
}
$EnvFile = '.\kalmido-agent.env'; $Flags = @(); $Command = @()
for ($i = 0; $i -lt $args.Count; $i++) {
  $a = [string]$args[$i]
  if ($a -in @('-e', '--env', '-EnvFile')) { $i++; if ($i -ge $args.Count) { Log '-e needs a file'; exit 2 }; $EnvFile = [string]$args[$i] }
  elseif ($a -in @('--once', '-Once')) { $Flags += '--once' }
  elseif ($a -in @('--events', '-Events')) { $Flags += '--events' }
  elseif ($a -in @('-h', '--help')) { $h = @(Get-Content -LiteralPath $PSCommandPath); $h[1..([array]::IndexOf($h, '#>') - 1)]; exit 0 }
  elseif ($a -eq '--') { $Command = @($args | Select-Object -Skip ($i + 1) | ForEach-Object { [string]$_ }); break }
  else { $Command = @($args | Select-Object -Skip $i | ForEach-Object { [string]$_ }); break }
}
$ErrorActionPreference = 'Stop'

# kalmido-starter-step: env_file -- KEY=VALUE per line (an optional "export ", quotes around the value), # comments (2.443.0,
# #2940: also behind a value, after a space, as in the shell); all go into this process's environment, so the runner and the
# command inherit them. KALMIDO_ENV_FILE = its full path: the model's process never gets KALMIDO_TOKEN (#6457)
if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) { Log "cannot read $EnvFile"; exit 2 }
foreach ($raw in Get-Content -LiteralPath $EnvFile) {
  $l = $raw.Trim()
  if (-not $l -or $l.StartsWith('#')) { continue }
  if ($l -match '^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
    $k = $Matches[1]; $v = $Matches[2].Trim()
    if ($v -match '^"([^"]*)"(\s+#.*)?$' -or $v -match "^'([^']*)'(\s+#.*)?$") { $v = $Matches[1] }
    else { $v = $v -replace '\s+#.*$', '' }
    [Environment]::SetEnvironmentVariable($k, $v, 'Process')
  }
}
$env:KALMIDO_ENV_FILE = (Resolve-Path -LiteralPath $EnvFile).ProviderPath
# the core (agent_run.py --launch) reads the token from KALMIDO_ENV_FILE; its environment carries none (#6457, Fable reader F5 of 2.1394)
Remove-Item Env:KALMIDO_TOKEN -ErrorAction SilentlyContinue

# kalmido-starter-step: python -- KALMIDO_PYTHON, else the first Python 3 on PATH, and mcp/agent_run.py next to this file
$Py = $env:KALMIDO_PYTHON
$order = if ($OnWindows) { @('py', 'python', 'python3') } else { @('python3', 'python') }  # Windows: python3 may be the Store stub
if (-not $Py) { foreach ($n in $order) { if (Get-Command $n -CommandType Application -ErrorAction SilentlyContinue) { $Py = $n; break } } }
$PyExe = if ($Py) { Get-Command $Py -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1 } else { $null }
if (-not $PyExe) { Log 'needs Python 3 (set KALMIDO_PYTHON, or python3 / py / python on PATH)'; exit 2 }
$Runner = Join-Path $PSScriptRoot 'agent_run.py'
if (-not (Test-Path -LiteralPath $Runner -PathType Leaf)) { Log "$Runner missing"; exit 2 }

# kalmido-starter-step: run -- agent_run.py --launch does the rest. PowerShell cannot replace itself with it (the .sh uses
# exec), so it runs it as a native command and passes its lines on: the log lines (stderr) the way Log writes them -- the
# scheduled task's *>> agent.log only sees PowerShell's streams --, the --once line (stdout) as output. TERM / INT here
# (PowerShell 7.2+ on macOS / Linux) go on to the runner as TERM, which ends the command with everything it started; on
# Windows the runner notices when this launcher is gone (KALMIDO_LAUNCHER_PID) and does the same.
$pre = @(); if ([IO.Path]::GetFileNameWithoutExtension($PyExe.Source).ToLower() -eq 'py') { $pre += '-3' }
$env:KALMIDO_LAUNCHER_PID = "$PID"
if (-not $OnWindows) {
  try {
    Add-Type -TypeDefinition @'
using System.Diagnostics;
using System.Runtime.InteropServices;
public static class KalmidoStop {
  static PosixSignalRegistration term, intr;
  static void Ask() {  // TERM to this launcher's own children (the runner); the launcher itself ends when the runner has
    try { Process.Start("pkill", "-TERM -P " + Process.GetCurrentProcess().Id); } catch { }
  }
  public static void Watch() {
    term = PosixSignalRegistration.Create(PosixSignal.SIGTERM, c => { c.Cancel = true; Ask(); });
    intr = PosixSignalRegistration.Create(PosixSignal.SIGINT, c => { c.Cancel = true; Ask(); });
  }
}
'@
    [KalmidoStop]::Watch()
  } catch { Log "no clean stop on TERM / INT here (PowerShell 7.2+ needed): $($_.Exception.Message)" }
}
$ErrorActionPreference = 'Continue'  # Windows PowerShell 5.1: a stderr line of a native command under 2>&1 must not end the script
$argv = @($pre + @($Runner, '--launch') + $Flags + @('--') + $Command)  # an array: a literal -- would be taken by PowerShell
& $PyExe.Source @argv 2>&1 | ForEach-Object {
  if ($_ -is [System.Management.Automation.ErrorRecord]) {
    $l = "$_"
    if ([Console]::IsErrorRedirected) { [Console]::Error.WriteLine($l) } else { Write-Information -MessageData $l -InformationAction Continue }
  } else { $_ }
}
exit $LASTEXITCODE
