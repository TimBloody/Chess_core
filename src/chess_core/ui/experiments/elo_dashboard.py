"""Interactive PyQtGraph dashboard for Elo model experiments."""

from __future__ import annotations

from dataclasses import replace

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.rating import (
    EloParameters,
    expected_score,
    rating_gap_for_probability,
    simulate_league,
)


_COLORS = (
    "#4cc9f0",
    "#f72585",
    "#b8f2e6",
    "#ffd166",
    "#9b5de5",
    "#f8961e",
    "#43aa8b",
    "#ef476f",
    "#90be6d",
    "#577590",
)


class MetricCard(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        caption = QLabel(title)
        caption.setObjectName("metricCaption")
        self.value = QLabel("—")
        self.value.setObjectName("metricValue")
        layout.addWidget(caption)
        layout.addWidget(self.value)


class EloDashboard(QWidget):
    """Dashboard that exposes assumptions and visualizes their consequences."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        pg.setConfigOptions(antialias=True, background="#111827", foreground="#cbd5e1")
        self._build_ui()
        self._connect_controls()
        self._refresh()

    def _build_ui(self) -> None:
        self.setObjectName("eloDashboard")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        title_row = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("Лаборатория Elo")
        title.setObjectName("dashboardTitle")
        subtitle = QLabel(
            "Интерактивная модель рейтинговой системы. Все результаты воспроизводимы по seed."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("dashboardSubtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        title_row.addLayout(title_block, 1)
        reset = QPushButton("Сбросить параметры")
        reset.clicked.connect(self._reset)
        title_row.addWidget(reset)
        root.addLayout(title_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._make_controls())
        splitter.addWidget(self._make_results())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 900])
        root.addWidget(splitter, 1)

        self.setStyleSheet(
            """
            QWidget#eloDashboard { background: #0b1220; color: #e5e7eb; }
            QLabel#dashboardTitle { font-size: 26px; font-weight: 700; color: #f8fafc; }
            QLabel#dashboardSubtitle { color: #94a3b8; }
            QGroupBox {
                border: 1px solid #263449; border-radius: 8px; margin-top: 12px;
                padding-top: 9px; font-weight: 600;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QFrame#metricCard { background: #142033; border: 1px solid #263449; border-radius: 9px; }
            QLabel#metricCaption { color: #94a3b8; font-size: 11px; }
            QLabel#metricValue { color: #f8fafc; font-size: 19px; font-weight: 700; }
            QPushButton {
                background: #2563eb; border: 0; border-radius: 6px;
                padding: 7px 12px; color: white; font-weight: 600;
            }
            QPushButton:hover { background: #3b82f6; }
            QSpinBox, QDoubleSpinBox {
                background: #142033; border: 1px solid #334155; border-radius: 5px;
                padding: 4px; color: #f8fafc;
            }
            QTableWidget {
                background: #111827; alternate-background-color: #142033;
                gridline-color: #263449; color: #e5e7eb;
            }
            QHeaderView::section {
                background: #1e293b; color: #cbd5e1; border: 0; padding: 6px;
            }
            QTabWidget::pane { border: 1px solid #263449; }
            QTabBar::tab { background: #142033; padding: 8px 12px; }
            QTabBar::tab:selected { background: #2563eb; }
            """
        )

    def _make_controls(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(280)
        panel = QWidget()
        layout = QVBoxLayout(panel)

        model_group = QGroupBox("Формула Elo")
        model_form = QFormLayout(model_group)
        self.k_factor = self._double_spin(5.0, 80.0, 24.0, 1.0)
        self.scale = self._double_spin(100.0, 800.0, 400.0, 10.0)
        self.provisional = self._double_spin(1.0, 3.0, 1.5, 0.1)
        self.k_decay = self._int_spin(5, 200, 40, 5)
        self.rating_floor = self._double_spin(0.0, 1000.0, 100.0, 50.0)
        model_form.addRow("K-фактор", self.k_factor)
        model_form.addRow("Масштаб кривой D", self.scale)
        model_form.addRow("K новичка ×", self.provisional)
        model_form.addRow("Стабилизация после игр", self.k_decay)
        model_form.addRow("Нижняя граница", self.rating_floor)
        layout.addWidget(model_group)

        pool_group = QGroupBox("Система и турнир")
        pool_form = QFormLayout(pool_group)
        self.player_count = self._int_spin(10, 500, 50, 10)
        self.rounds = self._int_spin(5, 200, 40, 5)
        self.initial_rating = self._double_spin(800.0, 2400.0, 1500.0, 50.0)
        self.strength_spread = self._double_spin(50.0, 1400.0, 600.0, 50.0)
        self.draw_rate = self._double_spin(0.0, 0.7, 0.25, 0.05, decimals=2)
        self.white_advantage = self._double_spin(0.0, 150.0, 35.0, 5.0)
        pool_form.addRow("Игроков", self.player_count)
        pool_form.addRow("Раундов", self.rounds)
        pool_form.addRow("Стартовый рейтинг", self.initial_rating)
        pool_form.addRow("Разброс силы", self.strength_spread)
        pool_form.addRow("Вероятность ничьей", self.draw_rate)
        pool_form.addRow("Преимущество белых", self.white_advantage)
        layout.addWidget(pool_group)

        confidence_group = QGroupBox("Вероятность и повторяемость")
        confidence_form = QFormLayout(confidence_group)
        self.certainty = self._double_spin(0.90, 0.999, 0.99, 0.005, decimals=3)
        self.seed = self._int_spin(0, 999_999, 42, 1)
        confidence_form.addRow("Практическая уверенность", self.certainty)
        confidence_form.addRow("Случайный seed", self.seed)
        layout.addWidget(confidence_group)

        note = QLabel(
            "Важно: конечная разница рейтингов не даёт математически гарантированной "
            "победы. Порог ниже означает выбранную практическую вероятность."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #fbbf24; padding: 8px;")
        layout.addWidget(note)
        layout.addStretch()
        scroll.setWidget(panel)
        return scroll

    def _make_results(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        metrics = QGridLayout()
        self.gap_card = MetricCard("Разница для заданной уверенности")
        self.error_card = MetricCard("Средняя ошибка рейтинга")
        self.leader_card = MetricCard("Лидер системы")
        self.pool_card = MetricCard("Объём симуляции")
        for index, card in enumerate(
            (self.gap_card, self.error_card, self.leader_card, self.pool_card)
        ):
            metrics.addWidget(card, 0, index)
        layout.addLayout(metrics)

        tabs = QTabWidget()
        self.trajectory_plot = self._plot(
            "Динамика рейтинга топ-10", "Раунд", "Elo"
        )
        tabs.addTab(self.trajectory_plot, "Динамика топ-10")
        self.ranking_plot = self._plot(
            "Финальный рейтинг топ-10", "Игрок", "Elo"
        )
        tabs.addTab(self.ranking_plot, "Рейтинг")
        self.probability_plot = self._plot(
            "Ожидаемый результат фаворита", "Разница рейтинга", "Вероятность"
        )
        tabs.addTab(self.probability_plot, "Кривая победы")
        self.sensitivity_plot = self._plot(
            "Чувствительность к K-фактору", "K", "Средняя абсолютная ошибка"
        )
        tabs.addTab(self.sensitivity_plot, "Подбор K")
        layout.addWidget(tabs, 3)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ("#", "Игрок", "Elo", "Истинная сила", "Игры", "П", "Н", "Пор")
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 2)
        return panel

    @staticmethod
    def _plot(title: str, bottom: str, left: str) -> pg.PlotWidget:
        plot = pg.PlotWidget()
        plot.setTitle(title, color="#f8fafc", size="13pt")
        plot.setLabel("bottom", bottom)
        plot.setLabel("left", left)
        plot.showGrid(x=True, y=True, alpha=0.18)
        return plot

    @staticmethod
    def _int_spin(
        minimum: int, maximum: int, value: int, step: int
    ) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        widget.setSingleStep(step)
        return widget

    @staticmethod
    def _double_spin(
        minimum: float,
        maximum: float,
        value: float,
        step: float,
        *,
        decimals: int = 1,
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        widget.setSingleStep(step)
        widget.setDecimals(decimals)
        return widget

    def _connect_controls(self) -> None:
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._refresh)
        for control in self._controls():
            control.valueChanged.connect(lambda _value: self._timer.start())

    def _controls(self) -> tuple[QSpinBox | QDoubleSpinBox, ...]:
        return (
            self.k_factor,
            self.scale,
            self.provisional,
            self.k_decay,
            self.rating_floor,
            self.player_count,
            self.rounds,
            self.initial_rating,
            self.strength_spread,
            self.draw_rate,
            self.white_advantage,
            self.certainty,
            self.seed,
        )

    def _parameters(self) -> EloParameters:
        return EloParameters(
            player_count=self.player_count.value(),
            rounds=self.rounds.value(),
            initial_rating=self.initial_rating.value(),
            strength_spread=self.strength_spread.value(),
            k_factor=self.k_factor.value(),
            scale=self.scale.value(),
            draw_probability=self.draw_rate.value(),
            white_advantage=self.white_advantage.value(),
            provisional_multiplier=self.provisional.value(),
            k_decay_games=self.k_decay.value(),
            rating_floor=self.rating_floor.value(),
            certainty=self.certainty.value(),
            seed=self.seed.value(),
        )

    def _reset(self) -> None:
        defaults = EloParameters()
        values = (
            defaults.k_factor,
            defaults.scale,
            defaults.provisional_multiplier,
            defaults.k_decay_games,
            defaults.rating_floor,
            defaults.player_count,
            defaults.rounds,
            defaults.initial_rating,
            defaults.strength_spread,
            defaults.draw_probability,
            defaults.white_advantage,
            defaults.certainty,
            defaults.seed,
        )
        for control, value in zip(self._controls(), values, strict=True):
            control.blockSignals(True)
            control.setValue(value)
            control.blockSignals(False)
        self._refresh()

    def _refresh(self) -> None:
        parameters = self._parameters()
        result = simulate_league(parameters)
        gap = rating_gap_for_probability(
            parameters.certainty, scale=parameters.scale
        )
        leader = result.top_ten[0]
        games = sum(player.games for player in result.players) // 2
        self.gap_card.value.setText(
            f"{gap:.0f} Elo → {parameters.certainty:.1%}"
        )
        self.error_card.value.setText(f"{result.rating_error:.1f} Elo")
        self.leader_card.value.setText(f"{leader.name}: {leader.rating:.0f}")
        self.pool_card.value.setText(f"{parameters.player_count} игроков · {games} партий")
        self._draw_trajectories(result)
        self._draw_ranking(result)
        self._draw_probability(parameters, gap)
        self._draw_sensitivity(parameters)
        self._fill_table(result)

    def _draw_trajectories(self, result) -> None:
        self.trajectory_plot.clear()
        for index, player in enumerate(result.top_ten):
            values = result.history[player.player_id]
            self.trajectory_plot.plot(
                range(len(values)),
                values,
                pen=pg.mkPen(_COLORS[index], width=2),
                name=player.name,
            )

    def _draw_ranking(self, result) -> None:
        self.ranking_plot.clear()
        top = tuple(reversed(result.top_ten))
        positions = list(range(1, len(top) + 1))
        baseline = min(player.rating for player in top) - 40.0
        heights = [player.rating - baseline for player in top]
        bars = pg.BarGraphItem(
            x=positions,
            height=heights,
            y0=baseline,
            width=0.72,
            brushes=[QColor(_COLORS[index]) for index in range(len(top))],
        )
        self.ranking_plot.addItem(bars)
        axis = self.ranking_plot.getAxis("bottom")
        axis.setTicks([[(pos, player.name) for pos, player in zip(positions, top)]])

    def _draw_probability(self, parameters: EloParameters, gap: float) -> None:
        self.probability_plot.clear()
        extent = max(800, int(gap * 1.15))
        differences = list(range(-extent, extent + 1, max(5, extent // 100)))
        probabilities = [
            expected_score(diff, 0.0, scale=parameters.scale)
            for diff in differences
        ]
        self.probability_plot.plot(
            differences, probabilities, pen=pg.mkPen("#4cc9f0", width=3)
        )
        threshold = pg.InfiniteLine(
            pos=gap,
            angle=90,
            pen=pg.mkPen("#fbbf24", width=2, style=Qt.PenStyle.DashLine),
            label=f"{parameters.certainty:.1%}: +{gap:.0f}",
            labelOpts={"color": "#fbbf24", "position": 0.88},
        )
        self.probability_plot.addItem(threshold)
        self.probability_plot.setYRange(0.0, 1.0, padding=0.02)

    def _draw_sensitivity(self, parameters: EloParameters) -> None:
        self.sensitivity_plot.clear()
        factors = (0.35, 0.55, 0.75, 1.0, 1.3, 1.65, 2.0)
        k_values = [max(1.0, parameters.k_factor * factor) for factor in factors]
        errors = [
            simulate_league(replace(parameters, k_factor=value)).rating_error
            for value in k_values
        ]
        self.sensitivity_plot.plot(
            k_values,
            errors,
            pen=pg.mkPen("#f72585", width=3),
            symbol="o",
            symbolBrush="#ffd166",
            symbolSize=8,
        )
        current = pg.InfiniteLine(
            pos=parameters.k_factor,
            angle=90,
            pen=pg.mkPen("#94a3b8", style=Qt.PenStyle.DotLine),
            label=f"K={parameters.k_factor:g}",
            labelOpts={"color": "#cbd5e1"},
        )
        self.sensitivity_plot.addItem(current)

    def _fill_table(self, result) -> None:
        self.table.setRowCount(len(result.top_ten))
        for row, player in enumerate(result.top_ten):
            values = (
                player.rank,
                player.name,
                f"{player.rating:.1f}",
                f"{player.true_strength:.1f}",
                player.games,
                player.wins,
                player.draws,
                player.losses,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column != 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if row == 0:
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QColor("#ffd166"))
                self.table.setItem(row, column, item)
