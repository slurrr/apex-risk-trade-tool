# Decision Record: Hyperliquid TP/SL Representation & Reconciliation

**ID**: 0006-hyperliquid-tp-sl-model  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

The UI and backend model “targets” as:
- one Take Profit price
- one Stop Loss price
per position (effectively per symbol in the current app).

On ApeX, TP/SL can be expressed either as “open TP/SL” at entry and/or as position TP/SL reduce-only orders, and the code maintains a reconciliation map `_tpsl_targets_by_symbol`.

Hyperliquid likely represents TP/SL using trigger orders, potentially as separate orders from the position itself. We need consistent behavior:
- setting TP/SL updates UI quickly
- clearing TP/SL cancels only the correct trigger order(s)
- positions table reflects TP/SL even if not directly present on the position payload

## Decision

- TP/SL will be represented internally as **at most one active TP and one active SL per symbol** on Hyperliquid.
- For new entries submitted from `POST /api/trade` with `tp` and `stop_price`, Hyperliquid will use a **single grouped submit**:
  - `bulk_orders(..., grouping="normalTpsl")`
  - entry limit leg + TP trigger leg + SL trigger leg are sent atomically in one exchange action.
- Post-submit verification inspects per-leg statuses from Hyperliquid and surfaces warnings when any attached TP/SL leg is not clearly accepted.
- When updating targets:
  - if setting a TP: cancel existing TP trigger (if any), then place a new TP trigger
  - if setting an SL: cancel existing SL trigger (if any), then place a new SL trigger
  - if clearing TP/SL: cancel only that side’s trigger order
- Maintain a local `tpsl_targets_by_symbol` map (similar to ApeX) to:
  - immediately reflect requested targets in UI responses
  - reconcile once venue state is observed via WS and/or REST snapshots
- Reconciliation sources:
  - Prefer WS order updates when available.
  - Fall back to periodic REST snapshots of open orders to rebuild TP/SL state.

## Options Considered

### Option A — Treat TP/SL as attributes on the position only
- Pros: simple conceptual model.
- Cons: not always supported by venues; likely incompatible with HL trigger orders.

### Option B — Mirror ApeX approach: maintain local TP/SL map derived from orders (chosen)
- Pros: stable UI; supports venues that represent TP/SL as orders; allows reconciliation.
- Cons: requires careful mapping and cancel targeting to avoid wrong cancels.

### Option C — Require UI to manage TP/SL order ids directly
- Pros: less backend inference.
- Cons: breaks UX and current contract; higher chance of operator error; exposes too much venue detail.

## Consequences

- Entry safety improves for delayed fills: TP/SL does not depend on a later API call or app uptime when attached on trade submit.
- The backend must reliably identify HL TP vs SL trigger orders (by type/fields) to cancel the correct one.
- There is a short window where local targets may not yet be confirmed by venue; UI should surface this as “pending” if needed (optional).
- Current behavior does not actively rebalance TP/SL sizes on partial fills at the app layer. We currently rely on exchange-side grouped semantics and venue state reconciliation.
- Future enhancement candidate: add fill-driven TP/SL rebalance logic (cancel/replace targets to exact filled size deltas when required by strategy).

## Validation Plan

- Unit tests:
  - grouped entry submit with TP/SL uses `normalTpsl`
  - grouped submit warnings are emitted when a TP/SL leg is rejected
  - “clear TP” does not cancel SL and vice versa
  - reconciliation rebuilds map correctly from an orders snapshot
- Manual:
  - submit one `POST /api/trade` with `tp` and confirm three open orders appear (entry + TP + SL) from the single request
  - set TP then set SL, confirm both display
  - clear TP only, confirm SL remains
  - confirm after refresh/resync the targets persist correctly
