import React, { useEffect, useMemo, useRef, useState } from "https://esm.sh/react@18.2.0";
import { createRoot } from "https://esm.sh/react-dom@18.2.0/client";

const h = React.createElement;
const rootNode = document.getElementById("catalog-island");
const unique = (items) => Array.from(new Set(items.filter(Boolean)));

function initialFilters() {
  const source = rootNode?.dataset.initialQuery || window.location.search.replace(/^\?/, "");
  const params = new URLSearchParams(source);
  return {
    q: params.get("q") || "",
    category: params.get("category") || "",
    brand: params.getAll("brand"),
    color: params.getAll("color"),
    memory: params.getAll("memory"),
    price_min: params.get("price_min") || "",
    price_max: params.get("price_max") || "",
    in_stock: params.get("in_stock") === "1",
    sort: params.get("sort") || "featured",
    page: 1,
  };
}

function buildParams(filters, options = {}) {
  const params = new URLSearchParams();
  ["q", "category", "price_min", "price_max"].forEach((key) => {
    if (filters[key]) params.set(key, filters[key]);
  });
  if (filters.sort && filters.sort !== "featured") params.set("sort", filters.sort);
  ["brand", "color", "memory"].forEach((key) => {
    filters[key].forEach((value) => params.append(key, value));
  });
  if (filters.in_stock) params.set("in_stock", "1");
  if (options.includePage && filters.page && filters.page > 1) params.set("page", String(filters.page));
  return params;
}

function CheckGroup({ title, name, items, selected, onToggle }) {
  if (!items.length) return null;
  return h(
    "div",
    { className: "filter-group choice-filter" },
    h("strong", null, title),
    h(
      "div",
      { className: "filter-options" },
      items.map((item) =>
        h(
          "label",
          { className: "check-row", key: item },
          h("input", {
            type: "checkbox",
            checked: selected.includes(item),
            onChange: () => onToggle(name, item),
          }),
          h("span", null, item),
        ),
      ),
    ),
  );
}

function ProductCard({ product }) {
  const visibleAttrs = Object.entries(product.attributes || {})
    .filter(([key]) => !["URL", "Источник", "Раздел"].includes(key))
    .slice(0, 2);
  const note = product.name.includes("iPhone 17e")
    ? "Имеет недостаток в виде невозможности предустановки RuStore"
    : visibleAttrs.length
      ? visibleAttrs.map(([key, value]) => `${key}: ${value}`).join(" · ")
      : product.in_stock
        ? "Доступно к заказу"
        : "Скоро в продаже";

  return h(
    "article",
    { className: `product-card${product.in_stock ? "" : " is-soon"}` },
    h(
      "a",
      { className: "product-image", href: product.url },
      h("img", { src: product.image, alt: product.name, loading: "lazy", decoding: "async" }),
    ),
    h(
      "div",
      { className: "product-body" },
      h("a", { className: "product-title", href: product.url }, product.name),
      h("p", { className: "product-meta" }, `${product.brand} · ${product.category}`),
      h("p", { className: "product-note" }, note),
      h(
        "div",
        { className: "price-row" },
        h("strong", null, `от ${product.price_display} ₽`),
        product.old_price ? h("span", null, `${product.old_price_display} ₽`) : null,
        product.in_stock
          ? h(
              "button",
              {
                className: "card-cart-button",
                type: "button",
                "data-add-to-cart": product.id,
                "aria-label": "Добавить в корзину",
              },
              "+",
            )
          : h("span", { className: "soon-sale-pill" }, "Скоро в продаже"),
      ),
    ),
  );
}

function SkeletonGrid() {
  return h(
    "div",
    { className: "product-grid skeleton-grid", "aria-hidden": "true" },
    Array.from({ length: 12 }, (_, index) =>
      h(
        "article",
        { className: "product-card skeleton-card", key: index },
        h("div", { className: "skeleton-image" }),
        h(
          "div",
          { className: "product-body" },
          h("span", { className: "skeleton-line wide" }),
          h("span", { className: "skeleton-line" }),
          h("span", { className: "skeleton-line short" }),
        ),
      ),
    ),
  );
}

