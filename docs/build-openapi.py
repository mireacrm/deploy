"""Сборка спецификации публичного интерфейса.

Спецификация не пишется руками, а собирается из двух источников правды:

  * маршрутная таблица шлюза — какие запросы существуют и кому доступны;
  * описания самих сервисов — какие у запросов параметры и тела.

Сервисы на Python отдают своё описание сами, поэтому их схемы забираются
у работающей системы. Для сервисов на Go описания нет, и их представления
заданы здесь по структурам из internal/api.

    docker compose up -d
    python3 docs/build-openapi.py

Расхождение с кодом невозможно по построению: путь, которого нет в таблице
шлюза, в спецификацию не попадёт, а путь, которого нет у сервиса, останется
без схемы и будет назван в отчёте сборки.
"""

import importlib.util
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "openapi.yaml"

# Откуда забирать описания сервисов на Python.
PYTHON_SERVICES = {
    "core": "http://localhost:8001",
    "catalog": "http://localhost:8002",
    "client": "http://localhost:8005",
    "billing": "http://localhost:8006",
    "analytics": "http://localhost:8008",
}

TAGS = {
    "core": "Организация",
    "catalog": "Услуги",
    "booking": "Записи",
    "inventory": "Склад",
    "client": "Клиенты",
    "billing": "Расчёты",
    "notification": "Уведомления",
    "analytics": "Аналитика",
}

ROLE_NOTE = {
    frozenset({"admin"}): "Только администратор.",
    frozenset({"admin", "manager"}): "Администратор и управляющий.",
    frozenset({"admin", "manager", "specialist"}): "Любая роль.",
}

# Запросы, где сервис-владелец дополнительно проверяет принадлежность объекта.
OWNERSHIP = {
    ("GET", "/employees/{employee_id}/schedule"),
    ("GET", "/appointments/{appointmentID}"),
    ("POST", "/appointments/{appointmentID}/complete"),
    ("GET", "/employees/{employee_id}/commission"),
    ("GET", "/employees/{employee_id}/workload"),
}


def load_routes():
    """Маршрутная таблица шлюза как есть, без запуска шлюза."""
    path = ROOT / "services" / "gateway" / "app" / "routing" / "table.py"
    spec = importlib.util.spec_from_file_location("gateway_table", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ROUTES


def fetch(url: str):
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"  ! {url}: {exc}", file=sys.stderr)
        return None


def uuid_param(name: str, where: str = "path") -> dict:
    return {
        "name": name, "in": where, "required": True,
        "schema": {"type": "string", "format": "uuid"},
    }


def datetime_param(name: str) -> dict:
    return {
        "name": name, "in": "query", "required": True,
        "schema": {"type": "string", "format": "date-time"},
    }


def ref(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}"}


def json_body(schema: dict, description: str = "") -> dict:
    body = {"content": {"application/json": {"schema": schema}}}
    if description:
        body["description"] = description
    return body


