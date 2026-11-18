# Launcher capabilities

What a host that runs an agent for Kalmido does, and where the reference launcher does it (2.35.0, #1098).

tests/launcher_parity_test.py checks that agent_run.py (with agent_extras.py / agent_job.py) carries every capability (a line '# kalmido-capability: <id>' where it does it) and has the code named in 'core'. A new capability of a hosted service gets its file here first; the test then fails until agent_run.py has it. Since 2.1394.0 (#4068) the launchers agent_launcher.sh and agent_launcher.ps1 only load the env file, find Python and start `agent_run.py --launch`: the runtime loop (model, auto-compact, restarts, git author, work window, host name, revoked token) lives in agent_run.py too, so a capability never needs a launcher change.

One file per capability, `<id>.json` with `id`, `since`, `what` and optionally `core` (code `agent_run.py` must have),
or `server` (done by the server alone, not checked; until #4068 also `launcher`, done by the launchers themselves). Until #6887 this was the
one file `launcher_capabilities.json`; two packages that each added a capability collided in it in GitHub's merge queue.
No runtime reads these files, they are no starter files.
