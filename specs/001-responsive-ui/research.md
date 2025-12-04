# Phase 0 Research

## Responsive layout and input grid
Decision: Use a two-column CSS grid for the trade form on ≥sm viewports with paired fields per row; stack to single-column on narrow screens while preserving pair groupings.  
Rationale: Maintains predictable field proximity (Symbol with Risk%, Entry with Stop, Take Profit with Side) while staying readable on phones.  
Alternatives considered: Pure flex rows (more brittle on wrap), fixed breakpoints per field (risks overlap), modal-based form (slower flow).

## Theme handling and color feedback
Decision: Respect `prefers-color-scheme` at load, listen for changes, and drive themes via CSS variables; set burnt-orange and pressed-red tokens with contrast-checked text colors.  
Rationale: System-level preference is reliable and fast; variable-driven theming reduces duplication and keeps pressed-state transitions consistent.  
Alternatives considered: Manual theme toggles only (ignores system), full page reload on theme change (breaks inputs), inline per-component colors (hard to keep consistent).

## Symbol dropdown with validation
Decision: Prefetch tradeable symbols on load, apply debounced (150–250 ms) type-ahead filtering on the client, and enforce a strict `^[A-Z0-9]+-[A-Z0-9]+$` format before selection.  
Rationale: Local filtering keeps typing responsive; prefetch avoids mid-form latency; format guard prevents malformed symbols.  
Alternatives considered: Server-side search per keystroke (adds latency), free-text symbols (error-prone), post-submit validation only (delays user feedback).

## Position management and partial closes
Decision: Use an inline manage panel with a 0–100% slider (markers at 0/25/50/100) plus Market Close and Limit Close actions; require limit price for limit closes; allow TP/SL modify form to update one or both fields without clearing unspecified targets.  
Rationale: Inline panel keeps context within the positions table; markers aid precision; validation prevents ambiguous partial closes and accidental target removal.  
Alternatives considered: Separate modal page (breaks context), discrete quick buttons without slider (less granular), requiring both TP and SL together (blocks partial updates).
