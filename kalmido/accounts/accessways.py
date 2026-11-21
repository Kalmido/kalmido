"""#7633 (decision 20.11.2026, audit #6007 F1): THE list of every way into an account and every way that sends its data out.
A new password (the own change with the tick, the admin's reset, the reset link) and the first second factor end them through
ONE place, accounts/sessions.py ses_access_end, which reads this table; there is no second way to end one. A new table that holds a
key, a token or a target outside (a token_hash, a secret ...) must be named here - as a way (ACCESS_WAYS) or as no way into the
account (ACCESS_NOT) with the reason; tests/access_ways_test.py reads the schema (key columns, columns with an address outside, the
fixed list of targets inside sealed data) and fails otherwise (the 13 fixes of #6354 .. #6558 were each one more way written in
by hand). Pure data, no imports: the test reads it without the app.

A row: key, tables (the tables / "table.column" it lives in), end, what (for people), and
  end = "session": the sessions themselves - ses_end, which every caller runs before ses_access_end
        "always":  also when the tick is taken out (a sign-in begun with the old password, the scan inbox keys, #6498 / #6499)
        "tick":    with the tick of the own password change (set by default, #4375), always with a reset and the first second factor
        "off":     like "tick", but switched off (enabled false / hook_state, the reason 'password', its queue emptied) instead
                   of deleted: the person switches it on again in the settings
        "stays":   not ended (why = the reason; the password dialog names the kind: "check what you do not know")
  sql   = statements run with (uid,) - or fn = "module:function" (relative to kalmido.accounts) called as fn(c, uid)
  mail  = the security mail (accounts/secmail.py SEC_EVENTS) sent when one is made
  where = #7633 F5: a "stays" way told by the mail out_new: the place in the app where the person checks it; the mail closes with
          "stays after a new password too: check it under <where>" (an "off" way: "a new password switches ... off")
Organisation webhooks, channels and document flows are no row: they belong to the organisation and act per event with the admin
right of the person who switched them on (integrations/webhooks.py, notify/channels.py, docs/flows.py fl_hook_author_ok)."""

N_ = str  # marks a text for the translation files (tools/i18n_check.py); no import, so the test reads the list without the app

ACCESS_WAYS = (
    {"key": "sessions", "tables": ("sessions", "kid_pin_open", "push_subs"), "end": "session",
     "what": "signed-in browsers and apps (with the push subscriptions made in them, push_subs.session_hash)"},
    {"key": "pending", "tables": (), "end": "always", "fn": ".sessions:ses_pend_end",
     "what": "a sign-in or second-factor enrolment begun with the old password (#6498)"},
    {"key": "scan_keys", "tables": ("doc_fetchers",), "end": "always", "fn": "..docs.scankeys:sk_revoke_all",
     "what": "scan inbox keys and receipt fetchers (#2865, #3453)"},
    {"key": "app_passwords", "tables": ("app_passwords",), "end": "tick", "mail": "apppw_new",
     "sql": ("DELETE FROM app_passwords WHERE user_id=?",), "what": "app passwords (calendar and contacts apps)"},
    {"key": "api_tokens", "tables": ("api_tokens",), "end": "tick", "mail": "token_new",
     # an agent's tokens belong to the agent's account: they stay (2.360.0 A #2496)
     "sql": ("DELETE FROM api_tokens WHERE user_id IN (SELECT id FROM users WHERE id=? AND COALESCE(kind, 'user')<>'agent')",),
     "what": "the person's own API tokens"},
    {"key": "event_feeds", "tables": ("ev_cal_feeds",), "end": "tick", "sql": ("DELETE FROM ev_cal_feeds WHERE user_id=?",),
     "what": "calendar feed links of events"},
    {"key": "absence_feeds", "tables": ("abs_cal_feeds",), "end": "tick", "sql": ("DELETE FROM abs_cal_feeds WHERE user_id=?",),
     "what": "calendar feed links of absences"},
    {"key": "task_feed", "tables": ("users.ical_token_hash",), "end": "tick",
     "sql": ("UPDATE users SET ical_token=NULL, ical_token_hash=NULL, ical_token_at=NULL WHERE id=?",), "what": "the task feed link"},
    {"key": "upload_token", "tables": ("users.drop_token_hash",), "end": "tick",
     "sql": ("UPDATE users SET drop_token=NULL, drop_token_hash=NULL, drop_token_at=NULL, drop_agent=0 WHERE id=?",),
     "what": "the upload token (/drop)"},
    {"key": "webhooks", "tables": ("webhooks",), "end": "off", "mail": "out_new",
     # #7633 F6: also one already off (after failures, by hand) gets the reason 'password': the list says "switched off by the new
     # password" and the hint, a stranger's webhook is not switched on again as "off after failures"
     "sql": ("DELETE FROM webhook_queue WHERE webhook_id IN (SELECT id FROM webhooks WHERE user_id=? AND org_id IS NULL AND agent=0)",
             "UPDATE webhooks SET enabled=false, disabled_reason='password', updated_at=now() "
             "WHERE user_id=? AND org_id IS NULL AND agent=0 AND (enabled OR disabled_reason<>'password')"),
     "what": "the person's own webhooks (data goes out to an address)"},
    {"key": "channels", "tables": ("notify_channels",), "end": "off", "mail": "out_new",
     "sql": ("DELETE FROM notify_channel_queue WHERE channel_id IN (SELECT id FROM notify_channels WHERE user_id=? AND org_id IS NULL)",
             "UPDATE notify_channels SET enabled=false, disabled_reason='password', updated_at=now() "
             "WHERE user_id=? AND org_id IS NULL AND (enabled OR disabled_reason<>'password')"),  # #7633 F6: as the webhooks
     "what": "the person's own forwardings to Slack, Matrix, Telegram, Signal"},
    # #7633 F1: the webhook action of a flow in the private workspace (the address lives in the sealed flow, doc_rules.data):
    # hook_state 'password' holds its calls (integrations/docflowhook.py dfh_author_ok, a waiting call goes 'off'); the flow and
    # its other actions run on, saving the flow again switches the webhook on (docs/flows.py fl_hook_reset). hook_state counts
    # only for a flow with a webhook (docs/web.py _rules_v), so every private flow is marked. An organisation's flows: no row.
    {"key": "flow_hooks", "tables": ("doc_rules.data",), "end": "off", "mail": "out_new",
     "sql": ("UPDATE doc_flow_runs SET hook='off' WHERE ws='u' || CAST(? AS TEXT) AND hook='wait'",
             # #7633 F6: also a webhook off after failed calls ('admin' holds the whole flow and is an organisation's)
             "UPDATE doc_rules SET hook_state='password', updated_at=now() WHERE ws='u' || CAST(? AS TEXT) AND hook_state IN ('', 'failures')"),
     "what": "the webhook action of the person's document flows in the private workspace"},
    {"key": "passkeys", "tables": ("webauthn_creds",), "end": "stays", "mail": "passkey_new",
     "why": "a second factor of the person, removed in the two-factor list; the dialog points there (#6354)"},
    {"key": "agents", "tables": (), "end": "stays", "mail": "agent_token_new",
     "why": "an agent's tokens and webhook belong to the agent's account (its webhook address is set by an instance admin, with "
            "the password and a mail out_new since #7633 F3, agents/admin.py); the dialog points to Your agents (#2496, #6354)",
     "where": N_("Settings > Agents")},
    {"key": "ntfy", "tables": (), "end": "stays",
     "why": "a topic name, no key: whoever knows it reads the push texts; the person changes it under Notifications"},
    {"key": "hooks_in", "tables": ("hook_in", "issue_hooks", "list_envs"), "end": "stays",
     "why": "inbound hooks of a project (tasks, error reports, deploys come in): they belong to the project, not to the account"},
    {"key": "git", "tables": ("git_conns",), "end": "stays",
     "why": "the Git connection of a project: it belongs to the project and reads only the repository"},
    {"key": "mail_in", "tables": ("mail_tokens", "doc_mail", "hub_tokens"), "end": "stays",
     "why": "secret e-mail addresses that let mail come in (tasks, documents, replies): nothing goes out through them"},
    {"key": "mailbox", "tables": ("hub_mailboxes",), "end": "stays", "mail": "out_new",
     "why": "the own mailbox: every new target for sending (server, port, user, the first password of a server that came in "
            "without it) asks the password (hub/mailbox.py mbx_put, #7633 F2); its login is the mail provider's",
     "where": N_("E-mail filing > Mailbox")},
)

