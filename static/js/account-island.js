import React, { useEffect, useMemo, useState } from "https://esm.sh/react@18.2.0";
import { createRoot } from "https://esm.sh/react-dom@18.2.0/client";

const h = React.createElement;
const rootNode = document.getElementById("account-island");

const emptyProfileForm = {
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  city: "",
  address: "",
  marketing_consent: false,
};

function formFromUser(user) {
  return {
    first_name: user.first_name || "",
    last_name: user.last_name || "",
    email: user.email || "",
    phone: user.phone || "",
    city: user.city || "",
    address: user.address || "",
    marketing_consent: Boolean(user.marketing_consent),
  };
}

function AccountApp() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("orders");
  const [selectedOrderId, setSelectedOrderId] = useState(null);
  const [profileForm, setProfileForm] = useState(emptyProfileForm);
  const [profileDirty, setProfileDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState({});

  async function loadAccount(options = {}) {
    try {
      const account = await window.Shop.apiFetch("/api/account/");
      setData(account);
      if (!options.preserveForm && !profileDirty) {
        setProfileForm(formFromUser(account.user));
      }
      if (!selectedOrderId && account.orders.length) {
        setSelectedOrderId(account.orders[0].id);
      }
    } catch (error) {
      window.Shop.toast(error.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAccount();
  }, []);

  useEffect(() => {
    const hasProcessingOrder = data && data.orders.some((order) => order.payment_status === "processing");
    if (!hasProcessingOrder) return undefined;
    const timer = window.setInterval(() => loadAccount({ preserveForm: true }), 4000);
    return () => window.clearInterval(timer);
  }, [data]);

  const selectedOrder = useMemo(() => {
    if (!data || !data.orders.length) return null;
    return data.orders.find((order) => order.id === selectedOrderId) || data.orders[0];
  }, [data, selectedOrderId]);

  function updateProfileField(name, value) {
    setProfileForm((current) => ({ ...current, [name]: value }));
    setProfileDirty(true);
    setErrors((current) => ({ ...current, [name]: "" }));
  }

  async function saveProfile(event) {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    try {
      const account = await window.Shop.apiFetch("/api/account/", {
        method: "PATCH",
        body: profileForm,
      });
      setData(account);
      setProfileForm(formFromUser(account.user));
      setProfileDirty(false);
      window.Shop.toast("Профиль сохранен");
    } catch (error) {
      if (error.data && error.data.errors) {
        setErrors(error.data.errors);
      } else {
        window.Shop.toast(error.message);
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading || !data) {
    return h("div", { className: "empty-state" }, h("h2", null, "Загрузка кабинета"));
  }

  return h(
    "div",
    { className: "account-layout account-dashboard" },
    h(AccountSidebar, { data, activeTab, setActiveTab }),
    h(
      "div",
      { className: "account-workspace" },
      h(AccountTabs, { activeTab, setActiveTab, ordersCount: data.orders.length }),
      activeTab === "settings"
        ? h(ProfileSettings, { profileForm, updateProfileField, saveProfile, saving, errors, username: data.user.username, dateJoined: data.user.date_joined })
        : h(OrdersHistory, { orders: data.orders, selectedOrder, setSelectedOrderId }),
    ),
  );
}

function AccountSidebar({ data, activeTab, setActiveTab }) {
  return h(
    "aside",
    { className: "account-profile account-summary" },
    h("div", { className: "account-avatar", "aria-hidden": "true" }, (data.user.first_name || data.user.username || "e").slice(0, 1).toUpperCase()),
    h("h2", null, data.user.name),
    h("p", { className: "account-muted break-word" }, data.user.email || "Email не указан"),
    h("dl", { className: "profile-facts" },
      h("div", null, h("dt", null, "Телефон"), h("dd", null, data.user.phone || "Не указан")),
      h("div", null, h("dt", null, "Город"), h("dd", null, data.user.city || "Не указан")),
      h("div", null, h("dt", null, "Покупатель с"), h("dd", null, data.user.date_joined)),
    ),
    h(
      "div",
      { className: "account-stat-grid" },
      h("div", null, h("strong", null, data.stats.orders_count), h("span", null, "заказов")),
      h("div", null, h("strong", null, `${data.stats.paid_total_display} ₽`), h("span", null, "оплачено")),
    ),
    h(
      "div",
      { className: "account-side-actions" },
      h("button", { className: activeTab === "orders" ? "is-active" : "", type: "button", onClick: () => setActiveTab("orders") }, "История заказов"),
      h("button", { className: activeTab === "settings" ? "is-active" : "", type: "button", onClick: () => setActiveTab("settings") }, "Настройки профиля"),
    ),
  );
}

function AccountTabs({ activeTab, setActiveTab, ordersCount }) {
  return h(
    "div",
    { className: "account-tabs", role: "tablist", "aria-label": "Разделы личного кабинета" },
    h("button", { type: "button", className: activeTab === "orders" ? "is-active" : "", onClick: () => setActiveTab("orders") }, `Заказы ${ordersCount ? `· ${ordersCount}` : ""}`),
    h("button", { type: "button", className: activeTab === "settings" ? "is-active" : "", onClick: () => setActiveTab("settings") }, "Настройки"),
  );
}

function ProfileSettings({ profileForm, updateProfileField, saveProfile, saving, errors, username, dateJoined }) {
  return h(
    "section",
    { className: "profile-settings" },
    h(
      "div",
      { className: "account-panel-head" },
      h("div", null, h("h2", null, "Данные профиля"), h("p", null, "Эти данные используются для оформления заказов и связи по выдаче.")),
      h("span", { className: "status-pill muted" }, `Логин: ${username}`),
    ),
    h(
      "form",
      { className: "profile-form", onSubmit: saveProfile },
      h(ProfileInput, { label: "Имя", name: "first_name", value: profileForm.first_name, error: errors.first_name, onChange: updateProfileField }),
      h(ProfileInput, { label: "Фамилия", name: "last_name", value: profileForm.last_name, error: errors.last_name, onChange: updateProfileField }),
      h(ProfileInput, { label: "Email", name: "email", value: profileForm.email, error: errors.email, onChange: updateProfileField, type: "email" }),
      h(ProfileInput, { label: "Телефон", name: "phone", value: profileForm.phone, error: errors.phone, onChange: updateProfileField, type: "tel", placeholder: "+7 700 000 00 00" }),
      h(ProfileInput, { label: "Город", name: "city", value: profileForm.city, error: errors.city, onChange: updateProfileField }),
      h(ProfileInput, { label: "Адрес для самовывоза/доставки", name: "address", value: profileForm.address, error: errors.address, onChange: updateProfileField }),
      h(
        "label",
        { className: "profile-checkbox" },
        h("input", {
          type: "checkbox",
          checked: profileForm.marketing_consent,
          onChange: (event) => updateProfileField("marketing_consent", event.target.checked),
        }),
        h("span", null, "Можно отправлять мне статусы, чеки и сервисные уведомления по email/телефону"),
      ),
      h(
        "div",
        { className: "profile-form-footer" },
        h("p", null, `Аккаунт создан: ${dateJoined}`),
        h("button", { className: "primary-button", type: "submit", disabled: saving }, saving ? "Сохраняем..." : "Сохранить профиль"),
      ),
    ),
  );
}

function ProfileInput({ label, name, value, error, onChange, type = "text", placeholder = "" }) {
  return h(
    "label",
    { className: "profile-field" },
    h("span", null, label),
    h("input", {
      type,
      name,
      value,
      placeholder,
      onChange: (event) => onChange(name, event.target.value),
    }),
    error ? h("small", { className: "form-error" }, error) : null,
  );
}

function OrdersHistory({ orders, selectedOrder, setSelectedOrderId }) {
  if (!orders.length) {
    return h(
      "div",
      { className: "empty-state account-empty" },
      h("h2", null, "Заказов пока нет"),
      h("p", null, "После демо-оплаты здесь появится история, чек и QR-код для получения."),
      h("p", null, h("a", { className: "primary-button", href: "/catalog/" }, "Выбрать товары")),
    );
  }

  return h(
    "section",
    { className: "orders-history" },
    h(
      "div",
      { className: "orders-list" },
      orders.map((order) =>
        h(OrderSummary, {
          order,
          key: order.id,
          selected: selectedOrder && selectedOrder.id === order.id,
          onSelect: () => setSelectedOrderId(order.id),
        }),
      ),
    ),
    h(OrderDetails, { order: selectedOrder }),
  );
}

function OrderSummary({ order, selected, onSelect }) {
  return h(
    "button",
    { className: `order-summary ${selected ? "is-selected" : ""}`, type: "button", onClick: onSelect },
    h("span", null, order.number),
    h("strong", null, `${order.total_display} ₽`),
    h("small", null, order.created_at),
    h("em", { className: order.status === "ready" ? "ready" : "" }, order.status_label),
  );
}

function OrderDetails({ order }) {
  if (!order) return null;
  const canPay = ["waiting", "failed"].includes(order.payment_status);
  return h(
    "article",
    { className: "order-card order-details-card" },
    h(
      "div",
      { className: "order-head" },
      h("div", null, h("h3", null, `Заказ ${order.number}`), h("div", { className: "order-meta" }, h("span", null, order.created_at), h("span", null, `${order.total_display} ₽`))),
      h("span", { className: `order-status ${order.status === "ready" ? "ready" : ""}` }, order.status_label),
    ),
    h(
      "div",
      { className: "order-payment-row" },
      h("span", null, `Оплата: ${order.payment_label}`),
      order.paid_at ? h("span", null, `Оплачен: ${order.paid_at}`) : null,
      canPay ? h("a", { className: "secondary-button", href: order.payment_url }, "Перейти к оплате") : null,
    ),
    h(
      "ul",
      { className: "order-items" },
      order.items.map((item, index) =>
        h(
          "li",
          { key: `${item.name}-${index}` },
          h("span", null, `${item.name} x ${item.quantity}`),
          h("strong", null, `${item.line_total_display} ₽`),
        ),
      ),
    ),
    order.qr_svg
      ? h(
          "div",
          { className: "qr-row" },
          h("div", { className: "qr-code", dangerouslySetInnerHTML: { __html: order.qr_svg } }),
          h("div", null, h("h4", null, `Код выдачи: ${order.pickup_code}`), h("p", null, "Покажите QR-код на пункте выдачи, чтобы получить заказ.")),
        )
      : h("div", { className: "order-note" }, "QR-код появится после успешной демо-оплаты и подготовки заказа."),
    h("p", { className: "order-link-row" }, h("a", { className: "secondary-button", href: order.url }, "Открыть чек и QR")),
  );
}

if (rootNode) {
  createRoot(rootNode).render(h(AccountApp));
}
