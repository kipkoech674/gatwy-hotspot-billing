(() => {
  const plansEl = document.querySelector("#plans");
  const form = document.querySelector("#checkout-form");
  const button = document.querySelector("#pay-button");
  const message = document.querySelector("#checkout-message");
  const receiptDisplay = document.querySelector("#payment-receipt");
  const summary = document.querySelector("#selection-summary");
  const checkoutDialog = document.querySelector("#checkout-dialog");
  const reactivateForm = document.querySelector("#reactivate-form");
  const reactivateMessage = document.querySelector("#reactivate-message");
  const reactivateCredentials = document.querySelector("#reactivate-credentials");
  const hotspotLogin = JSON.parse(document.querySelector("#hotspot-login-config").textContent);
  const portalPlans = JSON.parse(document.querySelector("#portal-plans-config").textContent);
  const paymentsEnabled = document.body.dataset.paymentsEnabled === "true";
  let selectedPlan = null;
  let statusTimer = null;

  const csrf = () => document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  const money = (amount) => `KSh ${Number(amount).toLocaleString("en-KE")}`;

  function connectDevice(statusElement) {
    statusElement.textContent = "Payment confirmed. Connecting this device to Wi-Fi…";
    statusElement.className = "checkout-message success";
    window.setTimeout(() => {
      if (hotspotLogin.login_url && hotspotLogin.device_mac) {
        const loginTarget = new URL(hotspotLogin.login_url, window.location.origin);
        loginTarget.searchParams.set("username", hotspotLogin.device_mac);
        loginTarget.searchParams.set("password", hotspotLogin.device_mac);
        loginTarget.searchParams.set("dst", hotspotLogin.destination || "http://neverssl.com/");
        window.location.assign(loginTarget.toString());
      } else {
        window.location.assign(hotspotLogin.destination || "http://neverssl.com/");
      }
    }, 700);
  }

  function renderPlans(plans) {
    plansEl.replaceChildren();
    const categories = ["Hourly", "Daily", "Weekly", "Monthly"];
    categories.forEach((category) => {
      const categoryPlans = plans.filter((plan) => plan.category === category);
      if (!categoryPlans.length) return;
      const group = document.createElement("section");
      group.className = "plan-group";
      group.setAttribute("aria-label", `${category} packages`);
      group.innerHTML = `<h3 class="plan-group-title">${category} packages</h3>`;
      const grid = document.createElement("div");
      grid.className = "plan-grid";
      group.appendChild(grid);
      categoryPlans.forEach((plan) => {
      const card = document.createElement("button");
      card.type = "button";
      const isPopular = plan.code === "day-1";
      card.className = `plan-card${isPopular ? " popular" : ""}`;
      card.setAttribute("aria-pressed", "false");
      const duration = plan.name.split(" · ")[0];
      const devices = `${plan.device_count} device${plan.device_count > 1 ? "s" : ""}`;
      const badge = isPopular ? '<span class="popular-tag">POPULAR</span>' : "";
      card.innerHTML = `${badge}<span class="plan-duration">${duration}</span><span class="plan-price">${money(plan.price_kes)}</span><span class="plan-devices"><strong>${devices}</strong><span class="device-dot"></span>5 Mbps each</span><span class="plan-select">Choose package <b>→</b></span>`;
      card.addEventListener("click", () => selectPlan(plan, card));
      grid.appendChild(card);
      });
      plansEl.appendChild(group);
    });
  }

  function selectPlan(plan, card) {
    document.querySelectorAll(".plan-card").forEach((item) => {
      item.classList.remove("selected");
      item.setAttribute("aria-pressed", "false");
    });
    card.classList.add("selected");
    card.setAttribute("aria-pressed", "true");
    selectedPlan = plan;
    summary.classList.remove("empty");
    summary.innerHTML = `<span class="summary-icon">⌁</span><span><strong>${plan.name}</strong><small>${plan.device_count} device${plan.device_count > 1 ? "s" : ""} · 5 Mbps each</small></span><b>${money(plan.price_kes)}</b>`;
    button.disabled = !paymentsEnabled;
    message.textContent = "";
    receiptDisplay.hidden = true;
    receiptDisplay.textContent = "";
    message.className = "checkout-message";
    checkoutDialog.showModal();
    window.setTimeout(() => document.querySelector("#phone").focus(), 0);
  }

  function watchPurchase(purchaseId) {
    if (statusTimer) window.clearInterval(statusTimer);
    const startedAt = Date.now();
    const poll = async () => {
      try {
        const response = await fetch(`/api/purchases/${purchaseId}/`, { cache: "no-store" });
        if (!response.ok) return;
        const state = await response.json();
        if (state.status === "paid") {
          if (receiptDisplay && state.mpesa_receipt) {
            receiptDisplay.hidden = false;
            receiptDisplay.textContent = `Receipt: ${state.mpesa_receipt}`;
          }
          if (state.access_activated) {
            window.clearInterval(statusTimer);
            connectDevice(message);
            return;
          }
          if (Date.now() - startedAt > 120000) {
            window.clearInterval(statusTimer);
            message.textContent = "Payment is confirmed, but Wi-Fi setup is taking longer than expected. Contact support with your M-Pesa receipt.";
            message.className = "checkout-message info";
            button.disabled = false;
            return;
          }
          message.textContent = "Payment confirmed. Setting up your Wi-Fi access…";
          message.className = "checkout-message info";
          return;
        }
        if (["failed", "expired"].includes(state.status)) {
          window.clearInterval(statusTimer);
          message.textContent = state.error || "Payment was not completed. You can choose a package and try again.";
          message.className = "checkout-message error";
          button.disabled = false;
          return;
        }
        if (Date.now() - startedAt > 120000) {
          window.clearInterval(statusTimer);
          message.textContent = "Still waiting for M-Pesa confirmation or Wi-Fi setup. Refresh this page in a moment or contact support.";
          message.className = "checkout-message info";
          button.disabled = false;
        }
      } catch (_) {
        // Keep polling; a temporary network error should not cancel the payment.
      }
    };
    statusTimer = window.setInterval(poll, 3000);
    poll();
  }

  renderPlans(portalPlans);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedPlan || !paymentsEnabled) return;
    button.disabled = true;
    button.classList.add("working");
    message.textContent = "Starting secure payment…";
    message.className = "checkout-message info";
    try {
      const response = await fetch("/api/checkout/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
        body: JSON.stringify({
          plan_id: selectedPlan.id,
          phone: document.querySelector("#phone").value,
          device_mac: hotspotLogin.device_mac,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Payment could not be started.");
      message.textContent = result.message;
      message.className = "checkout-message info";
      watchPurchase(result.purchase_id);
    } catch (error) {
      message.textContent = error.message;
      message.className = "checkout-message error";
    } finally {
      button.classList.remove("working");
      button.disabled = !selectedPlan;
    }
  });

  reactivateForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const reactivateButton = document.querySelector("#reactivate-button");
    reactivateButton.disabled = true;
    reactivateCredentials.hidden = true;
    reactivateCredentials.textContent = "";
    reactivateMessage.textContent = "Checking your M-Pesa receipt…";
    reactivateMessage.className = "checkout-message info";
    try {
      const response = await fetch("/api/reactivate/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
        body: JSON.stringify({
          phone: document.querySelector("#reactivate-phone").value,
          receipt: document.querySelector("#reactivate-receipt").value,
          device_mac: hotspotLogin.device_mac,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "We could not verify that package.");
      if (result.status === "active") {
        const expiry = new Date(result.expires_at).toLocaleString("en-KE", { dateStyle: "medium", timeStyle: "short" });
        reactivateCredentials.hidden = false;
        reactivateCredentials.textContent = `${result.plan} · ${result.devices_connected} of ${result.devices_allowed} device${result.devices_allowed === 1 ? "" : "s"} connected · Ends ${expiry}`;
        connectDevice(reactivateMessage);
        return;
      } else {
        reactivateMessage.textContent = result.message;
      }
      reactivateMessage.className = "checkout-message success";
    } catch (error) {
      reactivateMessage.textContent = error.message;
      reactivateMessage.className = "checkout-message error";
    } finally {
      reactivateButton.disabled = false;
    }
  });

  document.querySelectorAll(".dialog-close").forEach((button) => {
    button.addEventListener("click", () => {
      if (statusTimer) window.clearInterval(statusTimer);
      button.closest("dialog").close();
    });
  });
})();
