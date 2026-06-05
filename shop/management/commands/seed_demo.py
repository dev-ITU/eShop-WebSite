import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html import unescape
from http.client import InvalidURL
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand

from shop.models import Category, Product


BASE_URL = "https://biggeek.ru"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
MAX_PRODUCTS_DEFAULT = 140
MAX_ATTRIBUTES = 36
HIDDEN_ATTRIBUTE_KEYS = {"url", "источник", "раздел", "source", "source url"}


@dataclass(frozen=True)
class CatalogSource:
    category_slug: str
    url: str
    pages: int
    limit: int


CATEGORIES = [
    ("new", "Новиночки", "Свежие позиции из публичной витрины BigGeek", 10),
    ("accessories", "Аксессуары", "Кабели, зарядки, чехлы и мелкая электроника", 20),
    ("storage", "Накопители", "SSD, флешки, карты памяти и диски", 30),
    ("home", "Для дома", "Умный дом, свет, зонты и бытовые гаджеты", 40),
    ("smartphones", "Смартфоны", "Смартфоны из актуальных категорий BigGeek", 50),
    ("hobby", "Хобби", "Игровые консоли, игры, LEGO и коллекционные товары", 60),
]

CATALOG_SOURCES = [
    CatalogSource("new", f"{BASE_URL}/catalog/new", 2, 18),
    CatalogSource("storage", f"{BASE_URL}/catalog/karty-pamyati-zhestkie-diski-i-diskovody", 2, 22),
    CatalogSource("smartphones", f"{BASE_URL}/catalog/smartfony", 2, 22),
    CatalogSource("smartphones", f"{BASE_URL}/catalog/iphone-17e", 1, 8),
    CatalogSource("accessories", f"{BASE_URL}/catalog/aksessuary", 2, 18),
    CatalogSource("accessories", f"{BASE_URL}/catalog/perehodniki-i-adaptery-pitaniya", 1, 14),
    CatalogSource("home", f"{BASE_URL}/catalog/dlya-doma", 2, 20),
    CatalogSource("home", f"{BASE_URL}/catalog/zonty", 1, 14),
    CatalogSource("hobby", f"{BASE_URL}/catalog/mediapleery-i-igrovye-konsoli", 1, 18),
    CatalogSource("hobby", f"{BASE_URL}/catalog/konstruktory-lego", 1, 18),
]

KNOWN_BRANDS = [
    "Apple",
    "Samsung",
    "Xiaomi",
    "HONOR",
    "BLUNT",
    "SanDisk",
    "Benks",
    "VLP",
    "elago",
    "MOFT",
    "Yeelight",
    "Yandex",
    "LEGO",
    "Sony",
    "Microsoft",
    "MSI",
    "Lenovo",
    "Nintendo",
    "Spigen",
    "Cabletime",
    "Satechi",
    "PLAID",
    "Plaud",
    "PlayStation",
    "Cinereplicas",
    "DJI",
    "Google",
    "Anker",
    "Baseus",
    "UGREEN",
    "Deppa",
    "Nothing",
    "OnePlus",
    "Huawei",
    "Dreame",
    "Roborock",
]


def absolute_url(value):
    if not value:
        return ""
    if value.startswith("//"):
        value = f"https:{value}"
    else:
        value = urljoin(BASE_URL, value)
    parts = urlsplit(value)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            quote(parts.path, safe="/%:@"),
            quote(parts.query, safe="=&?/%:@+,"),
            parts.fragment,
        )
    )


def clean_text(value):
    value = unescape(str(value or ""))
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def truncate_text(value, limit):
    value = clean_text(value)
    if len(value) <= limit:
        return value
    by_sentence = value[:limit].rsplit(".", 1)[0].strip()
    if len(by_sentence) > 140:
        return f"{by_sentence}."
    return f"{value[: limit - 3].strip()}..."


def parse_money(value):
    if value in (None, ""):
        return None
    digits = re.sub(r"[^\d]", "", str(value))
    if not digits:
        return None
    try:
        return Decimal(digits)
    except (InvalidOperation, TypeError):
        return None


def product_slug(product_url):
    return urlparse(product_url).path.rstrip("/").split("/")[-1]


