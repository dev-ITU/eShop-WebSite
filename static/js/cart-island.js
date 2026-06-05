(function () {
  const rootNode = document.getElementById("cart-island");
  if (!rootNode) return;

  let cart = null;
  let busy = false;

  function node(tag, attrs, children) {
    const element = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (value === false || value === null || value === undefined) return;
      if (key === "className") {
        element.className = value;
      } else if (key === "text") {
        element.textContent = value;
      } else if (key === "onClick") {
        element.addEventListener("click", value);
      } else if (key === "disabled") {
        element.disabled = Boolean(value);
      } else {
        element.setAttribute(key, value === true ? "" : value);
      }
    });
    (children || []).forEach((child) => {
      if (child === null || child === undefined) return;
      element.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return element;
  }

  function renderLoading() {
    rootNode.replaceChildren(node("div", { className: "empty-state" }, [node("h2", { text: "Загрузка корзины" })]));
  }

  function renderError(message) {
    rootNode.replaceChildren(
      node("div", { className: "empty-state" }, [
        node("h2", { text: "Корзина временно недоступна" }),
        node("p", { text: message || "Не удалось загрузить корзину. Обновите страницу." }),
        node("button", { className: "primary-button", type: "button", onClick: () => loadCart(true) }, ["Повторить"]),
      ]),
    );
  }

  function renderEmpty() {
    rootNode.replaceChildren(
      node("div", { className: "empty-state" }, [
        node("h2", { text: "Корзина пуста" }),
        node("p", { text: "Добавьте товары из каталога, затем оформите демо-оплату." }),
        node("p", null, [node("a", { className: "primary-button", href: "/catalog/" }, ["Открыть каталог"])]),
      ]),
    );
  }

  function applyCart(nextCart) {
    cart = nextCart;
    window.Shop.updateCartCount(nextCart.count);
    renderCart();
  }

  async function mutateCart(method, item, quantity) {
    if (busy) return;
    busy = true;
    renderCart();
    try {
      const body = { product_id: item.id };
      if (quantity !== undefined) {
        body.quantity = quantity;
      }
      applyCart(
        await window.Shop.apiFetch("/api/cart/", {
          method,
          body,
        }),
      );
    } catch (error) {
      window.Shop.toast(error.message);
      renderCart();
    } finally {
      busy = false;
      renderCart();
    }
  }

  function renderItem(item) {
    return node("article", { className: "cart-item" }, [
      node("a", { href: item.url }, [node("img", { src: item.image, alt: item.name, loading: "lazy" })]),
      node("div", null, [
        node("h3", { text: item.name }),
        node("p", { text: `${item.brand} · ${item.category}` }),
        node("p", { text: `${item.price_display} ₽ за штуку` }),
      ]),
      node("div", { className: "cart-item-actions" }, [
        node("strong", { text: `${item.line_total_display} ₽` }),
        node("div", { className: "qty-control" }, [
          node(
            "button",
            {
              type: "button",
              "aria-label": "Уменьшить",
              disabled: busy,
              onClick: () => mutateCart("PATCH", item, item.quantity - 1),
            },
            ["-"],
          ),
          node("span", { text: item.quantity }),
          node(
            "button",
            {
              type: "button",
              "aria-label": "Увеличить",
              disabled: busy || item.quantity >= item.stock,
              onClick: () => mutateCart("PATCH", item, item.quantity + 1),
            },
            ["+"],
          ),
        ]),
        node(
          "button",
          {
            className: "ghost-button",
            type: "button",
            disabled: busy,
            onClick: () => mutateCart("DELETE", item),
          },
          ["Убрать"],
        ),
      ]),
    ]);
  }

  function renderCart() {
    if (!cart) {
      renderLoading();
      return;
    }

    if (!cart.items.length) {
      renderEmpty();
      return;
    }

    rootNode.replaceChildren(
      node("div", { className: "cart-layout" }, [
        node("div", { className: "cart-list" }, cart.items.map(renderItem)),
        node("aside", { className: "cart-summary" }, [
          node("div", { className: "cart-head" }, [
            node("h2", { text: "Итого" }),
            node("strong", { text: `${cart.count} шт.` }),
          ]),
          node("div", { className: "summary-total" }, [
            node("span", { text: "К оплате" }),
            node("strong", { text: `${cart.total_display} ₽` }),
          ]),
          node("a", { className: "primary-button wide", href: cart.checkout_url }, ["Оформить заказ"]),
          node("a", { className: "secondary-button wide", href: "/catalog/" }, ["Продолжить покупки"]),
        ]),
      ]),
    );
  }

  async function loadCart(showLoading) {
    if (showLoading) {
      renderLoading();
    }
    try {
      applyCart(await window.Shop.apiFetch("/api/cart/"));
    } catch (error) {
      window.Shop.toast(error.message);
      renderError(error.message);
    }
  }

  document.addEventListener("cart:updated", (event) => applyCart(event.detail));
  renderLoading();
  loadCart(false);
})();
