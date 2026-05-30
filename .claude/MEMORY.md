# Valeraup — пам'ять агента (working memory)

Це зафіксований контекст для будь-якого агента/розробника, що підхоплює проєкт.
Деталі статусу й roadmap — у [`docs/STATUS.md`](../docs/STATUS.md); інженерні
стандарти — у [`CLAUDE.md`](../CLAUDE.md).

## Що це
**Valeraup** — окремий продукт (на дизайн-системі NextCRM). Менеджер фотографує
накладну постачальника (PWA) → Gemini 2.5 Flash OCR → маппінг артикулів
постачальника на каталог SalesDrive (auto/manual + «запам'ятати») → генерація
.xlsx надходження для **ручного** імпорту в SalesDrive (прямого API нема).

- Репо `github.com/valera56856/docs` (назва «docs» оманлива — тут увесь монорепо).
- Монорепо: `backend/` (Django 5.1 + DRF + Celery, 5 апок), `frontend/`
  (React 19 + Vite PWA + Capacitor + Storybook), `docs/`, dev+prod compose.

## Статус
Story 1–13 **код-комплітні, верифіковані, у `main`**. Backend pytest **81/81 на
Postgres 16**; frontend `tsc -b` + `vite build` зелені. Не зроблено: реальний
деплой, реальні креди (Gemini/SalesDrive/R2), збірка Capacitor на пристрої.

## Рецепт верифікації (reusable)
- Backend: Python 3.10+ venv, `pip install -r backend/requirements.txt`. Тести
  ганяти на **Postgres**, не sqlite (sqlite `icontains`/LIKE не case-insensitive
  для кирилиці → хибний фейл пошуку): `postgres:16-alpine`. Env: SECRET_KEY,
  DATABASE_URL, CELERY_*, GEMINI_API_KEY(''), GEMINI_MODEL, SALESDRIVE_YML_URL.
  Міграції **закомічені** — `makemigrations` лише при зміні моделей.
- Frontend: Node 20+, `npm install && npm run build`.

## Граблі (не повторювати)
- Логи: ключі в `extra={}` не мають збігатися з полями `LogRecord`
  (created/name/module/message/args/process/...) → `KeyError`. Тут `was_created`,
  `created_count`.
- Profile авто-створюється `post_save`-сигналом — у тестах НЕ створювати вручну.
- `lucide-react` на **1.x** (`^1.17.0`). tsconfig — канонічний solution-layout
  Vite (`tsconfig.json` → `tsconfig.app.json` + `tsconfig.node.json`).
- Фронт у стилі shadcn: Tailwind v3 + CVA + Radix (Slot/Dialog) + токени NextCRM
  як CSS-змінні (dark/light). `@nextcrm/tokens` поки НЕ підключати (приватний).

## Архітектурні рішення
- `ReceiptPhoto.image` (ImageField, R2/default_storage) — щоб OCR-таск читав
  байти; `image_url` дзеркалить `image.url`. Flow: create draft → POST
  `{id}/photos/` (multipart) → recognize → таблиця → map → generate-xlsx.
- Gemini — реальний `google-genai` (lazy import, offline-guard по GEMINI_API_KEY).
- xlsx: дублі групуються, к-ть сумується, ціна = середньозважена (ТЗ §16 —
  бізнес ще має підтвердити).
- Авторизація рольова: `apps.accounts.permissions.IsAdmin/IsOperatorOrAdmin`.

## Org-TODO (ТЗ §16)
Звірити колонки Excel із шаблоном SalesDrive; рішення по ціні дублів.
