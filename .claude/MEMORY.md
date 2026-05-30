# Valeraup — пам'ять агента (working memory)

Зафіксований контекст для агента/розробника, що підхоплює проєкт. Статус і roadmap —
[`docs/STATUS.md`](../docs/STATUS.md); інженерні стандарти — [`CLAUDE.md`](../CLAUDE.md).

## Що це
**Valeraup** — PWA: менеджер фотографує накладну постачальника → Gemini 2.5 Flash OCR →
маппінг артикулів постачальника на каталог SalesDrive (auto/manual + «запам'ятати») →
генерація `.xlsx` надходження для **ручного** імпорту в SalesDrive (прямого API нема:
каталог читається з YML-експорту, надходження — Excel-імпорт вручну). Репо
`github.com/valera56856/docs` (увесь монорепо). Backend Django 5.1+DRF+Celery (5 апок),
frontend React 19+Vite PWA+Capacitor.

## Статус
Story 1–14 **код-комплітні, верифіковані, у `main`**. Backend **pytest 123/123 на
Postgres 16**; frontend `tsc -b`+`vite build` зелені. Story 14 = екран «Налаштування»
(`/admin`) через дизайн: SalesDrive (DB-URL+тест+синк), CRUD постачальників, керування
маппінгами. Не зроблено: живий OCR (треба GEMINI_API_KEY), деплой, Capacitor device,
керування користувачами.

## Локальний запуск
`docker compose up -d`. У dev порти можуть конфліктувати з іншими проєктами (5173/8000/
5432) — тоді перемапити (PWA/API/db). Демо-логіни після сіду: admin@valeraup.local /
admin12345 (admin, PIN 1234), op@valeraup.local / op12345 (PIN 1111). GEMINI_API_KEY
порожній → OCR повертає 0 рядків (offline-guard).

## Граблі (НЕ повторювати) — критичні зверху
- **`.gitignore` `lib/`** (Python-шаблон) мовчки ігнорував **`frontend/src/lib/`** —
  api.ts/auth.tsx/cn.ts/camera.ts/useTheme.ts не комітились, репо-фронт не збирався.
  Прибрано `lib/`+`lib64/`. УРОК: широкі патерни (`lib/`,`build/`,`dist/`) ловлять і
  фронтові теки — перевіряй `git check-ignore`, не лише локальний build.
- **Email-логін 500 `KeyError 'email'`**: кастомний `EmailTokenObtainPairSerializer` не
  має делегувати в `super().validate` SimpleJWT (він читає `attrs['email']`) — автентифікуй
  по реальному username + `get_token()`. pytest минав (фікстура мінтила токен напряму) →
  **реально запускай застосунок**, не лише юніт-тести.
- **colima bind-mount reload ненадійний:** Django runserver / Vite HMR у контейнері не
  бачать змін з хоста → `docker compose restart backend|frontend`.
- **Тести на Postgres, не sqlite** (sqlite `icontains` не case-insensitive для кирилиці).
- Структуровані логи: ключі `extra={}` ≠ полям `LogRecord` (created/name/module/message…)
  → KeyError. Тут `was_created`/`created_count`.
- Profile авто-створюється `post_save`-сигналом (у тестах не створювати вручну).
  `lucide-react` 1.x. tsconfig — solution-layout Vite. Фронт shadcn-стиль (Tailwind v3 +
  CVA + Radix + токени NextCRM як CSS-змінні, dark/light). Міграції закомічені; CI має
  `makemigrations --check`.

## Архітектурні рішення
- `IntegrationSettings` (singleton pk=1, `apps/catalog/models.py`) — SalesDrive YML-URL у
  БД, редагується з UI. Резолвинг: аргумент → DB → env. `GET/PUT /api/settings/salesdrive/`,
  `POST .../test/` (probe без запису, завжди 200).
- Постачальники `SupplierViewSet` (оператор бачить активних, адмін мутує; DELETE з
  накладними → 409). Маппінги `ArticleMappingViewSet` `/api/mappings/` (IsAdmin, ?supplier/?q;
  курація НЕ інкрементує times_used).
- `ReceiptPhoto.image` (ImageField, R2/default_storage) для OCR-байтів. xlsx: дублі
  групуються, ціна середньозважена (ТЗ §16). Авторизація рольова (`IsAdmin` по `Profile.role`).
- Gemini — реальний `google-genai` (lazy import, offline-guard по GEMINI_API_KEY).
