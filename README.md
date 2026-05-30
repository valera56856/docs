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
Постачальники (GET /api/suppliers/)  →  тап створює чернетку (POST /api/receipts/)
        │
        ▼
Камера: фото сторінок накладної  →  POST /api/receipts/{id}/photos/ (multipart 'image')
        │                            файл лягає в default storage (R2 / MEDIA_ROOT),
        │                            image_url ← image.url
        ▼
POST /api/receipts/{id}/recognize/  →  202  →  Celery task
        │
        ▼
Celery task читає байти фото з storage (photo.image.open) ──► Gemini 2.5 Flash Vision
        │                                                     ──► ReceiptLine[] (артикул, назва, к-сть, ціна)
        ▼
Маппінг: ArticleMapping (supplier, normalized SKU) → OurProduct
   • auto  — маппінг уже існує (times_used++)
   • unmapped — оператор обирає товар вручну (POST .../lines/{id}/map/, запам'ятовується)
        │  кожне map/patch → recompute_receipt_status() → needs_mapping | ready
        ▼
POST /api/receipts/{id}/generate-xlsx/  ──►  openpyxl (групування за товаром,
        │                                     сума к-сті, зважена середня ціна)
        │                                     ──►  bytes → default storage → xlsx_url
        ▼
Ручний імпорт у SalesDrive: Склад → Надходження → Імпорт
```

Каталог SalesDrive кешується локально (`OurProduct`) із YML-фіда — синхронізація запускається вручну (`POST /api/sync/catalog/`, лише адмін через `IsAdmin`), із CLI (`python manage.py sync_catalog`) і щодня через Celery beat.

PWA працює зі світлою/темною темою (`ThemeProvider`, токени `[data-theme='dark']`, перемикач у хедері), із дизайн-системою NextCRM та «Liquid Glass 2026» поверхнями карток.

Детальніше — у [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (Mermaid-діаграми потоку даних і станів `Receipt`).

---

## Стек

**Backend:** Django (>=5.1,<5.2) + Django REST Framework · DRF SimpleJWT · Celery + Redis · PostgreSQL · openpyxl · Pillow (ImageField) · drf-spectacular (OpenAPI/Swagger) · Cloudflare R2 (S3-сумісне сховище через django-storages) · Gemini 2.5 Flash через google-genai SDK · WhiteNoise + gunicorn (прод) · структуроване JSON-логування.

**Frontend:** React 19 + Vite + TypeScript (PWA через `vite-plugin-pwa`) + Capacitor · lucide-react · UI-кіт на CVA + Radix (`Button`, `Input`, `Card`, `Sheet`, `Spinner`, `Skeleton`, `EmptyState`, `Toast`, `StatusBadge`) · світла/темна тема (`ThemeProvider`) · Storybook · дизайн-токени NextCRM (navy → electric blue → cyan, шрифт Inter).

**Хостинг:** Hetzner + Docker Compose (dev `docker-compose.yml` · прод `docker-compose.prod.yml`).

---

## Структура монорепозиторію

```
valeraup/
├── README.md                    ← цей файл
├── CLAUDE.md                    ← інженерні стандарти (docstrings, WHY, DoD, логування)
├── docker-compose.yml           ← DEV: 5 сервісів (db, redis, backend, worker+beat -B, frontend)
├── docker-compose.prod.yml      ← ПРОД: db, redis, backend(gunicorn), worker, beat (окремо), frontend(nginx)
├── .env.prod.example            ← приклад прод-оточення (НЕ комітити .env.prod)
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
│   ├── requirements.txt         ← закріплені версії (+ Pillow, whitenoise)
│   ├── pytest.ini  conftest.py
│   ├── Dockerfile               ← python:3.12-slim, CMD = entrypoint.sh
│   ├── entrypoint.sh            ← прод: migrate → collectstatic → exec gunicorn
│   ├── .env.example
│   ├── valeraup/                ← пакет проєкту
│   │   ├── settings.py  urls.py  celery.py  __init__.py  wsgi.py  asgi.py
│   ├── apps/
│   │   ├── accounts/            ← Profile (роль, pin_hash); auth (login/refresh/pin/me/set-pin)
│   │   │   ├── signals.py       ← post_save → авто-Profile (operator)
│   │   │   └── permissions.py   ← IsAdmin / IsOperatorOrAdmin (за profile.role)
│   │   ├── suppliers/           ← Supplier
│   │   ├── catalog/             ← OurProduct (кеш SalesDrive) + services/tasks (YML sync)
│   │   │   └── management/commands/sync_catalog.py ← CLI-синхронізація каталогу
│   │   ├── mapping/             ← ArticleMapping + services (normalize_sku, match_line, …)
│   │   └── receipts/            ← Receipt / ReceiptPhoto(image+image_url) / ReceiptLine
│   │       ├── services/xlsx.py ← build_receipt_xlsx (4 колонки, групування+зважена ціна)
│   │       ├── services/status.py ← recompute_receipt_status / set_receipt_status
│   │       └── tasks.py         ← recognize_receipt_task (Celery, читає байти з storage)
│   ├── integrations/
│   │   ├── gemini.py            ← recognize_invoice() — реальний google-genai виклик
│   │   └── salesdrive.py        ← fetch_catalog_yml() / parse_catalog_yml() (namespace-tolerant)
│   └── tests/                   ← test_accounts / test_catalog / test_mapping / test_receipts /
│                                  test_upload / test_xlsx / test_models / test_api_smoke
│
└── frontend/
    ├── package.json  tsconfig.json  tsconfig.node.json
    ├── vite.config.ts           ← React + VitePWA (manifest Valeraup)
    ├── capacitor.config.ts      ← appId ua.nextcrm.valeraup
    ├── index.html  nginx.conf  Dockerfile  .env.example
    ├── .storybook/              ← main.ts  preview.ts (тема light/dark у toolbar)
    ├── public/                  ← manifest.webmanifest  robots.txt  icons/
    └── src/
        ├── main.tsx  App.tsx  router.tsx  vite-env.d.ts
        ├── styles/              ← tokens.css (light + [data-theme='dark'] + glass)  global.css
        ├── lib/                 ← cn.ts  api.ts (JWT fetch + postForm)  auth.tsx  camera.ts  useTheme.ts
        ├── types/index.ts       ← Supplier, OurProduct, Receipt, ReceiptLine, request/response shapes
        ├── components/
        │   ├── ThemeProvider.tsx ← тема + ThemeToggle (Sun/Moon)
        │   ├── ui/              ← Button, Input, Card, Sheet, Spinner, Skeleton, EmptyState,
        │   │                       Toast/Toaster/useToast, StatusBadge (+ .stories.tsx)
        │   └── MappingSheet.tsx ← bottom-sheet (Radix Dialog) для ручного маппінгу
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
- `worker` запускає Celery з вбудованим beat (`celery -A valeraup worker -B -l info`) — лише для dev.
- `frontend` робить `npm install` і піднімає Vite на `0.0.0.0:5173`.

> **Завантаження медіа:** фото накладної (`POST /api/receipts/{id}/photos/`) і згенеровані `.xlsx` зберігаються через Django default storage — у Cloudflare R2, якщо задані `R2_*`, інакше локально в `MEDIA_ROOT` (`backend/media/`). У DEBUG-режимі Django роздає `/media/` сам (`valeraup/urls.py`), тож прев'ю фото працює «з коробки» без R2. Celery-воркер читає байти фото назад зі storage (`photo.image.open()`), тому OCR не потребує публічного доступу до бакета.

Доступні адреси:

| Сервіс | URL |
| --- | --- |
| Frontend (PWA) | http://localhost:5173 |
| Backend API | http://localhost:8000/api/ |
| Swagger UI | http://localhost:8000/api/docs/ |
| OpenAPI schema | http://localhost:8000/api/schema/ |
| Django admin | http://localhost:8000/admin/ |

#### Ручні кроки після першого підняття

Міграції **закомічені в репозиторій** (`apps/<x>/migrations/0001_initial.py`) і застосовуються автоматично (`migrate` на старті `backend`, а в проді — у `entrypoint.sh`), тож генерувати їх не треба. Після підняття створіть суперкористувача й синхронізуйте каталог:

```bash
# Застосувати міграції (вже закомічені; також виконується автоматично при старті backend)
docker compose exec backend python manage.py migrate

# Створити адміністратора для входу в /admin/ та видачі ролей.
# Сигнал post_save автоматично створює Profile(role='operator') для кожного User;
# роль 'admin' проставляється вручну через Django admin.
docker compose exec backend python manage.py createsuperuser

# Підтягнути каталог SalesDrive у локальний кеш OurProduct — CLI-командою
#   (або через API: POST /api/sync/catalog/ під адмін-токеном; або щодня Celery beat)
docker compose exec backend python manage.py sync_catalog
```

> **PIN-логін:** найзручніше задати PIN самому через `POST /api/auth/set-pin/` (під access-токеном після входу email+пароль) — він захешує PIN у `Profile.pin_hash`. Альтернативно — через Django admin / shell (`make_password`). Після цього стає доступним швидкий вхід `POST /api/auth/pin/` (email + PIN).

> **Міграції:** згенеровані міграції закомічені в репо, тож `entrypoint.sh` (`migrate`) піднімає схему в будь-якому свіжому контейнері без додаткових кроків. Після зміни моделей згенеруйте нову міграцію (`makemigrations`) і закомітьте її.

### Варіант B — без Docker (локальна розробка)

**Backend** (потрібні запущені PostgreSQL і Redis — наприклад, `docker compose up db redis`):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# .env має вказувати на ваші локальні Postgres/Redis
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
| `GET` | `/api/auth/me/` | Поточний користувач → `{email, role, has_pin}` |
| `POST` | `/api/auth/set-pin/` | Встановити/змінити власний PIN → `204` |
| `POST` | `/api/sync/catalog/` | Запуск синхронізації каталогу (лише `IsAdmin`) → `202` |
| `GET` | `/api/suppliers/` | Список активних постачальників |
| `GET` | `/api/products/search/?q=` | Пошук `OurProduct` за SKU/назвою |
| `POST` | `/api/receipts/` | Створити чернетку накладної (`{supplier: id}`) |
| `POST` | `/api/receipts/{id}/photos/` | Завантажити фото сторінки (multipart `image`) → `201 {id, image_url}` |
| `POST` | `/api/receipts/{id}/recognize/` | Запустити Gemini OCR (Celery) → `202` |
| `GET` | `/api/receipts/{id}/` | Накладна з фото, позиціями та статусами |
| `POST` | `/api/receipts/{id}/lines/{line_id}/map/` | Замаппити позицію на товар (запам'ятати + recompute) |
| `PATCH` | `/api/receipts/{id}/lines/{line_id}/` | Редагувати кількість / ціну / SKU (+ recompute) |
| `POST` | `/api/receipts/{id}/generate-xlsx/` | Згенерувати Excel → `xlsx_url`, статус `xlsx_ready` |

Статуси `Receipt`: `draft → recognizing → needs_mapping → ready → xlsx_ready` (+ `error`). Перехід `needs_mapping → ready` тепер автоматичний: кожен map/patch викликає `recompute_receipt_status` (див. `apps/receipts/services/status.py`).

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

- `tests/test_accounts.py` — авто-створення `Profile` на `User`; `set-pin` → PIN-логін round-trip; `me`; `IsAdmin` блокує оператора.
- `tests/test_catalog.py` — парсинг невеликого YML; ідемпотентний upsert; пошук за sku/назвою.
- `tests/test_mapping.py` — нормалізація SKU (вкл. кирилицю), per-supplier ізоляція, корекція; авто-маппінг після `remember_mapping`.
- `tests/test_receipts.py` — створення чернетки; переходи `recompute_receipt_status`; PATCH рядка; map-флоу (`manual` + recompute).
- `tests/test_upload.py` — завантаження фото створює `ReceiptPhoto` з `image`; recognize без `GEMINI_API_KEY` → порожні рядки, розумний статус.
- `tests/test_xlsx.py` — `build_receipt_xlsx` формує 4 колонки; дублікати на один товар → ОДИН рядок (сума к-сті, зважена ціна).
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

Цільове середовище — **Hetzner** під **Docker Compose**. Для прода є окремий, готовий до бою файл **`docker-compose.prod.yml`** (dev-файл `docker-compose.yml` НЕ чіпаємо).

Відмінності прод-стеку від dev:

- **backend** запускається через образний `entrypoint.sh`: `migrate --noinput` → `collectstatic --noinput` → `exec gunicorn valeraup.wsgi:application -b 0.0.0.0:8000 -w 3 --timeout 60` (без bind-mount джерел, без live-reload).
- **beat** — окремий сервіс (`celery -A valeraup beat -l info`), відокремлений від `worker` (`celery -A valeraup worker -l info`), бо в проді розкладом має володіти рівно один процес. У dev beat вбудовано у worker (`-B`).
- **frontend** — багатостадійний nginx-образ (зібраний бандл, порт 80), який проксує `/api`, `/admin`, `/static` і `/media` на `backend:8000`, тож браузер працює з одним origin (CORS у браузері не потрібен).
- **Статика** (Django admin, Swagger UI) збирається в `STATIC_ROOT` і роздається **WhiteNoise** усередині gunicorn (middleware одразу після `SecurityMiddleware`, `STORAGES['staticfiles'] = CompressedManifestStaticFilesStorage`) — окремий статичний веб-сервер не потрібен.
- Усі сервіси з `restart: unless-stopped`, healthcheck'ами і `depends_on: condition: service_healthy`.

Кроки:

1. **Сервер.** VPS Hetzner з Docker + Docker Compose. Відкрити 80/443 для зовнішнього проксі/TLS.
2. **Конфігурація.** Скопіювати приклад і заповнити бойовими значеннями (НЕ комітити):
   ```bash
   cp .env.prod.example .env.prod    # DEBUG=False, SECRET_KEY, ALLOWED_HOSTS,
                                      # CORS_ALLOWED_ORIGINS, POSTGRES_*, DATABASE_URL,
                                      # CELERY_*, GEMINI_API_KEY, SALESDRIVE_YML_URL, R2_*
   ```
   `POSTGRES_USER/PASSWORD/DB` мають збігатися з `DATABASE_URL` (Compose читає їх для контейнера `db`).
3. **Міграції.** Згенеровані міграції закомічені в репо, тож `entrypoint.sh` (`migrate`) створює схему автоматично під час першого деплою — додаткових кроків не потрібно.
4. **Медіа.** Рекомендовано задати `R2_*` — фото й `.xlsx` ляжуть у Cloudflare R2 (durable, віддаються URL-ами R2). Без R2 — fallback на іменований том `media` (його роздає nginx-проксі `/media/`).
5. **Запуск/оновлення:**
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.prod build
   docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
   ```
   `migrate` і `collectstatic` виконуються автоматично в `entrypoint.sh` при старті `backend`.
6. **Зворотний проксі та TLS.** Поставте перед стеком проксі (Caddy/Traefik/nginx) з Let's Encrypt і термінуйте TLS на публічному порту фронтенду (80).

> **Важливо при редеплої:** ніколи не видаляйте томи БД та медіа. Використовуйте `build` + `up -d`, а **не** `down -v` (томи `pgdata` і `media` мають зберігатися між деплоями).

**Coolify (альтернатива):** Coolify на тому ж Hetzner-сервері може керувати `docker-compose.prod.yml` як ресурсом — додайте змінні оточення в інтерфейсі Coolify, увімкніть автодеплой із git, налаштуйте домен і TLS. Той самий принцип: окремий beat, збереження томів між деплоями.

---

## Подальша документація

- [`CLAUDE.md`](CLAUDE.md) — інженерні стандарти: docstrings + типи, пояснення «WHY», структуроване JSON-логування, ідемпотентність, Definition of Done (docs ✓ / tests ✓ / OpenAPI ✓).
- [`docs/STATUS.md`](docs/STATUS.md) — **статус проєкту й roadmap**: що зроблено (Story 1–13), як верифіковано, і що далі (креди, звірка Excel-шаблону, деплой, Capacitor).
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — компоненти, повний PWA-потік (suppliers → camera → table → mapping → generate), завантаження медіа, `recompute_receipt_status`, прод-деплой, Mermaid-діаграми (flowchart + stateDiagram статусів `Receipt`).
- [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md) — SalesDrive (YML-експорт, формат Excel-імпорту з групуванням і зваженою ціною (ТЗ §16), ручний крок) і Gemini (реальний `google-genai` виклик, системний промпт, fence-strip + retry, аудит `raw_ocr_json`).
- [`docs/MAPPING.md`](docs/MAPPING.md) — ядро маппінгу: нормалізація SKU, lookup `(supplier, normalized sku)`, auto vs unmapped, ручний маппінг і навчання (`times_used`), крайові випадки.

---

_Реалізація відповідає узгодженому ТЗ v2.2 (canonical manifest)._
