# День 23 — доказательства сдачи

Домашка курса «День 22 · первый RAG-запрос» → папка [`23-rag-query`](./) (карта: [`../WEEK-RAG-MAP.md`](../WEEK-RAG-MAP.md)).

Видео: `challenge-23.mp4` (пересъёмка после API-эмбеддингов + цитат в UI)  
Контрольные вопросы: [`QUESTIONS.md`](QUESTIONS.md) (10 шт.: ожидание + источники)  
Прод: `embed_model=openai/text-embedding-3-small`, ~1380+ vectors.

## Главное сравнение (задание)

**Вопрос:** Куда ходит публичный `:443`?

| Режим | Ожидание | Что видно | Статус |
|---|---|---|---|
| База **выкл** | ответ без блока источников | видео кадр «БЕЗ RAG» | **PASS** |
| База **вкл** | опора на docs + источники + цитаты + `model_id` | видео кадр «С RAG» | **PASS** |

Grounded путь с базой (кадр пересъёмки 2026-10-05):  
`:443 → xray VLESS Reality → host nginx :8443 → web 127.0.0.1:18080`  
(источник `docs/stand-edge-ports.md` + README; без базы — «недостаточно данных»).

## Чеклист

| # | Критерий | Где видно | Статус |
|---|---|---|---|
| 1 | Ask без RAG | видео | **PASS** |
| 2 | Ask с RAG (поиск → контекст → LLM) | видео + код `chat.py` / `format_rag_system_context` | **PASS** |
| 3 | Источники: title / section / source / chunk_id | UI «Источники базы» | **PASS** |
| 4 | Цитаты фрагментов | `rag-sources-quote` | **PASS** |
| 5 | `model_id` на ответе | badge | **PASS** |
| 6 | 10 контрольных вопросов | [`QUESTIONS.md`](QUESTIONS.md) | **PASS** |
| 7 | Upload → `rag_ingest` + саммари | видео | **PASS** |
| 8 | «Документы» → `rag_list_documents` | видео | **PASS** |

## Как повторить

```bash
# гейт
curl -sS https://aichallenge.arcilite.ru/api/v1/rag/stats | jq '{embed_model,vector_count}'
# видео
cd challenges/record && RECORD_ONLY=23 npm run record
```

1. Новый чат → Настройки → снять «Использовать базу» → вопрос про `:443`.  
2. Включить базу (режим full) → тот же вопрос → раскрыть источники и цитаты.  
3. **В базу** → карточка + саммари.  
4. **Документы** → свои загрузки.  
5. Пройти [`QUESTIONS.md`](QUESTIONS.md) 1–10 с базой вкл.

Диск (неделя): https://disk.yandex.ru/i/01KhOD_G7dBWPw
