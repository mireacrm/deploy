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

### Пересборка отчёта

```
python3 docs/report/report.py
```

Собирается из любого каталога, результат всегда ложится в `docs/architecture.pdf`.
Нужны `reportlab` и шрифты Liberation — путь к ним задан в `docs/report/build.py`
и на других дистрибутивах может отличаться.

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

```
cp .env.example .env
docker compose up -d
```

Вход в систему один — шлюз на `:8000`. Порты остальных сервисов слушают
только петлю: открыты для отладки, но снаружи система доступна одним адресом.

Образы берутся готовыми из `ghcr.io/mireacrm/*`: каждый сервис собирается
в своём репозитории и приезжает сюда опубликованным. Собрать систему отсюда
нельзя — исходников тут нет, и это не упущение, а следствие разъезда.

```
docker compose pull                              обновить до latest
docker compose --profile observability up -d     плюс трассировка
```
