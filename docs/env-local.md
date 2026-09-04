# Локальные секреты (не в git)

Рабочий файл: **`.env`** в корне репо.

- Уже в `.gitignore` (и `.cursorignore`) — не попадёт в коммит и не должен читаться агентом.
- Шаблон без секретов: `.env.example` (в git).

## Заполнить ключ (рекомендуемый prod: free-first)

Цель: стабильность ≥90% при минимуме оплаты — OpenRouter `:free` → дешёвые платные OR → RouterAI.

```env
LLM_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=сюда_ключ_openrouter
LLM_HTTP_PROXY=http://llm-proxy:11081
LLM_MODEL_CHAIN=openrouter/free,nvidia/nemotron-3-super-120b-a12b:free,google/gemma-4-31b-it:free,google/gemini-2.5-flash,deepseek/deepseek-chat
ROUTERAI_KEY=сюда_ключ_routerai
LLM_FALLBACK_BASE_URL=https://routerai.ru/api/v1
LLM_FALLBACK_MODEL_CHAIN=deepseek/deepseek-v4-flash,mistralai/mistral-nemo
LLM_MAX_ATTEMPTS=4
LLM_FIRST_TOKEN_TIMEOUT_SECONDS=18
LLM_EXHAUSTED_TTL_SECONDS=180
USE_FAKE_LLM=false
```

### Цепочка (free → cheap → RA)

| Порядок | Tier | Model | Зачем |
|--------:|------|-------|--------|
| 1–3 | OR primary | `openrouter/free`, nemotron-super:free, gemma:free | \$0 |
| 4–5 | OR primary | `gemini-2.5-flash`, `deepseek-chat` | дешёвый paid, добирает до ≥90% |
| 6–7 | RA fallback | `deepseek-v4-flash`, `mistral-nemo` | якорь стабильности |