# tables with a key or token that are no way into or out of an account: what the person shares on purpose with others (they end
# by themselves or in their own list), one-time links, an organisation's connections (its admins manage them). #7633 F1: also
# "table.column" with an address outside (tests/access_ways_test.py OUT) through which nothing of the account goes out by itself
_LINK = "a link shown to people: nothing is sent there"
_READ = "an address data is read from with the person's own access there: nothing of the account goes out"
ACCESS_NOT = {
    "conn_invites": "an invitation link for someone without an account, once",
    "disc_tokens": "the confirmation link of the findable address, once",
    "user_invites": "the invitation / reset link itself (once, short)",
    "forms": "a public form of a project: people send in, nothing is read",
    "fs_ext_links": "a shared file link, listed with the file",
    "fs_upload_requests": "an upload request for a folder, listed with the folder",
    "public_links": "the read-only link of a project, listed in its settings",
    "wiki_shares": "a shared wiki page, listed with the page",
    "sched_polls": "a date poll for guests",
    "office_pay_links": "a customer's payment link of an invoice",
    "office_signoffs": "a customer's sign-off link of an offer",
    "portal_logins": "a customer's sign-in link to the portal",
    "portal_tickets": "a customer's ticket link",
    "office_issuer_keys": "an organisation's issuer key (its admins)",
    "office_peppol": "an organisation's Peppol access (its admins)",
    "nl_conns": "a workspace's newsletter service (its admins)",
    # #7633 F1: addresses outside that send nothing of the account by themselves
    "bookmarks.url": _LINK, "bookmarks.image_url": _LINK, "events.url": _LINK, "tasks.url": _LINK, "list_links.url": _LINK,
    "office_fixed_costs.url": _LINK, "rss_items.url": _LINK, "git_commits.url": _LINK, "git_prs.url": _LINK,
    "video_versions.url": _LINK,
    "cal_subs.url": _READ, "contact_srcs.url": _READ, "rss_feeds.url": _READ, "rss_feeds.site_url": _READ, "pl_conns.url": _READ,
    "pl_sources.url": _READ, "kk_conns.url": _READ + " (only the mark 'archived' of a bookmark that came from there goes back)",
    "office_bank_accounts.fints_server": _READ + " (an organisation's bank account, its admins)",
    "msv_links.base_url": "the person's account on another Kalmido server: a request goes there only when the person acts in that view",
    "oauth_clients.redirect_uris": "where a hosted MCP client gets its one-time code after the person agreed (with the password, "
                                   "#6499); the access is an agent's token (row agents)",
    "oauth_codes.redirect_uri": "the redirect address of one consent, compared with the client's",
    "office_pay_sessions.url": "a customer's checkout page at the payment provider",
    "office_doc_log.target": "what a log entry is about (doc ...), no address",
    "doc_office_moves.target": "where a person moved receipts inside Kalmido, no address",
    "office_meals.host": "who hosted a business meal, no address",
}
