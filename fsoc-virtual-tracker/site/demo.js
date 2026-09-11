(() => {
  const canvas = document.getElementById("sim");
  const ctx = canvas.getContext("2d");
  const hud = document.getElementById("hud");
  const stateBadge = document.getElementById("stateBadge");

  const W = canvas.width;
  const H = canvas.height;
  const FOV_W = 280;
  const FOV_H = 210;

  const PRESETS = {
    calm: { turb: 0, vib: 0, noise: 0.05 },
    uav: { turb: 4, vib: 8, noise: 0.2 },
    stress: { turb: 7, vib: 15, noise: 0.35 },
  };

  const state = {
    t: 0,
    beacon: { x: W * 0.55, y: H * 0.42, vx: 42, vy: 18 },
    cam: { x: W * 0.5, y: H * 0.5 },
    est: { x: W * 0.5, y: H * 0.5, vx: 0, vy: 0 },
    tracking: "LOCKED",
    misses: 0,
    readiness: 0.85,
    reacq: 0,
    blind: 0,
    waypoints: [],
    wpIndex: 0,
    searchActive: false,
    det: null,
    fine: false,
  };

  const els = {
    scenario: document.getElementById("scenario"),
    scenarioLabel: document.getElementById("scenarioLabel"),
    turb: document.getElementById("turb"),
    vib: document.getElementById("vib"),
    noise: document.getElementById("noise"),
    turbVal: document.getElementById("turbVal"),
    vibVal: document.getElementById("vibVal"),
    noiseVal: document.getElementById("noiseVal"),
    detector: document.getElementById("detector"),
    btnBlind: document.getElementById("btnBlind"),
    btnReset: document.getElementById("btnReset"),
  };

  function clamp(v, a, b) {
    return Math.max(a, Math.min(b, v));
  }

  function applyPreset(name) {
    const p = PRESETS[name] || PRESETS.uav;
    els.turb.value = p.turb;
    els.vib.value = p.vib;
    els.noise.value = p.noise;
    els.scenarioLabel.textContent = name.toUpperCase();
    syncLabels();
  }

  function syncLabels() {
    els.turbVal.textContent = Number(els.turb.value).toFixed(1);
    els.vibVal.textContent = Number(els.vib.value).toFixed(1);
    els.noiseVal.textContent = Number(els.noise.value).toFixed(2);
  }

  function buildRaster(cx, cy) {
    const pts = [];
    const step = 70;
    let x0 = clamp(cx - 210, 40, W - 40);
    let y0 = clamp(cy - 150, 40, H - 40);
    let rows = 5;
    let cols = 7;
    for (let r = 0; r < rows; r++) {
      const y = y0 + r * step;
      if (r % 2 === 0) {
        for (let c = 0; c < cols; c++) pts.push({ x: x0 + c * step, y });
      } else {
        for (let c = cols - 1; c >= 0; c--) pts.push({ x: x0 + c * step, y });
      }
    }
    return pts.map((p) => ({
      x: clamp(p.x, 30, W - 30),
      y: clamp(p.y, 30, H - 30),
    }));
  }

  function resetSim() {
    state.t = 0;
    state.beacon = { x: W * 0.55, y: H * 0.42, vx: 42, vy: 18 };
    state.cam = { x: W * 0.5, y: H * 0.5 };
    state.est = { x: W * 0.5, y: H * 0.5, vx: 0, vy: 0 };
    state.tracking = "LOCKED";
    state.misses = 0;
    state.readiness = 0.85;
    state.reacq = 0;
    state.blind = 0;
    state.waypoints = [];
    state.wpIndex = 0;
    state.searchActive = false;
    state.fine = false;
    setBadge("LOCKED");
  }

  function setBadge(s) {
    stateBadge.textContent = s;
    stateBadge.className =
      "badge " +
      (s === "LOCKED" ? "badge-ok" : s === "COASTING" ? "badge-warn" : "badge-bad");
  }

  function detect(dt) {
    const turb = Number(els.turb.value);
    const noise = Number(els.noise.value);
    const fusion = els.detector.value === "fusion";
    if (state.blind > 0) {
      state.blind -= dt;
      return null;
    }

    // Beacon must be roughly in FOV to be "seen"
    const inFov =
      Math.abs(state.beacon.x - state.cam.x) < FOV_W * 0.48 &&
      Math.abs(state.beacon.y - state.cam.y) < FOV_H * 0.48;

    if (!inFov) return null;

    // Noise / turbulence make classical miss more often
    const missProb = clamp(0.02 + noise * 0.55 + turb * 0.025 - (fusion ? 0.12 : 0), 0.01, 0.85);
    if (Math.random() < missProb) return null;

    const jitter = (noise * 18 + turb * 1.2) * (fusion ? 0.55 : 1.0);
    return {
      x: state.beacon.x + (Math.random() - 0.5) * jitter,
      y: state.beacon.y + (Math.random() - 0.5) * jitter,
    };
  }

  function update(dt) {
    state.t += dt;
    const vib = Number(els.vib.value);
    const turb = Number(els.turb.value);

    // Beacon motion (circular-ish + wander)
    const ang = state.t * 0.55;
    const cx = W * 0.5 + Math.sin(ang * 0.35) * 90;
    const cy = H * 0.48 + Math.cos(ang * 0.28) * 55;
    const wander = turb * 2.5;
    state.beacon.x = cx + Math.cos(ang) * 160 + Math.sin(state.t * 3.1) * wander;
    state.beacon.y = cy + Math.sin(ang * 1.2) * 95 + Math.cos(state.t * 2.7) * wander;
    state.beacon.x = clamp(state.beacon.x, 40, W - 40);
    state.beacon.y = clamp(state.beacon.y, 40, H - 40);

    // Platform vibration on camera
    const vibOffX = Math.sin(state.t * 11.0) * vib * 0.35;
    const vibOffY = Math.cos(state.t * 9.5) * vib * 0.35;

    const meas = detect(dt);
    state.det = meas;

    if (meas) {
      state.misses = 0;
      // Simple CV Kalman-ish blend
      const ax = 0.35;
      state.est.vx = (meas.x - state.est.x) / Math.max(dt, 1e-3);
      state.est.vy = (meas.y - state.est.y) / Math.max(dt, 1e-3);
      state.est.x += (meas.x - state.est.x) * ax;
      state.est.y += (meas.y - state.est.y) * ax;
      if (state.searchActive) {
        state.searchActive = false;
        state.waypoints = [];
        state.reacq += 1;
      }
      state.tracking = "LOCKED";
    } else {
      state.misses += 1;
      // Coast on estimate
      state.est.x += state.est.vx * dt * 0.15;
      state.est.y += state.est.vy * dt * 0.15;
      if (state.misses < 18) state.tracking = "COASTING";
      else {
        if (state.tracking !== "LOST") {
          state.tracking = "LOST";
          state.searchActive = true;
          state.waypoints = buildRaster(state.est.x, state.est.y);
          state.wpIndex = 0;
        }
      }
    }
    setBadge(state.tracking);

    // Camera control
    let targetX = state.est.x;
    let targetY = state.est.y;
    if (state.tracking === "LOST" && state.waypoints.length) {
      const wp = state.waypoints[state.wpIndex];
      targetX = wp.x;
      targetY = wp.y;
      const d = Math.hypot(state.cam.x - wp.x, state.cam.y - wp.y);
      if (d < 14) state.wpIndex = (state.wpIndex + 1) % state.waypoints.length;
    }

    const errX = targetX - state.cam.x;
    const errY = targetY - state.cam.y;
    const dist = Math.hypot(errX, errY);
    const slew = state.tracking === "LOST" ? 220 : 160;
    const step = Math.min(dist, slew * dt);
    if (dist > 1e-3) {
      state.cam.x += (errX / dist) * step;
      state.cam.y += (errY / dist) * step;
    }
    state.cam.x = clamp(state.cam.x + vibOffX * dt * 8, FOV_W / 2, W - FOV_W / 2);
    state.cam.y = clamp(state.cam.y + vibOffY * dt * 8, FOV_H / 2, H - FOV_H / 2);

    // Readiness heuristic
    const pxErr = Math.hypot(state.est.x - state.beacon.x, state.est.y - state.beacon.y);
    let ready =
      0.45 * clamp(1 - pxErr / 80, 0, 1) +
      0.25 * clamp(1 - turb / 10, 0, 1) +
      0.15 * clamp(1 - Number(els.noise.value) / 0.6, 0, 1) +
      0.15 * (state.tracking === "LOCKED" ? 1 : state.tracking === "COASTING" ? 0.4 : 0);
    if (state.tracking === "LOST") ready = 0;
    state.readiness = state.readiness * 0.85 + ready * 0.15;
    state.fine = state.tracking === "LOCKED" && state.readiness >= 0.7 && pxErr < 40;
  }

  function draw() {
    const turb = Number(els.turb.value);
    const noise = Number(els.noise.value);

    ctx.fillStyle = "#071018";
    ctx.fillRect(0, 0, W, H);

    // Stars
    ctx.fillStyle = "#1c2a38";
    for (let i = 0; i < 80; i++) {
      const sx = (i * 97 + Math.floor(state.t * 3)) % W;
      const sy = (i * 53) % H;
      ctx.fillRect(sx, sy, 2, 2);
    }

    // Raster path
    if (state.searchActive && state.waypoints.length) {
      ctx.strokeStyle = "rgba(255,140,40,0.55)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      state.waypoints.forEach((p, i) => {
        if (i === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
      });
      ctx.stroke();
    }

    // Beacon glow (scintillation proxy)
    const scint = 0.65 + 0.35 * Math.sin(state.t * (4 + turb));
    const radius = 7 + turb * 0.35;
    const g = ctx.createRadialGradient(
      state.beacon.x,
      state.beacon.y,
      0,
      state.beacon.x,
      state.beacon.y,
      radius * 4
    );
    g.addColorStop(0, `rgba(255,255,210,${0.95 * scint})`);
    g.addColorStop(0.35, `rgba(120,200,255,${0.45 * scint})`);
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(state.beacon.x, state.beacon.y, radius * 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = `rgba(255,255,255,${0.85 * scint})`;
    ctx.beginPath();
    ctx.arc(state.beacon.x, state.beacon.y, radius, 0, Math.PI * 2);
    ctx.fill();

    // Noise speckles in FOV
    if (noise > 0.05) {
      const n = Math.floor(noise * 120);
      ctx.fillStyle = "rgba(180,180,180,0.25)";
      for (let i = 0; i < n; i++) {
        const x = state.cam.x - FOV_W / 2 + Math.random() * FOV_W;
        const y = state.cam.y - FOV_H / 2 + Math.random() * FOV_H;
        ctx.fillRect(x, y, 2, 2);
      }
    }

    // FOV
    ctx.strokeStyle = "#3ddc84";
    ctx.lineWidth = 2;
    ctx.strokeRect(state.cam.x - FOV_W / 2, state.cam.y - FOV_H / 2, FOV_W, FOV_H);
    ctx.fillStyle = "rgba(61,220,132,0.05)";
    ctx.fillRect(state.cam.x - FOV_W / 2, state.cam.y - FOV_H / 2, FOV_W, FOV_H);

    // Detection + estimate
    if (state.det) {
      ctx.strokeStyle = "#40e0ff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(state.det.x - 8, state.det.y);
      ctx.lineTo(state.det.x + 8, state.det.y);
      ctx.moveTo(state.det.x, state.det.y - 8);
      ctx.lineTo(state.det.x, state.det.y + 8);
      ctx.stroke();
    }
    ctx.strokeStyle = "#ff4fd8";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(state.est.x, state.est.y, 10, 0, Math.PI * 2);
    ctx.stroke();

    // Readiness bar
    const bx = W - 170;
    const by = 18;
    ctx.fillStyle = "rgba(0,0,0,0.45)";
    ctx.fillRect(bx - 8, by - 8, 158, 36);
    ctx.fillStyle = "#8899aa";
    ctx.font = "12px Consolas, monospace";
    ctx.fillText("Link Readiness", bx, by + 4);
    ctx.fillStyle = "#233";
    ctx.fillRect(bx, by + 10, 140, 8);
    const readyColor =
      state.readiness >= 0.7 ? "#3ddc84" : state.readiness >= 0.3 ? "#e6b422" : "#ff5a4f";
    ctx.fillStyle = readyColor;
    ctx.fillRect(bx, by + 10, 140 * clamp(state.readiness, 0, 1), 8);

    if (state.fine) {
      ctx.fillStyle = "#3ddc84";
      ctx.fillText("FINE 4-QD", bx, by + 42);
    }

    const pxErr = Math.hypot(state.est.x - state.beacon.x, state.est.y - state.beacon.y);
    const urad = pxErr * 6.25;
    hud.textContent =
      `state: ${state.tracking}\n` +
      `detector: ${els.detector.value}\n` +
      `err: ${pxErr.toFixed(1)} px (~${urad.toFixed(0)} µrad)\n` +
      `readiness: ${state.readiness.toFixed(2)}\n` +
      `re-acq: ${state.reacq}` +
      (state.blind > 0 ? `\nBLIND ${state.blind.toFixed(1)}s` : "");
  }

  let last = performance.now();
  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    update(dt);
    draw();
    requestAnimationFrame(frame);
  }

  els.scenario.addEventListener("change", () => {
    applyPreset(els.scenario.value);
  });
  ["turb", "vib", "noise"].forEach((id) => {
    els[id].addEventListener("input", syncLabels);
  });
  els.btnBlind.addEventListener("click", () => {
    state.blind = 1.2;
  });
  els.btnReset.addEventListener("click", resetSim);

  applyPreset("uav");
  resetSim();
  requestAnimationFrame(frame);
})();
