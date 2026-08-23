"""Pygame-native sliders and button groups for live demo controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pygame

from disturbance.disturbance import SensorNoiseModel, TurbulenceModel, VibrationModel
from scene.scene import TRAJECTORY_CIRCULAR, TRAJECTORY_LINEAR, TRAJECTORY_RANDOM_WALK
from ui.scenarios import PRESET_ORDER, PRESETS, ScenarioPreset

CONTROL_PANEL_HEIGHT = 168
PANEL_BG = (18, 22, 34)
PANEL_BORDER = (70, 80, 105)
SLIDER_TRACK = (45, 52, 68)
SLIDER_FILL = (90, 170, 230)
SLIDER_HANDLE = (210, 225, 245)
BUTTON_IDLE = (42, 48, 62)
BUTTON_ACTIVE = (72, 130, 200)
BUTTON_TEXT = (220, 228, 240)
LABEL_COLOR = (180, 190, 210)


@dataclass
class Slider:
    label: str
    rect: pygame.Rect
    min_value: float
    max_value: float
    value: float
    format_string: str = "{:.2f}"

    def __post_init__(self) -> None:
        self._dragging = False

    def set_value(self, value: float) -> None:
        self.value = max(self.min_value, min(self.max_value, value))

    def handle_event(self, event: pygame.event.Event) -> bool:
        track_rect = self._track_rect()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if track_rect.collidepoint(event.pos) or self._handle_rect().collidepoint(event.pos):
                self._dragging = True
                self._set_from_mouse(event.pos[0])
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._dragging:
                self._dragging = False
                return True
        elif event.type == pygame.MOUSEMOTION and self._dragging:
            self._set_from_mouse(event.pos[0])
            return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        label_surface = font.render(self.label, True, LABEL_COLOR)
        surface.blit(label_surface, (self.rect.x, self.rect.y))

        track_rect = self._track_rect()
        pygame.draw.rect(surface, SLIDER_TRACK, track_rect, border_radius=4)

        fill_width = int(round(track_rect.width * self._normalized()))
        if fill_width > 0:
            fill_rect = pygame.Rect(track_rect.x, track_rect.y, fill_width, track_rect.height)
            pygame.draw.rect(surface, SLIDER_FILL, fill_rect, border_radius=4)

        handle_rect = self._handle_rect()
        pygame.draw.rect(surface, SLIDER_HANDLE, handle_rect, border_radius=3)
        pygame.draw.rect(surface, PANEL_BORDER, track_rect, 1, border_radius=4)

        value_surface = font.render(self.format_string.format(self.value), True, BUTTON_TEXT)
        surface.blit(
            value_surface,
            (self.rect.right - value_surface.get_width(), self.rect.y),
        )

    def _track_rect(self) -> pygame.Rect:
        return pygame.Rect(self.rect.x, self.rect.y + 22, self.rect.width, 14)

    def _handle_rect(self) -> pygame.Rect:
        track_rect = self._track_rect()
        handle_x = track_rect.x + int(round((track_rect.width - 10) * self._normalized()))
        return pygame.Rect(handle_x, track_rect.y - 2, 10, track_rect.height + 4)

    def _normalized(self) -> float:
        span = self.max_value - self.min_value
        if span <= 0.0:
            return 0.0
        return (self.value - self.min_value) / span

    def _set_from_mouse(self, mouse_x: int) -> None:
        track_rect = self._track_rect()
        ratio = (mouse_x - track_rect.x) / max(track_rect.width, 1)
        ratio = max(0.0, min(1.0, ratio))
        self.value = self.min_value + ratio * (self.max_value - self.min_value)


@dataclass
class ButtonGroup:
    label: str
    rect: pygame.Rect
    options: list[tuple[str, str]]
    selected_index: int = 0

    def __post_init__(self) -> None:
        self._button_rects: list[pygame.Rect] = []
        self._layout_buttons()

    @property
    def selected_value(self) -> str:
        return self.options[self.selected_index][1]

    def set_selected_value(self, value: str) -> None:
        for index, (_, option_value) in enumerate(self.options):
            if option_value == value:
                self.selected_index = index
                return

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, button_rect in enumerate(self._button_rects):
                if button_rect.collidepoint(event.pos):
                    self.selected_index = index
                    return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        label_surface = font.render(self.label, True, LABEL_COLOR)
        surface.blit(label_surface, (self.rect.x, self.rect.y))

        for index, (label, _) in enumerate(self.options):
            button_rect = self._button_rects[index]
            color = BUTTON_ACTIVE if index == self.selected_index else BUTTON_IDLE
            pygame.draw.rect(surface, color, button_rect, border_radius=4)
            pygame.draw.rect(surface, PANEL_BORDER, button_rect, 1, border_radius=4)
            text_surface = font.render(label, True, BUTTON_TEXT)
            text_rect = text_surface.get_rect(center=button_rect.center)
            surface.blit(text_surface, text_rect)

    def _layout_buttons(self) -> None:
        self._button_rects = []
        count = len(self.options)
        if count == 0:
            return
        gap = 6
        button_y = self.rect.y + 24
        button_height = 28
        total_gap = gap * (count - 1)
        button_width = (self.rect.width - total_gap) // count
        x = self.rect.x
        for _ in self.options:
            self._button_rects.append(pygame.Rect(x, button_y, button_width, button_height))
            x += button_width + gap


class ControlPanel:
    """Bottom-strip controls for disturbances, slew rate, trajectory, and detector."""

    def __init__(self, screen_width: int, panel_y: int) -> None:
        self.rect = pygame.Rect(0, panel_y, screen_width, CONTROL_PANEL_HEIGHT)
        self.font = pygame.font.SysFont(None, 20)
        slider_width = (screen_width - 50) // 4
        slider_height = 40
        top_y = panel_y + 14
        left = 12
        gap = 10

        self.turbulence_slider = Slider(
            "Turbulence",
            pygame.Rect(left, top_y, slider_width, slider_height),
            0.0,
            TurbulenceModel.MAX_STRENGTH,
            0.0,
        )
        left += slider_width + gap
        self.vibration_slider = Slider(
            "Vibration",
            pygame.Rect(left, top_y, slider_width, slider_height),
            0.0,
            VibrationModel.MAX_AMPLITUDE,
            0.0,
        )
        left += slider_width + gap
        self.sensor_noise_slider = Slider(
            "Sensor Noise",
            pygame.Rect(left, top_y, slider_width, slider_height),
            0.0,
            SensorNoiseModel.MAX_NOISE_LEVEL,
            0.0,
            format_string="{:.2f}",
        )
        left += slider_width + gap
        self.slew_rate_slider = Slider(
            "Slew Rate",
            pygame.Rect(left, top_y, slider_width, slider_height),
            30.0,
            200.0,
            90.0,
            format_string="{:.0f}",
        )

        group_width = (screen_width - 36) // 2
        group_y = panel_y + 68
        self.trajectory_group = ButtonGroup(
            "Trajectory",
            pygame.Rect(12, group_y, group_width, 56),
            [
                ("Linear", TRAJECTORY_LINEAR),
                ("Circular", TRAJECTORY_CIRCULAR),
                ("Random", TRAJECTORY_RANDOM_WALK),
            ],
            selected_index=1,
        )
        self.detector_group = ButtonGroup(
            "Detector",
            pygame.Rect(24 + group_width, group_y, group_width, 56),
            [
                ("Classical", "classical"),
                ("AI", "ai"),
            ],
            selected_index=0,
        )

        preset_width = screen_width - 24
        self.scenario_group = ButtonGroup(
            "Scenario",
            pygame.Rect(12, panel_y + 118, preset_width, 44),
            [(PRESETS[key].label, key) for key in PRESET_ORDER],
            selected_index=0,
        )

        self._sliders = (
            self.turbulence_slider,
            self.vibration_slider,
            self.sensor_noise_slider,
            self.slew_rate_slider,
        )
        self._groups = (self.trajectory_group, self.detector_group, self.scenario_group)
        self._previous_trajectory = self.trajectory_group.selected_value
        self._previous_detector = self.detector_group.selected_value
        self._previous_scenario = self.scenario_group.selected_value

    def contains_point(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            if hasattr(event, "pos") and not self.contains_point(event.pos):
                if event.type == pygame.MOUSEBUTTONUP:
                    for slider in self._sliders:
                        slider._dragging = False
                elif event.type != pygame.MOUSEMOTION:
                    return False
                elif not any(slider._dragging for slider in self._sliders):
                    return False

        for slider in self._sliders:
            if slider.handle_event(event):
                return True
        for group in self._groups:
            if group.handle_event(event):
                return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, PANEL_BG, self.rect)
        pygame.draw.line(
            surface,
            PANEL_BORDER,
            (self.rect.left, self.rect.top),
            (self.rect.right, self.rect.top),
            2,
        )
        for slider in self._sliders:
            slider.draw(surface, self.font)
        for group in self._groups:
            group.draw(surface, self.font)

    def get_preset(self, scenario_id: str) -> ScenarioPreset:
        return PRESETS[scenario_id]

    def apply_preset(self, scenario_id: str) -> ScenarioPreset:
        preset = PRESETS[scenario_id]
        self.turbulence_slider.set_value(preset.turbulence)
        self.vibration_slider.set_value(preset.vibration)
        self.sensor_noise_slider.set_value(preset.sensor_noise)
        self.slew_rate_slider.set_value(preset.slew_rate)
        self.trajectory_group.set_selected_value(preset.trajectory)
        self.scenario_group.set_selected_value(scenario_id)
        self._previous_scenario = scenario_id
        self._previous_trajectory = preset.trajectory
        return preset

    def acknowledge_scenario(self, scenario_id: str) -> None:
        self.scenario_group.set_selected_value(scenario_id)
        self._previous_scenario = scenario_id

    def consume_scenario_changes(
        self,
        on_preset_applied: Callable[[ScenarioPreset], None],
    ) -> None:
        if self.scenario_group.selected_value != self._previous_scenario:
            preset = self.apply_preset(self.scenario_group.selected_value)
            on_preset_applied(preset)

    def apply_models(
        self,
        turbulence: TurbulenceModel,
        vibration: VibrationModel,
        sensor_noise: SensorNoiseModel,
        camera,
    ) -> None:
        turbulence.strength = self.turbulence_slider.value
        vibration.amplitude = self.vibration_slider.value
        sensor_noise.noise_level = self.sensor_noise_slider.value
        camera.max_slew_rate = self.slew_rate_slider.value

    def sync_from_models(
        self,
        turbulence: TurbulenceModel,
        vibration: VibrationModel,
        sensor_noise: SensorNoiseModel,
        camera,
        trajectory: str,
        detector_name: str,
    ) -> None:
        self.turbulence_slider.set_value(turbulence.strength)
        self.vibration_slider.set_value(vibration.amplitude)
        self.sensor_noise_slider.set_value(sensor_noise.noise_level)
        self.slew_rate_slider.set_value(camera.max_slew_rate)
        self.trajectory_group.set_selected_value(trajectory)
        self.detector_group.set_selected_value(detector_name)
        self._previous_trajectory = self.trajectory_group.selected_value
        self._previous_detector = self.detector_group.selected_value

    def acknowledge_trajectory(self, trajectory: str) -> None:
        self.trajectory_group.set_selected_value(trajectory)
        self._previous_trajectory = trajectory

    def acknowledge_detector(self, detector_name: str) -> None:
        self.detector_group.set_selected_value(detector_name)
        self._previous_detector = detector_name

    def consume_selection_changes(
        self,
        on_trajectory_change: Callable[[str], None],
        on_detector_change: Callable[[str], bool],
    ) -> None:
        if self.trajectory_group.selected_value != self._previous_trajectory:
            self._previous_trajectory = self.trajectory_group.selected_value
            on_trajectory_change(self._previous_trajectory)

        if self.detector_group.selected_value != self._previous_detector:
            accepted = on_detector_change(self.detector_group.selected_value)
            if accepted:
                self._previous_detector = self.detector_group.selected_value
            else:
                self.detector_group.set_selected_value(self._previous_detector)