Каталог free: [openrouter.ai/collections/free-models](https://openrouter.ai/collections/free-models). RouterAI: [routerai.ru](https://routerai.ru).

При `429` / quota / 404 / timeout роутер уходит на следующий id **до первого токена**.

### Дешёвая альтернатива только RouterAI

```env
LLM_BASE_URL=https://routerai.ru/api/v1
ROUTERAI_KEY=...
LLM_HTTP_PROXY=
LLM_MODEL_CHAIN=mistralai/mistral-nemo,meta-llama/llama-3.1-8b-instruct,deepseek/deepseek-v4-flash
```

Другие варианты — см. `.env.example`.

### Рекомендуемый prod: OpenRouter free-first + RouterAI fallback

Primary — free и дешёвые платные через proxy. Fallback — RouterAI flash/nemo.

```env
LLM_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=...
LLM_HTTP_PROXY=http://llm-proxy:11081
LLM_MODEL_CHAIN=openrouter/free,nvidia/nemotron-3-super-120b-a12b:free,google/gemma-4-31b-it:free,google/gemini-2.5-flash,deepseek/deepseek-chat
LLM_FALLBACK_BASE_URL=https://routerai.ru/api/v1
LLM_FALLBACK_MODEL_CHAIN=deepseek/deepseek-v4-flash,mistralai/mistral-nemo
ROUTERAI_KEY=...
```

### OpenRouter как primary (если с VPS 403 — нужен proxy)

На проде настроен `llm-proxy` в Docker → sing-box mixed на хосте. Проверено: OpenRouter **200** через прокси (без 403).

1. Ключ: [openrouter.ai/keys](https://openrouter.ai/keys) → `OPENROUTER_API_KEY` в `.env`
2. На VPS после деплоя: `sudo bash scripts/llm-proxy-firewall.sh` (iptables для docker bridge)
3. Переключение в `.env`:

```env
LLM_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=ключ_openrouter
LLM_API_KEY=
LLM_HTTP_PROXY=http://llm-proxy:11081
LLM_MODEL_CHAIN=nvidia/nemotron-3-ultra-550b-a55b:free,nvidia/nemotron-3-super-120b-a12b:free,nvidia/nemotron-3.5-lightning:free,minimax/minimax-m3:free,thinkingmachines/inkling:free,google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free,z-ai/glm-5.2:free,minimax/minimax-m2.7:free,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free,poolside/laguna-s-2.1:free,cohere/north-mini-code:free,inclusionai/ling-3.0-flash-fin:free,openrouter/free,liquid/lfm-2.5-2.6b:free,google/gemini-2.5-flash,deepseek/deepseek-chat,openai/gpt-4o-mini
LLM_FALLBACK_BASE_URL=https://routerai.ru/api/v1
LLM_FALLBACK_MODEL_CHAIN=mistralai/mistral-nemo,meta-llama/llama-3.1-8b-instruct,deepseek/deepseek-v4-flash
ROUTERAI_KEY=...   # fallback: дешёвые RouterAI после OpenRouter
```

4. `docker compose -f docker-compose.prod.yml up -d api --force-recreate`

## На хост деплоя

Скопируй `.env` на сервер **вне git** (scp/sftp/панель — как удобно), выставь права `600`, пересоздай контейнер `api` через `docker compose -f docker-compose.prod.yml`. Конкретные host/path/SSH-ключи в публичных доках не храним.

После смены только `LLM_*` достаточно `docker compose -f docker-compose.prod.yml up -d api --force-recreate` — **не** сноси volume Postgres (иначе браузерные сессии станут «призраками»).

Для полного редеплоя кода на сервере: `scripts/deploy.sh` (не вызывает `compose down`, не трогает ключи Reality).

Протокол (кратко):

1. Preflight: `./scripts/assert-edge-safe.sh` (на VPS ещё `STRICT_HOST=1`).
2. Rolling `docker compose -f docker-compose.prod.yml up --build -d` только для app-сервисов.
3. Не останавливать host nginx / xray; не занимать `:443` / `:8443` контейнерами.
4. Reality camouflage: `:443` → `127.0.0.1:8443` (nginx) → `:18080`. На хосте крутится `reality-guard.timer` — если fallthrough умер, а nginx жив, xray перезапустятся с лимитом.
5. Проверка: `STRICT_HOST=1 ./scripts/assert-edge-safe.sh` и браузер **https://aichallenge.arcilite.ru/**.

Media tools (картинки/видео в чате): в `.env` на сервере `MEDIA_TOOLS_ENABLED=true`, опционально `POLLINATIONS_API_KEY`, для видео `PIXAZO_API_KEY`. Затем recreate `api`.

Не вставляй ключи в чат Cursor/Claude и не коммить `.env`.

## Наблюдаемость и оценки (имена переменных)

Каждый завершённый ответ пишет `RunTrace`; вкладка «Модели → Рейтинг» строит по ним таблицу,
вкладка «Оценки» — по 👍/👎 под ответами. Значения ниже — дефолты, ключей здесь нет.

| Переменная | Что делает |
|------------|------------|
| `RUN_TRACE_ENABLED` | писать ли трейсы. `false` останавливает сбор, но уже собранное остаётся видимым |
| `MODEL_COST_PROXY_JSON` | JSON `{"model-id": 0.2}` — относительная цена модели для колонки Cost и Score. Пусто = без цены |
| `FEEDBACK_DOWN_RATE_THRESHOLD` | доля «Не полезно», с которой модель уезжает в конец авто-цепочки (0.6) |
| `FEEDBACK_MIN_VOTES` | минимум голосов, до которого штраф не применяется (5) |
| `FEEDBACK_PENALTY_TTL_SECONDS` | окно голосов; оно же само снимает штраф, когда старые голоса выпали (86400) |
| `FEEDBACK_PENALTY_REFRESH_SECONDS` | как часто процесс перечитывает агрегаты (60) |
| `FEEDBACK_EXPORT_ENABLED` | включает `GET /lab/preference-export`; выключено — ручка отвечает 404 |
| `FEEDBACK_EXPORT_INCLUDE_CONTENT` | класть ли текст промпта и ответа в выгрузку. По умолчанию нет |

Штраф — это **переупорядочивание, а не бан**: оштрафованная модель уходит в конец цепочки, но
остаётся в ней, а явный пин модели в композере всегда пробуется первым. Правило «переключаться
только до первого токена» это не меняет.

Выгрузка предпочтений выключена по умолчанию потому, что каждая строка ссылается на конкретное
сообщение. Включать её стоит на время выгрузки датасета, а не постоянно.

## Каскад дешёвая → сильная модель (имена переменных)

Дешёвая модель отвечает первой, эвристический скорер смотрит на её ответ, и если ответ
не годится — вопрос уходит на модель из основной цепочки. Читатель видит только один ответ:
решение принимается **до** первого показанного символа.

| Переменная | Что делает |
|------------|------------|
| `CASCADE_ENABLED` | включает каскад. По умолчанию `false` — поведение чата не меняется |
| `CASCADE_CHEAP_MODELS` | csv моделей дешёвого этапа. Пусто = первая модель из `LLM_MODEL_CHAIN` |
| `CASCADE_SCORE_THRESHOLD` | порог приёмки ответа (0.75) |
| `CASCADE_MIN_ANSWER_CHARS` | короче — считаем, что показывать нечего (40) |
| `CASCADE_MAX_CHEAP_CHARS` | вопрос длиннее — сразу на сильную модель, без дешёвой попытки (1200) |
| `CASCADE_TIMEOUT_SECONDS` | сколько ждём дешёвый этап, прежде чем идти обычным путём (12) |

Скорер отвергает ответ за отказ («не могу», «как языковая модель»), обрыв на полуслове,
незакрытый блок кода и сваливание на другой язык. Никаких LLM-вызовов он не делает —
иначе съел бы ровно ту экономию, ради которой каскад и нужен.

Явный пин модели в композере отключает каскад: выбор человека сильнее автоматики.
Дешёвый этап не стримит, поэтому принятый ответ появляется целиком, а не по словам —
это осознанный компромисс, а не баг. Доля эскалаций видна в «Модели → Рейтинг»,
а сам факт — бейджем «эскалировали» под ответом.

Если каскад эскалирует слишком часто или слишком редко, крутить надо
`CASCADE_SCORE_THRESHOLD` и `CASCADE_MIN_ANSWER_CHARS`, глядя на строку эскалаций.

## Судья ответов и колонка «Качество» (имена переменных)

Отдельная модель оценивает **часть** ответов по рубрике из `configs/lab/judge_rubric.yaml`
и ставит оценку 0..1. Судья работает **после** доставки ответа, отдельной задачей со своей
сессией БД: он физически не в пути SSE, не может замедлить чат и не может его уронить.
Оценки видны в «Модели → Рейтинг» колонкой «Качество» — процент и, в подсказке ячейки,
число оценённых прогонов.

| Переменная | Что делает |
|------------|------------|
| `JUDGE_MODEL` | модель-судья. **Пусто по умолчанию = фича выключена**, и выключенная даёт ровно прежнюю таблицу и прежний Score |
| `JUDGE_SAMPLE_RATE` | доля подходящих ответов, которые вообще судим (0.2) |
| `JUDGE_MIN_ANSWER_CHARS` | короче — оценивать нечего (80) |
| `JUDGE_MAX_PER_HOUR` | потолок оценок в час, чтобы всплеск трафика не превратился в счёт (60) |
| `JUDGE_MIN_RUNS` | сколько оценок нужно модели, прежде чем качество начнёт двигать её в рейтинге (5) |
| `JUDGE_TIMEOUT_SECONDS` | сколько ждём судью, прежде чем бросить оценку (20) |

Судья обязан быть **другой** моделью, чем та, что писала ответ: модели систематически
предпочитают собственный текст, и при совпадении оценка просто не сохраняется.

Формула Score получает ветвление: пока оценок у модели меньше `JUDGE_MIN_RUNS`, числитель —
прежний «успех», дальше — «качество». Поэтому включение судьи не переставляет таблицу задним
числом. Сломанный или неполный вердикт — это `None`, а не `0.0`: ноль означал бы «судья счёл
ответ плохим», а на деле не удался разбор.

Колонка «Качество» рисуется только тогда, когда в окне есть хоть одна оценка. С пустым
`JUDGE_MODEL` таблица выглядит ровно как раньше — без колонки прочерков.

Рубрику правят в `configs/lab/judge_rubric.yaml`, без пересборки: критерии и промпт лежат
в YAML именно потому, что их будут крутить.
