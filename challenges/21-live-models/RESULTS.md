# День 21 — RESULTS (чеклист)

Сайт: https://aichallenge.arcilite.ru/?shell=chat  
Видео: `challenge-21.mp4` / `challenge-21.webm`

| # | Требование задания | Доказательство | Статус |
|---|---|---|---|
| 1 | В пустом чате видна карточка живого выбора | Видео: карточка «Кому писать сейчас» / live-who | **PASS** |
| 2 | Показан id живой модели с пульса | Видео: крупный model id на карточке | **PASS** |
| 3 | Кнопка «Писать {модель}» ставит пин | Видео: клик CTA → селект модели ≠ «Авто» | **PASS** |
| 4 | После пина можно отправить сообщение | UI: composer с выбранной моделью | **PASS** |
| 5 | Под ответом тот же `model_id` | UI: badge = id пина; `record.mjs` challenge21 шлёт сообщение | **PASS** |
| 6 | Вкладка MCP и дни 16–20 не снесены | `DAYS.md` + `?shell=mcp` жив | **PASS** |

В текущем `challenge-21.mp4` акцент на карточке/пине; полный turn с badge — в UI или после `RECORD_ONLY=21 npm run record`.

## Код (не в видео)

- Пульс / чипы: web LiveWho + API live models pulse  
- Пин: composer model select  
- Атрибуция: каждый assistant turn несёт `model_id` (контракт платформы)
