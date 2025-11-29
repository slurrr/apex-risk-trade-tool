function normalizeOrder(order) {
  return {
    id: order.orderId || order.order_id || order.id || order.clientOrderId || "N/A",
    symbol: order.symbol || order.market || "-",
    side: order.side || order.positionSide || "-",
    size: order.size || order.qty || order.quantity || "-",
    status: order.status || order.state || "-",
  };
}

async function fetchOrders() {
  const resp = await fetch("/api/orders");
  const data = await resp.json();
  if (!resp.ok) {
    const msg = data?.detail || "Unable to load orders";
    throw new Error(msg);
  }
  return data;
}

async function cancelOrder(orderId) {
  const resp = await fetch(`/api/orders/${orderId}/cancel`, { method: "POST" });
  const data = await resp.json();
  if (!resp.ok) {
    const msg = data?.detail || "Cancel failed";
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
    const info = normalizeOrder(order);
    const row = document.createElement("tr");
    const cancelCell = document.createElement("td");
    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.disabled = !info.id || info.id === "N/A";
    cancelBtn.dataset.orderId = info.id;
    cancelCell.appendChild(cancelBtn);

    row.innerHTML = `
      <td>${info.id}</td>
      <td>${info.symbol}</td>
      <td>${info.side}</td>
      <td>${info.size}</td>
      <td>${info.status}</td>
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
});
