# eShop

Интернет-магазин электроники на Django с каталогом, корзиной, оформлением заказа, личным кабинетом и кастомной административной панелью.

## Стек

- Python, Django
- PostgreSQL
- Redis, Celery
- HTML, CSS, JavaScript
- React Islands для интерактивных частей каталога и личного кабинета
- Docker Compose

## Возможности

- Главная страница, каталог, карточка товара, корзина, оформление заказа, оплата, чек и страница заказа.
- Фильтрация каталога по реальным категориям, брендам и характеристикам из загруженных товаров.
- Автодогрузка товаров в каталоге при прокрутке.
- Сессионная корзина с изменением количества и удалением позиций.
- Оформление заказа для гостей и авторизованных пользователей.
- Регистрация с имитацией email-кода подтверждения, вход и восстановление пароля.
- Личный кабинет с настройками профиля, телефоном, адресными данными и историей заказов.
- Привязка гостевых заказов к аккаунту после регистрации по той же почте.
- Имитация оплаты, генерация чека и QR-кода для получения заказа.
- Кастомная админка `/control/`: товары, категории, контент, заказы, пользователи, роли сотрудников, системная и веб-аналитика.
- Сервисный режим для создания первого пользователя админки.
- Seed-команда с товарами, ценами, характеристиками и изображениями из публичной витрины BigGeek.

## Локальный запуск

```bash
docker compose up --build
```

После запуска:

- сайт: http://localhost:8000
- кастомная админка: http://localhost:8000/control/
- техническая Django admin: http://localhost:8000/admin/

В dev-сборке демо-данные загружаются автоматически командой `seed_demo` при старте web-контейнера.

## Production-запуск

Создайте `.env` на основе `.env.example` и задайте реальные значения:

- `SECRET_KEY`
- `DEBUG=0`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `POSTGRES_PASSWORD`
- `WEB_PORT`

Запуск:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Команды после первого запуска:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput
docker compose -f docker-compose.prod.yml exec web python manage.py seed_demo
```

Для первого входа в кастомную админку включите `CONTROL_SERVICE_MODE=1`, откройте `/control/service/`, создайте владельца, затем выключите сервисный режим обратно на `0`.

## Проверка

```bash
python3 manage.py check
python3 manage.py test shop
```

Через Docker:

```bash
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py test shop
```

## Репозиторий

В git не добавляются локальные секреты, база SQLite, пользовательские медиа, `staticfiles/`, временные документы и кеши Python. Статические изображения товаров лежат в `static/img/biggeek-products/` и нужны для демо-каталога.
