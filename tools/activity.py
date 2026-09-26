#!/usr/bin/env python3
"""Генератор активности Mirea CRM.

Наполняет поднятую систему справочниками и гоняет по ней поток запросов,
похожий на работу сети салонов: записи, завершение визитов, списание
материалов, счета, оплаты, пополнение склада, отчёты.

    python3 tools/activity.py setup              справочники: компания, филиалы,
                                                 сотрудники, услуги, склад, клиенты
    python3 tools/activity.py load --minutes 20  поток активности
    python3 tools/activity.py load --forever

Запросы идут только через шлюз, под настоящими токенами Keycloak: события
в RabbitMQ, метрики в Prometheus и трейсы в Jaeger появляются сами.
"""

import argparse
import json
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "http://127.0.0.1:8000"
STATE_FILE = "tools/.activity-state.json"

# Учётные записи из mirea-realm.json. Роль определяет, что вызывающему можно:
# оплата счетов и цены — только владельцу, записи и клиенты — администратору
# филиала, завершение визита — кому угодно, но своё.
USERS = {
    "owner": ("owner", "owner"),
    "manager": ("admin-tverskaya", "manager"),
    "specialist": ("specialist-anna", "specialist"),
}

FIRST = ["Анна", "Мария", "Ольга", "Екатерина", "Ирина", "Наталья", "Светлана",
         "Юлия", "Дарья", "Ксения", "Алина", "Полина", "Вера", "Тамара",
         "Дмитрий", "Сергей", "Алексей", "Андрей", "Максим", "Илья", "Роман"]
LAST = ["Иванова", "Петрова", "Смирнова", "Кузнецова", "Соколова", "Попова",
        "Лебедева", "Козлова", "Новикова", "Морозова", "Волкова", "Зайцева",
        "Павлова", "Семёнова", "Голубева", "Виноградова", "Богданова"]

BRANCHES = [
    ("Тверская", "Москва, Тверская улица, 12"),
    ("Арбат", "Москва, Старый Арбат, 27"),
    ("Сокол", "Москва, Ленинградский проспект, 75"),
]

# Нормативы расхода описывают материал именем и единицей: склад заводит позицию
# по этому же имени, поэтому названия здесь и в пополнении должны совпадать.
SERVICES = [
    ("Женская стрижка", 60, 250_000, [("Шампунь", "мл", 30), ("Кондиционер", "мл", 20)]),
    ("Мужская стрижка", 40, 150_000, [("Шампунь", "мл", 20)]),
    ("Окрашивание", 120, 650_000, [("Краска", "г", 60), ("Окислитель", "мл", 60),
                                   ("Шампунь", "мл", 30)]),
    ("Маникюр", 90, 300_000, [("Лак", "мл", 8), ("База", "мл", 5),
                              ("Обезжириватель", "мл", 10)]),
    ("Укладка", 45, 180_000, [("Мусс", "мл", 15), ("Лак для волос", "мл", 20)]),
]

# Запас берётся небольшим намеренно: за несколько десятков визитов расход
# доходит до порога, и система публикует stock.low — иначе это событие в потоке
# не появится вовсе.
STOCK = {"Шампунь": 4000, "Кондиционер": 2500, "Краска": 3000, "Окислитель": 3000,
         "Лак": 900, "База": 600, "Обезжириватель": 1200, "Мусс": 1500,
         "Лак для волос": 2000}
THRESHOLDS = {"Шампунь": 1200, "Кондиционер": 800, "Краска": 900, "Окислитель": 900,
              "Лак": 300, "База": 200, "Обезжириватель": 400, "Мусс": 500,
              "Лак для волос": 700}

lock = threading.Lock()
stats = {}
verbose = False


def note(kind):
    with lock:
        stats[kind] = stats.get(kind, 0) + 1


def log(role, method, path, status, comment=""):
    stamp = datetime.now().strftime("%H:%M:%S")
    mark = "·" if 200 <= status < 300 else "×"
    line = f"{stamp} {mark} {role:10} {method:4} {path[:52]:52} {status}"
    if comment:
        line += f"  {comment}"
    with lock:
        print(line, flush=True)


