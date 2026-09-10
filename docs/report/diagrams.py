"""Векторные схемы для отчёта.

Различие типов связи кодируется начертанием линии, а не цветом: документ
должен одинаково читаться на печати.
"""

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Flowable

INK = colors.HexColor("#1A1A1A")
GREY = colors.HexColor("#666666")
FILL = colors.HexColor("#F2F2F2")

SOLID = []
DASH = [3, 2]
DOT = [1, 2]
LONG = [6, 2]


class Diagram(Flowable):
    """Базовый холст: рамки, стрелки, подписи."""

    def __init__(self, width, height, font="Body", mono="Mono"):
        super().__init__()
        self.width = width
        self.height = height
        self.font = font
        self.mono = mono

    def wrap(self, avail_width, avail_height):
        return self.width, self.height

    def box(self, x, y, w, h, text, *, sub=None, dashed=False, fill=True):
        c = self.canv
        c.saveState()
        c.setStrokeColor(INK)
        c.setLineWidth(0.7)
        if dashed:
            c.setDash(DASH)
        if fill:
            c.setFillColor(FILL)
            c.rect(x, y, w, h, stroke=1, fill=1)
        else:
            c.rect(x, y, w, h, stroke=1, fill=0)
        c.setDash([])
        c.setFillColor(INK)
        if sub:
            c.setFont(self.mono, 7.4)
            c.drawCentredString(x + w / 2, y + h / 2 + 1.4, text)
            c.setFont(self.font, 6.4)
            c.setFillColor(GREY)
            c.drawCentredString(x + w / 2, y + h / 2 - 6.2, sub)
        else:
            c.setFont(self.mono, 7.4)
            c.drawCentredString(x + w / 2, y + h / 2 - 2.6, text)
        c.restoreState()

    def line(self, points, *, dash=SOLID, width=0.6, arrow=True, both=False):
        c = self.canv
        c.saveState()
        c.setStrokeColor(INK)
        c.setLineWidth(width)
        c.setDash(dash)
        path = c.beginPath()
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        c.drawPath(path)
        c.setDash([])
        if arrow:
            self._head(points[-2], points[-1])
        if both:
            self._head(points[1], points[0])
        c.restoreState()

    def _head(self, frm, to, size=3.4):
        import math

        c = self.canv
        angle = math.atan2(to[1] - frm[1], to[0] - frm[0])
        c.setFillColor(INK)
        path = c.beginPath()
        path.moveTo(*to)
        path.lineTo(
            to[0] - size * math.cos(angle - 0.42), to[1] - size * math.sin(angle - 0.42)
        )
        path.lineTo(
            to[0] - size * math.cos(angle + 0.42), to[1] - size * math.sin(angle + 0.42)
        )
        path.close()
        c.drawPath(path, stroke=0, fill=1)

    def caption(self, x, y, text, *, size=6.4, anchor="c", grey=True):
        c = self.canv
        c.saveState()
        c.setFont(self.font, size)
        c.setFillColor(GREY if grey else INK)
        if anchor == "c":
            c.drawCentredString(x, y, text)
        elif anchor == "r":
            c.drawRightString(x, y, text)
        else:
            c.drawString(x, y, text)
        c.restoreState()

    def bus(self, x, y, w, h, text):
        c = self.canv
        c.saveState()
        c.setStrokeColor(INK)
        c.setLineWidth(0.7)
        c.setFillColor(colors.HexColor("#E4E4E4"))
        c.roundRect(x, y, w, h, 2, stroke=1, fill=1)
        c.setFillColor(INK)
        c.setFont(self.mono, 7.4)
        c.drawCentredString(x + w / 2, y + h / 2 - 2.6, text)
        c.restoreState()