# Представления сервисов на Go: у них нет самоописания, поэтому заданы здесь
# по структурам из internal/api/dto.go.
GO_SCHEMAS = {
    "BookRequest": {
        "type": "object", "required": ["branch_id", "client_id", "employee_id",
                                       "service_id", "starts_at"],
        "properties": {
            "branch_id": {"type": "string", "format": "uuid"},
            "client_id": {"type": "string", "format": "uuid"},
            "employee_id": {"type": "string", "format": "uuid"},
            "service_id": {"type": "string", "format": "uuid"},
            "starts_at": {"type": "string", "format": "date-time"},
        },
    },
    "CancelRequest": {
        "type": "object",
        "properties": {"reason": {"type": "string", "description": "Необязательна"}},
    },
    "Appointment": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "branch_id": {"type": "string", "format": "uuid"},
            "client_id": {"type": "string", "format": "uuid"},
            "employee_id": {"type": "string", "format": "uuid"},
            "service_id": {"type": "string", "format": "uuid"},
            "starts_at": {"type": "string", "format": "date-time"},
            "ends_at": {"type": "string", "format": "date-time"},
            "status": {"type": "string", "enum": ["scheduled", "completed", "cancelled"]},
            "price_kopecks": {"type": "integer", "format": "int64"},
        },
    },
    "Slot": {
        "type": "object",
        "properties": {
            "employee_id": {"type": "string", "format": "uuid"},
            "starts_at": {"type": "string", "format": "date-time"},
            "ends_at": {"type": "string", "format": "date-time"},
        },
    },
    "ReplenishItem": {
        "type": "object", "required": ["name", "unit", "amount"],
        "properties": {
            "consumable_id": {"type": "string", "format": "uuid",
                              "description": "Пусто для нового материала"},
            "name": {"type": "string"},
            "unit": {"type": "string", "example": "г"},
            "amount": {"type": "number", "minimum": 0},
        },
    },
    "ReplenishRequest": {
        "type": "object", "required": ["items"],
        "properties": {"items": {"type": "array", "items": ref("ReplenishItem")}},
    },
    "ThresholdRequest": {
        "type": "object", "required": ["threshold"],
        "properties": {"threshold": {"type": "number", "minimum": 0}},
    },
    "StockItem": {
        "type": "object",
        "properties": {
            "consumable_id": {"type": "string", "format": "uuid"},
            "name": {"type": "string"},
            "unit": {"type": "string"},
            "quantity": {"type": "number"},
            "threshold": {"type": "number"},
            "is_low": {"type": "boolean"},
            "updated_at": {"type": "string", "format": "date-time"},
        },
    },
    "SendRequest": {
        "type": "object", "required": ["client_id", "subject", "body"],
        "properties": {
            "client_id": {"type": "string", "format": "uuid"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
    },
    "Notification": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "channel": {"type": "string", "enum": ["sms", "email", "telegram", "dashboard"]},
            "recipient": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "status": {"type": "string", "enum": ["sent", "failed"]},
            "reason": {"type": "string"},
            "sent_at": {"type": "string", "format": "date-time"},
        },
    },
    "Template": {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
    },
}

# Операции сервисов на Go: путь шлюза -> описание.
GO_OPERATIONS = {
    ("GET", "/branches/*/slots"): {
        "path": "/branches/{branchID}/slots",
        "summary": "Свободные слоты филиала",
        "parameters": [
            uuid_param("branchID"),
            uuid_param("employee_id", "query"),
            uuid_param("service_id", "query"),
            datetime_param("from"),
            datetime_param("to"),
        ],
        "response": {"type": "array", "items": ref("Slot")},
    },
    ("POST", "/appointments"): {
        "path": "/appointments",
        "summary": "Записать клиента",
        "body": ref("BookRequest"),
        "status": "201",
        "response": ref("Appointment"),
    },
    ("GET", "/appointments/*"): {
        "path": "/appointments/{appointmentID}",
        "summary": "Карточка записи",
        "parameters": [uuid_param("appointmentID")],
        "response": ref("Appointment"),
    },
    ("POST", "/appointments/*/complete"): {
        "path": "/appointments/{appointmentID}/complete",
        "summary": "Закрыть визит",
        "parameters": [uuid_param("appointmentID")],
        "response": ref("Appointment"),
    },
    ("POST", "/appointments/*/cancel"): {
        "path": "/appointments/{appointmentID}/cancel",
        "summary": "Отменить запись",
        "parameters": [uuid_param("appointmentID")],
        "body": ref("CancelRequest"),
        "response": ref("Appointment"),
    },
    ("GET", "/branches/*/stock"): {
        "path": "/branches/{branchID}/stock",
        "summary": "Остатки филиала",
        "parameters": [uuid_param("branchID")],
        "response": {"type": "array", "items": ref("StockItem")},
    },
    ("GET", "/branches/*/stock/low"): {
        "path": "/branches/{branchID}/stock/low",
        "summary": "Позиции ниже порога",
        "parameters": [uuid_param("branchID")],
        "response": {"type": "array", "items": ref("StockItem")},
    },
    ("POST", "/branches/*/stock/replenish"): {
        "path": "/branches/{branchID}/stock/replenish",
        "summary": "Пополнить склад",
        "parameters": [uuid_param("branchID")],
        "body": ref("ReplenishRequest"),
        "response": {"type": "array", "items": ref("StockItem")},
    },
    ("PUT", "/branches/*/stock/*/threshold"): {
        "path": "/branches/{branchID}/stock/{consumableID}/threshold",
        "summary": "Порог остатка",
        "parameters": [uuid_param("branchID"), uuid_param("consumableID")],
        "body": ref("ThresholdRequest"),
        "response": ref("StockItem"),
    },
    ("POST", "/notifications"): {
        "path": "/notifications",
        "summary": "Отправить уведомление",
        "body": ref("SendRequest"),
        "status": "201",
        "response": ref("Notification"),
    },
    ("GET", "/notifications/*"): {
        "path": "/notifications/{notificationID}",
        "summary": "Статус отправки",
        "parameters": [uuid_param("notificationID")],
        "response": ref("Notification"),
    },
    ("GET", "/templates"): {
        "path": "/templates",
        "summary": "Шаблоны сообщений",
        "response": {"type": "array", "items": ref("Template")},
    },
}

