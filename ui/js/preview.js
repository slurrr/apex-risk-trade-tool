(function () {
  const API_BASE = window.API_BASE || "http://localhost:8000";

  async function postPreview(payload) {
    const response = await fetch(`${API_BASE}/api/trade`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      const msg = data?.detail || "Preview request failed";
      throw new Error(msg);
    }
    return data;
  }

  function renderResult(container, result) {
    container.innerHTML = `
      <div><strong>Side:</strong> ${result.side}</div>
      <div><strong>Size:</strong> ${result.size}</div>
      <div><strong>Notional:</strong> ${result.notional}</div>
      <div><strong>Estimated Loss:</strong> ${result.estimated_loss}</div>
      <div><strong>Entry:</strong> ${result.entry_price}</div>
      <div><strong>Stop:</strong> ${result.stop_price}</div>
      <div><strong>Warnings:</strong> ${(result.warnings || []).join(", ") || "None"}</div>
    `;
  }

  function renderError(container, message) {
    container.innerHTML = `<div class="error">${message}</div>`;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("preview-form");
    const resultContainer = document.getElementById("preview-result");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = {
        symbol: document.getElementById("symbol").value.trim(),
        entry_price: parseFloat(document.getElementById("entry_price").value),
        stop_price: parseFloat(document.getElementById("stop_price").value),
        risk_pct: parseFloat(document.getElementById("risk_pct").value),
        side: document.getElementById("side").value.trim() || null,
        tp: document.getElementById("tp").value ? parseFloat(document.getElementById("tp").value) : null,
        preview: true,
        execute: false,
      };

      try {
        const result = await postPreview(payload);
        renderResult(resultContainer, result);
      } catch (err) {
        renderError(resultContainer, err.message);
      }
    });
  });
})();
