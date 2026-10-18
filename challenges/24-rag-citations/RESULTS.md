# День 24 — доказательства сдачи

Домашка: **Цитаты, источники и анти-галлюцинации**. Папка [`24-rag-citations`](./).

Видео: `challenge-24.mp4`  
Вопросы: [`QUESTIONS.md`](QUESTIONS.md)

## Чеклист

| # | Критерий | Где видно | Статус |
|---|---|---|---|
| 1 | Ответ с источниками | UI «Источники базы» | **PASS** |
| 2 | Цитаты фрагментов | `rag-sources-quote` | **PASS** |
| 3 | source + section/chunk_id | meta в списке | **PASS** |
| 4 | Смысл ответа согласован с цитатами | видео + QUESTIONS 1–9 | **PASS** |
| 5 | «не знаю по базе» при пустом/слабом контексте | QUESTIONS #10 + prompt | **PASS** |
| 6 | 10 контрольных вопросов | QUESTIONS.md | **PASS** |

Код: `apps/api/.../rag.py` (`format_rag_system_context`), web `Turn.tsx` / `RagMemoryChat.tsx`.

Диск (неделя): https://disk.yandex.ru/i/01KhOD_G7dBWPw
