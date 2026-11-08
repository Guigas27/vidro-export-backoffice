(function () {
  "use strict";

  // Modal de confirmação para formulários com a classe .js-confirm
  var modalEl = document.getElementById("confirmModal");
  var pendingForm = null;
  if (modalEl && window.bootstrap) {
    var modal = new bootstrap.Modal(modalEl);
    document.addEventListener("submit", function (event) {
      var form = event.target;
      if (!form.classList || !form.classList.contains("js-confirm") || form.dataset.confirmed === "1") return;
      event.preventDefault();
      pendingForm = form;
      document.getElementById("confirmModalBody").textContent = form.dataset.confirm || "Tem certeza?";
      modal.show();
    });
    document.getElementById("confirmModalOk").addEventListener("click", function () {
      if (!pendingForm) return;
      pendingForm.dataset.confirmed = "1";
      modal.hide();
      pendingForm.submit();
    });
  }

  // Mostrar/ocultar senha
  document.querySelectorAll(".js-toggle-password").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.getElementById(btn.dataset.target);
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.innerHTML = show ? '<i class="bi bi-eye-slash"></i>' : '<i class="bi bi-eye"></i>';
      btn.setAttribute("aria-label", show ? "Ocultar senha" : "Mostrar senha");
    });
  });

  // Alertas de sucesso desaparecem sozinhos
  document.querySelectorAll(".flash-stack .alert-success").forEach(function (el) {
    setTimeout(function () { if (window.bootstrap) bootstrap.Alert.getOrCreateInstance(el).close(); }, 6000);
  });

  // Prévia do preço de venda no formulário de produto
  var costInput = document.querySelector("[data-cost-input]");
  var preview = document.getElementById("sale-preview");
  var multEl = document.querySelector("[data-multiplier]");
  var currency = document.getElementById("f-moeda");
  function parseDecimal(value) {
    value = (value || "").trim().replace(/\s/g, "");
    if (value.indexOf(",") >= 0) value = value.replace(/\./g, "").replace(",", ".");
    var n = parseFloat(value);
    return isNaN(n) ? null : n;
  }
  function updatePreview() {
    var cost = parseDecimal(costInput.value);
    var mult = parseFloat(multEl.dataset.multiplier);
    preview.textContent = cost === null ? "—" : window.VE.formatMoney(cost * mult, currency.value);
  }
  window.VE = {
    formatMoney: function (value, cur) {
      var n = Number(value);
      return (cur ? cur + " " : "") + n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },
    csrf: function () {
      var el = document.querySelector('input[name="csrf_token"]');
      return el ? el.value : "";
    }
  };
  if (costInput && preview && multEl) {
    costInput.addEventListener("input", updatePreview);
    if (currency) currency.addEventListener("change", updatePreview);
    updatePreview();
  }
})();