class Topology(Diagram):
    """Ярусы системы и две шины.

    По краям оставлены свободные каналы: через них проходят линии NATS,
    не пересекая блоки.
    """

    MARGIN = 16

    def draw(self):
        m = self.MARGIN
        w = self.width - 2 * m
        bw, bh = 72, 19
        gap = (w - 4 * bw) / 3

        def col(i):
            return m + i * (bw + gap)

        def mid(i):
            return col(i) + bw / 2

        centre = m + w / 2

        # шлюз и распределительная шина запросов
        self.box(mid(1), 248, bw + gap, bh, "gateway", sub="JWT · маршрутизация")
        self.line([(centre, 248), (centre, 234)], arrow=False)
        self.line([(mid(0), 234), (mid(3), 234)], arrow=False)

        top = 192
        names = [
            ("core", "организация"),
            ("catalog", "услуги"),
            ("booking", "записи"),
            ("client", "клиенты"),
        ]
        for i, (name, sub) in enumerate(names):
            self.box(col(i), top, bw, bh, name, sub=sub)
            self.line([(mid(i), 234), (mid(i), top + bh)])

        # шина доменных событий
        self.bus(m, 132, w, 16, "RabbitMQ · обменник mirea.events")
        for i in (0, 2, 3):
            self.line([(mid(i), top), (mid(i), 148)], dash=DASH)

        low = 76
        consumers = [
            ("inventory", "склад"),
            ("billing", "расчёты"),
            ("notification", "уведомления"),
            ("analytics", "аналитика"),
        ]
        for i, (name, sub) in enumerate(consumers):
            self.box(col(i), low, bw, bh, name, sub=sub)
            self.line([(mid(i) + 8, 132), (mid(i) + 8, low + bh)], dash=DASH)

        # потребители, которые сами публикуют
        for i in (0, 1):
            self.line([(mid(i) - 14, low + bh), (mid(i) - 14, 132)], dash=DASH)

        # шина реального времени
        self.bus(m, 20, w, 16, "NATS · табло занятости и предупреждения")

        # booking публикует: вниз под ряд блоков, затем правым каналом
        self.line([(mid(2) + 16, top), (mid(2) + 16, 182),
                   (self.width - 6, 182), (self.width - 6, 28),
                   (m + w - 6, 28)], dash=DOT)
        # inventory публикует: левый свободный канал
        self.line([(col(0), low + 6), (6, low + 6), (6, 28), (m + 6, 28)], dash=DOT)
        # notification подписан
        self.line([(mid(2), 36), (mid(2), low)], dash=DOT)

        self.caption(self.width / 2, 6,
                     "сплошная — синхронный вызов   ·   штриховая — доменное событие"
                     "   ·   пунктирная — эфемерное сообщение")


class SyncCalls(Diagram):
    """Ярусы зависимостей: стрелка ведёт от вызывающего к вызываемому.

    Подписи вызовов не дублируются — они приведены в таблице. Схема нужна,
    чтобы увидеть форму графа: он разрежен и ацикличен.
    """

    MARGIN = 18

    def draw(self):
        m = self.MARGIN
        iw = self.width - 2 * m
        bw, bh = 84, 17

        left = m
        centre = m + (iw - bw) / 2
        right = m + iw - bw

        b1, b2, b3, b4 = 136, 96, 56, 16

        self.box(left, b1, bw, bh, "core")
        self.box(right, b1, bw, bh, "catalog")
        self.box(centre, b2, bw, bh, "booking")
        self.box(left, b3, bw, bh, "client")
        self.box(right, b3, bw, bh, "inventory")
        self.box(left, b4, bw, bh, "notification")
        self.box(centre, b4, bw, bh, "billing")
        self.box(right, b4, bw, bh, "analytics")

        # booking → core, booking → catalog
        self.line([(centre + 18, b2 + bh), (centre + 18, b1 + bh / 2),
                   (left + bw, b1 + bh / 2)])
        self.line([(centre + bw - 18, b2 + bh), (centre + bw - 18, b1 + bh / 2),
                   (right, b1 + bh / 2)])

        # client → booking
        self.line([(left + bw, b3 + bh / 2), (centre + 24, b3 + bh / 2),
                   (centre + 24, b2)])

        # inventory → catalog
        self.line([(right + bw / 2, b3 + bh), (right + bw / 2, b1)])

        # billing → booking, billing → client
        self.line([(centre + bw / 2 - 14, b4 + bh), (centre + bw / 2 - 14, b2)])
        self.line([(centre + 16, b4 + bh), (centre + 16, 44),
                   (left + bw / 2 + 16, 44), (left + bw / 2 + 16, b3)])

        # notification → client
        self.line([(left + bw / 2 - 16, b4 + bh), (left + bw / 2 - 16, b3)])

        # analytics → core, дальним правым каналом
        self.line([(right + bw, b4 + bh / 2), (self.width - 6, b4 + bh / 2),
                   (self.width - 6, 166), (left + bw / 2, 166),
                   (left + bw / 2, b1 + bh)])

        self.caption(self.width / 2, 2,
                     "граф ацикличен: ни один сервис не вызывает того, кто вызывает его")