ERRORS = {
    "401": "Токен отсутствует, просрочен или не проходит проверку",
    "403": "Роли недостаточно либо объект принадлежит другому сотруднику",
    "404": "Объект не найден",
    "422": "Тело или параметры запроса не проходят проверку",
    "503": "Сервис-исполнитель недоступен",
}


def matches(pattern: str, path: str) -> bool:
    """Путь шлюза со звёздочками против пути сервиса с именованными частями."""
    left = [p for p in pattern.split("/") if p]
    right = [p for p in path.split("/") if p]
    if len(left) != len(right):
        return False
    return all(a == "*" or a == b for a, b in zip(left, right, strict=True))


def build() -> dict:
    routes = load_routes()
    schemas: dict = dict(GO_SCHEMAS)
    paths: dict = {}
    missing: list[str] = []

    documents = {}
    for name, base in PYTHON_SERVICES.items():
        document = fetch(f"{base}/openapi.json")
        if document is None:
            missing.append(f"{name}: описание недоступно")
            continue
        documents[name] = document
        for key, value in document.get("components", {}).get("schemas", {}).items():
            schemas.setdefault(key, value)

    for route in routes:
        pattern = route.path
        operation = None
        target = None

        document = documents.get(route.upstream)
        if document is not None:
            for path, methods in document["paths"].items():
                if matches(pattern, path) and route.method.lower() in methods:
                    target, operation = path, dict(methods[route.method.lower()])
                    break

        if operation is None:
            described = GO_OPERATIONS.get((route.method, pattern))
            if described is None:
                missing.append(f"{route.method} {pattern} ({route.upstream})")
                continue
            target = described["path"]
            operation = {
                "summary": described["summary"],
                "parameters": described.get("parameters", []),
                "responses": {
                    described.get("status", "200"): json_body(described["response"],
                                                              "Успешный ответ"),
                },
            }
            if "body" in described:
                operation["requestBody"] = {"required": True} | json_body(described["body"])

        # Заголовок берётся из маршрутной таблицы: FastAPI выводит его из
        # имени функции, и в описании оказывается «Get Schedule».
        operation["summary"] = route.summary
        operation["tags"] = [TAGS[route.upstream]]
        operation["operationId"] = f"{route.upstream}_{route.method.lower()}_" + \
            target.strip("/").replace("/", "_").replace("{", "").replace("}", "")
        operation["security"] = [{"bearerAuth": []}]

        note = ROLE_NOTE.get(route.roles, "Роли: " + ", ".join(sorted(route.roles)))
        description = [route.summary + ".", note]
        if (route.method, target) in OWNERSHIP:
            description.append(
                "Специалист работает только со своими объектами: принадлежность "
                "проверяет сервис-владелец."
            )
        operation["description"] = " ".join(description)

        responses = operation.setdefault("responses", {})
        responses.pop("422", None)
        for code, body in responses.items():
            if code.startswith("2"):
                body["description"] = "Успешный ответ"
        for code, text in ERRORS.items():
            responses[code] = json_body(ref("Error"), text)

        paths.setdefault(target, {})[route.method.lower()] = operation

    schemas["Error"] = {
        "type": "object",
        "properties": {"detail": {"description": "Причина отказа"}},
    }
    schemas["TokenRequest"] = {
        "type": "object", "required": ["username", "password"],
        "properties": {"username": {"type": "string"}, "password": {"type": "string"}},
    }
    schemas["Token"] = {
        "type": "object",
        "properties": {
            "access_token": {"type": "string"},
            "token_type": {"type": "string", "example": "Bearer"},
            "expires_in": {"type": "integer"},
            "subject": {"type": "string", "format": "uuid"},
            "username": {"type": "string"},
            "roles": {"type": "array", "items": {"type": "string"}},
        },
    }
    schemas["Route"] = {
        "type": "object",
        "properties": {
            "method": {"type": "string"},
            "path": {"type": "string"},
            "upstream": {"type": "string"},
            "roles": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
    }

    paths["/auth/token"] = {
        "post": {
            "tags": ["Доступ"],
            "operationId": "gateway_issue_token",
            "summary": "Получить токен по логину и паролю",
            "description": (
                "Существует потому, что фронтенда нет. В боевой системе браузер "
                "идёт в Keycloak сам по authorization code с PKCE, и пароль до "
                "шлюза не доходит вовсе."
            ),
            "security": [],
            "requestBody": {"required": True} | json_body(ref("TokenRequest")),
            "responses": {
                "200": json_body(ref("Token"), "Токен выдан"),
                "401": json_body(ref("Error"), "Неверный логин или пароль"),
                "503": json_body(ref("Error"), "Keycloak недоступен"),
            },
        }
    }
    paths["/routes"] = {
        "get": {
            "tags": ["Доступ"],
            "operationId": "gateway_list_routes",
            "summary": "Маршрутная таблица с требуемыми ролями",
            "description": "Права системы читаются целиком, а не собираются по сервисам.",
            "security": [],
            "responses": {
                "200": json_body({"type": "array", "items": ref("Route")}, "Таблица маршрутов"),
            },
        }
    }

    document = {
        "openapi": "3.1.0",
        "info": {
            "title": "Mirea CRM",
            "version": "1.0.0",
            "description": (
                "Публичный интерфейс системы. Единственный вход — шлюз: сервисы "
                "за ним публичных портов не имеют.\n\n"
                "Проверка доступа двухуровневая. Роль проверяет шлюз — она указана "
                "в описании каждого запроса. Принадлежность объекта проверяет "
                "сервис-владелец: специалист работает только со своими записями, "
                "администратор и управляющий — с любыми.\n\n"
                "Документ собирается из маршрутной таблицы шлюза и описаний самих "
                "сервисов, руками не правится: docs/build-openapi.py."
            ),
        },
        "servers": [{"url": "http://localhost:8000", "description": "Локальный запуск"}],
        "tags": [{"name": "Доступ", "description": "Токены и права"}] + [
            {"name": title} for title in dict.fromkeys(TAGS.values())
        ],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http", "scheme": "bearer", "bearerFormat": "JWT",
                    "description": "Токен Keycloak области mirea.",
                }
            },
            "schemas": dict(sorted(schemas.items())),
        },
        "paths": dict(sorted(paths.items())),
    }

    if missing:
        print("Без схемы остались:", file=sys.stderr)
        for item in missing:
            print(f"  · {item}", file=sys.stderr)
    return document, missing


def main() -> int:
    document, missing = build()
    OUTPUT.write_text(
        yaml.dump(document, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    operations = sum(len(methods) for methods in document["paths"].values())
    print(f"{OUTPUT.relative_to(ROOT)}: {len(document['paths'])} путей, "
          f"{operations} операций, {len(document['components']['schemas'])} схем")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
