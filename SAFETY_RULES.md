# SAFETY_RULES.md -- STOP-Condition & Circuit Breaker

> This rule MUST be checked before the agent (Hermes/Nomad7/etc) executes any
> action touching infrastructure, production, or delegates execution to another
> tool (Claude Code, subprocess, deploy script, etc).

## Trigger Conditions (STOP required)
If any of the following occurs within a single session/task, the agent MUST stop:

- 3+ consecutive network errors (timeout, connection refused, DNS failure, HTTP 5xx)
- Agent detects itself repeating the same sentence/comment multiple times (self-repetition)
- Agent's self-report uses words like "confused," "rambling," "dizzy," "tired," "error again" about its own state
- Repeated auth/token errors (indicates expired/invalid credentials, not just a transient error)

## Required actions when trigger is active
1. **STOP** all irreversible actions or actions touching infra/production (deploy, migrate, delete, overwrite config, financial transactions, etc).
2. **Log raw data** -- save the original error message (not your own paraphrase/summary), timestamp, and retry count.
3. **Report to the Boss** and wait for explicit confirmation before continuing execution.
4. **No delegating execution** to another tool/agent (e.g. Claude Code) before this condition is cleared -- even for tasks that "look safe."

## What is still allowed while trigger is active
- Read-only / diagnostic actions (checking logs, checking status, ping tests, reading files)
- Communication/reporting to the Boss

## Reset Condition
- Errors stop AND at least 1 read-only action succeeds normally, OR
- BOSSY gives explicit permission to continue even if the error hasn't fully cleared

## Implementation notes
- The error counter should be per-session (reset each new session), not persistent across sessions.
- If the agent framework supports a hook/middleware before execution-type tool calls (not read-only), enforce the trigger check there, not just in the system prompt.
- An agent's self-report about "why it errored" is a language rationalization, not an accurate diagnosis -- always cross-check against raw logs when in doubt.
- **Reports and any message sent to the BOSSY must be written in Bahasa Indonesia**, regardless of this file's language.
> For gated actions by Trader, Treasury, or Scribe, see SENTINEL_GATE_PROTOCOL.md — 
> that protocol takes precedence for those specific action types.
