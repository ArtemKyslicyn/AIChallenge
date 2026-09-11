# Challenge 09 — Context Compression

Сжатие истории: последние N реплик «как есть», старше — LLM-summary в Postgres.
Сравнение токенов и качества с/без сжатия.

## На платформе

1. https://aichallenge.arcilite.ru/?shell=agents → Один агент  
2. Набери длинный диалог без тумблера → смотри токены  
3. Включи **Сжимать историю**, продолжай → «сырой → сжатый», блок **Сводка**

## Код / видео

```bash
python3 challenges/09-compression/run.py
cd challenges/record && RECORD_ONLY=09 npm run record
```
