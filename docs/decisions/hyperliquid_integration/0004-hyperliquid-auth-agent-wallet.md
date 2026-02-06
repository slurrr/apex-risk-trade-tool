# Decision Record: Hyperliquid Authentication (Agent Wallet)

**ID**: 0004-hyperliquid-auth-agent-wallet  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

Hyperliquid provides an “API wallet / agent wallet” concept (agent private key) for API access. The team’s goal is to trade on HL mainnet from the backend, without exposing secrets to the UI, and with clear operational practices (rotation/revocation).

We must confirm the exact signing scheme and request requirements (nonce/time) during Phase 0, but we can decide the operational posture and secret handling model now.

## Decision

- Use **agent wallet** credentials as the sole auth mechanism for Hyperliquid v1.
- Store agent wallet private key in `.env` (and placeholder in `.env.example`) under a dedicated variable (proposed: `HL_AGENT_PRIVATE_KEY`).
- Do **not** store any master/private key beyond the agent key in the backend.
- Derive and log the agent wallet public address (when useful) but never log the private key. Redact signatures and any request auth material.
- Support key rotation by:
  - allowing backend restart with a new agent key
  - providing clear docs for revoking the old agent key in Hyperliquid UI
- If request signing requires synchronized time or monotonic nonce, the backend must:
  - fail safely (no retry storms)
  - surface a structured auth error and recommend operator action

## Options Considered

### Option A — Use a master EOA private key directly
- Pros: straightforward conceptually.
- Cons: higher blast radius; operationally risky; not aligned with “agent wallet” model.

### Option B — Use agent wallet only (chosen)
- Pros: least privilege; supports rotation; aligns with Hyperliquid model described by operator.
- Cons: requires correct signing implementation and good documentation.

### Option C — Support both master and agent keys
- Pros: fallback if agent wallet limitations are found.
- Cons: larger surface area; more complex security posture.

## Consequences

- Phase 0 must pin down:
  - signing method
  - nonce/time rules
  - WS auth requirements (if any)
- `.env.example` must include HL variables, and documentation must explain how to create/rotate/revoke the agent wallet.

## Validation Plan

- Phase 0 checklist:
  - successful authenticated “read” call (account summary) on mainnet
  - successful order placement and cancellation using agent wallet
- Logging review:
  - ensure no secrets appear in structured logs (including exceptions)
- Operational drill:
  - rotate agent key; confirm old key fails and new key works

