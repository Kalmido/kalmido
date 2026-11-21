# Upgrading Kalmido

What an update needs from you, version by version, and how far back you can go. The steps of an update itself are in the
[README](../README.md) and in [Production updates](SELF-HOSTING.md#production-updates); the way back step by step in
[Back to the previous version](SELF-HOSTING.md#back-to-the-previous-version).

## Rule for every release

A release that needs a step from you lists it here, in the same release, whatever its version number says: **a version
number alone does not tell you whether a step is needed**, 2.37, 2.45 and 2.149 needed one and were minor versions.
Read this list before an update; nothing listed between your version and the new one means nothing to do.

A big jump is allowed: every migration runs in order on the first start. Do the steps of **every** version you pass, and
make a backup first. There is no need to stop at each version in between, with one exception: the oldest version an update
starts from.

## Oldest version to update from: 2.1000

Since 2.1380 (#6826) a version updates only a database that last ran **2.1000.0 or newer**. The one-time data steps and
column steps every such database has behind it are gone from the code. A database that last ran an older version (or one
from before 2.149 without a version stamp) is refused at the start with a line starting `FATAL: this database`, and the
container stops with exit code 3; nothing is changed. A backup from such a version is refused by *Check* and *Restore* the
same way. The way through: update to 2.1001.0 (the first release from the limit on; there was no 2.1000.x) or any
newer one older than 2.1380 first, start it once, then update to the current version (a backup made there restores here). A new, empty database is not affected. The limit is
`MIN_FROM` in `kalmido/core/db.py`; a release that raises it says so here.

**How far back, in short (#6616):** directly from 2.1000; from 2.37 on with one stop at 2.1001.0; an install from before
2.37 (SQLite, `data/tasks.db`) goes through 2.37.0 first - its start says so and names the commands
([Installs from before 2.37](SELF-HOSTING.md#installs-from-before-237-sqlite)). Tested starting points (the dumps in
`tests/fixtures/upgrade`, suite `p2192_c_upgrade`): 2.1001.0 and 2.1380.0 are updated and compared, 2.101.0 and 2.941.0 must
be refused with the way through.

## Versions that need a step

| Version | What to do | Details |
|---|---|---|
| 2.37 | PostgreSQL is required: add the database service, set `POSTGRES_PASSWORD` and `DATABASE_URL`. The installer does it. An install still on SQLite (2.36 or older) must update to 2.37.0 first: the move from SQLite is not in newer versions any more (#5304). | [Installs from before 2.37](SELF-HOSTING.md#installs-from-before-237-sqlite) |
| 2.45 | The server key moves into a file on its own folder: `mkdir secret && chown 1000 secret` next to `data`, then restart. The installer does it. | [The server key](SELF-HOSTING.md#first-setup-and-the-server-key) |
| 2.46 | One kind of server: the instance mode is gone; its variable is only read for the row-level security check (see ENV.md). | CHANGELOG 2.46.0 |
| 2.79 | Reverse proxy on the host in front of a published Docker port: `KALMIDO_TRUSTED_PROXIES` now defaults to loopback only, the Docker bridge gateway no longer counts: add it (`KALMIDO_TRUSTED_PROXIES=127.0.0.1,::1,172.17.0.1`). With a virus scanner an upload it could not check is held back (`KALMIDO_CLAMD_STRICT=0`: as before). | CHANGELOG 2.79.0 |
| 2.149 | `.env` needs a `COMPOSE_PROFILES` line (for example `COMPOSE_PROFILES=localdb,clamav`) and Docker Compose 2.20 or newer. The installer adds the line. | [Update, downgrade and restore](SELF-HOSTING.md#update-downgrade-and-restore) |
| 2.182 | The container runs read-only as user 1000. An installation that ran it as root: `sudo chown -R 1000:1000 data secret` once, or keep your own `user:` line. An own compose file needs a writable `/tmp`. | [First setup](SELF-HOSTING.md#first-setup-and-the-server-key) |
| 2.239 | The server log shortens IP addresses and names accounts by number: fail2ban and the like need `KALMIDO_LOG_FULL_IP=1`. | CHANGELOG 2.239.0 |
| 2.240 | The mail server is reached with a checked certificate: an own certificate or an IP address as host needs `KALMIDO_SMTP_INSECURE=1`, otherwise no mail goes out. Mails taken in from the instance mailbox are deleted there (`KALMIDO_IMAP_KEEP=1`: only marked read). An embedding service on another host needs `KALMIDO_EMBED_EXTERNAL=1`. | CHANGELOG 2.240.0 |
| 2.499 | On the channel *Web Push* nothing goes to the public `ntfy.sh` any more. If you had subscribed to your random topic there as a backup, for example for reminders, switch to the channel *ntfy* under *Settings > Notifications*. An own ntfy server changes nothing. | [Installed app and push](SELF-HOSTING.md#installed-app-pwa-and-push) |
| 2.1312 | A workspace mailbox sends only with an SMTP user name and password and only through port 465 / 587 (25 or another port: a `host:port` of the allowed internal hosts). A mailbox stored without a login or on another port sends nothing until an admin fixes it (the dialog says why). The admin's allowed internal hosts for *mail* now count only for the workspaces of the server's admins, and an entry without a port only for the mail ports; `KALMIDO_CALENDAR_ALLOW_HOSTS` still counts for every workspace. | CHANGELOG 2.1312.0 |

## Format limits: going back

Going forward never needs one of these. Going **back** is the other way round: **from 2.763 on, back only through a backup.**
Since 2.763 (#5269, the first stage of the shared core) many releases move data one way - into the shared core, into real
column types, into one search index - and drop the old tables or columns. Each such release raises the database's limit
(`back_floor` in the table `kalmido_meta`, only ever raised); an older image refuses to start below it and names the limit and
the reason (emergency only: `KALMIDO_ALLOW_DOWNGRADE=1`, which starts it on data it does not fully know). Its CHANGELOG entry
names the one-way step. To go back below such a release, restore a backup made before the update; there is no step that turns
the data back. Going back to the version right before an update (the automatic rollback after a failed update, an operator who
keeps the previous image) works while that update raised no limit.

Older releases had steps by hand before going back (`decrypt-all` below 2.42, `decrypt-private` below 2.64, `decrypt-wiki` and
`docs-to-server-key` to 2.125 or older); from 2.763 or newer, going back that far goes through a backup of that time anyway. **Never go back below 2.149:** those versions have no start check at all and would run on a newer database without a
word (`BACK_LIMITS` in `kalmido/core/db.py`); every version from 2.359.3 on refuses to start below the limit of its database.
