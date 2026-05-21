# `auto_file` flag — let Kit silently sweep "just file it" items at the top of the walk

## Status

**Shipping 2026-05-21.** This note captures the decision trail before the code lands, mostly so future-us doesn't re-litigate the options we ruled out.

## The trigger

Captures pile up in the triage queue between Kit sessions. A lot of them don't need Brendan's judgment — they're "just file this to a reading list," "drop this in the Foo initiative inbox," "log this person update." Today every one of those still requires Kit to walk Brendan through it one at a time, which is friction for items he's already pre-decided don't matter much.

He wants a way to say *at capture time* "Kit, you handle this — I don't need to be in the loop."

## The spec

### Capture side
- One new checkbox on the Chrome extension compose popup, alongside the existing flag grid: **"Just file it (Kit's call)"**.
- Wires through `collectFlags()` as `flags.auto_file = true`. No destination picker, no extra metadata fields, no hint text. One bit.
- Multiple flags can co-exist as today (e.g. `auto_file + needs_jira` would mean "file the inbox item and draft the ticket without asking me"). The auto-sweep step honors `auto_file` and the existing post-resolution side-effect flags still fire.

### Kit side (triage walk only — not startup)
At the **top of the walk-the-queue flow** (Kit and Kit-Lite, same protocol):

1. Pull pending items via `get_triage_queue()`.
2. Partition into auto-sweep (`flags.auto_file: true`) and human-review (everything else).
3. For each auto-sweep item:
   - `claim_triage_item` as usual (multi-agent safety still applies).
   - Kit infers destination from content + context: `brain_dump`, `thrivenote`, `daily_note`, `initiative` inbox, `discard`, `mark_resolved` — same set of routes the human walk supports.
   - File it via the normal destination-specific path (e.g. for `thrivenote`, write the markdown file with the source embedded; for `brain_dump`, call `triage_item(action='brain_dump', ...)` with reasonable fields synthesized from content).
   - **Ask only if genuinely stuck.** Anchor: *"Brendan wouldn't have clicked auto if it mattered too much."* Default lean is "pick something reasonable and move on." Asking should be the rare exception, not the norm.
   - Run any post-resolution side-effects implied by other flags on the same item (e.g. if `auto_file + needs_jira`, draft + create the ticket and `add_external_ref` it onto the resulting entity).
4. Report **per item** what was done and where: title/preview, destination, path or ID. Not just a count — Brendan wants to see what was filed, in case something needs a quick follow-up.
5. Then walk the remaining (non-auto) items interactively, as today.

### Triggered only on "walk the queue"
- **Not** on Kit full-mode startup. The startup checklist is heavy enough; auto-sweep belongs to the explicit "I'm doing queue work now" intent.
- **Not** on Kit-Lite activation. Lite's whole pitch is "no front-loaded work." Auto-sweep on Lite invocation would break that — it'd silently file things before Brendan even asked.
- **Yes** when Brendan says "triage," "walk the queue," "what's in the queue," or similar — same triggers as today.

## Options we ruled out

A long chain of "maybe we should..." that all collapsed into the spec above. Logging them so the trail is visible:

| Option | Why we ruled it out |
|---|---|
| **Cloud-scheduled Routines** (anthropic-managed cron) | No filesystem access. Can't write to `~/Notes/ThriveNotes/`, can't talk to local SQLite or sidecar. Would need a bunch of network plumbing to recover what local already gives us. |
| **Desktop scheduled tasks** (claude code's local cron) | Solves filesystem access, but adds infra (plist or cron entry, separate scheduler config). Whole reason to schedule is "process between Kit sessions" — but if Kit's the only consumer of the queue, "process at Kit-invocation time" is the same outcome with zero new machinery. |
| **`/loop` started by Kit on full-mode startup** | Same logic: Kit-launched loop runs while Kit's open, which is exactly when Brendan would be walking the queue manually anyway. The loop adds nothing. |
| **Startup-sweep instead of walk-queue-sweep** | Brendan considered it. Ruled out because (a) Kit startup is already heavy, (b) some auto items might do meaningful work (file a ThriveNote, draft a Jira ticket), and that work belongs to an explicit "I'm doing queue work now" intent, not the activation greeting. |
| **Extension destination picker** ("auto-file to: reading list / initiative X / ThriveNote Y") | More UX cost than just trusting Kit's inference. Brendan's framing: *"I wouldn't have clicked auto if it mattered too much."* If Kit picks wrong on an auto-flagged item, that's an acceptable failure mode. The checkbox is one bit on purpose. |
| **Inference instead of an explicit flag** (Kit infers which items are "auto-able" from content alone) | Considered, but explicit signal is safer. Lots of room for "Kit thought this was auto, but I actually wanted to see it." A checkbox at capture time is unambiguous. |

## Open questions

None blocking. A few that might surface during implementation:

- **Reporting verbosity.** Per-item summary lines could get noisy if the auto-batch is large. If this becomes a problem, fall back to a one-line group summary ("auto-filed 5 items: 3 brain dumps, 1 ThriveNote, 1 discard") with a follow-up "want the details?" prompt.
- **Confidence threshold.** "Ask only if genuinely stuck" is a vibe, not a rule. If Kit starts asking too much (defeats the point) or too little (files things wrong), tune the threshold in the kit.md instructions.
- **Failure mode for an auto item Kit can't classify at all.** Default: leave it in the queue as pending (un-claimed), surface in the human-review section of the walk. Don't make Kit ask mid-sweep — just defer it cleanly.

## Why this matters

Today the queue is a 100% human-attention surface. Every capture, even the trivial ones, costs a triage turn. With `auto_file`, the queue becomes a *graded* attention surface — the items that need Brendan's judgment are the only ones he walks, and the rest are handled in a batch sweep before the walk even starts.

Small change in code, meaningful change in cadence.