class FanOut(Diagram):
    """Одно событие — три независимых потребителя."""

    def draw(self):
        w = self.width
        bw, bh = 108, 18

        self.box(w / 2 - bw / 2, 116, bw, bh, "booking", sub="закрывает визит")
        self.bus(w / 2 - 130, 78, 260, 16, "appointment.completed")
        self.line([(w / 2, 116), (w / 2, 94)], dash=DASH)

        targets = [
            ("inventory", "списывает материалы"),
            ("billing", "выставляет счёт"),
            ("analytics", "считает выручку"),
        ]
        step = (w - bw) / 2
        for i, (name, sub) in enumerate(targets):
            x = i * step
            self.box(x, 22, bw, bh, name, sub=sub)
            self.line([(w / 2, 78), (x + bw / 2, 62), (x + bw / 2, 40)], dash=DASH)

        self.caption(w / 2, 8, "издатель не знает о потребителях; четвёртый добавляется новым биндингом")


class Sequence(Diagram):
    """Последовательность записи клиента."""

    def draw(self):
        w = self.width
        actors = ["администратор", "gateway", "booking", "core", "catalog", "шина"]
        step = w / len(actors)
        top = self.height - 12
        bottom = 26

        xs = {}
        for i, name in enumerate(actors):
            x = step * i + step / 2
            xs[name] = x
            self.canv.saveState()
            self.canv.setFont(self.mono, 6.8)
            self.canv.setFillColor(INK)
            self.canv.drawCentredString(x, top, name)
            self.canv.setStrokeColor(GREY)
            self.canv.setLineWidth(0.4)
            self.canv.setDash(DOT)
            self.canv.line(x, top - 6, x, bottom)
            self.canv.setDash([])
            self.canv.restoreState()

        rows = [
            ("администратор", "gateway", "POST /appointments", False),
            ("gateway", "booking", "токен проверен", False),
            ("booking", "core", "график специалиста", False),
            ("core", "booking", "смены", True),
            ("booking", "catalog", "длительность и цена", False),
            ("catalog", "booking", "услуга", True),
            ("booking", "booking", "захват слота", False),
            ("booking", "шина", "appointment.created", False),
            ("booking", "администратор", "201 Created", True),
        ]

        y = top - 20
        gap = (y - bottom - 8) / len(rows)
        for src, dst, label, reply in rows:
            x1, x2 = xs[src], xs[dst]
            if src == dst:
                self.canv.saveState()
                self.canv.setStrokeColor(INK)
                self.canv.setFillColor(colors.white)
                self.canv.setLineWidth(0.6)
                self.canv.setDash([])
                self.canv.rect(x1 - 3, y - 5.5, 62, 11, stroke=1, fill=1)
                self.canv.restoreState()
                self.caption(x1 + 28, y - 2, label, grey=False)
            else:
                self.line([(x1, y), (x2, y)], dash=DASH if reply else SOLID, width=0.6)
                mid = (x1 + x2) / 2
                self.caption(mid, y + 3.4, label, grey=False)
            y -= gap

        self.caption(w / 2, 8, "сплошная — вызов · штрих — ответ")


