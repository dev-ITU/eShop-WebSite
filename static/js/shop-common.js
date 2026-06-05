(function () {
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
      return parts.pop().split(";").shift();
    }
    return "";
  }

  function updateCartCount(count) {
    document.querySelectorAll("[data-cart-count]").forEach((node) => {
      node.textContent = String(count || 0);
      node.hidden = !count;
    });
  }

  function toast(message) {
    const host = document.querySelector("[data-toast-host]");
    if (!host) return;
    const node = document.createElement("div");
    node.className = "toast";
    node.textContent = message;
    host.appendChild(node);
    window.setTimeout(() => node.remove(), 2600);
  }

  async function apiFetch(url, options) {
    const opts = options || {};
    const headers = new Headers(opts.headers || {});
    headers.set("X-Requested-With", "XMLHttpRequest");
    if (!headers.has("Content-Type") && opts.body && typeof opts.body !== "string") {
      headers.set("Content-Type", "application/json");
    }
    const method = (opts.method || "GET").toUpperCase();
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      headers.set("X-CSRFToken", getCookie("csrftoken"));
    }

    const response = await fetch(url, {
      ...opts,
      headers,
      body: opts.body && typeof opts.body !== "string" ? JSON.stringify(opts.body) : opts.body,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.detail || "Ошибка запроса");
      error.data = data;
      throw error;
    }
    return data;
  }

  async function addToCart(productId, quantity) {
    const cart = await apiFetch("/api/cart/", {
      method: "POST",
      body: { product_id: productId, quantity: quantity || 1 },
    });
    updateCartCount(cart.count);
    document.dispatchEvent(new CustomEvent("cart:updated", { detail: cart }));
    toast("Товар добавлен в корзину");
    return cart;
  }

  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-add-to-cart]");
    if (!button) return;
    event.preventDefault();
    if (button.disabled || button.getAttribute("aria-disabled") === "true") return;
    const productId = button.getAttribute("data-add-to-cart");
    button.disabled = true;
    try {
      await addToCart(productId, 1);
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    updateCartCount(window.ESHOP && window.ESHOP.cartCount);
    if (window.lucide) {
      window.lucide.createIcons();
    }
  });

  window.Shop = {
    apiFetch,
    addToCart,
    toast,
    updateCartCount,
  };
})();
