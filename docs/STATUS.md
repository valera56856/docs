# Статус проєкту Valeraup

> Актуально на: **2026-05-30**. Гілка `main`. Цей файл — «єдина правда» про те, що
> зроблено, як це перевірено і що далі. Оновлюйте його разом із кодом.

## Загальний стан

**MVP код-комплітна.** Усі Story 1–13 з ТЗ реалізовані, верифіковані й залиті в
`main`. Застосунок збирається й проходить тести; залишилось підключити реальні
зовнішні сервіси та задеплоїти (див. [«Що далі»](#що-далі)).

| # | Story | Стан |
|---|-------|------|
| 1 | Скелет + документація | ✅ |
| 2 | Авторизація (JWT + PIN + ролі) | ✅ рольові permissions, авто-Profile (signal), `set-pin`, email+PIN |
| 3 | Дизайн-система NextCRM | ✅ dark/light токени + ThemeProvider; UI-кіт (Button, Input, Card, Sheet, Spinner, Skeleton, EmptyState, Toast, StatusBadge) + Storybook |
| 4 | Синхронізація каталогу (YML) | ✅ namespace-tolerant парсер, upsert по `salesdrive_id`, `manage.py sync_catalog`, admin-API + Celery beat |
| 5 | Моделі | ✅ |
| 6 | Gemini Vision (OCR) | ✅ реальний виклик `google-genai` (lazy import, offline-guard по `GEMINI_API_KEY`) |
| 7 | Движок маппінгу | ✅ `normalize_sku` / `match_line` / `remember_mapping` (ідемпотентно, per-supplier, корекція, лічильник навчання) |
| 8 | PWA: камера + завантаження | ✅ Capacitor Camera з веб-фолбеком, multipart-upload фото |
| 9 | PWA: таблиця + маппінг | ✅ inline-редагування к-ті/ціни, статус-бейджі, MappingSheet з пошуком каталогу |
| 10 | Збереження маппінгу | ✅ |
| 11 | Генерація Excel | ✅ 4 колонки, групування дублів + середньозважена ціна; інструкція імпорту |
| 12 | Workflow статусів | ✅ `recompute_receipt_status` (draft→recognizing→needs_mapping/ready→xlsx_ready, error) |
| 13 | Деплой | ✅ `docker-compose.prod.yml`, `entrypoint.sh`, whitenoise, gunicorn, split beat |
| 14 | Адмін-екран «Налаштування» (PWA) | ✅ SalesDrive (DB-URL + тест + синк), CRUD постачальників, керування маппінгами — все через дизайнерський PWA `/admin`, не Django admin |
| 15 | Авто-визначення постачальника (scan-first) | 🟡 backend готовий — OCR віддає `{supplier, lines}`, авто-match/create по ЄДРПОУ→назві, `PATCH /api/receipts/{id}/` для зміни постачальника з ре-маппінгом; фронтенд scan-first потоку — окремо |

### Story 14 — деталі (delta поверх MVP)

Адмін керує системою через дизайнерський екран `/admin` («Налаштування»,
`frontend/src/pages/AdminPage.tsx`, гейт за роллю через `GET /api/auth/me/`), а не
через Django admin. Три секції, усі ендпоінти `IsAuthenticated` + `IsAdmin`:

- **SalesDrive** — YML-URL тепер у БД (`IntegrationSettings` singleton, pk=1),
  env-змінна `SALESDRIVE_YML_URL` лишається фолбеком. `GET/PUT
  /api/settings/salesdrive/` (`{salesdrive_yml_url, last_synced, product_count}`),
  `POST /api/settings/salesdrive/test/` — «перевірка підключення» через
  `probe_catalog_yml` (без запису в БД), завжди **HTTP 200** навіть на помилці
  (`{ok, product_count, error}`). Кнопка «Синхронізувати» = наявний
  `POST /api/sync/catalog/`.
- **Постачальники** — повний CRUD через `SupplierViewSet` (DRF `DefaultRouter`):
  `GET/POST /api/suppliers/`, `GET/PUT/PATCH/DELETE /api/suppliers/{id}/`. Оператор
  читає лише активних; мутації — лише адмін. `DELETE` дає **409** із підказкою
  «деактивуйте» коли є повʼязані накладні (`Receipt.supplier=PROTECT`).
- **Маппінги** — керування `ArticleMapping` через `ArticleMappingViewSet`:
  `GET /api/mappings/` (фільтри `?supplier`, `?q`; `-times_used`; cap 200), `POST`
  (створення/перепривʼязка, **не** інкрементує `times_used`), `PATCH /{id}/`
  (перепривʼязка товару / зміна sku, колізія → 409), `DELETE /{id}/`.

Нові фронтенд-компоненти: `SupplierFormSheet`, `ProductPickerSheet` (адаптовано з
`MappingSheet`, який лишається для флоу накладної). `SuppliersPage` має шестірню
«Налаштування» в шапці (тільки для адміна). Деталі — у
[ARCHITECTURE.md](ARCHITECTURE.md) та [INTEGRATIONS.md](INTEGRATIONS.md) §1.4.

### Story 15 — авто-визначення постачальника (delta, backend)

Система **сама визначає постачальника** зі сканованої накладної замість того, щоб
оператор обирав його першим. Замість «обери постачальника → фотографуй» —
«фотографуй → система визначила постачальника».

- **Модель.** `Supplier.edrpou` (`CharField`, indexed, blank) — код ЄДРПОУ,
  надійний ключ постачальника. `Receipt.supplier` тепер `null=True` (чернетка
  scan-first ще не має постачальника), додано `Receipt.recognized_supplier`
  (`JSONField`) — сирий OCR-дикт постачальника для аудиту.
- **OCR-контракт.** `gemini.recognize_invoice` повертає **один обʼєкт**
  `{"supplier": {"name", "edrpou"}|None, "lines": [...]}`. Промпт читає шапку
  накладної (постачальник/продавець + ЄДРПОУ). Толерантний до легасі-масиву рядків
  (обгортає як `{supplier: None, lines: array}`); offline-guard повертає
  `{supplier: None, lines: []}`.
- **Сервіс.** `apps.suppliers.services.match_or_create_supplier(name, edrpou)` —
  match спершу по **ЄДРПОУ** (точно, якщо не порожній), потім по нормалізованій
  назві (`normalize_supplier_name`: trim/collapse/UPPER), інакше створює нового.
  Ідемпотентний.
- **Таск.** `recognize_receipt_task` після OCR авто-визначає постачальника (лише
  якщо `receipt.supplier` ще порожній), завжди пише `recognized_supplier`,
  виконує per-supplier маппінг тільки коли постачальник є (інакше рядки лишаються
  unmapped, статус `needs_mapping`).
- **API.** `POST /api/receipts/` — постачальник **опційний** (scan-first створює
  чернетку без нього). Деталь-серіалізатор віддає вкладений `supplier`
  (`{id, name, edrpou}` або `null`) + `recognized_supplier`. Новий
  `PATCH /api/receipts/{id}/ {"supplier": <id>}` встановлює/змінює постачальника й
  **повторно** виконує маппінг наявних рядків (`remap_receipt_lines`) + перераховує
  статус; ручні маппінги зберігаються.

Деталі — у [INTEGRATIONS.md](INTEGRATIONS.md) §2 (Gemini supplier extraction).
Міграції (`Supplier.edrpou`, `Receipt.supplier` nullable + `recognized_supplier`)
генерує інтегратор через `makemigrations` (не закомічені цим агентом).

## Верифікація (перевірено, не на словах)

- **Backend:** `pytest` **81 passed / 0 failed** на **PostgreSQL 16** (та сама БД, що в проді й CI), `manage.py check` чистий. Міграції згенеровані й **закомічені** (5 апок).
- **Frontend:** `tsc -b` + `vite build` зелені (dist ≈ 401 KB JS → gzip 126 KB, PWA service worker генерується).

### Відтворити локально

```bash
# Backend (потрібен Python 3.10+)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Тести ганяти на Postgres (sqlite дає хибний фейл пошуку по кирилиці через LIKE):
docker run -d --name vp -e POSTGRES_USER=valeraup -e POSTGRES_PASSWORD=valeraup \
  -e POSTGRES_DB=valeraup -p 5433:5432 postgres:16-alpine
DATABASE_URL=postgres://valeraup:valeraup@localhost:5433/valeraup \
  SECRET_KEY=dev GEMINI_API_KEY= python -m pytest -q

# Frontend (Node 20+)
cd ../frontend && npm install && npm run build
```

## Що далі

### 0. Блок перед продом (потребує доступів/рішень бізнесу)
1. **Реальні креди** у `.env.prod` (з `.env.prod.example`): `SECRET_KEY`, `GEMINI_API_KEY`, `R2_*`, `POSTGRES_*`. `SALESDRIVE_YML_URL` тепер опційний фолбек — основне джерело URL задається в адмін-екрані «Налаштування» (`PUT /api/settings/salesdrive/`, зберігається в `IntegrationSettings`).
2. **Звірити шаблон Excel** надходження в кабінеті SalesDrive (`Склад → Надходження → Імпорт → завантажити шаблон`) із колонками генератора (`apps/receipts/services/xlsx.py`, `COLUMN_HEADERS`). Поточні: `SKU/Артикул, Назва, Кількість, Ціна (собівартість)`.
3. **Рішення по ціні дублів** (ТЗ §16): зараз середньозважена; підтвердити чи змінити на last/min.

### 1. Деплой (Hetzner + Coolify)
- Розгорнути `docker-compose.prod.yml` (db, redis, gunicorn-backend, worker, beat, nginx-frontend). Coolify дає reverse-proxy + TLS. `entrypoint.sh` сам робить `migrate` + `collectstatic`.
- ⚠️ Ніколи `down -v` при редеплої — томи `pgdata`/`media` мають жити.

### 2. Мобільний застосунок (Capacitor)
- `npx cap add ios/android`, збірка під пристрій; нативна камера вже через `@capacitor/camera` (зараз веб-фолбек).
- Біометрія (Face ID / відбиток) як гейт перед PIN — окремий Capacitor-плагін (зараз TODO в `LoginPage`).
- Захищене сховище refresh-токена (Capacitor Secure Storage) замість localStorage-фолбеку.

### 3. Покращення якості (за потреби)
- E2E-тести флоу (камера→OCR→маппінг→Excel) на реальному фото-зразку.
- Реальний прогін OCR на кількох накладних різних постачальників → калібрування промпта.
- Моніторинг/алерти на структурованих JSON-логах.

## Ключові рішення та граблі (щоб не повторювати)

- **`ReceiptPhoto.image`** (`ImageField`, R2/`default_storage`) додано понад вихідне ТЗ — щоб OCR-таск читав байти сервер-сайд; `image_url` дзеркалить `image.url`.
- **Авторизація рольова** через `apps.accounts.permissions.IsAdmin/IsOperatorOrAdmin` (по `Profile.role`), **не** Django `is_staff`. Profile авто-створюється `post_save`-сигналом.
- **Структуровані логи:** ключі в `extra={}` не мають збігатися з полями `LogRecord` (`created`, `name`, `module`, `message`…) — інакше `KeyError`. Тут використано `was_created` / `created_count`.
- **Frontend стек** — shadcn-стиль: Tailwind v3 + CVA + Radix (Slot/Dialog) + токени NextCRM як CSS-змінні (dark/light). `@nextcrm/tokens` поки не підключений (приватний) — локальний `src/styles/tokens.css`.
- **lucide-react** на гілці **1.x** (`^1.17.0`). **tsconfig** — канонічний solution-layout Vite (`tsconfig.json` → `tsconfig.app.json` + `tsconfig.node.json`).

Деталі архітектури, інтеграцій і ядра маппінгу — у [ARCHITECTURE.md](ARCHITECTURE.md), [INTEGRATIONS.md](INTEGRATIONS.md), [MAPPING.md](MAPPING.md). Інженерні стандарти — у [CLAUDE.md](../CLAUDE.md).