def is_allowed_product(product_url):
    slug = product_slug(product_url)
    return bool(slug) and not slug.startswith("service-")


def page_url(url, page):
    if page == 1:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}page={page}"


def request(url, timeout=35):
    return Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": USER_AGENT,
        },
    )


def fetch_text(url, timeout=35):
    with urlopen(request(url, timeout), timeout=timeout) as response:
        encoding = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(encoding, "replace")


def fetch_bytes(url, timeout=35):
    req = Request(
        url,
        headers={
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(req, timeout=timeout) as response:
        return response.read()


def meta_content(page_html, target):
    for match in re.finditer(r"<meta\s+([^>]+)>", page_html, flags=re.I):
        attrs = dict(re.findall(r'([\w:-]+)=["\'](.*?)["\']', match.group(1)))
        if attrs.get("property") == target or attrs.get("name") == target:
            return clean_text(attrs.get("content"))
    return ""


def extract_catalog_cards(page_html, source_category_slug):
    cards = {}
    for chunk in page_html.split('<div class="catalog-card">')[1:]:
        href_match = re.search(r'href=["\'](/products/[^"\']+)["\']', chunk)
        if not href_match:
            continue
        product_url = absolute_url(href_match.group(1))
        if not is_allowed_product(product_url):
            continue

        title_match = re.search(
            r'class=["\']catalog-card__title[^"\']*["\'][^>]*>(.*?)</a>',
            chunk,
            flags=re.S,
        )
        image_match = re.search(
            r'<img[^>]+src=["\']([^"\']+)["\'][^>]+alt=["\']([^"\']*)["\']',
            chunk,
            flags=re.S,
        )
        price_match = re.search(
            r'<b[^>]+class=["\']cart-modal-count["\'][^>]*>(.*?)</b>',
            chunk,
            flags=re.S,
        )
        old_price_match = re.search(r'class=["\']old-price["\'][^>]*>(.*?)</span>', chunk, flags=re.S)
        note_match = re.search(
            r'class=["\']catalog-card__subname["\'][^>]*>(.*?)</div>',
            chunk,
            flags=re.S,
        )

        title = clean_text(title_match.group(1) if title_match else "")
        image_url = absolute_url(image_match.group(1)) if image_match else ""
        image_alt = clean_text(image_match.group(2) if image_match else "")
        cards[product_url] = {
            "title": title or image_alt,
            "image_url": image_url,
            "price": parse_money(price_match.group(1) if price_match else ""),
            "old_price": parse_money(old_price_match.group(1) if old_price_match else ""),
            "note": clean_text(note_match.group(1) if note_match else ""),
            "source_category_slug": source_category_slug,
        }
    return cards


def find_product_json(value):
    if isinstance(value, list):
        for item in value:
            found = find_product_json(item)
            if found:
                return found
        return None
    if not isinstance(value, dict):
        return None

    item_type = value.get("@type")
    if isinstance(item_type, list):
        is_product = "Product" in item_type
    else:
        is_product = item_type == "Product"
    if is_product:
        return value

    graph = value.get("@graph")
    if graph:
        return find_product_json(graph)
    for item in value.values():
        found = find_product_json(item)
        if found:
            return found
    return None


def extract_ld_product(page_html):
    for raw in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page_html,
        flags=re.S | re.I,
    ):
        try:
            payload = json.loads(unescape(raw).strip())
        except json.JSONDecodeError:
            continue
        product = find_product_json(payload)
        if product:
            return product
    return {}


def extract_properties(page_html):
    match = re.search(
        r'<script[^>]+id=["\']product-properties-json["\'][^>]*>(.*?)</script>',
        page_html,
        flags=re.S | re.I,
    )
    if not match:
        return {}
    try:
        return json.loads(unescape(match.group(1)).strip())
    except json.JSONDecodeError:
        return {}


def is_public_attribute(key, value):
    key_text = clean_text(key)
    value_text = clean_text(value)
    if not key_text or not value_text:
        return False
    if key_text.lower() in HIDDEN_ATTRIBUTE_KEYS or "url" in key_text.lower():
        return False
    if "http://" in value_text.lower() or "https://" in value_text.lower():
        return False
    return True


def add_attribute(attributes, key, value):
    key = clean_text(key)
    value = clean_text(value)
    if not is_public_attribute(key, value) or key in attributes:
        return
    attributes[key] = truncate_text(value, 180)


def flatten_attributes(properties, fallback_note=""):
    attributes = {}
    picker = properties.get("variantCharacteristicPicker") or {}
    for characteristic in picker.get("characteristics") or []:
        values = characteristic.get("values") or []
        selected = next((item for item in values if item.get("isSelected")), None)
        if selected:
            add_attribute(attributes, characteristic.get("name"), selected.get("name") or selected.get("label"))

    for group_items in (properties.get("featureGroups") or {}).values():
        for item in group_items or []:
            add_attribute(attributes, item.get("name"), item.get("value"))
            if len(attributes) >= MAX_ATTRIBUTES:
                break
        if len(attributes) >= MAX_ATTRIBUTES:
            break

    if fallback_note:
        add_attribute(attributes, "Особенность", fallback_note)
    return attributes


def selected_offer_price(ld_product):
    offers = ld_product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    return parse_money(offers.get("price") or offers.get("lowPrice"))


def selected_availability(ld_product):
    offers = ld_product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    return str(offers.get("availability") or "")


def selected_compare_price(properties):
    picker = properties.get("variantCharacteristicPicker") or {}
    price = parse_money(picker.get("comparePrice"))
    if price:
        return price
    for variant in picker.get("variantsMatrix") or []:
        price = parse_money(variant.get("comparePrice"))
        if price:
            return price
    return None


def selected_variant_price(properties):
    picker = properties.get("variantCharacteristicPicker") or {}
    price = parse_money(picker.get("price"))
    if price:
        return price
    for variant in picker.get("variantsMatrix") or []:
        price = parse_money(variant.get("price"))
        if price:
            return price
    return None


def extract_overview(page_html):
    start = page_html.find('id="product-overview"')
    if start == -1:
        return ""
    inner_marker = page_html.find("tabs-content__inner", start)
    if inner_marker == -1:
        return ""
    inner_start = page_html.find(">", inner_marker)
    if inner_start == -1:
        return ""
    inner_start += 1
    end_candidates = [
        page_html.find('id="product-characteristics"', inner_start),
        page_html.find('id="product-questions"', inner_start),
        page_html.find("</section>", inner_start),
    ]
    end_candidates = [candidate for candidate in end_candidates if candidate != -1]
    if not end_candidates:
        return ""
    return truncate_text(page_html[inner_start : min(end_candidates)], 760)


def extract_brand(name, ld_brand):
    if isinstance(ld_brand, dict):
        brand = clean_text(ld_brand.get("name"))
        if brand:
            return brand[:100]
    if isinstance(ld_brand, str) and ld_brand.strip():
        return clean_text(ld_brand)[:100]

    name_lower = name.lower()
    for brand in KNOWN_BRANDS:
        if brand.lower() in name_lower:
            return brand[:100]
    return clean_text(name.split(" ", 1)[0])[:100] or "BigGeek"


def normalize_memory(value):
    matches = re.findall(r"(\d+(?:[.,]\d+)?)\s*(тб|tb|гб|gb)", value or "", flags=re.I)
    if not matches:
        return ""
    amount, unit = matches[-1]
    unit = "ТБ" if unit.lower() in {"тб", "tb"} else "ГБ"
    return f"{amount.replace(',', '.')} {unit}"


def extract_memory(name, attributes):
    for key, value in attributes.items():
        if "пам" in key.lower() or "накоп" in key.lower() or "емкость" in key.lower():
            memory = normalize_memory(value)
            if memory:
                return memory
    return normalize_memory(name)


def extract_color(name, attributes):
    for key, value in attributes.items():
        if "цвет" in key.lower():
            return clean_text(value).replace("«", "").replace("»", "")[:80]
    bracket_match = re.search(r"\(([^)]*(?:black|white|orange|pink|silver|blue|green|gray|ч[её]рн|бел|роз|сер|син|зел)[^)]*)\)", name, flags=re.I)
    if bracket_match:
        return clean_text(bracket_match.group(1))[:80]
    return ""


def extract_screen_size(attributes):
    for key, value in attributes.items():
        key_lower = key.lower()
        if "диагональ" in key_lower or key_lower == "экран":
            return clean_text(value)[:40]
    return ""


def guess_category(name, source_category_slug, attributes):
    category_slugs = {slug for slug, *_ in CATEGORIES}
    if source_category_slug in category_slugs:
        return source_category_slug

    haystack = f"{name} {' '.join(attributes.values())}".lower()
    storage_markers = [
        "ssd",
        "накопител",
        "флеш",
        "карта памяти",
        "microsd",
        "жестк",
        "диск",
        "drive",
    ]
    accessory_markers = [
        "чехол",
        "кабель",
        "адаптер",
        "заряд",
        "держател",
        "magsafe",
        "стекло",
        "пленка",
        "ремешок",
        "hub",
        "dock",
    ]
    home_markers = [
        "ламп",
        "свет",
        "умн",
        "пылесос",
        "зонт",
        "humidifier",
        "vacuum",
        "umbrella",
        "bulb",
    ]
    hobby_markers = [
        "lego",
        "конструктор",
        "игр",
        "playstation",
        "ps5",
        "nintendo",
        "console",
        "gaming",
        "модель",
        "коллекцион",
    ]
    smartphone_markers = ["смартфон", "iphone", "galaxy", "pixel", "honor", "xiaomi", "oneplus"]

    if any(marker in haystack for marker in storage_markers):
        return "storage"
    if any(marker in haystack for marker in accessory_markers):
        return "accessories"
    if any(marker in haystack for marker in home_markers):
        return "home"
    if any(marker in haystack for marker in hobby_markers):
        return "hobby"
    if any(marker in haystack for marker in smartphone_markers):
        return "smartphones"
    if source_category_slug in category_slugs:
        return source_category_slug
    return "accessories"


def image_from_ld(ld_product):
    image = ld_product.get("image") or ""
    if isinstance(image, list):
        image = image[0] if image else ""
    return absolute_url(str(image))


def safe_image_name(slug, image_url):
    suffix = Path(urlparse(image_url).path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    safe_slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", slug).strip("-")[:180] or "product"
    return f"{safe_slug}{suffix}"


def download_image(image_url, slug):
    if not image_url:
        return ""
    filename = safe_image_name(slug, image_url)
    target_dir = settings.BASE_DIR / "static" / "img" / "biggeek-products"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    if target.exists() and target.stat().st_size > 0:
        return f"img/biggeek-products/{filename}"

    data = fetch_bytes(absolute_url(image_url))
    if len(data) < 256:
        return ""
    target.write_bytes(data)
    return f"img/biggeek-products/{filename}"


def extract_product(product_url, fallback):
    page_html = fetch_text(product_url)
    ld_product = extract_ld_product(page_html)
    properties = extract_properties(page_html)
    attributes = flatten_attributes(properties, fallback.get("note", ""))

    name = clean_text(ld_product.get("name")) or fallback.get("title") or meta_content(page_html, "og:title")
    overview = extract_overview(page_html)
    description = (
        overview
        or truncate_text(ld_product.get("description") or "", 760)
        or truncate_text(meta_content(page_html, "og:description"), 760)
        or "Товар импортирован из публичной витрины BigGeek."
    )
    price = selected_variant_price(properties) or selected_offer_price(ld_product) or fallback.get("price")
    old_price = selected_compare_price(properties) or fallback.get("old_price")
    if old_price and price and old_price <= price:
        old_price = None

    image_url = image_from_ld(ld_product) or fallback.get("image_url") or meta_content(page_html, "og:image")
    brand = extract_brand(name, ld_product.get("brand"))
    category_slug = guess_category(name, fallback.get("source_category_slug"), attributes)
    color = extract_color(name, attributes)
    memory = extract_memory(name, attributes)
    availability = selected_availability(ld_product)

    return {
        "slug": product_slug(product_url),
        "name": name[:220],
        "category_slug": category_slug,
        "brand": brand,
        "description": description,
        "price": price,
        "old_price": old_price,
        "image_url": image_url,
        "stock": 0 if "OutOfStock" in availability else None,
        "color": color,
        "memory": memory,
        "screen_size": extract_screen_size(attributes),
        "attributes": attributes,
    }


def collect_catalog_products(stdout, verbosity):
    ordered_urls = []
    cards_by_url = {}

    for source in CATALOG_SOURCES:
        added_from_source = 0
        for page in range(1, source.pages + 1):
            if added_from_source >= source.limit:
                break
            url = page_url(source.url, page)
            try:
                page_html = fetch_text(url)
            except (HTTPError, URLError, TimeoutError) as exc:
                stdout.write(f"BigGeek page skipped: {url} ({exc})")
                continue

            cards = extract_catalog_cards(page_html, source.category_slug)
            if verbosity >= 2:
                stdout.write(f"BigGeek: {url} -> {len(cards)} product cards")

            for product_url, card in cards.items():
                if added_from_source >= source.limit:
                    break
                existing = cards_by_url.get(product_url)
                if existing:
                    continue
                ordered_urls.append(product_url)
                cards_by_url[product_url] = card
                added_from_source += 1
            time.sleep(0.08)

    return ordered_urls, cards_by_url


class Command(BaseCommand):
    help = "Scrape categories and full product cards from public BigGeek pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-products",
            type=int,
            default=MAX_PRODUCTS_DEFAULT,
            help=f"Maximum number of product detail pages to import. Default: {MAX_PRODUCTS_DEFAULT}.",
        )
        parser.add_argument(
            "--no-images",
            action="store_true",
            help="Do not download product images; keep existing local image paths when possible.",
        )

    def handle(self, *args, **options):
        category_map = {}
        Category.objects.exclude(slug__in=[slug for slug, *_ in CATEGORIES]).update(is_active=False)
        for slug, name, description, sort_order in CATEGORIES:
            category, _ = Category.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "description": description,
                    "sort_order": sort_order,
                    "is_active": True,
                },
            )
            category_map[slug] = category

        ordered_urls, cards_by_url = collect_catalog_products(self.stdout, options["verbosity"])
        max_products = max(1, options["max_products"])
        imported_slugs = []
        failed = 0

        for index, product_url in enumerate(ordered_urls[:max_products], 1):
            fallback = cards_by_url[product_url]
            try:
                product_data = extract_product(product_url, fallback)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                failed += 1
                self.stdout.write(f"Product skipped: {product_url} ({exc})")
                continue

            slug = product_data["slug"]
            price = product_data["price"]
            if not slug or not product_data["name"] or not price:
                failed += 1
                self.stdout.write(f"Product skipped: {product_url} (missing name, slug or price)")
                continue

            existing = Product.objects.filter(slug=slug).first()
            image_path = existing.image if existing else ""
            if not options["no_images"]:
                try:
                    image_path = download_image(product_data["image_url"], slug) or image_path
                except (HTTPError, URLError, TimeoutError, InvalidURL) as exc:
                    self.stdout.write(f"Image skipped: {product_data['image_url']} ({exc})")

            if not image_path:
                failed += 1
                self.stdout.write(f"Product skipped: {product_url} (image unavailable)")
                continue

            category = category_map[product_data["category_slug"]]
            stock = product_data["stock"]
            if stock is None:
                stock = 5 + (index % 17)

            Product.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": product_data["name"],
                    "category": category,
                    "brand": product_data["brand"],
                    "price": price,
                    "old_price": product_data["old_price"],
                    "image": image_path,
                    "stock": stock,
                    "color": product_data["color"],
                    "memory": product_data["memory"],
                    "screen_size": product_data["screen_size"],
                    "is_featured": index <= 18,
                    "is_active": True,
                    "attributes": product_data["attributes"],
                    "description": product_data["description"],
                },
            )
            imported_slugs.append(slug)
            if options["verbosity"] >= 2:
                self.stdout.write(f"Imported {index}: {product_data['name']}")
            time.sleep(0.08)

        if imported_slugs:
            Product.objects.exclude(slug__in=imported_slugs).update(is_active=False, is_featured=False)
        else:
            self.stdout.write(self.style.WARNING("No products were imported; existing products were left untouched."))
            return

        with_attributes = Product.objects.filter(is_active=True).exclude(attributes={}).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(category_map)} categories and {len(imported_slugs)} products "
                f"({with_attributes} with detailed attributes, {failed} skipped)."
            )
        )
