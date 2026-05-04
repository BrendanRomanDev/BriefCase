# Sidecar "skip the queue" actions

## Idea

The sidecar `/draft` endpoint shells out to `claude -p` using Brendan's existing Claude Code subscription auth. This pattern generalizes — the compose popup could grow more **immediate-action buttons** (alongside Send, Cancel, Draft now) for any workflow where Brendan wants the action to happen now, not via deferred queue triage.

## Candidates

| Action | Feasibility | Notes |
|---|---|---|
| **Create Jira ticket now** | High | `claude -p` invocation has access to the user-level atlassian MCP. Sidecar passes captured content + context as the prompt, claude drafts the ticket body, calls `mcp__atlassian__createJiraIssue`, returns the ticket key/URL. Popup shows the result with a "Open in Jira" link. ~10-15s latency. |
| **Schedule meeting now** | High | Similar pattern via gcal MCP. After meeting-scheduler is built (queued ahead), this becomes the immediate-action variant. |
| **Record decision now** | High | Sidecar invokes claude with the capture, claude synthesizes decision + rationale + initiative, calls `mcp__briefcase__record_decision` directly, returns the decision_id. ~5-10s. |
| **Codebase review** | Medium | `claude -p` invoked with `cwd=/path/to/thriveworks` so it can grep/read the repo. Prompt would instruct it to investigate the captured content against the codebase. Latency 20-40s+. Worth it for things like "look at what auth middleware does and tell me if this concern is valid" without leaving the browser. |
| **File ThriveNote now** | High | Sidecar invokes claude with the capture, claude reads the global thrive-notes.md rule, files to vault, returns the path. Confirmation in popup. |
| **Log meeting notes** | High | Same as ThriveNote but specifically routed through `file_meeting_notes`. |

## Why this is interesting

Right now there's a mental friction: "do I queue this for triage later, or do I context-switch to a Kit session to handle it now?" The compose popup having more "do it now" buttons collapses that decision — Brendan picks the action at capture time, sidecar handles it, result lands in the popup, no terminal involved.

The queue still matters for things he genuinely wants to defer (he doesn't want to do everything inline at the moment of every capture). But for fast-track items, skip-the-queue is real value.

## Cost / Complexity

Each new action button is roughly:
- A prompt template in the sidecar
- A new endpoint or extension to `/draft` (route by `mode` field perhaps)
- A button + result-rendering UI in compose popup
- Maybe ~30-45 min per action

## Risk / Constraint

- `claude -p` invocations are billable (against Brendan's subscription). High-volume use could matter eventually.
- Latency: 5-30s+ per action. The popup needs clear loading state.
- Failure modes: claude exits non-zero, MCP not loaded in the spawned context, timeout, etc. All need clear error rendering in the popup.
- Atomicity: if claude calls `createJiraIssue` and then crashes, the ticket exists but the popup may not know. Worth a "verify and confirm" step, especially for irreversible actions.

## When to revisit

After the meeting scheduler ships and Brendan has a few weeks of real usage data on which captures he wants to "skip the queue" for. Then build the highest-frequency one as a second action button (probably Jira ticket creation, given how often Dave's chats spawn tickets).

## Status

**Deferred.** Logged 2026-04-30. Pattern is feasible, just not the right priority right now.
