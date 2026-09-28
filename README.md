# Clicuster Beta

Лёгкая CRM для онлайн-записи в салоны красоты и барбершопы.
Помогает управлять мастерами, услугами и расписанием, а клиентам — записываться онлайн.

[![CI](https://github.com/DonFerz/Clicuster_beta/actions/workflows/ci.yml/badge.svg)](https://github.com/DonFerz/Clicuster_beta/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-compose-blue)](https://www.docker.com/)

> ⚠️ Проект в стадии разработки. API может меняться.

## 📸 Демо

- Живое демо: `-`
- Документация API: `http://localhost:8000/docs`
- Скриншоты: `-`

## ✨ Возможности

- Управление салонами, мастерами и услугами
- Онлайн-запись клиентов (в разработке)
- Учёт рабочего графика и занятости мастеров
- Клиентская база и история визитов
- Роли и права доступа (владелец, администратор, мастер)
- REST API с автоматической документацией (Swagger / ReDoc)
- Docker-окружение для быстрого старта
- Миграции БД через Alembic

## 🛠 Стек

- **Backend:** Python 3.11+, FastAPI, Pydantic
- **БД:** PostgreSQL, SQLAlchemy, Alembic
- **Аутентификация:** JWT (планируется)
- **Инфраструктура:** Docker, Docker Compose
- **Тесты:** pytest (планируется)

## Архитектура

app/
├── api/ # Роутеры FastAPI
├── core/ # Конфиг, безопасность, зависимости
├── crud/ # Операции с БД
├── models/ # SQLAlchemy-модели
├── schemas/ # Pydantic-схемы
├── services/ # Бизнес-логика
└── main.py # Точка входа


Схема БД: `-`

## 🚀 Быстрый старт

### Через Docker (рекомендуется)

```bash
git clone https://github.com/DonFerz/Clicuster_beta.git
cd Clicuster_beta
cp .env.example .env
docker compose up --build -d
docker compose exec app alembic upgrade head


Приложение будет доступно:

API: http://localhost:8000
Swagger: http://localhost:8000/docs
ReDoc: http://localhost:8000/redoc

### Локально без Docker
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# создайте БД PostgreSQL и укажите DATABASE_URL в .env
alembic upgrade head
uvicorn app.main:app --reload


⚙️ Переменные окружения
Создайте .env на основе .env.example.

DATABASE_URL Строка подключения к БД postgresql+asyncpg://user:pass@db:5432/clicuster
SECRET_KEY Ключ для JWT
ACCESS_TOKEN_EXPIRE_MINUTESВремя жизни токена 30
POSTGRES_USER Пользователь PostgreSQL postgres
POSTGRES_PASSWORD Пароль PostgreSQL postgres
POSTGRES_DB Имя БД clicuster
DEBUG Режим отладки True
CORS_ORIGINS Разрешённые источники http://localhost:3000


🗄 Миграции
# Создать новую миграцию
alembic revision --autogenerate -m "add appointments table"
# Применить миграции
alembic upgrade head
# Откатить последнюю
alembic downgrade -1


📚 API
После запуска откройте:
Swagger UI: /docs
ReDoc: /redoc

Основные эндпоинты:
POST /auth/login — авторизация
GET /salons — список салонов
GET /masters — список мастеров
POST /appointments — создать запись


🧪 Тесты
pytest
pytest --cov=app


🐳 Деплой
Краткая инструкция для продакшена:
Соберите образ: docker build -t clicuster .
Настройте reverse proxy (Nginx / Caddy).
Укажите продакшн-переменные окружения.
Примените миграции: alembic upgrade head.


🗺 Roadmap
☑ Базовые модели: салон, мастер, услуга, запись
□ Публичная страница онлайн-записи
□ Уведомления (Email / Telegram / SMS)
□ Онлайн-оплата
□ Аналитика и дашборд владельца
□ Telegram-бот для клиентов
□ Покрытие тестами > 70%
□ CI/CD через GitHub Actions


🤝 Contributing
Форкните репозиторий
Создайте ветку: git checkout -b feature/my-feature
Закоммитьте изменения: git commit -m "feat: add my feature"
Запушьте: git push origin feature/my-feature
Откройте Pull Request
Перед PR убедитесь, что проходят тесты и линтеры.


📄 Лицензия
MIT. См. LICENSE.


📬 Контакты
Авторы: <Иван Кузнецов>
GitHub: @DonFerz
Telegram: <@DonFerz>
Email: <Don_Ferz@mail.ru>
