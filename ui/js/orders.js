(function () {
  const API_BASE = (window.TradeApp && window.TradeApp.API_BASE) || 
  window.API_BASE || 
  `${window.location.protocol}//${window.location.hostname}:8000`;
  const formatNumber = (window.TradeApp && window.TradeApp.formatNumber) || ((v) => v);
  let streamSocket = null;
  let streamToken = 0;

  async function fetchOrders() {
    const resp = await fetch(`${API_BASE}/api/orders`);
    const data = await resp.json();
    if (!resp.ok) {
      const msg = data?.detail || "Unable to load orders";
      throw new Error(msg);
    }
    return data;
  }

  async function cancelOrder(orderId) {
    const resp = await fetch(`${API_BASE}/api/orders/${orderId}/cancel`, { method: "POST" });
    const data = await resp.json();
    if (!resp.ok) {
      const msg = data?.detail || "Cancel failed";
      throw new Error(msg);
    }
    if (data?.canceled !== true) {
      const msg =
        data?.raw?.errors?.join("; ") ||
        data?.raw?.msg ||
        data?.raw?.status ||
        "Cancel not confirmed by exchange";
      throw new Error(msg);
    }
    return data;
  }

  function renderOrders(orders) {
    const tbody = document.querySelector("#orders-table tbody");
    const emptyState = document.getElementById("orders-empty");
    tbody.innerHTML = "";
    if (!orders || orders.length === 0) {
      emptyState.style.display = "block";
      return;
    }
    emptyState.style.display = "none";

    orders.forEach((order) => {
      const row = document.createElement("tr");
      const cancelCell = document.createElement("td");
      cancelCell.classList.add("actions-cell");
      const cancelBtn = document.createElement("button");
      cancelBtn.className = "btn ghost";
      cancelBtn.textContent = "Cancel";
      const oid = order.client_id || order.id || order._cache_id;
      cancelBtn.disabled = !oid;
      cancelBtn.dataset.orderId = oid || "";
      cancelCell.appendChild(cancelBtn);

      const sideIsClose = !!order.reduce_only;
      const sideIcon = sideIsClose ? "/assets/close.png" : "/assets/open.png";
      row.innerHTML = `
        <td>${order.symbol || ""}</td>
        <td>${formatNumber(order.entry_price)}</td>
        <td><span class="side-cell">${order.side || ""}<img src="${sideIcon}" alt="" /></span></td>
        <td>${order.size ?? ""}</td>
        <td>${order.status || ""}</td>
      `;
      row.appendChild(cancelCell);
      tbody.appendChild(row);
    });
  }

  async function loadOrders() {
    const errorBox = document.getElementById("orders-error");
    errorBox.textContent = "";
    try {
      const orders = await fetchOrders();
      renderOrders(orders);
    } catch (err) {
      errorBox.textContent = err.message;
    }
  }

  function startStream(attempt = 0, token = streamToken) {
    const errorBox = document.getElementById("orders-error");
    try {
      const wsUrl = (API_BASE.replace(/^http/, "ws")) + "/ws/stream";
      const socket = new WebSocket(wsUrl);
      streamSocket = socket;
      socket.onmessage = (event) => {
        if (token !== streamToken) {
          return;
        }
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "account" && window.TradeApp && typeof window.TradeApp.applyAccountPayload === "function") {
            window.TradeApp.applyAccountPayload(msg.payload);
          }
          if (msg.type === "ticker" && window.TradeApp && typeof window.TradeApp.updateTickerCache === "function") {
            window.TradeApp.updateTickerCache(msg.symbol, msg.price);
          }
          if (msg.type === "orders" && Array.isArray(msg.payload)) {
            renderOrders(msg.payload);
          }
        } catch (err) {
          // ignore malformed frames
        }
      };
      socket.onerror = () => {
        errorBox.textContent = "Stream disconnected; falling back to manual refresh.";
      };
      socket.onclose = () => {
        if (token !== streamToken) {
          return;
        }
        errorBox.textContent = "Stream closed; attempting to reconnect.";
        setTimeout(
          () => startStream(Math.min(attempt + 1, 5), token),
          1000 * Math.min(attempt + 1, 5)
        );
      };
    } catch (err) {
      errorBox.textContent = err.message;
    }
  }

  function restartStream() {
    streamToken += 1;
    if (streamSocket && streamSocket.readyState < WebSocket.CLOSING) {
      streamSocket.close();
    }
    startStream(0, streamToken);
  }

  document.addEventListener("DOMContentLoaded", () => {
    const refreshBtn = document.getElementById("refresh-orders");
    const table = document.getElementById("orders-table");
    refreshBtn.addEventListener("click", loadOrders);
    table.addEventListener("click", async (event) => {
      const target = event.target;
      if (target.tagName !== "BUTTON" || !target.dataset.orderId) {
        return;
      }
      target.disabled = true;
      try {
        await cancelOrder(target.dataset.orderId);
        await loadOrders();
      } catch (err) {
        const errorBox = document.getElementById("orders-error");
        errorBox.textContent = err.message;
      } finally {
        target.disabled = false;
      }
    });

    loadOrders();
    restartStream();

    window.addEventListener("venue:changed", () => {
      loadOrders();
      restartStream();
    });
  });
})();
