import math

MODE_SPIRAL = "spiral"
MODE_RASTER = "raster"


class ReacquisitionController:
    """Spiral + raster acquisition search for a lost beacon."""

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
        self.mode = MODE_SPIRAL
        self.spiral_restarts = 0
        self._last_velocity = (0.0, 0.0)
        self._lost_time = 0.0

    def activate(
        self,
        last_locked_x: float,
        last_locked_y: float,
        velocity_x: float,
        velocity_y: float,
        lost_time: float = 0.0,
        *,
        force_raster: bool = False,
        uncertainty_radius_px: float | None = None,
    ) -> None:
        del force_raster  # Raster is default — spiral corner-traps under high error.
        self._last_velocity = (velocity_x, velocity_y)
        self._lost_time = lost_time
        self.spiral_restarts = 0
        # Scale search spacing from Kalman 1-sigma (clamped).
        if uncertainty_radius_px is not None and uncertainty_radius_px > 0.0:
            self.step_spacing = max(40.0, min(160.0, 0.85 * uncertainty_radius_px))

        center_x, center_y = self._search_center(
            last_locked_x, last_locked_y, velocity_x, velocity_y, lost_time
        )
        self.center = (center_x, center_y)
        self.mode = MODE_RASTER
        self._build_raster_waypoints()
        self._snap_index_to_nearest(center_x, center_y)
        self.active = True

    def deactivate(self) -> None:
        self.active = False

    def get_next_waypoint(
        self,
        dt: float,
        camera_x: float,
        camera_y: float,
        lost_time: float = 0.0,
    ) -> tuple[float, float]:
        del dt
        self._lost_time = lost_time
        if not self.active or not self.waypoints:
            return camera_x, camera_y

        waypoint_x, waypoint_y = self.current_waypoint
        distance = math.hypot(waypoint_x - camera_x, waypoint_y - camera_y)

        if (
            self.current_index >= len(self.waypoints) - 1
            and distance <= self.arrival_threshold
        ):
            self._restart_search(camera_x, camera_y)

        elif (
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

    def predict_target(
        self,
        last_x: float,
        last_y: float,
        velocity_x: float,
        velocity_y: float,
        lost_time: float,
    ) -> tuple[float, float]:
        """Extrapolate last lock using constant velocity (no ground truth)."""
        lead = min(max(lost_time, 0.0), 5.0)
        return self._clamp(
            last_x + velocity_x * lead,
            last_y + velocity_y * lead,
        )

    def _restart_search(self, camera_x: float, camera_y: float) -> None:
        self.spiral_restarts += 1
        vx, vy = self._last_velocity
        center_x, center_y = self._search_center(
            camera_x, camera_y, vx, vy, self._lost_time
        )
        self.center = (center_x, center_y)
        self.mode = MODE_RASTER
        self._build_raster_waypoints()
        self._snap_index_to_nearest(center_x, center_y)

    def _search_center(
        self,
        x: float,
        y: float,
        velocity_x: float,
        velocity_y: float,
        lost_time: float,
    ) -> tuple[float, float]:
        pred_x = x + velocity_x * min(max(lost_time, 0.0), 4.0)
        pred_y = y + velocity_y * min(max(lost_time, 0.0), 4.0)
        pred_x, pred_y = self._clamp(pred_x, pred_y)

        edge_clear = min(
            pred_x - self.margin,
            self.screen_width - self.margin - pred_x,
            pred_y - self.margin,
            self.screen_height - self.margin - pred_y,
        )
        if edge_clear < 150.0:
            scene_cx = self.screen_width / 2.0
            scene_cy = self.screen_height / 2.0
            blend = 1.0 - max(edge_clear, 0.0) / 150.0
            pred_x = pred_x * (1.0 - blend) + scene_cx * blend
            pred_y = pred_y * (1.0 - blend) + scene_cy * blend

        return self._clamp(pred_x, pred_y)

    def _build_raster_waypoints(self) -> None:
        """Serpentine grid covering the full scene (corner-safe)."""
        step = self.step_spacing * (1.35 if self._lost_time > 4.0 else 1.2)
        waypoints: list[tuple[float, float]] = []
        y = self.margin
        left_to_right = True
        while y <= self.screen_height - self.margin:
            if left_to_right:
                x = self.margin
                while x <= self.screen_width - self.margin:
                    waypoints.append((x, y))
                    x += step
            else:
                x = self.screen_width - self.margin
                while x >= self.margin:
                    waypoints.append((x, y))
                    x -= step
            y += step
            left_to_right = not left_to_right
        self.waypoints = waypoints or [self._clamp(self.screen_width / 2, self.screen_height / 2)]
        self.current_index = 0
        self.current_waypoint = self.waypoints[0]

    def _snap_index_to_nearest(self, x: float, y: float) -> None:
        if not self.waypoints:
            return
        best = 0
        best_dist = float("inf")
        for index, (wx, wy) in enumerate(self.waypoints):
            dist = math.hypot(wx - x, wy - y)
            if dist < best_dist:
                best_dist = dist
                best = index
        self.current_index = best
        self.current_waypoint = self.waypoints[best]

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

        # Symmetric radius — avoids corner collapse when center is near an edge.
        max_radius = max(
            min(center_x - self.margin, self.screen_width - self.margin - center_x),
            min(center_y - self.margin, self.screen_height - self.margin - center_y),
            self.step_spacing,
        )
        scene_cap = min(self.screen_width, self.screen_height) / 2.0 - self.margin
        max_radius = min(max_radius * 2.2, scene_cap)

        angle = start_angle
        radius = self.step_spacing
        angular_step = self.step_spacing / max(radius, self.step_spacing)
        spiral_growth = self.step_spacing / (2.0 * math.pi)
        stagnant = 0

        while radius <= max_radius:
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            clamped = self._clamp(x, y)
            if not waypoints or self._distance(clamped, waypoints[-1]) > self.step_spacing * 0.35:
                waypoints.append(clamped)
                stagnant = 0
            else:
                stagnant += 1
                if stagnant > 40:
                    break

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
