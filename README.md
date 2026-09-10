# Mirea CRM — сборка системы

Система разъехалась по репозиториям организации: каждый сервис живёт
и собирается сам по себе. Здесь то, что относится ко всей системе целиком
и ни одному сервису в отдельности не принадлежит.

## Состав

| Что | Где |
|---|---|
| Описание архитектуры, 22 страницы, шесть схем | [`docs/architecture.pdf`](docs/architecture.pdf) |
| Единый язык: сущности, события, команды, правила | [`docs/glossary.md`](docs/glossary.md) |
| Публичный интерфейс | [`docs/openapi.yaml`](docs/openapi.yaml) |
| Настройки Keycloak, Prometheus, Grafana, RabbitMQ, Postgres | [`deploy/`](deploy/) |

## Репозитории

**Контракты** — [`proto`](https://github.com/mireacrm/proto) — источник правды.
Тег на нём раскладывает сгенерированный код по
[`contracts-go`](https://github.com/mireacrm/contracts-go) и
[`contracts-py`](https://github.com/mireacrm/contracts-py).

**Обвяз** — [`go-common`](https://github.com/mireacrm/go-common),
[`py-common`](https://github.com/mireacrm/py-common).

**Сервисы** — [`notification-service`](https://github.com/mireacrm/notification-service)
и остальные восемь.

## Запуск

`docker-compose.yml` появится здесь, когда сервисы будут опубликованы:
он поднимает систему из готовых образов, а не собирает её из исходников —
исходников тут больше нет.
