# Clicuster

Лёгкая CRM для онлайн-записи в салоны красоты, барбершопы и студии.
Помогает управлять салонами, мастерами, услугами и расписанием, а клиентам —
записываться онлайн.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-compose-blue)](https://www.docker.com/)

> ⚠️ Проект в стадии разработки (pre-MVP). API может меняться.
> Отчёт о проведённом аудите и список исправлений — в
> [`ОТЧЁТ_О_ПРОВЕРКЕ.md`](ОТЧЁТ_О_ПРОВЕРКЕ.md).

## ✨ Возможности

- Регистрация и вход по email/паролю, JWT (access + refresh), bcrypt-хеширование
- Роли: `admin`, `client`, `master`; владелец салона — клиент, создавший салон
- Салоны: CRUD, публичный каталог только активных салонов
- Услуги: CRUD, цена в копейках, длительность, скрытие без удаления (`is_active`)
- Мастера: CRUD, привязка услуг к мастеру, права владельца/самого мастера
- **Онлайн-запись**: создание/перенос/отмена/завершение, защита от двойной
  записи (проверка в приложении + `EXCLUDE`-ограничение в PostgreSQL)
- Разграничение видимости записей: клиент — свои, мастер — к себе,
  владелец — по своим салонам, админ — все
- Защита от подбора пароля (rate limit), security-заголовки, единый формат ошибок
- Пагинация (`skip`/`limit`, заголовок `X-Total-Count`)
- Alembic-миграции, Docker-окружение, pytest-тесты

## 🛠 Стек

- **Backend:** Python 3.11+, FastAPI 0.115, Pydantic 2
- **БД:** PostgreSQL 18, SQLAlchemy 2 (async, asyncpg), Alembic
- **Аутентификация:** JWT (python-jose, HS256), bcrypt
- **Инфраструктура:** Docker, Docker Compose
- **Тесты:** pytest, pytest-asyncio, httpx

## Архитектура

```
app/
├── api/           # HTTP-роутеры (auth, users, salons, services, masters, appointments)
├── core/          # бизнес-логика: auth, security, appointments, rate_limit, exceptions
├── crud/          # запросы к БД (возвращают ORM-объекты, не вызывают другие CRUD)
├── models/        # SQLAlchemy-модели
├── schemas/       # Pydantic-схемы (вход/выход)
├── dependencies/  # Depends: сессия БД, текущий пользователь, пагинация, Redis
├── middleware/    # логирование запросов, security-заголовки
├── utils/         # время, вспомогательные функции
├── tasks/         # фоновые задачи (заглушка воркера)
├── tests/         # pytest-тесты
├── config.py      # настройки (Pydantic Settings)
├── database.py    # async engine + сессии
└── main.py        # точка входа, middleware, обработчики ошибок
```

## 🚀 Быстрый старт

### Через Docker (рекомендуется)

```bash
cp .env.example .env
# отредактируйте .env: SECRET_KEY, POSTGRES_PASSWORD
docker compose up --build -d
```

Миграции применяются автоматически при старте API
(`scripts/docker-entrypoint.sh`). Приложение будет доступно:

- API: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Health: <http://localhost:8000/health>, готовность: `/health/ready`

### Локально без Docker

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

# 1. Создайте БД PostgreSQL (например, clicuster_db)
# 2. Скопируйте .env.example -> .env и укажите доступы
alembic upgrade head
uvicorn app.main:app --reload
```

### Первый администратор

Регистрация через API всегда создаёт `client` — админа нужно создать скриптом:

```bash
python -m scripts.create_admin --email admin@example.com \
    --full-name "Иван Петров" --phone "+79990000000"
# пароль сгенерируется и будет напечатан один раз
```

Демо-данные (салон, услуги, мастер, клиент, запись):

```bash
python -m scripts.seed_demo
```

## ⚙️ Переменные окружения

Полный список с комментариями — в [`.env.example`](.env.example).
Ключевые:

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `APP_ENV` | `local` / `dev` / `prod` | `local` |
| `DEBUG` | подробные логи SQL | `false` |
| `SECRET_KEY` | ключ подписи JWT, **≥ 32 байт** | — (обязательна) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | время жизни access-токена | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | время жизни refresh-токена | `7` |
| `BCRYPT_ROUNDS` | стоимость bcrypt (4 в тестах, 12 в проде) | `12` |
| `POSTGRES_*` | подключение к БД | `localhost:5432` |
| `CORS_ORIGINS` | разрешённые источники (JSON/CSV) | `http://localhost:3000` |
| `ALLOWED_HOSTS` | белый список Host (пусто — выкл.) | — |
| `RATE_LIMIT_ENABLED` | защита от подбора пароля | `true` |
| `BOOKING_HORIZON_DAYS` | на сколько дней вперёд можно записаться | `90` |
| `ENABLE_DOCS` | отдавать `/docs`, `/redoc` | `true` |

Сгенерировать `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 🗄 Миграции

```bash
alembic revision --autogenerate -m "add something"
alembic upgrade head
alembic downgrade -1
```

## 📚 API

Базовый префикс — `/api/v1`. Полная документация — Swagger `/docs`.

### Аутентификация

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/auth/register` | регистрация (всегда роль `client`) |
| `POST` | `/auth/login` | логин (`username` = email, form-data) |
| `POST` | `/auth/refresh` | новая пара токенов по refresh-токену |

### Пользователи

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/users/me` | свой профиль |
| `PATCH` | `/users/me` | обновить имя/email/телефон |
| `POST` | `/users/me/password` | смена пароля |
| `GET` | `/users` | список (только админ) |
| `GET` | `/users/{id}` | публичный профиль |
| `PATCH` | `/users/{id}` | роль/блокировка (только админ) |
| `DELETE` | `/users/{id}` | удаление (только админ) |

### Салоны / услуги / мастера

| Метод | Путь | Описание |
|---|---|---|
| `GET`/`POST` | `/salons` | каталог / создать салон |
| `GET` | `/salons/my` | мои салоны |
| `GET`/`PATCH`/`DELETE` | `/salons/{id}` | салон |
| `GET`/`POST` | `/services` | прайс (`?salon_id=`, `?include_inactive=`) / создать |
| `GET`/`PATCH`/`DELETE` | `/services/{id}` | услуга |
| `GET`/`POST` | `/masters` | мастера (`?salon_id=`) / создать мастера |
| `GET`/`PATCH`/`DELETE` | `/masters/{id}` | мастер |
| `POST`/`DELETE` | `/masters/{id}/services/{service_id}` | привязать/отвязать услугу |

### Записи

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/appointments` | создать запись |
| `GET` | `/appointments` | список (фильтры: `status`, `master_id`, `salon_id`, `client_id`, `date_from`, `date_to`) |
| `GET` | `/appointments/{id}` | запись |
| `PATCH` | `/appointments/{id}` | перенос `/` статус `/` комментарий |
| `DELETE` | `/appointments/{id}` | удалить (владелец салона/админ) |

Пример создания записи:

```json
POST /api/v1/appointments
{
  "master_id": 1,
  "service_id": 2,
  "start_time": "2026-12-01T15:00:00+03:00",
  "comment": "первый визит"
}
```

`start_time` обязателен с часовым поясом; `end_time` считается сервером по
длительности услуги. Пересечение с другой записью к тому же мастеру → `409`.

## 🧪 Тесты

Тесты используют отдельную БД (`clicuster_test`), схема пересоздаётся и
накатываются миграции:

```bash
pytest                     # весь набор
pytest --cov=app           # с покрытием
pytest -q app/tests/test_api/test_appointments.py
```

По умолчанию `TEST_POSTGRES_DB=clicuster_test`; можно переопределить
переменной окружения.

## 🔒 Безопасность

- Пароли — bcrypt (SHA-256 pre-hash, совместимо со старыми хешами passlib)
- JWT подписывается HS256, проверяются `exp/iat/nbf/iss/aud` и тип токена
- Одинаковый ответ на неверный email и неверный пароль (защита от enumeration)
- Rate limit на `/auth/login` и `/auth/register`
- Разграничение прав на каждом эндпоинте (владелец салона / мастер / админ)
- Числовые id в путях валидируются (`ge=1`), входные схемы запрещают лишние поля
- Security-заголовки, `TrustedHostMiddleware` (при `ALLOWED_HOSTS`),
  CORS без `credentials` при wildcard-origin
- Внутренние ошибки не отдают наружу стек/детали SQL

## 🗺 Roadmap до MVP

- [x] Модели: салон, мастер, услуга, запись
- [x] JWT-аутентификация и роли
- [x] CRUD салонов/услуг/мастеров
- [x] Онлайн-запись с защитой от двойного бронирования
- [x] Тесты API
- [ ] Рабочий график мастера (рабочие часы, перерывы, выходные) и расчёт свободных окон
- [ ] Уведомления (Email / Telegram / SMS) и напоминания за N часов
- [ ] Публичная страница онлайн-записи (фронтенд)
- [ ] Дашборд владельца: выручка, загрузка, повторные визиты
- [ ] Онлайн-оплата / предоплата
- [ ] Отзывы и рейтинги мастеров
- [ ] Мультиарендность и лимиты тарифов
- [ ] CI (GitHub Actions): ruff + mypy + pytest

## 🤝 Contributing

1. Форкните репозиторий
2. Создайте ветку: `git checkout -b feature/my-feature`
3. Закоммитьте: `git commit -m "feat: add my feature"`
4. Запушьте и откройте Pull Request

Перед PR: `ruff check app && mypy app && pytest`.

## 📄 Лицензия

MIT. См. [LICENSE](LICENSE).

## 📬 Контакты

Автор: Иван Кузнецов · GitHub: [@DonFerz](https://github.com/DonFerz) ·
Telegram: [@DonFerz](https://t.me/DonFerz) · Email: <Don_Ferz@mail.ru>
