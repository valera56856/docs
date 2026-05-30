# Valeraup

> Прийом товару зі сканом накладної: фото → Gemini OCR → маппінг артикулів → `.xlsx` для імпорту в SalesDrive.

**Valeraup** — це PWA, у якому менеджер фотографує накладну постачальника на телефоні, **Gemini 2.5 Flash Vision** розпізнає позиції (артикул постачальника, назва, кількість, ціна), система співставляє артикули постачальника з артикулами нашого каталогу **SalesDrive** (автоматично, якщо маппінг уже існує; вручну — інакше, і запам'ятовує вибір), після чого генерує `.xlsx`-накладну надходження для ручного імпорту в SalesDrive (**Склад → Надходження → Імпорт**).

Один склад. Облік кількості та закупівельної ціни (собівартості). Друковані накладні. Зручна авторизація (JWT + PIN/біометрія). Дизайн-система NextCRM. Повністю задокументований код.

Контракт реалізації зафіксовано в **узгодженому ТЗ v2.2** (canonical manifest) — він є єдиним джерелом істини для всіх частин системи.

---

## Зміст

- [Архітектура коротко](#архітектура-коротко)
- [Стек](#стек)
- [Структура монорепозиторію](#структура-монорепозиторію)
- [Передумови (Prerequisites)](#передумови-prerequisites)
- [Змінні оточення (Env vars)](#змінні-оточення-env-vars)
- [Локальний запуск](#локальний-запуск)
- [Документація API](#документація-api)
- [Тести](#тести)
- [Деплой](#деплой-hetzner--docker-compose--coolify)
- [Подальша документація](#подальша-документація)

---

## Архітектура коротко

```
Фото накладної (PWA / Capacitor camera)
        │  POST /api/receipts/  →  POST /api/receipts/{id}/recognize/
        ▼
Celery task  ──►  Gemini 2.5 Flash Vision  ──►  ReceiptLine[] (артикул, назва, к-сть, ціна)
        │
        ▼
Маппінг: ArticleMapping (supplier, normalized SKU) → OurProduct
   • auto  — маппінг уже існує
   • unmapped — оператор обирає товар вручну (запам'ятовується, times_used++)
        │
        ▼
POST /api/receipts/{id}/generate-xlsx/  ──►  openpyxl  ──►  xlsx_url (Cloudflare R2)
        │
        ▼
Ручний імпорт у SalesDrive: Склад → Надходження → Імпорт
```

Каталог SalesDrive кешується локально (`OurProduct`) із YML-фіда — синхронізація запускається вручну (`POST /api/sync/catalog/`, лише адмін) і щодня через Celery beat.

Детальніше — у [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (Mermaid-діаграми потоку даних і станів `Receipt`).

---

## Стек

**Backend:** Django (>=5.1,<5.2) + Django REST Framework · DRF SimpleJWT · Celery + Redis · PostgreSQL · openpyxl · drf-spectacular (OpenAPI/Swagger) · Cloudflare R2 (S3-сумісне сховище через django-storages) · Gemini 2.5 Flash через google-genai SDK · структуроване JSON-логування.

**Frontend:** React 19 + Vite + TypeScript (PWA через `vite-plugin-pwa`) + Capacitor · lucide-react · кнопка на CVA + Radix Slot · Storybook · дизайн-токени NextCRM (navy → electric blue → cyan, шрифт Inter).

**Хостинг:** Hetzner + Docker Compose.

---

## Структура монорепозиторію

```
valeraup/
├── README.md                    ← цей файл
├── CLAUDE.md                    ← інженерні стандарти (docstrings, WHY, DoD, логування)
├── docker-compose.yml           ← 5 сервісів: db, redis, backend, worker, frontend
├── .dockerignore  .gitignore
├── .github/workflows/ci.yml     ← CI: backend (check + pytest) і frontend (tsc + build)
│
├── docs/
│   ├── ARCHITECTURE.md          ← компоненти, потік даних, Mermaid-діаграми
│   ├── INTEGRATIONS.md          ← SalesDrive (YML / Excel-імпорт) + Gemini
│   └── MAPPING.md               ← нормалізація SKU, lookup, навчання маппінгу
│
├── backend/
│   ├── manage.py                ← DJANGO_SETTINGS_MODULE=valeraup.settings
│   ├── requirements.txt         ← закріплені версії (контракт ТЗ v2.2)
│   ├── pytest.ini  conftest.py
│   ├── Dockerfile  .env.example
│   ├── valeraup/                ← пакет проєкту
│   │   ├── settings.py  urls.py  celery.py  __init__.py  wsgi.py  asgi.py
│   ├── apps/
│   │   ├── accounts/            ← Profile (роль, pin_hash), auth (login / refresh / pin)
│   │   ├── suppliers/           ← Supplier
│   │   ├── catalog/             ← OurProduct (кеш SalesDrive) + services/tasks (YML sync)
│   │   ├── mapping/             ← ArticleMapping + services (normalize_sku, match_line, …)
│   │   └── receipts/            ← Receipt / ReceiptPhoto / ReceiptLine
│   │       ├── services/xlsx.py ← build_receipt_xlsx (4 колонки)
│   │       └── tasks.py         ← recognize_receipt_task (Celery)
│   ├── integrations/
│   │   ├── gemini.py            ← recognize_invoice() — Gemini Vision OCR
│   │   └── salesdrive.py        ← fetch_catalog_yml() / parse_catalog_yml()
│   └── tests/                   ← test_mapping / test_xlsx / test_models / test_api_smoke
│
└── frontend/
    ├── package.json  tsconfig.json  tsconfig.node.json
    ├── vite.config.ts           ← React + VitePWA (manifest Valeraup)
    ├── capacitor.config.ts      ← appId ua.nextcrm.valeraup
    ├── index.html  nginx.conf  Dockerfile  .env.example
    ├── .storybook/              ← main.ts  preview.ts
    ├── public/                  ← manifest.webmanifest  robots.txt  icons/
    └── src/
        ├── main.tsx  App.tsx  router.tsx  vite-env.d.ts
        ├── styles/              ← tokens.css (палітра NextCRM)  global.css
        ├── lib/                 ← cn.ts  api.ts (JWT fetch)  auth.tsx (AuthProvider)
        ├── types/index.ts       ← Supplier, OurProduct, Receipt, ReceiptLine, MatchStatus
        ├── components/
        │   ├── ui/              ← Button (CVA + Slot) + .stories  StatusBadge
        │   └── MappingSheet.tsx ← bottom-sheet для ручного маппінгу
        └── pages/               ← Login, Suppliers, Camera, ReceiptTable, Generate, Admin
```

> **Примітка про іконки PWA:** `frontend/public/icons/` поки що містить лише `.gitkeep`. Перед збіркою PWA додайте `icon-192.png` та `icon-512.png` (на них посилаються `manifest.webmanifest` і `vite.config.ts`).

> **Примітка про дизайн-токени:** `src/styles/tokens.css` тимчасово містить CSS-змінні палітри NextCRM напряму. Згодом його замінить приватний пакет `@nextcrm/tokens`.

---

## Передумови (Prerequisites)

Для запуску через Docker (рекомендований шлях) достатньо:

- **Docker** + **Docker Compose** (v2).

Для локальної розробки поза контейнерами:

- **Python 3.12** (backend, Celery worker).
- **Node.js 22** + npm (frontend, Storybook).
- **PostgreSQL 16** і **Redis 7** (або підняти лише ці сервіси з compose).
- **API-ключ Gemini** (Google AI Studio) — для реального OCR.
- **Bucket Cloudflare R2** (S3-сумісний) — для зберігання фото та згенерованих `.xlsx`. Без R2-змінних backend використовує локальне `FileSystemStorage`.

---

## Змінні оточення (Env vars)

### Backend — `backend/.env`

Скопіюйте приклад і заповніть реальні значення (справжні ключі **ніколи** не комітяться):

```bash
cp backend/.env.example backend/.env
```

| Змінна | Призначення | Приклад / дефолт |
| --- | --- | --- |
| `SECRET_KEY` | Django secret key | `change-me-in-prod` |
| `DEBUG` | Режим налагодження | `True` |
| `ALLOWED_HOSTS` | Дозволені хости | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | Origin фронтенду для CORS | `http://localhost:5173` |
| `DATABASE_URL` | Підключення до PostgreSQL | `postgres://valeraup:valeraup@db:5432/valeraup` |
| `CELERY_BROKER_URL` | Брокер Celery (Redis) | `redis://redis:6379/0` |
| `CELERY_RESULT_BACKEND` | Бекенд результатів Celery | `redis://redis:6379/1` |
| `GEMINI_API_KEY` | Ключ Gemini для OCR | `your-gemini-key` |
| `GEMINI_MODEL` | Модель Gemini | `gemini-2.5-flash` |
| `SALESDRIVE_YML_URL` | URL YML-фіда каталогу SalesDrive | `https://example.salesdrive.ua/export/yml/` |
| `R2_ACCESS_KEY_ID` | Cloudflare R2 access key | *(порожньо → FileSystemStorage)* |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 secret key | *(порожньо)* |
| `R2_BUCKET_NAME` | Назва R2-бакета | *(порожньо)* |
| `R2_ENDPOINT_URL` | R2 endpoint | *(порожньо)* |
| `R2_REGION` | Регіон R2 | `auto` |
| `ACCESS_TOKEN_LIFETIME_MIN` | Час життя access-токена (хв) | `15` |
| `REFRESH_TOKEN_LIFETIME_DAYS` | Час життя refresh-токена (дні) | `30` |

### Frontend — `frontend/.env`

```bash
cp frontend/.env.example frontend/.env
```

| Змінна | Призначення | Дефолт |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Базовий URL API | `http://localhost:8000/api` |

> У `docker-compose.yml` `VITE_API_BASE_URL` для контейнера `frontend` вже задано (`http://localhost:8000/api`), тож для запуску «з коробки» окремий `.env` не обов'язковий.

---

## Локальний запуск

### Варіант A — Docker Compose (рекомендовано)

Піднімає всі п'ять сервісів: `db`, `redis`, `backend`, `worker`, `frontend`.

```bash
# 1. Підготувати env
cp backend/.env.example backend/.env     # за потреби впишіть GEMINI_API_KEY, R2_*
cp frontend/.env.example frontend/.env   # опційно

# 2. Зібрати і підняти стек
docker compose up --build
```

Що відбувається автоматично:

- `db` (PostgreSQL 16) і `redis` (Redis 7) піднімаються з healthcheck'ами; `backend` чекає, поки вони стануть здоровими.
- `backend` виконує `python manage.py migrate --noinput`, далі запускає dev-сервер на `0.0.0.0:8000`.
- `worker` запускає Celery з вбудованим beat (`celery -A valeraup worker -B -l info`).
- `frontend` робить `npm install` і піднімає Vite на `0.0.0.0:5173`.

Доступні адреси:

| Сервіс | URL |
| --- | --- |
| Frontend (PWA) | http://localhost:5173 |
| Backend API | http://localhost:8000/api/ |
| Swagger UI | http://localhost:8000/api/docs/ |
| OpenAPI schema | http://localhost:8000/api/schema/ |
| Django admin | http://localhost:8000/admin/ |

#### Ручні кроки після першого підняття

Міграції застосовуються автоматично, але міграційні файли в репозиторій **не закомічені** (їх генерують через `makemigrations`). Першого разу згенеруйте та застосуйте їх, створіть суперкористувача й синхронізуйте каталог:

```bash
# Згенерувати міграції для всіх застосунків (за потреби — лише першого разу)
docker compose exec backend python manage.py makemigrations \
  accounts suppliers catalog mapping receipts

# Застосувати міграції (також виконується автоматично при старті backend)
docker compose exec backend python manage.py migrate

# Створити адміністратора для входу в /admin/ та видачі ролей
docker compose exec backend python manage.py createsuperuser

# Підтягнути каталог SalesDrive у локальний кеш OurProduct
#   (або через API: POST /api/sync/catalog/ під адмін-токеном)
docker compose exec backend python manage.py shell -c \
  "from apps.catalog.tasks import sync_catalog_task; print(sync_catalog_task())"
```

> **PIN-логін:** `Profile.pin_hash` зберігає хеш PIN. Задайте PIN оператору через Django admin або shell (`make_password`) — після цього стане доступним швидкий вхід `POST /api/auth/pin/`.

### Варіант B — без Docker (локальна розробка)

**Backend** (потрібні запущені PostgreSQL і Redis — наприклад, `docker compose up db redis`):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# .env має вказувати на ваші локальні Postgres/Redis
python manage.py makemigrations accounts suppliers catalog mapping receipts
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

Celery worker (окремий термінал, те саме venv):

```bash
cd backend
celery -A valeraup worker -B -l info
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev            # Vite → http://localhost:5173

# Storybook (UI-компоненти, токени NextCRM)
npm run storybook      # → http://localhost:6006

# Збірка production-бандла
npm run build          # tsc -b && vite build

# Синхронізація нативних оболонок Capacitor (після build)
npm run cap:sync
```

---

## Документація API

OpenAPI-схема генерується автоматично через **drf-spectacular**:

- **Swagger UI:** http://localhost:8000/api/docs/
- **OpenAPI JSON/YAML:** http://localhost:8000/api/schema/

Ключові ендпоінти (усі, крім auth, потребують `IsAuthenticated`):

| Метод | Шлях | Призначення |
| --- | --- | --- |
| `POST` | `/api/auth/login/` | Вхід email+пароль → JWT |
| `POST` | `/api/auth/refresh/` | Оновлення access-токена |
| `POST` | `/api/auth/pin/` | Швидкий вхід за 4-значним PIN → JWT |
| `POST` | `/api/sync/catalog/` | Запуск синхронізації каталогу (лише адмін) |
| `GET` | `/api/suppliers/` | Список активних постачальників |
| `GET` | `/api/products/search/?q=` | Пошук `OurProduct` за SKU/назвою |
| `POST` | `/api/receipts/` | Створити чернетку накладної + фото |
| `POST` | `/api/receipts/{id}/recognize/` | Запустити Gemini OCR (Celery) → `202` |
| `GET` | `/api/receipts/{id}/` | Накладна з позиціями та статусами |
| `POST` | `/api/receipts/{id}/lines/{line_id}/map/` | Замаппити позицію на товар (запам'ятати) |
| `PATCH` | `/api/receipts/{id}/lines/{line_id}/` | Редагувати кількість / ціну / SKU |
| `POST` | `/api/receipts/{id}/generate-xlsx/` | Згенерувати Excel → `xlsx_url` |

Статуси `Receipt`: `draft → recognizing → needs_mapping → ready → xlsx_ready` (+ `error`).

---

## Тести

### Backend (pytest + pytest-django)

```bash
# через Docker
docker compose exec backend pytest

# локально (з активованим venv у backend/)
cd backend && pytest
```

Покриття (Definition of Done):

- `tests/test_mapping.py` — нормалізація SKU + авто-маппінг після `remember_mapping`.
- `tests/test_xlsx.py` — `build_receipt_xlsx` формує 4 коректні колонки.
- `tests/test_models.py` — створення моделей, `unique_together`, дефолтний статус `Receipt`.
- `tests/test_api_smoke.py` — `/api/schema/` віддає `200`; `/api/suppliers/` без авторизації → `401`.

`pytest.ini` задає `DJANGO_SETTINGS_MODULE=valeraup.settings` і `pythonpath=.`.

### Frontend

```bash
cd frontend
npm run lint           # ESLint (.ts/.tsx)
npm run build          # tsc -b — перевірка типів + продакшн-збірка
npm run build-storybook
```

### CI

`.github/workflows/ci.yml` запускає два паралельні джоби:

- **backend** (Python 3.12): `pip install` → `python manage.py check` → `pytest`.
- **frontend** (Node 22): `npm ci` → `tsc -b` → `npm run build`.

---

## Деплой (Hetzner + Docker Compose / Coolify)

Цільове середовище — **Hetzner** під **Docker Compose**.

1. **Сервер.** VPS Hetzner з Docker + Docker Compose. Відкрити порти для зворотного проксі (HTTPS).
2. **Конфігурація.** На сервері заповнити `backend/.env` бойовими значеннями:
   - `DEBUG=False`, реальний `SECRET_KEY`, ваш домен в `ALLOWED_HOSTS` і `CORS_ALLOWED_ORIGINS`;
   - бойові `DATABASE_URL`, `CELERY_*`, `GEMINI_API_KEY`, `SALESDRIVE_YML_URL`, `R2_*`.
3. **Backend для прод.** У `docker-compose.yml` замінити dev-команду `runserver` на gunicorn (закоментований варіант уже наведено):
   ```
   gunicorn valeraup.wsgi:application --bind 0.0.0.0:8000 --workers 3
   ```
4. **Celery beat у проді.** Для дев-зручності beat вбудовано у `worker` (`-B`). У продакшені винесіть beat в **окремий сервіс**, щоб розкладом володів рівно один процес (інакше періодичні задачі дублюватимуться).
5. **Статика та медіа.** Фото й згенеровані `.xlsx` зберігаються в **Cloudflare R2** (при заданих `R2_*`). Frontend збирається у статику й роздається через **nginx** (`frontend/Dockerfile` — багатостадійна збірка node → nginx, `frontend/nginx.conf` — SPA-fallback).
6. **Зворотний проксі та TLS.** Поставте перед стеком проксі (Caddy/Traefik/nginx) з Let's Encrypt; пропустіть API на `backend:8000`, статику — на nginx фронтенду.
7. **Запуск/оновлення:**
   ```bash
   docker compose pull        # якщо образи в реєстрі
   docker compose up -d --build
   docker compose exec backend python manage.py migrate
   ```

> **Важливо при редеплої:** ніколи не видаляйте том БД та медіа. Використовуйте `docker compose up -d --build`, а не `down + up` (том `pgdata` і дані R2 мають зберігатися між деплоями).

**Coolify (альтернатива):** Coolify на тому ж Hetzner-сервері може керувати цим `docker-compose.yml` як ресурсом — додайте змінні оточення в інтерфейсі Coolify, увімкніть автодеплой із git, налаштуйте домен і TLS. Той самий принцип: окремий beat у проді, збереження томів між деплоями.

---

## Подальша документація

- [`CLAUDE.md`](CLAUDE.md) — інженерні стандарти: docstrings + типи, пояснення «WHY», структуроване JSON-логування, ідемпотентність, Definition of Done (docs ✓ / tests ✓ / OpenAPI ✓).
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — компоненти, потік даних, Mermaid-діаграми (flowchart + stateDiagram статусів `Receipt`).
- [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md) — SalesDrive (YML-експорт, формат Excel-імпорту, ручний крок імпорту, собівартість) і Gemini (системний промпт, JSON-формат, fence-strip + retry, аудит `raw_ocr_json`).
- [`docs/MAPPING.md`](docs/MAPPING.md) — ядро маппінгу: нормалізація SKU, lookup `(supplier, normalized sku)`, auto vs unmapped, ручний маппінг і навчання (`times_used`), крайові випадки.

---

_Реалізація відповідає узгодженому ТЗ v2.2 (canonical manifest)._
