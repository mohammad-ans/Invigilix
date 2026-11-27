# Folio

A cross-vendor development kit for the Secure Examination Management System. The product stack is React, FastAPI and PostgreSQL. One checked-in SRS, one design system and explicit branch scopes let Claude Code, Gemini CLI and Codex build separate features in parallel.

## 1  Establish the baseline

Extract the archive, then copy the contents of folio-repo-kit, including .github, into your new repository. For an empty remote, the simplest bootstrap is to create it with a README, clone it, and merge the kit as the first PR. The root AGENTS.md is the shared instruction file. CLAUDE.md and GEMINI.md import it for their respective tools. The kickoff prompt below also names the file explicitly.

- docs/requirements.md is the text-readable SRS with 29 requirement IDs and 12 acceptance cases. Its PDF is beside it.
- collaboration/ownership.json assigns each requirement to one owner, maps acceptance cases, and allows writes only under named paths. A shared test can have multiple contributors in their respective test directories.
- docs/pages.md assigns production pages. docs/theme.md and frontend/src/design/ define their shared visual system. Open docs/Folio-preview.html directly for the offline interactive reference.
- contracts/exam_schema.sql and contracts/attempt-api.md define the relational baseline and the critical handoffs between owners.

Establish this baseline on main before creating the three feature branches. Enable Actions for the repository. Replace the owner in .github/CODEOWNERS.example with a real maintainer with write access and rename it to .github/CODEOWNERS. In GitHub’s branch rule or ruleset for main, require a pull request and the status check named scope. Run the workflow on a first PR so the check is available to select. Require up-to-date branches. Where available, require Code Owner approval, dismiss stale reviews and restrict bypass. A solo owner cannot approve their own PR. Use manual merge review and the required status check in that setup. Some settings depend on repository visibility and plan.

Suggested bootstrap commands for a new repo you already cloned, after copying the kit and reviewing the files:

```sh
git switch -c foundation/bootstrap
git add .
git commit -m "Add exam requirements, Folio design and ownership rules"
git push -u origin foundation/bootstrap
```

Merge the baseline once through the repository’s bootstrap process, then enable the required check. For a completely empty remote, create the initial main commit first. The scope workflow reads rules and code from its base commit, so the baseline must already be on main before enforcing it.

## 2  Give each model a separate checkout

From the main checkout with the baseline merged:

```sh
git fetch origin
git worktree add -b work/authoring ../exam-authoring origin/main
git worktree add -b work/delivery ../exam-delivery origin/main
git worktree add -b work/results ../exam-results origin/main
```

Open each path in its own coding-agent session. Start Claude Code inside ../exam-authoring, open ../exam-delivery as a local project in Codex, and start Gemini CLI inside ../exam-results. In terminal sessions, change to the worktree directory and run claude or gemini after installing and signing in to that client. For Codex, open the delivery worktree as the local folder. The choices are interchangeable. Use each client’s normal model selection and authentication. For a hosted runner, assign the same branch and paths in its own clone. Different tools do not need to communicate with each other or share API keys.

| Suggested session | Owns | First deliverable |
| --- | --- | --- |
| Claude Code on work/authoring | Exam configuration, question bank, enrollment, sandbox and bulk import | Publish a three-item paper with a validated mark total and immutable question versions. |
| Codex on work/delivery | Candidate dashboard, attempt, autosave, expiry, preferences and scratchpad | Start twice, receive one paper, disconnect, reconnect and recover accepted progress. |
| Gemini CLI on work/results | Monitor, announcements, grading, analytics, release and reports | Score the 7/10 SRS example, block early release and verify the issued PDF. |
| Human integrator on foundation/topic | Access, shared schema, API contracts, theme, routing, migrations and integration tests | Mount the three routers and page modules. Run the cross-feature acceptance cases and own final release. |

Assign one person to dispatch work. Record the branch, model session, task and baseline SHA in one GitHub issue per lane. The manifest defines the reservation. One active writer per branch is a team rule. Git worktrees isolate changes on a machine. GitHub does not lock a requirement or prevent two machines from pushing to the same branch. Keep assignments on main and make handoffs explicit.

## 3  Start each session with the same prompt

```text
Read AGENTS.md, docs/requirements.md, docs/pages.md, docs/theme.md,
contracts/attempt-api.md and collaboration/ownership.json.
Confirm your current branch and identify its owned requirements and paths.
Build the first deliverable for this branch using the shared Folio primitives.
Use the agreed API shapes and fixtures until dependent code is merged.
Exercise your mapped acceptance cases. In your PR include the SRS IDs,
test results, and desktop and 360 px screenshots for changed pages.
If a shared contract needs changing, propose it to the integrator.
```

## 4  Integrate without overriding each other

The integrator supplies a common session/authorization dependency, migrations and a router skeleton in a foundation branch. Parallel feature work can begin against fixtures. Before handoff, authoring and delivery agree on the frozen paper payload. Delivery calls the results-owned objective grading function in the finalization transaction. An example callable boundary is score_objective(kind, selected_ids, correct_ids, rule, max_marks) returning decimal marks. Results implements that policy and grants no candidate access to the key.

Feature PRs are limited to their manifest paths. The workflow checks both sides of renames and fails on unfamiliar branches or an incomplete file list. Foundation PRs change only the enumerated shared paths. A branch name grants no identity or reviewer guarantee. Protect the workflow, rules and shared files with actual review settings. Theme consistency also needs screenshot review. A path check cannot assess typography, behavior or the meaning of an SRS change.

If two owners need a new response field or theme component, land one small foundation PR first. Each model then updates its branch from main and reruns its tests. Merge independently testable features, then run integrated acceptance tests before release. Keep commits, pushes, builds and deployments within the competition deadline.

Run the guard’s tests with python3 -m unittest discover -s tools. A local sanity check from the repo root:

```sh
python3 tools/check_scope.py --branch work/delivery frontend/src/features/delivery/Attempt.jsx
```

## 5  Run the theme

Open docs/Folio-preview.html for a self-contained demo. Switch roles in the masthead. Answer, flag or review a question, try the scratchpad and settings, post a preview announcement, or filter the account register. The demo clock is a fixed sample. Preview state and fictional records are separate from production data. The offline HTML embeds an MIT-licensed React runtime solely to open directly from disk.

For development run the editable React source with a current Node release supported by Vite 7 (20.19+ or 22.12+):

```sh
cd frontend
npm install
npm run dev
```

Commit the generated lockfile on a foundation branch. Use npm run build for the production bundle and npm ci for subsequent locked installs. The source uses the dependency versions in package.json. The starter contains the design prototype and contracts. The three feature branches implement the live FastAPI workflows described by the SRS.

## Reference documentation

- [Git worktrees](https://git-scm.com/docs/git-worktree)
- [Codex repository instructions](https://developers.openai.com/codex/guides/agents-md/)
- [Claude Code project instructions](https://code.claude.com/docs/en/memory)
- [Gemini CLI context files](https://geminicli.com/docs/cli/gemini-md/)
- [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [GitHub code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
