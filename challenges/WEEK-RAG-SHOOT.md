# План пересъёмки недели 21–25 (как в домашке)

Прод: https://aichallenge.arcilite.ru/

**Гейт:** `GET /api/v1/rag/stats` → `embed_model` ≠ `fake-hash`.

| Порядок | День | Папка | Файл | Риск |
|--------:|------|-------|------|------|
| 1 | **21** | `21-rag-index` | `challenge-21.mp4` | низкий |
| 2 | **22** | `22-rag-query` | `challenge-22.mp4` | ask + upload |
| 3 | **23** | `23-rag-rerank` | `challenge-23.mp4` | 3 режима |
| 4 | **24** | `24-rag-citations` | `challenge-24.mp4` | цитаты + «не знаю» |
| 5 | **25** | `25-rag-memory` | `challenge-25.mp4` | shell rag |

```bash
cd challenges/record
RECORD_ONLY=21,22,23,24,25 npm run record
```

Опционально live pulse: `RECORD_ONLY=live npm run record` → `live-models/live-models.mp4`.

Диск: https://disk.yandex.ru/i/01KhOD_G7dBWPw
