# Challenge 14 — Invariants & state constraints

Инварианты (архитектура, стек, решения, бизнес-правила) живут в JSON-колонке диалога, **не в чате**. Ассистент видит блок `[инварианты]` в system. Конфликт запроса → отказ без вызова LLM, с цитатой нарушенного пункта.

## На платформе

1. https://aichallenge.arcilite.ru/?shell=agents  
2. Полоса **Инварианты** → **Посеять**  
3. Запрос: `Переведи API на Django без слоёв` → отказ с цитатой  
4. Запрос внутри ограничений проходит, в конце может быть «инварианты: ок»

## Код / видео

```bash
python3 challenges/14-invariants/run.py
cd challenges/record && RECORD_ONLY=14 npm run record
```

Текст: [`VIDEO.md`](VIDEO.md)
