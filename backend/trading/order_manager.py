from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple
import re
import time

from backend.core.logging import get_logger
from backend.exchange.exchange_gateway import ExchangeGateway
from backend.risk import risk_engine

logger = get_logger(__name__)


def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _infer_decimal_places(value: Any) -> Optional[int]:
    if value in (None, "", 0):
        return None
    try:
        dec_value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    dec_value = dec_value.normalize()
    if dec_value == dec_value.to_integral():
        return 0
    exponent = -dec_value.as_tuple().exponent
    return max(0, exponent)


class OrderManager:
    """Coordinates sizing, risk caps, and order placement."""

    def __init__(
        self,
        gateway: ExchangeGateway,
        *,
        per_trade_risk_cap_pct: Optional[float] = None,
        daily_loss_cap_pct: Optional[float] = None,
        open_risk_cap_pct: Optional[float] = None,
        slippage_factor: float = 0.0,
        fee_buffer_pct: float = 0.0,
        hyperliquid_min_notional_usdc: float = 10.0,
    ) -> None:
        self.gateway = gateway
        self.per_trade_risk_cap_pct = per_trade_risk_cap_pct
        self.daily_loss_cap_pct = daily_loss_cap_pct
        self.open_risk_cap_pct = open_risk_cap_pct
        self.slippage_factor = slippage_factor or 0.0
        self.fee_buffer_pct = fee_buffer_pct or 0.0
        self.hyperliquid_min_notional_usdc = max(0.0, float(hyperliquid_min_notional_usdc or 0.0))
        self.daily_realized_loss: float = 0.0
        self.open_risk_estimates: Dict[str, float] = {}
        self.open_orders: list[Dict[str, Any]] = []
        self.positions: list[Dict[str, Any]] = []
        self.pending_order_prices: Dict[str, float] = {}
        self.pending_order_prices_client: Dict[str, float] = {}
        self.position_targets: Dict[str, Dict[str, float]] = {}
        self._tpsl_targets_by_symbol: Dict[str, Dict[str, float]] = {}
        self._tpsl_local_hints: Dict[str, Dict[str, Any]] = {}
        settings = getattr(gateway, "settings", None)
        self._tpsl_hint_ttl_seconds = max(
            0.0,
            float(getattr(settings, "apex_local_hint_ttl_seconds", 20.0) or 20.0),
        )
        self._depth_summary_cache: Dict[tuple[str, int, int], tuple[float, Dict[str, Any]]] = {}
        self._depth_summary_cache_ttl = 1.5
        self._tpsl_backfill_last_ts = 0.0
        self._tpsl_backfill_min_gap_seconds = 5.0

    async def _get_account_context(self) -> tuple[float, Optional[float]]:
        equity = await self.gateway.get_account_equity()
        available_margin: Optional[float] = None
        summary_getter = getattr(self.gateway, "get_account_summary", None)
        if callable(summary_getter):
            try:
                summary = await summary_getter()
                if isinstance(summary, dict):
                    available_margin = _coerce_float(summary.get("available_margin"))
            except Exception:
                available_margin = None
        if available_margin is None:
            available_margin = equity
        return equity, available_margin

    def _enforce_venue_margin_guard(
        self,
        *,
        symbol: str,
        sizing: risk_engine.PositionSizingResult,
        available_margin: Optional[float],
    ) -> None:
        venue = (getattr(self.gateway, "venue", "") or "").lower()
        if venue != "hyperliquid":
            return
        margin = float(available_margin or 0.0)
        if margin <= 0:
            raise risk_engine.PositionSizingError(
                "Available margin is non-positive for Hyperliquid. Transfer collateral to your perp account."
            )
        symbol_info = self.gateway.get_symbol_info(symbol) or {}
        max_leverage = _coerce_float(symbol_info.get("maxLeverage"))
        if max_leverage is None or max_leverage <= 0:
            max_leverage = 1.0
        required_initial_margin = float(sizing.notional) / float(max_leverage)
        if required_initial_margin > margin:
            raise risk_engine.PositionSizingError(
                f"Required initial margin {required_initial_margin:.6f} exceeds available margin "
                f"{margin:.6f} on Hyperliquid (notional={float(sizing.notional):.6f}, "
                f"max_leverage={float(max_leverage):.2f}x)."
            )
        min_notional = float(self.hyperliquid_min_notional_usdc or 0.0)
        if min_notional > 0 and float(sizing.notional) < min_notional:
            raise risk_engine.PositionSizingError(
                f"Order notional {sizing.notional:.6f} is below Hyperliquid minimum "
                f"{min_notional:.2f} USDC."
            )

    def _estimate_position_risk(self, position: Dict[str, Any]) -> Optional[float]:
        entry = _coerce_float(position.get("entry_price") or position.get("entryPrice"))
        stop = _coerce_float(
            position.get("stop_loss")
            or position.get("stopLoss")
            or position.get("sl")
            or position.get("slPrice")
            or position.get("stopLossPrice")
        )
        size = _coerce_float(position.get("size") or position.get("positionSize"))
        if entry is None or stop is None or size is None:
            return None
        loss = abs(entry - stop) * abs(size)
        return loss if loss > 0 else None

    def _verify_hyperliquid_grouped_submit(
        self,
        *,
        payload: Dict[str, Any],
        order_resp: Dict[str, Any],
    ) -> list[str]:
        """
        Validate grouped HL order submission (entry + attached TP/SL legs).
        Returns warning strings when TP/SL legs were not clearly accepted.
        """
        venue = (getattr(self.gateway, "venue", "") or "").lower()
        order_requests = payload.get("order_requests")
        if venue != "hyperliquid" or not isinstance(order_requests, list) or len(order_requests) <= 1:
            return []

        raw = order_resp.get("raw") if isinstance(order_resp, dict) else None
        response = raw.get("response") if isinstance(raw, dict) else None
        data = response.get("data") if isinstance(response, dict) else None
        statuses = data.get("statuses") if isinstance(data, dict) else None
        if not isinstance(statuses, list):
            return ["Hyperliquid grouped submit did not return per-leg statuses; TP/SL acceptance is unconfirmed."]

        expected_legs = len(order_requests)
        if len(statuses) < expected_legs:
            return [
                f"Hyperliquid grouped submit returned {len(statuses)}/{expected_legs} leg statuses; "
                "TP/SL acceptance may be incomplete."
            ]

        def _accepted(status: Any) -> bool:
            if isinstance(status, str):
                return status == "waitingForFill"
            if isinstance(status, dict):
                if status.get("error"):
                    return False
                for key in ("resting", "filled", "success"):
                    if status.get(key):
                        return True
            return False

        failed: list[str] = []
        for idx, status in enumerate(statuses[:expected_legs], start=1):
            if _accepted(status):
                continue
            failed.append(f"leg{idx}={status}")

        if failed:
            return [
                "Hyperliquid grouped submit did not fully accept all attached TP/SL legs: "
                + ", ".join(failed[:3])
            ]
        return []

    def _rebuild_open_risk_estimates(
        self,
        *,
        open_orders: Optional[list[Dict[str, Any]]] = None,
        positions: Optional[list[Dict[str, Any]]] = None,
    ) -> None:
        open_orders = open_orders if open_orders is not None else self.open_orders
        positions = positions if positions is not None else self.positions
        open_ids = {order.get("id") for order in open_orders if order.get("id")}
        rebuilt: Dict[str, float] = {
            order_id: risk
            for order_id, risk in self.open_risk_estimates.items()
            if order_id in open_ids
        }
        for pos in positions or []:
            risk = self._estimate_position_risk(pos)
            if risk is None:
                continue
            pos_id = pos.get("id") or pos.get("positionId") or pos.get("symbol")
            if pos_id:
                rebuilt[f"pos:{pos_id}"] = risk
        self.open_risk_estimates = rebuilt

    def _normalize_symbol_value(self, symbol: Optional[str]) -> str:
        """Normalize symbols to a consistent KEY-QUOTE shape for map lookups."""
        if not symbol:
            return ""
        sym = str(symbol).upper()
        if "-" in sym:
            return sym
        for quote in ("USDT", "USDC", "USDC.E", "USD"):
            if sym.endswith(quote):
                return f"{sym[:-len(quote)]}-{quote}"
        return sym

    def _set_local_tpsl_hint(
        self,
        *,
        symbol: str,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        clear_tp: bool = False,
        clear_sl: bool = False,
    ) -> None:
        sym_key = self._normalize_symbol_value(symbol)
        if not sym_key:
            return
        now = time.time()
        hint = self._tpsl_local_hints.setdefault(sym_key, {})
        if take_profit is not None:
            hint["take_profit"] = float(take_profit)
            hint["take_profit_observed_at"] = now
        if stop_loss is not None:
            hint["stop_loss"] = float(stop_loss)
            hint["stop_loss_observed_at"] = now
        if clear_tp:
            hint["take_profit"] = None
            hint["take_profit_observed_at"] = now
        if clear_sl:
            hint["stop_loss"] = None
            hint["stop_loss_observed_at"] = now
        if not hint:
            self._tpsl_local_hints.pop(sym_key, None)

    def _resolve_tpsl_value(
        self,
        *,
        symbol: str,
        kind: str,
        ws_or_cache_value: Optional[float],
    ) -> Optional[float]:
        """
        Resolve TP/SL display precedence:
        local_hint (fresh) > ws/cache, with immediate WS contradiction override.
        """
        sym_key = self._normalize_symbol_value(symbol)
        hint = self._tpsl_local_hints.get(sym_key, {})
        hint_val = hint.get(kind)
        hint_ts = hint.get(f"{kind}_observed_at")
        if hint_ts is None:
            return ws_or_cache_value
        try:
            age = max(0.0, time.time() - float(hint_ts))
        except Exception:
            age = self._tpsl_hint_ttl_seconds + 1.0
        # Fresh hint wins.
        if age <= self._tpsl_hint_ttl_seconds:
            return ws_or_cache_value if hint_val is None else hint_val
        # Hint expired; drop it and surface WS/cache value.
        hint.pop(kind, None)
        hint.pop(f"{kind}_observed_at", None)
        if not hint:
            self._tpsl_local_hints.pop(sym_key, None)
        recorder = getattr(self.gateway, "record_tpsl_hint_unconfirmed", None)
        if callable(recorder):
            try:
                recorder()
            except Exception:
                pass
        return ws_or_cache_value

    @staticmethod
    def _is_tpsl_order(order: Dict[str, Any]) -> bool:
        """Detect TP/SL reduce-only orders even when isPositionTpsl flag is missing."""
        if not isinstance(order, dict):
            return False
        order_type = (order.get("type") or order.get("orderType") or order.get("order_type") or "").upper()
        if not (order_type.startswith("STOP") or order_type.startswith("TAKE_PROFIT")):
            return False
        if bool(order.get("isPositionTpsl")):
            return True
        reduce_only = order.get("reduceOnly")
        if reduce_only is None:
            reduce_only = order.get("reduce_only")
        return bool(reduce_only)

    def _include_in_open_orders(self, order: Dict[str, Any]) -> bool:
        """Hide venue-specific conditional TP/SL orders from open-orders UI feed."""
        if self._is_tpsl_order(order):
            return False
        return True

    def _merge_tpsl_map(self, new_map: Dict[str, Dict[str, Optional[float]]], *, replace: bool = False) -> None:
        """Merge TP/SL values into the existing map, optionally replacing missing symbols."""
        if replace:
            self._tpsl_targets_by_symbol.clear()
        for symbol, vals in (new_map or {}).items():
            sym_key = self._normalize_symbol_value(symbol)
            cur = self._tpsl_targets_by_symbol.setdefault(sym_key, {})
            if replace:
                cur.clear()
            tp_val = vals.get("take_profit") if isinstance(vals, dict) else None
            sl_val = vals.get("stop_loss") if isinstance(vals, dict) else None
            if tp_val is not None:
                cur["take_profit"] = tp_val
            if sl_val is not None:
                cur["stop_loss"] = sl_val

    def _reconcile_tpsl(self, raw_orders: list[Dict[str, Any]]) -> bool:
        """
        Reconcile TP/SL map from a single orders_raw payload:
        - If the payload contains active TP/SL orders:
            * When the payload looks like a full snapshot, replace the map with the active entries.
            * Otherwise, merge updates for symbols present without clearing others.
        - If the payload has no active TP/SL orders, leave the existing map untouched.
        - Special case: a single canceled TP/SL order payload indicates removal for that symbol; clear its entry.
        Returns True when the payload only carried cancellations (no surviving targets) so callers
        can trigger a follow-up refresh to rehydrate the map.
        """
        needs_refresh = False
        # Work only on TP/SL position orders; ignore unrelated orders to avoid churn.
        tpsl_orders: list[Dict[str, Any]] = []
        for o in raw_orders or []:
            if not isinstance(o, dict):
                continue
            status_raw = str(o.get("status") or o.get("orderStatus") or "").lower()
            order_type = (o.get("type") or o.get("orderType") or o.get("order_type") or "").upper()
            if not self._is_tpsl_order(o):
                continue
            tpsl_orders.append(o)
        if not tpsl_orders:
            return False
        raw_orders = tpsl_orders

        # Handle one-off canceled TP/SL pushes to drop only that target for the symbol.
        if len(raw_orders or []) == 1:
            o = raw_orders[0]
            if isinstance(o, dict):
                status_raw = str(o.get("status") or o.get("orderStatus") or "").lower()
                order_type = (o.get("type") or o.get("orderType") or o.get("order_type") or "").upper()
                if status_raw in {"canceled", "cancelled"} and self._is_tpsl_order(o):
                    sym_key = self._normalize_symbol_value(o.get("symbol") or o.get("market"))
                    if sym_key:
                        entry = self._tpsl_targets_by_symbol.get(sym_key, {}).copy()
                        hints = self.position_targets.get(sym_key, {}).copy()
                        if order_type.startswith("TAKE_PROFIT"):
                            entry.pop("take_profit", None)
                            hints.pop("take_profit", None)
                        if order_type.startswith("STOP"):
                            entry.pop("stop_loss", None)
                            hints.pop("stop_loss", None)
                        if entry:
                            self._tpsl_targets_by_symbol[sym_key] = entry
                        else:
                            self._tpsl_targets_by_symbol.pop(sym_key, None)
                        if hints:
                            self.position_targets[sym_key] = hints
                        else:
                            self.position_targets.pop(sym_key, None)
                        self._set_local_tpsl_hint(
                            symbol=sym_key,
                            clear_tp=order_type.startswith("TAKE_PROFIT"),
                            clear_sl=order_type.startswith("STOP"),
                        )
                    needs_refresh = True
                    return needs_refresh

        active_map = self._extract_tpsl_from_orders(raw_orders)
        has_active = bool(active_map)
        if active_map:
            # Explicit stream payload contradiction overrides fresh local hints immediately.
            for sym_key, values in active_map.items():
                hint = self._tpsl_local_hints.get(sym_key)
                if not hint:
                    continue
                tp_val = values.get("take_profit")
                if tp_val is not None and hint.get("take_profit") is not None and float(hint["take_profit"]) != float(tp_val):
                    hint.pop("take_profit", None)
                    hint.pop("take_profit_observed_at", None)
                sl_val = values.get("stop_loss")
                if sl_val is not None and hint.get("stop_loss") is not None and float(hint["stop_loss"]) != float(sl_val):
                    hint.pop("stop_loss", None)
                    hint.pop("stop_loss_observed_at", None)
                if not hint:
                    self._tpsl_local_hints.pop(sym_key, None)

        # Handle batches that carry only canceled TP/SL orders (no active updates).
        removed_symbol = False
        if not has_active:
            for o in raw_orders or []:
                if not isinstance(o, dict):
                    continue
                status_raw = str(o.get("status") or o.get("orderStatus") or "").lower()
                order_type = (o.get("type") or o.get("orderType") or o.get("order_type") or "").upper()
                if status_raw not in {"canceled", "cancelled", "triggered", "filled"}:
                    continue
                if not self._is_tpsl_order(o):
                    continue
                sym_key = self._normalize_symbol_value(o.get("symbol") or o.get("market"))
                if not sym_key:
                    continue
                entry = self._tpsl_targets_by_symbol.get(sym_key, {}).copy()
                hints = self.position_targets.get(sym_key, {}).copy()
                if order_type.startswith("TAKE_PROFIT"):
                    entry.pop("take_profit", None)
                    hints.pop("take_profit", None)
                if order_type.startswith("STOP"):
                    entry.pop("stop_loss", None)
                    hints.pop("stop_loss", None)
                if entry:
                    self._tpsl_targets_by_symbol[sym_key] = entry
                else:
                    self._tpsl_targets_by_symbol.pop(sym_key, None)
                if hints:
                    self.position_targets[sym_key] = hints
                else:
                    self.position_targets.pop(sym_key, None)
                self._set_local_tpsl_hint(
                    symbol=sym_key,
                    clear_tp=order_type.startswith("TAKE_PROFIT"),
                    clear_sl=order_type.startswith("STOP"),
                )
                removed_symbol = True
        if active_map:
            # Merge without clearing missing keys; cancels are handled above, so merging keeps surviving targets intact.
            self._merge_tpsl_map(active_map, replace=False)
        # canceled-only snapshot: do nothing; keep existing map intact
        if removed_symbol and not active_map:
            needs_refresh = True
        return needs_refresh

    async def preview_trade(
        self,
        *,
        symbol: str,
        entry_price: float,
        stop_price: float,
        risk_pct: float,
        side: Optional[str] = None,
        tp: Optional[float] = None,
    ) -> Tuple[risk_engine.PositionSizingResult, list[str]]:
        """Run sizing without placing an order."""
        await self.gateway.ensure_configs_loaded()
        equity, available_margin = await self._get_account_context()
        symbol_info = self.gateway.get_symbol_info(symbol)
        if not symbol_info:
            raise risk_engine.PositionSizingError(f"Symbol config unavailable for {symbol}; refresh configs and retry.")

        result = risk_engine.calculate_position_size(
            equity=equity,
            risk_pct=risk_pct,
            entry_price=entry_price,
            stop_price=stop_price,
            symbol_config=symbol_info,
            slippage_factor=self.slippage_factor,
            fee_buffer_pct=self.fee_buffer_pct,
        )
        self._enforce_venue_margin_guard(
            symbol=symbol,
            sizing=result,
            available_margin=available_margin,
        )
        # logger.info(
        #     "preview_trade",
        #     extra={
        #         "event": "preview_trade",
        #         "symbol": symbol,
        #         "entry": entry_price,
        #         "stop": stop_price,
        #         "risk_pct": risk_pct,
        #         "size": result.size,
        #         "side": result.side,
        #         "warnings": result.warnings,
        #     },
        # )
        # warnings may be extended later with caps/other checks
        return result, result.warnings

    async def execute_trade(
        self,
        *,
        symbol: str,
        entry_price: float,
        stop_price: float,
        risk_pct: float,
        side: Optional[str] = None,
        tp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Re-run sizing and place order when safe."""
        await self.gateway.ensure_configs_loaded()
        equity, available_margin = await self._get_account_context()
        symbol_info = self.gateway.get_symbol_info(symbol)
        if not symbol_info:
            raise risk_engine.PositionSizingError(f"Symbol config unavailable for {symbol}; refresh configs and retry.")

        # Risk caps
        if self.per_trade_risk_cap_pct is not None and risk_pct > self.per_trade_risk_cap_pct:
            raise risk_engine.PositionSizingError(
                f"Risk % {risk_pct} exceeds per-trade cap {self.per_trade_risk_cap_pct}"
            )

        sizing = risk_engine.calculate_position_size(
            equity=equity,
            risk_pct=risk_pct,
            entry_price=entry_price,
            stop_price=stop_price,
            symbol_config=symbol_info,
            slippage_factor=self.slippage_factor,
            fee_buffer_pct=self.fee_buffer_pct,
        )
        self._enforce_venue_margin_guard(
            symbol=symbol,
            sizing=sizing,
            available_margin=available_margin,
        )

        if self.daily_loss_cap_pct is not None:
            daily_limit = equity * (self.daily_loss_cap_pct / 100.0)
            if self.daily_realized_loss >= daily_limit:
                raise risk_engine.PositionSizingError("Daily loss cap exceeded.")
            if (self.daily_realized_loss + sizing.estimated_loss) > daily_limit:
                raise risk_engine.PositionSizingError("Order would exceed daily loss cap.")

        if self.open_risk_cap_pct is not None:
            open_risk_limit = equity * (self.open_risk_cap_pct / 100.0)
            if sum(self.open_risk_estimates.values()) + sizing.estimated_loss > open_risk_limit:
                raise risk_engine.PositionSizingError("Order would exceed open-risk cap.")

        payload, payload_warning = await self.gateway.build_order_payload(
            symbol=symbol,
            side=sizing.side,
            size=sizing.size,
            entry_price=sizing.entry_price,
            reduce_only=False,
            tp=tp,
            stop=stop_price,
        )
        warnings = list(sizing.warnings)
        if payload_warning:
            warnings.append(payload_warning)

        # logger.info(
        #     "execute_trade",
        #     extra={
        #         "event": "execute_trade",
        #         "symbol": symbol,
        #         "entry": entry_price,
        #         "stop": stop_price,
        #         "risk_pct": risk_pct,
        #         "size": sizing.size,
        #         "side": sizing.side,
        #         "warnings": warnings,
        #     },
        # )

        order_resp = await self.gateway.place_order(payload)
        exchange_order_id = order_resp.get("exchange_order_id")
        if not exchange_order_id:
            raw = order_resp.get("raw")
            raise risk_engine.PositionSizingError(f"Order placement failed: {raw}")
        warnings.extend(
            self._verify_hyperliquid_grouped_submit(
                payload=payload,
                order_resp=order_resp,
            )
        )

        self.open_risk_estimates[exchange_order_id] = sizing.estimated_loss

        return {
            "executed": True,
            "exchange_order_id": exchange_order_id,
            "warnings": warnings,
            "sizing": sizing,
        }

    async def refresh_state(self) -> None:
        """Refresh in-memory orders and positions from gateway."""
        positions_raw = await self.gateway.get_open_positions()
        self.positions = await self._enrich_positions(positions_raw, tpsl_map=self._tpsl_targets_by_symbol)

        raw_orders = await self.gateway.get_open_orders()
        self.open_orders = [self._normalize_order(order) for order in raw_orders]
        self._rebuild_open_risk_estimates(open_orders=self.open_orders, positions=self.positions)
        # logger.info(
        #     "state_refreshed",
        #     extra={
        #         "event": "state_refreshed",
        #         "positions_count": len(self.positions),
        #         "open_orders_count": len(self.open_orders),
        #     },
        # )

    async def list_orders(self) -> list[Dict[str, Any]]:
        """Return open orders from gateway and update cache."""
        raw_orders = await self.gateway.get_open_orders()
        normalized: list[Dict[str, Any]] = []
        for order in raw_orders:
            if not self._include_in_open_orders(order):
                continue
            norm = self._normalize_order(order)
            oid = norm.get("id")
            cid = norm.get("client_id")
            if not norm.get("entry_price"):
                if oid and oid in self.pending_order_prices:
                    norm["entry_price"] = self.pending_order_prices.get(oid)
                elif cid and cid in self.pending_order_prices_client:
                    norm["entry_price"] = self.pending_order_prices_client.get(cid)
            normalized.append(norm)
        self.open_orders = normalized
        self._rebuild_open_risk_estimates(open_orders=self.open_orders, positions=self.positions)
        # drop pending price hints for orders no longer open
        open_ids = {o.get("id") for o in self.open_orders if o.get("id")}
        open_cids = {o.get("client_id") for o in self.open_orders if o.get("client_id")}
        self.pending_order_prices = {k: v for k, v in self.pending_order_prices.items() if k in open_ids}
        self.pending_order_prices_client = {
            k: v for k, v in self.pending_order_prices_client.items() if k in open_cids
        }
        return self.open_orders

    async def list_symbols(self) -> list[Dict[str, Any]]:
        """Return cached symbol catalog for dropdowns (normalized to SymbolResponse)."""
        raw = await self.gateway.list_symbols()
        symbols: list[Dict[str, Any]] = []
        for cfg in raw or []:
            if not isinstance(cfg, dict):
                continue
            code = cfg.get("symbol") or cfg.get("code")
            if not code or not isinstance(code, str):
                continue
            code_clean = code.strip().upper()
            if not re.fullmatch(r"[A-Z0-9]+-[A-Z0-9]+", code_clean):
                continue
            base = cfg.get("baseAsset") or cfg.get("baseTokenId") or cfg.get("base_token")
            quote = cfg.get("quoteAsset") or cfg.get("settleAssetId") or cfg.get("quote_token")
            status = cfg.get("status")
            if status is None and cfg.get("enableTrade") is not None:
                status = "ENABLED" if cfg.get("enableTrade") else "DISABLED"
            tick_size = _coerce_float(cfg.get("tickSize") or cfg.get("tick_size"))
            step_size = _coerce_float(cfg.get("stepSize") or cfg.get("step_size"))
            raw_cfg = cfg.get("raw") or {}
            price_decimals = _infer_decimal_places(raw_cfg.get("tickSize") or tick_size)
            size_decimals = _infer_decimal_places(raw_cfg.get("stepSize") or step_size)
            tick_value = tick_size if tick_size and tick_size > 0 else None
            step_value = step_size if step_size and step_size > 0 else None
            symbols.append(
                {
                    "code": code_clean,
                    "base_asset": base,
                    "quote_asset": quote,
                    "status": status,
                    "tick_size": tick_value,
                    "step_size": step_value,
                    "price_decimals": price_decimals,
                    "size_decimals": size_decimals,
                }
            )
        return symbols

    async def get_account_summary(self) -> Dict[str, Any]:
        """Return account metrics for UI header."""
        return await self.gateway.get_account_summary()

    async def get_stream_health(self) -> Dict[str, Any]:
        """Return exchange stream/reconcile health metrics for diagnostics."""
        getter = getattr(self.gateway, "get_stream_health_snapshot", None)
        payload = getter() if callable(getter) else {}
        return {"venue": (getattr(self.gateway, "venue", "unknown") or "unknown"), **(payload or {})}

    async def list_positions(self) -> list[Dict[str, Any]]:
        """Return open positions from gateway and update cache, merging TP/SL from open orders when available."""
        positions_raw = await self.gateway.get_open_positions(force_rest=False, publish=True)
        if not positions_raw:
            positions_raw = await self.gateway.get_open_positions(force_rest=True, publish=True)
        self.positions = await self._enrich_positions(positions_raw, tpsl_map=self._tpsl_targets_by_symbol)

        # If positions exist but TP/SL map is missing, do a bounded account-orders backfill once
        # to avoid "blank until hard refresh" on initial load.
        venue = (getattr(self.gateway, "venue", "") or "").lower()
        if venue in {"apex", "hyperliquid"} and self.positions:
            needs_backfill = False
            for pos in self.positions:
                symbol = self._normalize_symbol_value(pos.get("symbol"))
                entry = self._tpsl_targets_by_symbol.get(symbol, {})
                if entry.get("take_profit") is None and entry.get("stop_loss") is None:
                    needs_backfill = True
                    break
            now = time.time()
            if needs_backfill and (now - self._tpsl_backfill_last_ts) >= self._tpsl_backfill_min_gap_seconds:
                self._tpsl_backfill_last_ts = now
                try:
                    snapshot = self.gateway.get_account_orders_snapshot()
                    if not snapshot:
                        snapshot = await self.gateway.refresh_account_orders_from_rest()
                    if snapshot:
                        self._reconcile_tpsl(snapshot)
                        self.positions = await self._enrich_positions(positions_raw, tpsl_map=self._tpsl_targets_by_symbol)
                except Exception:
                    pass

        self._rebuild_open_risk_estimates(open_orders=self.open_orders, positions=self.positions)
        return self.positions

    async def close_position(
        self, *, position_id: str, close_percent: float, close_type: str, limit_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """Close a portion of a position via reduce-only order."""
        positions = await self.list_positions()
        target = next((p for p in positions if str(p.get("id")) == str(position_id)), None)
        if not target:
            raise ValueError(f"Position {position_id} not found")
        size_raw = target.get("size")
        try:
            size_val = float(size_raw)
        except Exception:
            raise ValueError("Position size unavailable")
        close_size = size_val * (close_percent / 100.0)
        if close_size <= 0:
            raise ValueError("close_percent must be greater than 0")
        # logger.info(
        #     "close_position_request",
        #     extra={
        #         "event": "close_position_request",
        #         "position_id": position_id,
        #         "symbol": target.get("symbol"),
        #         "side": target.get("side"),
        #         "close_percent": close_percent,
        #         "close_size": close_size,
        #         "close_type": (close_type or "").lower(),
        #         "limit_price": limit_price,
        #     },
        # )
        resp = await self.gateway.place_close_order(
            symbol=target.get("symbol") or "",
            side=target.get("side") or "",
            size=close_size,
            close_type=close_type,
            limit_price=limit_price,
        )
        resp = resp or {}
        order_id = resp.get("exchange_order_id")
        client_id = resp.get("client_id")
        if not order_id:
            raw = resp.get("raw")
            def _extract_error_message(payload: Any) -> Optional[str]:
                if isinstance(payload, dict):
                    for key in ("retMsg", "ret_msg", "message", "detail", "msg"):
                        val = payload.get(key)
                        if val:
                            return str(val)
                    nested = payload.get("result") or payload.get("data")
                    if isinstance(nested, dict):
                        for key in ("retMsg", "ret_msg", "message", "detail", "msg"):
                            val = nested.get(key)
                            if val:
                                return str(val)
                return None
            error_detail = _extract_error_message(raw)
            logger.error(
                "close_position_submit_failed",
                extra={
                    "event": "close_position_submit_failed",
                    "position_id": position_id,
                    "symbol": target.get("symbol"),
                    "close_percent": close_percent,
                    "close_type": (close_type or "").lower(),
                    "limit_price": limit_price,
                    "response": raw,
                },
            )
            raise ValueError(error_detail or "Exchange rejected close order")
        if order_id and limit_price is not None:
            self.pending_order_prices[str(order_id)] = limit_price
        if client_id and limit_price is not None:
            self.pending_order_prices_client[str(client_id)] = limit_price
        # logger.info(
        #     "close_position_submitted",
        #     extra={
        #         "event": "close_position_submitted",
        #         "position_id": position_id,
        #         "symbol": target.get("symbol"),
        #         "close_type": (close_type or "").lower(),
        #         "close_percent": close_percent,
        #         "order_id": order_id,
        #         "client_id": client_id,
        #     },
        # )
        if isinstance(close_type, str) and close_type.lower() == "limit":
            try:
                await self.gateway.get_open_orders(force_rest=True, publish=True)
            except Exception:
                # Non-fatal; WS/next refresh will pick up the new order.
                # logger.debug("close_position_refresh_orders_failed", exc_info=True)
                return {
                    "position_id": position_id,
                    "requested_percent": close_percent,
                    "close_size": close_size,
                    "exchange": resp,
                }

    async def modify_targets(
        self,
        *,
        position_id: str,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        clear_tp: bool = False,
        clear_sl: bool = False,
    ) -> Dict[str, Any]:
        """Update TP/SL targets for a position via exchange create_order_v3 TP/SL flags."""
        if take_profit is None and stop_loss is None and not clear_tp and not clear_sl:
            raise ValueError("At least one of take_profit, stop_loss, clear_tp, or clear_sl must be provided")

        # logger.info(
        #     "modify_targets_request",
        #     extra={
        #         "event": "modify_targets_request",
        #         "position_id": position_id,
        #         "take_profit": take_profit,
        #         "stop_loss": stop_loss,
        #         "clear_tp": clear_tp,
        #         "clear_sl": clear_sl,
        #     },
        # )

        positions = await self.list_positions()
        target = next((p for p in positions if str(p.get("id")) == str(position_id)), None)
        if not target:
            raise ValueError(f"Position {position_id} not found")
        symbol = target.get("symbol") or ""
        side = target.get("side") or ""
        size_raw = target.get("size")
        existing_tp = target.get("take_profit")
        existing_sl = target.get("stop_loss")
        try:
            size_val = float(size_raw)
        except Exception:
            raise ValueError("Position size unavailable for TP/SL update")

        symbol_key = self._normalize_symbol_value(symbol or target.get("id"))
        response: Dict[str, Any] = {"position_id": position_id}

        if clear_tp or clear_sl:
            cancel_resp = await self.gateway.cancel_tpsl_orders(
                symbol=symbol or None,
                cancel_tp=clear_tp,
                cancel_sl=clear_sl,
            )
            response["canceled"] = cancel_resp
            canceled_ids = (cancel_resp or {}).get("canceled") if isinstance(cancel_resp, dict) else None
            errors = (cancel_resp or {}).get("errors") if isinstance(cancel_resp, dict) else None
            cancel_ok = not errors or bool(canceled_ids)
            response["cancel_ok"] = bool(cancel_ok)
            response["cancel_errors"] = errors

            # Only clear local cache/hints when the exchange cancel succeeded or nothing was present to cancel.
            if cancel_ok:
                cache_entry = self._tpsl_targets_by_symbol.get(symbol_key, {})
                if clear_tp:
                    cache_entry.pop("take_profit", None)
                if clear_sl:
                    cache_entry.pop("stop_loss", None)
                if not cache_entry:
                    self._tpsl_targets_by_symbol.pop(symbol_key, None)
                else:
                    self._tpsl_targets_by_symbol[symbol_key] = cache_entry
                if clear_tp and clear_sl:
                    self.position_targets.pop(symbol_key, None)
                else:
                    hints = self.position_targets.get(symbol_key, {})
                    if clear_tp:
                        hints.pop("take_profit", None)
                    if clear_sl:
                        hints.pop("stop_loss", None)
                    if hints:
                        self.position_targets[symbol_key] = hints
                    else:
                        self.position_targets.pop(symbol_key, None)
                self._set_local_tpsl_hint(
                    symbol=symbol_key,
                    clear_tp=clear_tp,
                    clear_sl=clear_sl,
                )

        if take_profit is not None or stop_loss is not None:
            resp = await self.gateway.update_targets(
                symbol=symbol,
                side=side,
                size=size_val,
                take_profit=take_profit,
                stop_loss=stop_loss,
                cancel_existing=False,
                cancel_tp=False,
                cancel_sl=False,
            )
            response["exchange"] = resp

            current = self.position_targets.get(symbol_key, {})
            if existing_tp is not None and "take_profit" not in current:
                current["take_profit"] = existing_tp
            if existing_sl is not None and "stop_loss" not in current:
                current["stop_loss"] = existing_sl
            if take_profit is not None:
                current["take_profit"] = take_profit
            if stop_loss is not None:
                current["stop_loss"] = stop_loss
            if current:
                self.position_targets[symbol_key] = current
                # seed TP/SL map immediately so list_positions reflects latest request even if REST snapshots lag
                map_entry = self._tpsl_targets_by_symbol.setdefault(symbol_key, {})
                if take_profit is not None:
                    map_entry["take_profit"] = take_profit
                if stop_loss is not None:
                    map_entry["stop_loss"] = stop_loss
                self._set_local_tpsl_hint(
                    symbol=symbol_key,
                    take_profit=take_profit,
                    stop_loss=stop_loss,
                )

        return response

    async def _enrich_positions(
        self, positions_raw: list[Dict[str, Any]], tpsl_map: Optional[Dict[str, Dict[str, float]]] = None
    ) -> list[Dict[str, Any]]:
        """Normalize positions and populate pnl using mark price when available."""
        normalized: list[Dict[str, Any]] = []
        symbols = set()
        for pos in positions_raw:
            norm = self._normalize_position(pos, tpsl_map=tpsl_map)
            if norm:
                normalized.append(norm)
                if norm.get("symbol"):
                    symbols.add(norm["symbol"])
        mark_cache: Dict[str, float] = {}
        for sym in symbols:
            try:
                mark_cache[sym] = await self.gateway.get_mark_price(sym)
            except Exception:
                continue
        for pos in normalized:
            symbol = pos.get("symbol")
            mark = mark_cache.get(symbol)
            entry = pos.get("entry_price")
            size = pos.get("size")
            side = pos.get("side", "").upper()
            try:
                if mark is not None and entry is not None and size is not None:
                    pnl = (mark - float(entry)) * float(size)
                    if side == "SHORT" or side == "SELL":
                        pnl = -pnl
                    pos["pnl"] = pnl
            except Exception:
                continue
        return normalized

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order and refresh cached state."""
        client_id = None
        for order in self.open_orders:
            if str(order.get("id")) == str(order_id):
                client_id = order.get("client_id")
                break
        result = await self.gateway.cancel_order(order_id, client_id=client_id)
        await self.refresh_state()
        still_open = any(str(o.get("id")) == str(order_id) for o in self.open_orders)
        canceled = result.get("canceled") or not still_open
        result["canceled"] = canceled
        if canceled:
            self.open_risk_estimates.pop(order_id, None)
        # logger.info(
        #     "cancel_order",
        #     extra={
        #         "event": "cancel_order",
        #         "order_id": order_id,
        #         "canceled": canceled,
        #         "still_open": still_open,
        #     },
        # )
        return result

    def _normalize_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Return a consistent shape for UI/API consumption."""

        def _coerce_float(value: Any) -> Optional[float]:
            try:
                if value is None:
                    return None
                return float(value)
            except Exception:
                return None

        oid = (
            order.get("orderId")
            or order.get("order_id")
            or order.get("clientOrderId")
            or order.get("_cache_id")
            or order.get("id")
            or ""
        )
        size_val = _coerce_float(order.get("size") or order.get("qty") or order.get("quantity"))
        price_val = _coerce_float(
            order.get("price")
            or order.get("avgPrice")
            or order.get("orderPrice")
            or order.get("order_price")
            or order.get("limitPrice")
            or order.get("origPrice")
            or order.get("triggerPrice")
        )
        normalized = {
            "id": str(oid),
            "symbol": order.get("symbol") or order.get("market"),
            "side": (order.get("side") or order.get("positionSide") or order.get("direction") or "").upper(),
            "size": size_val if size_val is not None else order.get("size") or order.get("qty") or order.get("quantity"),
            "status": order.get("status") or order.get("state") or order.get("orderStatus"),
            "entry_price": price_val,
        }
        client_id = order.get("clientOrderId") or order.get("clientId")
        if client_id is not None:
            normalized["client_id"] = client_id
        # reduce_only indicates a closing order in many exchanges; if not present, infer from payload if possible
        normalized["reduce_only"] = order.get("reduceOnly") or order.get("reduce_only") or False
        if not normalized.get("entry_price"):
            if normalized.get("id") and normalized["id"] in self.pending_order_prices:
                normalized["entry_price"] = self.pending_order_prices.get(normalized["id"])
            elif client_id and client_id in self.pending_order_prices_client:
                normalized["entry_price"] = self.pending_order_prices_client.get(client_id)
        return normalized

    def _extract_tpsl_from_orders(self, orders: list[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        """Build a symbol->tp/sl map from TP/SL orders (reduce-only or position TP/SL)."""

        def _first_number(values: list[Any]) -> Optional[float]:
            for val in values:
                if val is None:
                    continue
                if isinstance(val, (int, float)):
                    return float(val)
                if isinstance(val, str):
                    try:
                        return float(val)
                    except Exception:
                        continue
            return None

        tpsl: Dict[str, Dict[str, Any]] = {}
        debug_counts = {"total": 0, "position_tpsl": 0, "tp": 0, "sl": 0, "skipped_status": 0, "skipped_trigger": 0}
        for order in orders or []:
            debug_counts["total"] += 1
            if not isinstance(order, dict):
                continue
            status_raw = str(order.get("status") or order.get("orderStatus") or "").lower()
            if status_raw in {"canceled", "cancelled", "filled", "triggered"} or "cancel" in status_raw:
                debug_counts["skipped_status"] += 1
                continue
            symbol = self._normalize_symbol_value(order.get("symbol") or order.get("market"))
            if not symbol:
                continue
            order_type = (order.get("type") or order.get("orderType") or order.get("order_type") or "").upper()
            is_position_tpsl = self._is_tpsl_order(order)
            if not is_position_tpsl:
                continue
            debug_counts["position_tpsl"] += 1

            tp_candidates = [
                order.get("tpTriggerPrice"),
                order.get("tpPrice"),
                order.get("openTpParam"),
                order.get("takeProfitPrice"),
                order.get("takeProfit"),
                order.get("tp"),
                order.get("triggerPrice") if order_type.startswith("TAKE_PROFIT") else None,
                (order.get("openTpParams") or {}).get("triggerPrice"),
            ]
            sl_candidates = [
                order.get("slTriggerPrice"),
                order.get("slPrice"),
                order.get("openSlParam"),
                order.get("stopLossPrice"),
                order.get("stopLoss"),
                order.get("sl"),
                order.get("triggerPrice") if order_type.startswith("STOP") else None,
                (order.get("openSlParams") or {}).get("triggerPrice"),
            ]

            tp_val = _first_number(tp_candidates)
            sl_val = _first_number(sl_candidates)
            if tp_val is None and sl_val is None:
                debug_counts["skipped_trigger"] += 1
            entry = tpsl.setdefault(symbol, {})

            def _update_target(field: str, value: Optional[float]) -> None:
                if value is None:
                    return
                entry[field] = value

            if "TAKE_PROFIT" in order_type or tp_val is not None:
                _update_target("take_profit", tp_val)
                if tp_val is not None:
                    debug_counts["tp"] += 1
            if "STOP" in order_type or sl_val is not None:
                _update_target("stop_loss", sl_val)
                if sl_val is not None:
                    debug_counts["sl"] += 1

        cleaned: Dict[str, Dict[str, float]] = {}
        for sym, data in tpsl.items():
            tp_val = data.get("take_profit")
            sl_val = data.get("stop_loss")
            clean_entry: Dict[str, float] = {}
            if tp_val is not None:
                clean_entry["take_profit"] = tp_val
            if sl_val is not None:
                clean_entry["stop_loss"] = sl_val
            if clean_entry:
                cleaned[sym] = clean_entry
        #try:
            # logger.info(
            #     "tpsl_extract_summary",
            #     extra={
            #         "event": "tpsl_extract_summary",
            #         "total": debug_counts["total"],
            #         "position_tpsl": debug_counts["position_tpsl"],
            #         "tp_found": debug_counts["tp"],
            #         "sl_found": debug_counts["sl"],
            #         "skipped_status": debug_counts["skipped_status"],
            #         "skipped_trigger": debug_counts["skipped_trigger"],
            #         "symbols": list(cleaned.keys()),
            #     },
            # )
        #except Exception:
        #    pass
        return cleaned

    def _normalize_position(
        self, position: Dict[str, Any], tpsl_map: Optional[Dict[str, Dict[str, float]]] = None
    ) -> Dict[str, Any]:
        """Return a consistent shape for UI/API consumption."""
        raw_size = position.get("size") or position.get("positionSize")

        def _coerce_float(value: Any) -> Optional[float]:
            try:
                if value is None:
                    return None
                return float(value)
            except Exception:
                return None

        size_val = _coerce_float(raw_size)
        if size_val is not None and size_val <= 0:
            return None

        symbol = self._normalize_symbol_value(position.get("symbol") or position.get("market"))
        side = (position.get("side") or position.get("positionSide") or position.get("direction") or "").upper()
        entry_price = _coerce_float(position.get("entryPrice") or position.get("avgPrice") or position.get("entry_price"))
        tp_raw = _coerce_float(
            position.get("takeProfit")
            or position.get("tp")
            or position.get("tpPrice")
            or position.get("takeProfitPrice")
            or position.get("tp_trigger_price")
            or position.get("tpTriggerPrice")
        )
        sl_raw = _coerce_float(
            position.get("stopLoss")
            or position.get("sl")
            or position.get("slPrice")
            or position.get("stopLossPrice")
            or position.get("sl_trigger_price")
            or position.get("slTriggerPrice")
            or position.get("triggerPrice")
        )
        pnl_val = None
        pnl_candidates = (
            position.get("pnl"),
            position.get("unrealizedPnl"),
            position.get("unrealizedPnlUsd"),
            position.get("unrealizedPnlValue"),
        )
        for candidate in pnl_candidates:
            pnl_val = _coerce_float(candidate)
            if pnl_val is not None:
                break

        norm = {
            "id": position.get("positionId") or position.get("id") or symbol,
            "symbol": symbol,
            "side": side,
            "size": size_val if size_val is not None else raw_size,
            "entry_price": entry_price,
            "take_profit": tp_raw,
            "stop_loss": sl_raw,
            "pnl": pnl_val,
        }

        map_src = tpsl_map or self._tpsl_targets_by_symbol
        sym_key = symbol or norm.get("symbol") or ""
        tpsl_entry = map_src.get(sym_key) if map_src else None
        if tpsl_entry:
            if tpsl_entry.get("take_profit") is not None:
                norm["take_profit"] = tpsl_entry["take_profit"]
            if tpsl_entry.get("stop_loss") is not None:
                norm["stop_loss"] = tpsl_entry["stop_loss"]

        hint = None
        for key in (sym_key, norm.get("id"), position.get("positionId"), position.get("id")):
            if key and key in self.position_targets:
                hint = self.position_targets[key]
                break
        if hint:
            if norm.get("take_profit") is None and "take_profit" in hint:
                norm["take_profit"] = hint.get("take_profit")
            if norm.get("stop_loss") is None and "stop_loss" in hint:
                norm["stop_loss"] = hint.get("stop_loss")

        norm["take_profit"] = self._resolve_tpsl_value(
            symbol=sym_key,
            kind="take_profit",
            ws_or_cache_value=norm.get("take_profit"),
        )
        norm["stop_loss"] = self._resolve_tpsl_value(
            symbol=sym_key,
            kind="stop_loss",
            ws_or_cache_value=norm.get("stop_loss"),
        )

        return norm

    async def get_symbol_price(self, symbol: str) -> Dict[str, Any]:
        price, _source = await self.gateway.get_reference_price(symbol)
        return {"symbol": symbol, "price": price}

    async def get_depth_summary(
        self, *, symbol: str, tolerance_bps: int, levels: int
    ) -> Dict[str, Any]:
        if not symbol:
            raise ValueError("symbol is required")
        symbol_key = self._normalize_symbol_value(symbol)
        cache_key = (symbol_key, int(tolerance_bps), int(levels))
        now = time.monotonic()
        cached = self._depth_summary_cache.get(cache_key)
        if cached and now - cached[0] < self._depth_summary_cache_ttl:
            return cached[1]
        payload = await self.gateway.get_depth_snapshot(symbol_key, levels=levels)
        from backend.market.depth_summary import compute_depth_summary

        summary = compute_depth_summary(payload, tolerance_bps=tolerance_bps)
        if summary.get("bid") is None or summary.get("ask") is None:
            raise ValueError("Liquidity unavailable")
        self._depth_summary_cache[cache_key] = (now, summary)
        return summary

    async def resync_tpsl_from_account(self) -> bool:
        """Force a refresh of TP/SL orders via full account snapshot."""
        try:
            snapshot = await self.gateway.refresh_account_orders_from_rest()
        except Exception as exc:
            logger.warning(
                "tpsl_resync_snapshot_failed",
                extra={"event": "tpsl_resync_snapshot_failed", "error": str(exc)},
            )
            return False
        if not snapshot:
            logger.warning(
                "tpsl_resync_empty",
                extra={"event": "tpsl_resync_empty"},
            )
            return False
        try:
            self._reconcile_tpsl(snapshot)
        except Exception as exc:
            logger.warning(
                "tpsl_resync_reconcile_failed",
                extra={"event": "tpsl_resync_reconcile_failed", "error": str(exc)},
            )
            return False
        await self.list_positions()
        return True