class Client:
    """Сессия одной учётной записи: токен и запросы через шлюз."""

    def __init__(self, role):
        self.role = role
        self.username, self.password = USERS[role]
        self.token = ""
        self.subject = ""
        self.issued = 0.0
        self.lock = threading.Lock()

    def login(self):
        body = json.dumps({"username": self.username, "password": self.password})
        request = urllib.request.Request(
            f"{BASE}/auth/token", data=body.encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read())
        self.token = payload["access_token"]
        self.subject = payload.get("subject", "")
        self.issued = time.monotonic()
        return payload

    def _fresh(self):
        with self.lock:
            # Токен живёт 900 секунд; обновляем заранее, чтобы запрос не уехал
            # с протухшим и не получил 401 на ровном месте.
            if not self.token or time.monotonic() - self.issued > 600:
                self.login()
            return self.token

    def call(self, method, path, body=None, params=None, quiet=False, retry=True):
        url = f"{BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self._fresh()}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            raw, status = error.read(), error.code
            if status == 401 and retry:
                with self.lock:
                    self.token = ""
                return self.call(method, path, body, params, quiet, retry=False)
        except urllib.error.URLError as error:
            if not quiet:
                log(self.role, method, path, 0, str(error.reason)[:40])
            note("сеть недоступна")
            return 0, None
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = None
        if not quiet and (verbose or not 200 <= status < 300):
            comment = ""
            if isinstance(parsed, dict):
                comment = str(parsed.get("detail") or parsed.get("message") or "")[:48]
            log(self.role, method, path, status, comment)
        return status, parsed


