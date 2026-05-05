# Making BriefCase shareable with teammates

## Status

**Deferred 2026-05-04.** Logged for future pickup. Demo'd to the team and they want it; this captures the rollout plan + key design calls so we can resume cleanly when ready.

## The trigger

I demoed BriefCase + Kit + the sidecar + the Chrome extension to my team. They want it on their machines. Right now the system is heavily Brendan-shaped — hardcoded paths, voice profile assumed to exist, PDLC integration assumed, code-research / PR-review checkboxes a PM wouldn't want, etc. This doc is the plan for making it installable for someone who isn't me.

## The core insight

This isn't about per-role *access control*. It's about per-role *default experience*. The PM doesn't see code-research checkboxes because their default profile doesn't enable it, but they could toggle it on. Same install, different defaults. Don't maintain "PM build" vs "dev build" — maintain one build with feature flags.

## Phased rollout

### Phase 1 — Generalize. Same features, no hardcodes.

- Every Brendan-shaped path moves into `settings.yaml` with sensible defaults: vault path, code repo paths (a list, optional), voice profile path, PDLC root.
- Kit handles missing-vault, missing-codebase, missing-PDLC gracefully (silent skip, not crash).
- Empty-initiative-DB flow: Kit detects on startup and offers to walk through setup ("I see no initiatives yet — want to add one? Or start with a blank slate?").
- Drop the `needs_reply` checkbox from the popup (redundant with brain_dump + "draft a reply later" in context).

### Phase 2 — Versioning + agentic upgrade infrastructure (CRITICAL: ships in v1.0)

If v1.0 doesn't have the upgrade lane baked in, then v1.1's first migration has nothing to migrate from. Every teammate would have to manually re-set-up. Bake the upgrade infrastructure into v1.0 itself.

**The model: "ship a version, fork your fate."** Each user's install is a frozen snapshot of whatever version they installed. They can use it forever without upgrading. When they want a newer version, they opt in via an agentic upgrade Claude Code drives on their machine.

- `~/.briefcase/version` — installed version stamp
- `briefcase.db` includes a `meta` row tracking schema_version
- `migrations/v0.10_to_v0.11.py` etc. — idempotent, content-addressable migration scripts
- `/briefcase:upgrade` slash command kicks off an agentic upgrade conversation:
  1. Read current version + check GitHub for newer
  2. Show changelog diff between versions
  3. Ask for green light (user can bail at any step)
  4. Back up DB + settings + claude.json patch + plist (timestamped)
  5. Run migrations one at a time, validating each
  6. Ask user about ambiguous decisions mid-migration ("v2.0 splits `tags` into `tags` + `categories`. You have a tag called 'urgent' — should that become a category?")
  7. On any failure: restore from backup, report honestly. No half-migrated state.
  8. Stamp the new version, exit.

**Hard rules:**
- Backup is non-negotiable. Even for trivial-looking migrations.
- Fail closed. Any error = automatic rollback.
- Old versions stay valid forever. No deprecation forcing.
- Migration scripts are forever once shipped. Discipline matters.
- The agent reads the migration script as documentation, explains in plain language.

**Why this matters for Brendan's support burden:** the user's upgrade is *their* conversation with Claude Code, not Brendan's. He's never on the hook for someone's lost data. Each user opts into when (and if) to upgrade.

### Phase 3 — Optional feature modules.

Anything that's not core gets gated behind `features:` flags in `settings.yaml`:

```yaml
features:
  voice_profile: false      # off by default, requires writing your own profile
  draft_skill: false        # depends on voice_profile
  thermal_printer: false
  pdlc_bridge: false        # depends on having a pdlc dir
  code_research: false      # for devs, exploratory codebase work
  pr_review: false          # depends on code_research
```

Kit reads these at startup. The triage flow respects them. The Chrome extension reads them too (via `/health` endpoint exposing active flags) so checkboxes that aren't enabled don't render.

### Phase 4 — One-stop installer.

A `setup.sh` (or `briefcase setup` Python entrypoint) that asks ~5-7 questions:
1. *"What's your name and role?"* (PM / dev — steers feature defaults)
2. *"Where do you want your notes vault? (path, or 'skip' for no vault)"*
3. *"Any code repositories you want Kit to be aware of? (comma-separated paths, or skip)"*
4. *"Want voice-profile drafting? (requires you to write a voice profile after install)"*
5. *"Want code research / PR review features? (default: yes if dev, no if PM)"*