class AccessControl(Diagram):
    """Четыре заслона на пути запроса и коды отказа на каждом."""

    # Левое поле шире обычного: в нём помещается стрелка входа с подписью.
    MARGIN = 34

    def draw(self):
        m = self.MARGIN
        w = self.width - 2 * m
        bw, bh = 84, 20
        gap = (w - 4 * bw) / 3
        y = 62

        def col(i):
            return m + i * (bw + gap)

        stages = [
            ("маршрут", "таблица путей"),
            ("токен", "подпись, срок, iss"),
            ("роль", "требование пути"),
            ("сервис", "запрос исполнен"),
        ]
        for i, (name, sub) in enumerate(stages):
            self.box(col(i), y, bw, bh, name, sub=sub, fill=i < 3)

        self.line([(4, y + bh / 2), (col(0), y + bh / 2)])
        self.caption((4 + m) / 2, y + bh / 2 + 5, "запрос", grey=False)

        for i in range(3):
            self.line([(col(i) + bw, y + bh / 2), (col(i + 1), y + bh / 2)])

        # Отказы уводят вниз: до следующего заслона запрос не доходит.
        for i, code in enumerate(("404 · 405", "401", "403")):
            x = col(i) + bw / 2
            self.line([(x, y), (x, y - 22)], dash=DOT)
            self.caption(x, y - 31, code, size=7, grey=False)

        x = col(2) + bw + gap / 2
        self.line([(x, y + bh / 2 + 4), (x, y + bh + 14)], dash=DOT, arrow=False)
        self.caption(x, y + bh + 18, "личность в заголовках")

        self.caption(self.width / 2, 8,
                     "заслоны проходятся по порядку: отказ на любом прекращает обработку")


class TraceWaterfall(Diagram):
    """Трасса одного запроса: участки работы сервисов на общей шкале."""

    MARGIN = 4
    REPLY_AT = 0.30

    def draw(self):
        label_width = 120
        left = self.MARGIN + label_width
        width = self.width - left - self.MARGIN
        row = 14
        top = self.height - 18

        # (глубина, сервис, операция, начало и конец в долях трассы)
        spans = [
            (0, "gateway", "POST /appointments/*/complete", 0.00, 1.00),
            (1, "booking", "закрытие визита", 0.05, 0.30),
            (2, "booking", "publish appointment.completed", 0.20, 0.27),
            (2, "inventory", "consume", 0.32, 0.62),
            (3, "catalog", "GetConsumptionNorms", 0.38, 0.52),
            (2, "billing", "consume", 0.36, 0.78),
            (3, "booking", "GetAppointment", 0.40, 0.55),
            (2, "analytics", "consume", 0.34, 0.70),
        ]

        for index, (depth, service, operation, begin, end) in enumerate(spans):
            y = top - index * row
            self.caption(self.MARGIN + depth * 8, y, service, size=6.6,
                         anchor="l", grey=False)

            x1 = left + width * begin
            x2 = max(left + width * end, x1 + 4)

            c = self.canv
            c.saveState()
            c.setStrokeColor(INK)
            c.setLineWidth(0.6)
            c.setFillColor(FILL if depth else colors.white)
            c.rect(x1, y - 2.8, x2 - x1, 9, stroke=1, fill=1)
            c.restoreState()

            # Подпись уходит правее полосы, если внутрь не помещается:
            # иначе она вылезает за рамку и наезжает на соседние участки.
            size = 6.2
            text_width = self.canv.stringWidth(operation, self.font, size)
            if text_width + 6 <= x2 - x1:
                self.caption(x1 + 3, y, operation, size=size, anchor="l")
            else:
                self.caption(x2 + 3, y, operation, size=size, anchor="l")

        base = top - len(spans) * row - 6
        reply = left + width * self.REPLY_AT
        self.line([(left, base), (left + width, base)], arrow=False, dash=DOT, width=0.4)
        self.line([(reply, base - 3), (reply, base + 5)], arrow=False, width=0.8)
        self.caption(reply, base - 11, "ответ клиенту отправлен здесь", size=6.2)

        self.caption(self.width / 2, 4,
                     "работа после ответа продолжается: потребители событий "
                     "остаются в той же трассе")
