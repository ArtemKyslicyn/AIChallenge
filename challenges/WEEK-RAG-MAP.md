# Карта недели RAG: домашка курса ↔ папки репо

В репозитории нумерация **не сдвинута**: папка `NN-…` = день NN стенда.  
В некоторых формулировках курса «день 21» = индексация — у нас это **день 22** (день 21 уже занят живым выбором модели).

| Домашка (формулировка) | Папка стенда | Видео | Тесты / прогон |
|---|---|---|---|
| Живой выбор модели (пульс → пин → `model_id`) | [`21-live-models/`](21-live-models/) | `challenge-21.mp4` | UI + live pulse |
| Индексация: chunking ×2 + meta + эмбеддинги | [`22-rag-index/`](22-rag-index/) | `challenge-22.mp4` | `apps/rag/tests` chunking/pipeline |
| Первый RAG ask ± база + 10 вопросов | [`23-rag-query/`](23-rag-query/) | `challenge-23.mp4` | [`QUESTIONS.md`](23-rag-query/QUESTIONS.md) |
| Реранк / filter / rewrite (raw·filtered·full) | [`24-rag-rerank/`](24-rag-rerank/) | `challenge-24.mp4` | `apps/rag/tests/test_rerank.py` |
| Цитаты + «не знаю» при слабом контексте | закрыто в **23+24** (UI цитаты + prompt) | те же ролики | `test_rag_context.py` |
| Мини-чат RAG + память задачи 2×12 | [`25-rag-memory/`](25-rag-memory/) | `challenge-25.mp4` | `run.py` 12/12 |

Общий ролик недели (Яндекс.Диск): https://disk.yandex.ru/i/01KhOD_G7dBWPw  

Локальные файлы `challenge-NN.mp4` в каждой папке — доказательство кадрами; ссылка на Диск дублирует сводку.
