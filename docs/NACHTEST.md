# Retest guide (template)

*Since #7535.* The review job of the starter's dispatcher reads this file before it retests a built task (project switch
*Retest after the build* = *By a review job*, see [AGENTS.md](AGENTS.md#retest-after-the-build)). Copy it into your project's
repository as `docs/NACHTEST.md` (another path: `retest_doc` in the dispatcher's `KALMIDO-DISPATCH.json`) and fill in the steps.

**No values in this file.** It lies in the repository: everyone who reads the repository reads it, and the agent that built
the change could edit it. It names only **variables**; their values (the address of the test instance, test accounts,
passwords) stay in a local file outside the repository on the computer the agent runs on, or in the runner's env file.
The review job uses the values and never writes one into its evidence, a comment or a commit; the dispatcher also replaces
the value of every `NACHTEST_*` variable of its environment in the evidence by the variable's name. A commit that changes
this file is told to the person, and its retest follows the guide from before that commit.

## Where the values are

- `NACHTEST_ENV_FILE`: the path of the local file with the values below (one `NAME=value` per line, outside the repository).
- `NACHTEST_URL`: the address of the test instance that runs the state of the main branch.
- `NACHTEST_USER`, `NACHTEST_PASSWORD`: the test account (never a real person's account, never production data).

## Is the test instance ready?

The dispatcher starts the retest only once the test instance runs the built commit. Give it a ready command in the runner's
env file (`KALMIDO_DISPATCH_READY_CMD`, `{commit}` = the commit): it ends with 0 when the instance runs that commit or a
younger one that holds it. Without one the retest starts at once.

## How to test

1. Read the task, its comments and earlier retests (they come with the brief as data): what was broken here before?
2. Open the test instance (`NACHTEST_URL`) and sign in with `NACHTEST_USER`.
3. Do what the task describes, the way a person would: in, on, back. Note what you did and what you saw.
4. Without a test instance: read the change at the checkout of the main branch and run the project's test command; say so
   in the evidence.

## What counts as evidence

- *works*: the steps you took and what you saw (a page, a message, a number), short and checkable by a person.
- *does not work*: what you did, what you expected and what happened instead.

The very last line of the review job's answer is `RETEST: works - <evidence>` or `RETEST: fails - <reason>`.
