# Deployment

Инструкция описывает публикацию проекта через Docker Compose. Локальные секреты должны храниться только в `.env`; файл `.env` игнорируется git.

## Требования

- Docker и Docker Compose
- Домен, направленный на сервер
- Reverse proxy с HTTPS, например Caddy
- Открытый внутренний порт из `WEB_PORT`

## Переменные окружения

Создайте `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

Минимально проверьте значения:

```env
SECRET_KEY=replace-with-secure-secret
DEBUG=0
ALLOWED_HOSTS=eshop.itunity.dev,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://eshop.itunity.dev
WEB_PORT=18490
CONTROL_SERVICE_MODE=0

POSTGRES_DB=eshop
POSTGRES_USER=eshop
POSTGRES_PASSWORD=replace-with-secure-password
POSTGRES_HOST=db
POSTGRES_PORT=5432

REDIS_URL=redis://redis:6379/0
CELERY_TASK_ALWAYS_EAGER=0
```

## Запуск

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

После первого запуска:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput
docker compose -f docker-compose.prod.yml exec web python manage.py seed_demo
```

## Первый пользователь админки

1. Установите `CONTROL_SERVICE_MODE=1` в `.env`.
2. Перезапустите web-контейнер.
3. Откройте `https://eshop.itunity.dev/control/service/`.
4. Создайте владельца админки.
5. Верните `CONTROL_SERVICE_MODE=0`.
6. Перезапустите web-контейнер.

## Caddy

Пример проксирования:

```caddyfile
eshop.itunity.dev {
  reverse_proxy 127.0.0.1:18490
}
```

## Проверка

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 web
docker compose -f docker-compose.prod.yml exec web python manage.py check
```
