import math


class ReacquisitionController:
    """Spiral search pattern for re-acquiring a lost beacon."""

    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        step_spacing: float = 70.0,
        arrival_threshold: float = 12.0,
        margin: float = 60.0,
    ) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.step_spacing = step_spacing
        self.arrival_threshold = arrival_threshold
        self.margin = margin

        self.waypoints: list[tuple[float, float]] = []
        self.current_index = 0
        self.active = False
        self.current_waypoint = (screen_width / 2, screen_height / 2)
        self.center = (screen_width / 2, screen_height / 2)

    def activate(
        self,
        last_locked_x: float,
        last_locked_y: float,
        velocity_x: float,
        velocity_y: float,
    ) -> None:
        self.center = (last_locked_x, last_locked_y)
        self.waypoints = self._generate_spiral_waypoints(
            last_locked_x,
            last_locked_y,
            velocity_x,
            velocity_y,
        )
        self.current_index = 0
        self.current_waypoint = self.waypoints[0]
        self.active = True

    def deactivate(self) -> None:
        self.active = False

    def get_next_waypoint(
        self,
        dt: float,
        camera_x: float,
        camera_y: float,
    ) -> tuple[float, float]:
        del dt  # Advance is proximity-based; slew rate is enforced by the camera.
        if not self.active or not self.waypoints:
            return camera_x, camera_y

        waypoint_x, waypoint_y = self.current_waypoint
        distance = math.hypot(waypoint_x - camera_x, waypoint_y - camera_y)
        if (
            distance <= self.arrival_threshold
            and self.current_index < len(self.waypoints) - 1
        ):
            self.current_index += 1
            self.current_waypoint = self.waypoints[self.current_index]

        return self.current_waypoint

    def get_display_waypoints(self) -> list[tuple[float, float]]:
        return list(self.waypoints)

    def get_current_waypoint_index(self) -> int:
        return self.current_index

    def _clamp(self, x: float, y: float) -> tuple[float, float]:
        min_x = self.margin
        max_x = self.screen_width - self.margin
        min_y = self.margin
        max_y = self.screen_height - self.margin
        return (
            min(max(x, min_x), max_x),
            min(max(y, min_y), max_y),
        )

    def _generate_spiral_waypoints(
        self,
        center_x: float,
        center_y: float,
        velocity_x: float,
        velocity_y: float,
    ) -> list[tuple[float, float]]:
        waypoints: list[tuple[float, float]] = []
        speed = math.hypot(velocity_x, velocity_y)
        if speed > 1.0:
            start_angle = math.atan2(velocity_y, velocity_x)
            bias_x = center_x + (velocity_x / speed) * self.step_spacing
            bias_y = center_y + (velocity_y / speed) * self.step_spacing
        else:
            start_angle = 0.0
            bias_x = center_x + self.step_spacing
            bias_y = center_y

        waypoints.append(self._clamp(bias_x, bias_y))

        max_radius = min(
            center_x - self.margin,
            self.screen_width - self.margin - center_x,
            center_y - self.margin,
            self.screen_height - self.margin - center_y,
        )
        max_radius = max(max_radius, self.step_spacing)

        angle = start_angle
        radius = self.step_spacing
        angular_step = self.step_spacing / max(radius, self.step_spacing)
        spiral_growth = self.step_spacing / (2.0 * math.pi)

        while radius <= max_radius:
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            clamped = self._clamp(x, y)
            if not waypoints or self._distance(clamped, waypoints[-1]) > self.step_spacing * 0.4:
                waypoints.append(clamped)

            angle += angular_step
            radius += spiral_growth * angular_step

        if len(waypoints) == 1:
            waypoints.append(self._clamp(center_x, center_y))

        return waypoints

    @staticmethod
    def _distance(
        a: tuple[float, float],
        b: tuple[float, float],
    ) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])
