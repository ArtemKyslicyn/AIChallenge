# Публичный край стенда AIChallenge (порты)

Краткая шпаргалка для базы знаний / RAG.

## Куда ходит публичный `:443`

Цепочка на проде:

1. Клиент → **`:443`** (xray **VLESS Reality**)
2. Reality fallthrough / dest → host **nginx `:8443`**
3. nginx проксирует на product web → **`127.0.0.1:18080`**

Итого: **`:443` → xray Reality → nginx `:8443` → web `:18080`**.

## Чего нельзя

- Не делать `docker compose down` на проде при обычном деплое.
- Не вешать product-контейнеры на `:443` / `:8443`.
- App deploys не правят Reality keys / privateKey / shortIds.

См. также: `AGENTS.md`, `.cursor/rules/deploy-vless-safe.mdc`, README Production.