function LoadMoreSentinel({ pagination, loadingMore, sentinelRef }) {
  if (!pagination.total || pagination.pages <= 1) return null;
  return h(
    "div",
    { className: `load-more-sentinel${loadingMore ? " is-loading" : ""}`, ref: sentinelRef },
    loadingMore
      ? h("span", { className: "load-more-spinner", "aria-label": "Загружаем товары" })
      : pagination.has_next
        ? null
        : h("span", null, "Все товары показаны"),
  );
}

function CatalogApp() {
  const [filters, setFilters] = useState(initialFilters);
  const [meta, setMeta] = useState({ categories: [], brands: [], colors: [], memories: [] });
  const [products, setProducts] = useState([]);
  const [pagination, setPagination] = useState({ page: filters.page, pages: 1, total: 0 });
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const loadMoreRef = useRef(null);
  const sortLabels = {
    featured: "Начиная с популярных",
    price_asc: "Цена по возрастанию",
    price_desc: "Цена по убыванию",
    newest: "Сначала новые",
  };

  useEffect(() => {
    const panel = document.querySelector(".filters-panel");
    if (!panel) return undefined;

    let frame = 0;
    const syncHeight = () => {
      if (frame) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        const panelTop = Math.max(12, panel.getBoundingClientRect().top);
        const maxHeight = Math.max(280, window.innerHeight - panelTop - 12);
        panel.style.setProperty("--filters-max-height", `${Math.floor(maxHeight)}px`);
        frame = 0;
      });
    };

    syncHeight();
    window.addEventListener("scroll", syncHeight, { passive: true });
    window.addEventListener("resize", syncHeight);

    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", syncHeight);
      window.removeEventListener("resize", syncHeight);
      panel.style.removeProperty("--filters-max-height");
    };
  }, []);

  useEffect(() => {
    const productParams = buildParams(filters, { includePage: true });
    const metaParams = buildParams({ ...filters, page: 1 });
    const controller = new AbortController();
    const isNextPage = filters.page > 1;
    if (isNextPage) {
      setLoadingMore(true);
    } else {
      setLoading(true);
    }
    const timer = window.setTimeout(() => {
      const productQuery = productParams.toString();
      const metaQuery = metaParams.toString();
      Promise.all([
        window.Shop.apiFetch(`/api/products/?${productQuery}`, { signal: controller.signal }).then((data) => {
          const nextProducts = data.products || [];
          setProducts((current) => {
            if (!isNextPage) return nextProducts;
            const existingIds = new Set(current.map((product) => product.id));
            return [...current, ...nextProducts.filter((product) => !existingIds.has(product.id))];
          });
          setPagination(data.pagination || { page: filters.page, pages: 1, total: data.count || 0 });
        }),
        isNextPage
          ? Promise.resolve(null)
          : window.Shop.apiFetch(`/api/catalog-meta/?${metaQuery}`, { signal: controller.signal }).then(setMeta),
      ])
        .catch((error) => {
          if (error.name !== "AbortError") window.Shop.toast(error.message);
        })
        .finally(() => {
          if (isNextPage) {
            setLoadingMore(false);
          } else {
            setLoading(false);
          }
        });
      const nextUrl = `${window.location.pathname}${metaParams.toString() ? `?${metaParams.toString()}` : ""}`;
      window.history.replaceState({}, "", nextUrl);
    }, 120);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [filters]);

  useEffect(() => {
    const node = loadMoreRef.current;
    if (!node || loading || loadingMore || !pagination.has_next) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        setFilters((current) => {
          const nextPage = pagination.next_page || current.page + 1;
          if (!nextPage || current.page >= nextPage) return current;
          return { ...current, page: nextPage };
        });
      },
      { rootMargin: "520px 0px" },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [loading, loadingMore, pagination.has_next, pagination.next_page]);

  const priceBounds = useMemo(() => {
    if (!products.length) return { min: meta.price_min, max: meta.price_max };
    const currentPrices = products.map((product) => Number(product.price)).filter(Boolean);
    const ceilingPrices = products.map((product) => Number(product.old_price || product.price)).filter(Boolean);
    return {
      min: currentPrices.length ? Math.min(...currentPrices) : meta.price_min,
      max: ceilingPrices.length ? Math.max(...ceilingPrices) : meta.price_max,
    };
  }, [products, meta.price_min, meta.price_max]);

  function setField(name, value) {
    setFilters((current) => ({ ...current, [name]: value, page: name === "page" ? value : 1 }));
  }

  function toggleArray(name, value) {
    setFilters((current) => {
      const exists = current[name].includes(value);
      return {
        ...current,
        [name]: exists ? current[name].filter((item) => item !== value) : [...current[name], value],
        page: 1,
      };
    });
  }

  const isInitialLoading = loading && !products.length;
  const loadedCount = products.length;
  const totalCount = pagination.total || loadedCount;

  return h(
    "div",
    { className: "catalog-layout" },
      h(
        "aside",
        { className: "filters-panel" },
        h(
          "div",
          { className: "filters-head" },
        h("h2", null, "Фильтры"),
      ),
      h(
        "div",
        { className: "filter-group" },
        h(
          "label",
          null,
          h("span", null, "Категория"),
          h(
            "select",
            { value: filters.category, onChange: (event) => setField("category", event.target.value) },
            h("option", { value: "" }, "Все категории"),
            meta.categories.map((category) => h("option", { value: category.slug, key: category.slug }, category.name)),
          ),
        ),
      ),
      h(CheckGroup, {
        title: "Бренд",
        name: "brand",
        items: unique(meta.brands || []),
        selected: filters.brand,
        onToggle: toggleArray,
      }),
      h(
        "div",
        { className: "filter-group" },
        h("strong", null, "Цена"),
        h(
          "div",
          { className: "price-fields" },
          h("input", {
            inputMode: "numeric",
            placeholder: priceBounds.min ? `от ${priceBounds.min}` : "от",
            value: filters.price_min,
            onChange: (event) => setField("price_min", event.target.value.replace(/\D/g, "")),
          }),
          h("input", {
            inputMode: "numeric",
            placeholder: priceBounds.max ? `до ${priceBounds.max}` : "до",
            value: filters.price_max,
            onChange: (event) => setField("price_max", event.target.value.replace(/\D/g, "")),
          }),
        ),
      ),
      h(CheckGroup, {
        title: "Цвет",
        name: "color",
        items: unique(meta.colors || []),
        selected: filters.color,
        onToggle: toggleArray,
      }),
      h(CheckGroup, {
        title: "Объем встроенной памяти",
        name: "memory",
        items: unique(meta.memories || []),
        selected: filters.memory,
        onToggle: toggleArray,
      }),
      h(
        "div",
        { className: "filter-group availability-group" },
        h(
          "label",
          { className: "check-row" },
          h("input", {
            type: "checkbox",
            checked: filters.in_stock,
            onChange: (event) => setField("in_stock", event.target.checked),
          }),
          h("span", null, "Доступные к заказу"),
        ),
      ),
    ),
    h(
      "section",
      { className: "catalog-results" },
      h(
        "div",
        { className: "products-head" },
        h(
          "div",
          null,
          h("h2", null, loading ? "Загрузка" : sortLabels[filters.sort] || "Начиная с популярных"),
          h("p", null, loading ? "Обновляем витрину" : `Показано ${loadedCount} из ${totalCount} товаров`),
        ),
        h(
          "select",
          { className: "sort-select", value: filters.sort, onChange: (event) => setField("sort", event.target.value) },
          h("option", { value: "featured" }, "Сначала популярные"),
          h("option", { value: "price_asc" }, "Цена по возрастанию"),
          h("option", { value: "price_desc" }, "Цена по убыванию"),
          h("option", { value: "newest" }, "Сначала новые"),
        ),
      ),
      isInitialLoading
        ? h(SkeletonGrid)
        : !loading && !products.length
          ? h("div", { className: "empty-state" }, h("h3", null, "Ничего не найдено"), h("p", null, "Попробуйте убрать часть фильтров."))
          : h(
              React.Fragment,
              null,
              h(
                "div",
                { className: `product-grid${loading && !loadingMore ? " is-loading" : ""}` },
                products.map((product) => h(ProductCard, { product, key: product.id })),
              ),
              h(LoadMoreSentinel, { pagination, loadingMore, sentinelRef: loadMoreRef }),
            ),
    ),
  );
}

if (rootNode) {
  createRoot(rootNode).render(h(CatalogApp));
}
