# Valeraup — пам'ять агента (working memory)

Контекст для агента/розробника. Деталі — [`docs/STATUS.md`](../docs/STATUS.md), стандарти — [`CLAUDE.md`](../CLAUDE.md).

## Що це
PWA: фото накладної постачальника → Gemini 2.5 Flash OCR → **авто-визначення постачальника** (назва+ЄДРПОУ з шапки) + позиції → маппінг артикулів постачальника на каталог SalesDrive (auto/manual, навчається один раз) → .xlsx надходження для ручного імпорту. Backend Django 5.2 + DRF + Celery; frontend React 19 + Vite PWA + Capacitor. Репо `valera56856/docs`.

## Статус
**ЗАДЕПЛОЄНО й живе:** https://nextcrm-chat.duckdns.org (Caddy + Let's Encrypt; http→https). Story 1–15 + авто-постачальник (scan-first) + жива камера (getUserMedia) + повний адаптив (десктоп) + преміальний дизайн. **Живий OCR працює** (Gemini-ключ заданий). pytest 185 на Django 5.2, frontend build green. Каталог на проді порожній → синк SalesDrive у Налаштуваннях.

## Безпека (аудит + фікси задеплоєні; live-перевірено)
fail2ban; DRF throttling (Redis-кеш, pin 5/хв login 10/хв); IDOR-scope накладних (created_by); SSRF-guard YML-fetch; ліміти upload; SECRET_KEY fail-closed; HSTS/secure-cookies/SECURE_PROXY_SSL_HEADER/CSRF_TRUSTED_ORIGINS; JWT ротація+blacklist+/auth/logout/; Django 5.2 LTS; CI pip-audit+npm-audit; IP→301 https. **Лишилось:** SSH key-only + змінити слабкий пароль Sudakvalera1 + root + reboot ядра.

## Граблі (НЕ повторювати)
- **JWT ротація ON** → фронт мусить зберігати НОВИЙ refresh із кожної /refresh/ (старий blacklisted) — інакше сесія падає.
- **Throttling потребує спільного кешу** (Redis у проді; LocMem per-worker → bypass).
- **Tailwind arbitrary** потребує type-hint: `text-[length:var(...)]` / `text-[color:var(...)]`.
- **`.gitignore` `lib/`** ловив `frontend/src/lib/` (прибрано). Email-логін: не делегувати в SimpleJWT super().validate. colima reload ненадійний → `docker compose restart`; caddy-config → `up -d --force-recreate caddy`. Тести на Postgres не sqlite. Лог extra-ключі ≠ полям LogRecord. python-json-logger тримати <3.
- **PWA stale-cache:** після передеплою фронту клієнти бачать старий UI, поки service-worker не оновиться → reload/перевідкрити (перевіряти прод з очищенням SW). Точка входу скану: головна → «Сканувати накладну» (камера) → /receipt/new.
- **worker/beat — ОКРЕМІ docker-образи** → `docker compose build backend worker beat` (build backend НЕ перезбирає worker; OCR біжить на worker!). OCR: ретрай Gemini 503/500/429 з backoff (4 спроби); фото стискається до ≤1600px JPEG перед upload (lib/camera.ts downscaleImage). Норм. OCR ≈5с.

## Архітектура
`IntegrationSettings` singleton — SalesDrive YML у БД (UI `/api/settings/salesdrive/`). Маппінг детермінований по нормалізованому supplier_sku per-supplier (без fuzzy), `remember_mapping` навчається. `ReceiptPhoto.image` (R2/storage) для OCR-байтів. Авто-постачальник: gemini повертає {supplier:{name,edrpou}, lines}; match_or_create по ЄДРПОУ→назві; Receipt.supplier nullable + recognized_supplier; PATCH supplier перемапить. Авторизація рольова (IsAdmin по Profile.role). Деплой: `docker compose -f docker-compose.prod.yml --env-file .env.prod build && up -d`, ніколи `down -v`.
