(function () {
  "use strict";
  var form = document.getElementById("order-form");
  if (!form) return;
  var itemsEl = document.getElementById("items");
  var linesEl = document.getElementById("calc-lines");
  var totalEl = document.getElementById("calc-total");
  var statusEl = document.getElementById("calc-status");
  var currencyEl = document.getElementById("f-moeda");
  var timer = null;
  var requestId = 0;

  function rows() { return Array.prototype.slice.call(itemsEl.querySelectorAll(".order-item")); }

  function addItem() {
    var template = rows()[0];
    var clone = template.cloneNode(true);
    clone.querySelector(".item-product").value = "";
    clone.querySelector(".item-qty").value = "";
    itemsEl.appendChild(clone);
    clone.querySelector(".item-product").focus();
    schedule();
  }

  function collect() {
    return rows().map(function (row) {
      return { produto_id: row.querySelector(".item-product").value, quantidade: row.querySelector(".item-qty").value };
    }).filter(function (i) { return i.produto_id && i.quantidade; });
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function calculate() {
    var items = collect();
    var currency = currencyEl.value;
    linesEl.innerHTML = "";
    if (!items.length) {
      totalEl.textContent = "—";
      statusEl.className = "small text-muted mb-2";
      statusEl.textContent = "Selecione produtos e quantidades para calcular.";
      return;
    }
    var current = ++requestId;
    statusEl.className = "small text-muted mb-2";
    statusEl.textContent = "Calculando…";
    fetch(form.dataset.calcUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": window.VE.csrf() },
      body: JSON.stringify({ moeda: currency, itens: items }),
      credentials: "same-origin"
    }).then(function (resp) { return resp.json(); }).then(function (data) {
      if (current !== requestId) return;
      if (!data.ok) {
        totalEl.textContent = "—";
        statusEl.className = "small text-danger mb-2";
        statusEl.textContent = data.mensagem || "Não foi possível calcular.";
        return;
      }
      statusEl.className = "small text-success mb-2";
      statusEl.textContent = "Valores calculados com a cotação atual.";
      data.itens.forEach(function (i) {
        var li = document.createElement("li");
        li.className = "list-group-item px-0";
        var rate = i.moeda_custo !== data.moeda ? '<div class="text-muted">1 ' + i.moeda_custo + " = " + Number(i.taxa_cambio).toLocaleString("pt-BR", { maximumFractionDigits: 6 }) + " " + data.moeda + "</div>" : "";
        li.innerHTML = '<div class="d-flex justify-content-between gap-2"><span class="text-truncate"><code>' + escapeHtml(i.codigo) + "</code> × " + i.quantidade +
          '</span><strong class="text-nowrap">' + window.VE.formatMoney(i.subtotal, data.moeda) + '</strong></div><div class="text-muted">' +
          window.VE.formatMoney(i.preco_unitario, data.moeda) + " / un.</div>" + rate;
        linesEl.appendChild(li);
      });
      totalEl.textContent = window.VE.formatMoney(data.total, data.moeda);
    }).catch(function () {
      if (current !== requestId) return;
      statusEl.className = "small text-danger mb-2";
      statusEl.textContent = "Falha ao calcular. Verifique a conexão.";
    });
  }

  function schedule() { clearTimeout(timer); timer = setTimeout(calculate, 350); }

  document.getElementById("add-item").addEventListener("click", addItem);
  itemsEl.addEventListener("click", function (event) {
    var btn = event.target.closest(".remove-item");
    if (!btn) return;
    var row = btn.closest(".order-item");
    if (rows().length > 1) row.remove();
    else { row.querySelector(".item-product").value = ""; row.querySelector(".item-qty").value = ""; }
    schedule();
  });
  itemsEl.addEventListener("change", schedule);
  itemsEl.addEventListener("input", schedule);
  currencyEl.addEventListener("change", schedule);
  calculate();
})();