Then:
- Generates `settings.yaml` + `~/.briefcase/user_profile.yaml`
- Patches `~/.claude.json` to register the briefcase MCP at user level
- Runs `briefcase/sidecar/install.sh`
- Copies the right slash commands to `~/.claude/commands/` (kit, kit-lite always; draft only if voice_profile enabled)
- Prints next steps for the Chrome extension (load unpacked + paste auth token)

### Phase 5 — Distribution polish.

Chrome Web Store publish would kill the "load unpacked" friction. Requires $5 dev account + review cycle. Optional polish, not blocking.

## Default profile taxonomy

Two roles to start: `pm` and `dev`. Each role just sets defaults for the feature flags, nothing more. Anyone can toggle a feature on after install.

| Feature | PM default | Dev default |
|---|---|---|
| voice_profile | off | off (user opts in either way) |
| draft_skill | off | off |
| thermal_printer | off | off |
| pdlc_bridge | on (PMs care about roadmap) | off |
| code_research | off | on |
| pr_review | off | on |

Push back from Mary the analyst is welcome — maybe role isn't the right abstraction at all. Could be orthogonal axes: `uses_atlassian`, `uses_codebase`, `uses_pdlc`, `uses_voice_profile`. Each independently toggleable. Validate with the architect.

## The BMAD-driven planning loop

BMAD will live locally in BriefCase (gitignored — `.bmad-core/`, `.claude/commands/BMad/`, `web-bundles/` already in `.gitignore`). Teammates installing BriefCase don't see BMAD scaffolding. Brendan iterates on BriefCase with BMAD agents.

Sequence:
1. **Mary (analyst)** — audit current codebase. Inventory hardcodes. Categorize by must-change vs config-driven vs optional. Deliver to `docs/audit-2026-05-XX.md`.
2. **Winston (architect)** — translate Mary's audit into a design. Schema for `settings.yaml`, feature-flag taxonomy, module dependency graph, versioning model, migration strategy. Deliver to `docs/architecture-shareable-v1.md`.
3. **PM persona** — break the architect's design into user stories. Prioritize. Identify the *minimum viable shareable cut*.
4. **Dev** — implement.

## Risks worth naming

1. **Once teammates install, breaking changes have a coordinated cost.** Versioning + agentic upgrade mitigates this but doesn't eliminate it.
2. **Voice profile is genuinely hard to bootstrap.** Brendan's took weeks of grepping his own writing. Teammates would either invest the same effort or skip `/draft`. Honest framing required.
3. **User-level vs repo-level files.** Migrations need to span `~/.claude.json`, `~/.briefcase/`, `~/Library/LaunchAgents/`, the BriefCase repo, AND the Chrome extension. Each needs versioning and migration handling.
4. **Local user customizations.** Someone tweaks their `kit-lite.md`. v1.1 tries to overwrite. Conflict. Solution: agentic migration *diffs* files, surfaces conflicts, asks user to resolve. More like `git rebase` than `git pull`.
5. **Voice profile is sacred.** Migration logic must NEVER touch the user's voice profile content — only surrounding scaffolding. Hard rule, easy to violate accidentally.
6. **Extension upgrades are weird.** Self-installed unpacked extensions don't auto-update. Upgrade agent prompts user to drop in new code + verify version in `manifest.json`.

## Pre-decisions still open

1. **Roles vs orthogonal feature axes** — let Winston push back on the role abstraction.
2. **Distribution model** — public GitHub repo or invite-only? Public is more in keeping with the personal-tool spirit; invite-only gives more control.
3. **Onboarding flavor** — script-only (`setup.sh`), conversational (`/kit-onboard` slash command), or both. Brendan's lean: both. Script handles paths/installs (mechanical, fast). Conversational handles "set up your first initiative, here's the conventions" (warm intro).
4. **Versioning numbers** — semver? Date-versioned? Hand-stamped milestones? Probably semver with the major bump signaling "your migration has user-input questions, plan time for it."

## When to revisit

When Brendan has bandwidth to drive a full BMAD-led planning sprint (Mary → Winston → PM → Dev), probably 1-2 weeks of focused work. Until then, BriefCase stays personal. The team keeps asking — that's a useful signal but not a forcing function.