def iso(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def person():
    return f"{random.choice(FIRST)} {random.choice(LAST)}"


def phone():
    return "+79" + "".join(random.choice("0123456789") for _ in range(9))


# ---------------------------------------------------------------- справочники

def setup(clients):
    owner, manager = clients["owner"], clients["manager"]
    subjects = {role: client.login().get("subject", "") for role, client in clients.items()}
    print(f"учётные записи: {', '.join(f'{r}={s[:8]}…' for r, s in subjects.items())}\n")

    status, company = owner.call("POST", "/companies", {
        "name": "Сеть салонов «Мирэа Бьюти»",
        "inn": "".join(random.choice("0123456789") for _ in range(10)),
    })
    if status != 201:
        sys.exit("компанию завести не удалось — дальше смысла нет")
    print(f"компания {company['name']}")

    state = {"branches": [], "clients": []}
    for index, (name, address) in enumerate(BRANCHES):
        _, branch = owner.call("POST", f"/companies/{company['id']}/branches", {
            "name": name, "address": address, "timezone": "Europe/Moscow"})
        if not branch:
            continue
        branch_id = branch["id"]
        entry = {"id": branch_id, "name": name, "specialists": [],
                 "services": [], "consumables": []}

        # Смены на неделю вперёд: без них у сотрудника нет свободных слотов,
        # и запись создать не на что.
        today = datetime.now(timezone.utc).replace(hour=7, minute=0, second=0, microsecond=0)
        shifts = [{"starts_at": iso(today + timedelta(days=day)),
                   "ends_at": iso(today + timedelta(days=day, hours=13))}
                  for day in range(-1, 8)]

        def hire(role_name, subject):
            """Принять сотрудника, при необходимости — без привязки к учётке.

            Учётная запись соответствует ровно одному сотруднику, поэтому
            повторный запуск на непустой базе получает на привязке конфликт.
            Сотрудник в этом случае нужен всё равно: без него филиалу некому
            работать, а привязка останется за тем, кто её занял раньше."""
            body = {"full_name": person(), "role": role_name,
                    "keycloak_subject": subject, "shifts": shifts}
            status, employee = owner.call(
                "POST", f"/branches/{branch_id}/employees", body)
            if status == 409 and subject:
                body["keycloak_subject"] = ""
                status, employee = owner.call(
                    "POST", f"/branches/{branch_id}/employees", body)
                subject = ""
            if not isinstance(employee, dict) or "id" not in employee:
                return None
            return {"id": employee["id"], "name": employee["full_name"],
                    "subject": subject}

        for number in range(4):
            # Первому специалисту первого филиала достаётся учётная запись Анны:
            # тогда «специалист закрывает свой визит» проходит проверку
            # принадлежности, а не упирается в пустую привязку.
            wanted = subjects.get("specialist", "") if (index == 0 and number == 0) else ""
            hired = hire("specialist", wanted)
            if hired:
                entry["specialists"].append(hired)

        hire("manager", subjects.get("manager", "") if index == 0 else "")

        # Идентификаторы материалов назначает catalog-service, когда заводится
        # норматив, и списание по завершённому визиту идёт по ним же. Поэтому
        # склад пополняется идентификаторами из ответа на создание услуги,
        # а не одними названиями: пополнение по имени попадает мимо норматива.
        consumables = {}
        for title, duration, price, norms in SERVICES:
            _, service = manager.call("POST", "/services", {
                "branch_id": branch_id, "name": title, "duration_minutes": duration,
                "price_kopecks": price,
                "norms": [{"name": n, "unit": u, "amount": a} for n, u, a in norms]})
            if service:
                entry["services"].append({"id": service["id"], "name": title,
                                          "duration": duration})
                for norm in service.get("norms", []):
                    consumables[norm["consumable_id"]] = (norm["name"], norm["unit"])

        items = [{"consumable_id": identifier, "name": name_, "unit": unit,
                  "amount": STOCK.get(name_, 2000)}
                 for identifier, (name_, unit) in consumables.items()]
        if items:
            manager.call("POST", f"/branches/{branch_id}/stock/replenish", {"items": items})

        for identifier, (name_, _unit) in consumables.items():
            entry["consumables"].append({"id": identifier, "name": name_})
            threshold = THRESHOLDS.get(name_)
            if threshold:
                owner.call("PUT",
                           f"/branches/{branch_id}/stock/{identifier}/threshold",
                           {"threshold": threshold})

        for _ in range(18):
            channel = random.choice(["sms", "email", "telegram"])
            name_ = person()
            handle = re.sub(r"\W+", "", name_.lower())[:12] or "client"
            _, created = manager.call("POST", "/clients", {
                "full_name": name_, "phone": phone(), "branch_id": branch_id,
                "email": f"{handle}@example.com", "telegram": f"@{handle}",
                "preferred": channel})
            if created:
                state["clients"].append({"id": created["id"], "branch_id": branch_id,
                                         "name": name_})

        state["branches"].append(entry)
        print(f"филиал {name}: {len(entry['specialists'])} специалистов, "
              f"{len(entry['services'])} услуг, {len(entry['consumables'])} позиций склада")

    print(f"клиентов: {len(state['clients'])}")
    with open(STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=1)
    print(f"справочники записаны в {STATE_FILE}")
    return state


# ---------------------------------------------------------------- активность

class Load:
    """Поток запросов по справочникам, разложенным при setup."""

    def __init__(self, clients, state):
        self.clients = clients
        self.state = state
        self.scheduled = []   # созданные записи, ждущие завершения или отмены
        self.paid = set()
        self.stop = threading.Event()

    def branch(self):
        return random.choice(self.state["branches"])

    def client_of(self, branch_id):
        pool = [c for c in self.state["clients"] if c["branch_id"] == branch_id]
        return random.choice(pool) if pool else None

    # -- действия ---------------------------------------------------------

    def book(self):
        branch = self.branch()
        if not branch["specialists"] or not branch["services"]:
            return
        specialist = random.choice(branch["specialists"])
        service = random.choice(branch["services"])
        client = self.client_of(branch["id"])
        if not client:
            return

        now = datetime.now(timezone.utc)
        status, slots = self.clients["manager"].call(
            "GET", f"/branches/{branch['id']}/slots",
            params={"employee_id": specialist["id"], "service_id": service["id"],
                    "from": iso(now - timedelta(hours=2)),
                    "to": iso(now + timedelta(days=3))}, quiet=True)
        if status != 200 or not slots:
            note("слотов нет")
            return
        # Выбор из широкого окна, а не из ближайших нескольких слотов: иначе
        # потоки толкутся в одном и том же начале расписания и конфликт слота
        # получается не от нагрузки, а от узкого выбора.
        slot = random.choice(slots[:60])

        actor = "manager" if random.random() < 0.8 else "owner"
        status, appointment = self.clients[actor].call("POST", "/appointments", {
            "branch_id": branch["id"], "client_id": client["id"],
            "employee_id": specialist["id"], "service_id": service["id"],
            "starts_at": slot["starts_at"]})
        if status == 201 and appointment:
            note("записей создано")
            with lock:
                self.scheduled.append({
                    "id": appointment["id"], "branch": branch["id"],
                    "employee": specialist["id"], "subject": specialist["subject"],
                    "service": service["name"], "client": client["name"]})
            log(actor, "POST", "/appointments", status,
                f"{service['name']} · {client['name']}")
        elif status == 409:
            note("слот уже занят")

    def complete(self):
        with lock:
            if not self.scheduled:
                return
            appointment = self.scheduled.pop(random.randrange(len(self.scheduled)))
        # Свой визит закрывает сам специалист: это проходит через сопоставление
        # учётной записи с сотрудником и проверку принадлежности в booking.
        actor = "specialist" if appointment["subject"] else "manager"
        status, _ = self.clients[actor].call(
            "POST", f"/appointments/{appointment['id']}/complete")
        if 200 <= status < 300:
            note("визитов завершено")
            log(actor, "POST", "/appointments/…/complete", status,
                f"{appointment['service']} → списание, счёт")
        else:
            note("завершить не вышло")

    def cancel(self):
        with lock:
            if len(self.scheduled) < 4:
                return
            appointment = self.scheduled.pop(random.randrange(len(self.scheduled)))
        status, _ = self.clients["manager"].call(
            "POST", f"/appointments/{appointment['id']}/cancel",
            {"reason": random.choice(["клиент не придёт", "перенос по просьбе клиента",
                                      "специалист заболел"])})
        if 200 <= status < 300:
            note("записей отменено")
            log("manager", "POST", "/appointments/…/cancel", status, appointment["service"])

    def pay(self):
        branch = self.branch()
        status, invoices = self.clients["manager"].call(
            "GET", f"/branches/{branch['id']}/invoices", quiet=True)
        if status != 200 or not invoices:
            return
        pending = [i for i in invoices
                   if str(i.get("status", "")).lower() in ("issued", "выставлен", "")
                   and i.get("id") not in self.paid]
        if not pending:
            return
        invoice = random.choice(pending)
        status, _ = self.clients["owner"].call("POST", f"/invoices/{invoice['id']}/pay")
        if 200 <= status < 300:
            self.paid.add(invoice["id"])
            note("счетов оплачено")
            amount = invoice.get("total_kopecks") or invoice.get("amount_kopecks") or 0
            log("owner", "POST", "/invoices/…/pay", status,
                f"{amount / 100:.0f} ₽" if amount else "")

    def replenish(self):
        branch = self.branch()
        status, low = self.clients["manager"].call(
            "GET", f"/branches/{branch['id']}/stock/low", quiet=True)
        if status != 200 or not low:
            return
        items = [{"consumable_id": item["consumable_id"], "name": item["name"],
                  "unit": item["unit"], "amount": round(random.uniform(800, 2500), 1)}
                 for item in low]
        status, _ = self.clients["manager"].call(
            "POST", f"/branches/{branch['id']}/stock/replenish", {"items": items})
        if 200 <= status < 300:
            note("пополнений склада")
            log("manager", "POST", "/branches/…/stock/replenish", status,
                f"{branch['name']}: {', '.join(i['name'] for i in items)[:40]}")

    def new_client(self):
        branch = self.branch()
        name = person()
        handle = re.sub(r"\W+", "", name.lower())[:12] or "client"
        status, created = self.clients["manager"].call("POST", "/clients", {
            "full_name": name, "phone": phone(), "branch_id": branch["id"],
            "email": f"{handle}@example.com", "telegram": f"@{handle}",
            "preferred": random.choice(["sms", "email", "telegram"])})
        if status == 201 and created:
            with lock:
                self.state["clients"].append({"id": created["id"],
                                              "branch_id": branch["id"], "name": name})
            note("клиентов заведено")
            log("manager", "POST", "/clients", status, name)

    def notify(self):
        branch = self.branch()
        client = self.client_of(branch["id"])
        if not client:
            return
        status, _ = self.clients["manager"].call("POST", "/notifications", {
            "client_id": client["id"],
            "subject": random.choice(["Напоминание о визите", "Спасибо за визит",
                                      "Бонусы начислены", "Свободное окно завтра"]),
            "body": "Ждём вас в салоне «Мирэа Бьюти»."})
        if 200 <= status < 300:
            note("уведомлений отправлено")

    def reprice(self):
        branch = self.branch()
        if not branch["services"]:
            return
        service = random.choice(branch["services"])
        status, _ = self.clients["owner"].call(
            "PUT", f"/services/{service['id']}/price",
            {"price_kopecks": random.randrange(150_000, 700_000, 10_000)})
        if 200 <= status < 300:
            note("цен изменено")

    def read(self):
        branch = self.branch()
        now = datetime.now(timezone.utc)
        window = {"from": iso(now - timedelta(days=7)), "to": iso(now + timedelta(days=1))}
        reads = [
            ("manager", "GET", f"/branches/{branch['id']}/services", None),
            ("manager", "GET", f"/branches/{branch['id']}/stock", None),
            ("manager", "GET", f"/branches/{branch['id']}/revenue", window),
            ("manager", "GET", f"/branches/{branch['id']}/funnel", window),
            ("manager", "GET", "/reports/consumables", dict(window, branch_id=branch["id"])),
            ("owner", "GET", f"/branches/{branch['id']}/invoices", None),
            ("specialist", "GET", "/templates", None),
        ]
        client = self.client_of(branch["id"])
        if client:
            reads.append(("manager", "GET", f"/clients/{client['id']}/loyalty", None))
            reads.append(("manager", "GET", f"/clients/{client['id']}", None))
        if branch["specialists"]:
            employee = random.choice(branch["specialists"])["id"]
            reads.append(("manager", "GET", f"/employees/{employee}/commission", window))
            reads.append(("manager", "GET", f"/employees/{employee}/schedule", window))

        role, method, path, params = random.choice(reads)
        status, _ = self.clients[role].call(method, path, params=params, quiet=True)
        note("чтений" if 200 <= status < 300 else f"чтение {status}")

    def forbidden(self):
        """Заведомо запрещённый вызов: специалист пытается оплатить счёт.

        В потоке нужны не только удачные запросы: отказ по роли — штатное
        поведение шлюза, и на графиках он должен быть виден."""
        branch = self.branch()
        status, invoices = self.clients["manager"].call(
            "GET", f"/branches/{branch['id']}/invoices", quiet=True)
        if status != 200 or not invoices:
            return
        invoice = random.choice(invoices)
        status, _ = self.clients["specialist"].call(
            "POST", f"/invoices/{invoice.get('id')}/pay", quiet=True)
        note(f"отказ по роли {status}")

    # -- цикл -------------------------------------------------------------

    def worker(self, pace):
        actions = ([self.book] * 7 + [self.complete] * 6 + [self.read] * 6 +
                   [self.pay] * 4 + [self.cancel] * 2 + [self.replenish] * 2 +
                   [self.new_client] * 2 + [self.notify] * 2 +
                   [self.reprice] + [self.forbidden])
        while not self.stop.is_set():
            try:
                random.choice(actions)()
            except Exception as error:  # поток не должен умирать из-за одного запроса
                note(f"сбой: {type(error).__name__}")
            self.stop.wait(random.uniform(pace * 0.4, pace * 1.6))

    def run(self, workers, pace, seconds):
        threads = [threading.Thread(target=self.worker, args=(pace,), daemon=True)
                   for _ in range(workers)]
        for thread in threads:
            thread.start()
        try:
            if seconds:
                self.stop.wait(seconds)
            else:
                while not self.stop.wait(1):
                    pass
        except KeyboardInterrupt:
            pass
        self.stop.set()
        for thread in threads:
            thread.join(timeout=5)


def main():
    global BASE, verbose

    parser = argparse.ArgumentParser(description="Генератор активности Mirea CRM")
    parser.add_argument("command", choices=["setup", "load", "all"])
    parser.add_argument("--minutes", type=float, default=15)
    parser.add_argument("--forever", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--pace", type=float, default=1.5,
                        help="средняя пауза между действиями одного потока, с")
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--verbose", action="store_true", help="печатать и удачные запросы")
    args = parser.parse_args()

    BASE = args.base.rstrip("/")
    verbose = args.verbose

    clients = {role: Client(role) for role in USERS}
    try:
        clients["owner"].login()
    except Exception as error:
        sys.exit(f"шлюз на {BASE} не отвечает или не выдаёт токен: {error}")

    state = None
    if args.command in ("setup", "all"):
        state = setup(clients)
        print()
    if args.command == "setup":
        return

    if state is None:
        try:
            with open(STATE_FILE, encoding="utf-8") as handle:
                state = json.load(handle)
        except OSError:
            sys.exit(f"нет {STATE_FILE} — сначала: python3 tools/activity.py setup")

    seconds = 0 if args.forever else args.minutes * 60
    print(f"поток активности: {args.workers} потока, пауза ~{args.pace} с, "
          f"{'без ограничения' if args.forever else f'{args.minutes:g} мин'} "
          f"(Ctrl+C — остановить)\n")
    started = time.monotonic()
    Load(clients, state).run(args.workers, args.pace, seconds)

    elapsed = time.monotonic() - started
    print(f"\nитог за {elapsed / 60:.1f} мин:")
    for kind, count in sorted(stats.items(), key=lambda pair: -pair[1]):
        print(f"  {count:5}  {kind}")


if __name__ == "__main__":
    main()
