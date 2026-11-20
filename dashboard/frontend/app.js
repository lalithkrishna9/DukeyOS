"use strict";
/* DukeyOS front end. No frameworks. Talks only to its own origin (/api, /ws). */
const $ = s => document.querySelector(s), sleep = ms => new Promise(r => setTimeout(r, ms));
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const HDR = { "X-Requested-With": "DukeyOS" };                      // CSRF marker required by the backend
const api = async (path, opt = {}) => {
  const o = { credentials: "same-origin", ...opt, headers: { ...HDR, ...(opt.headers || {}) } };
  const r = await fetch(path, o);
  if (r.status === 401 && !path.startsWith("/api/login") && !path.startsWith("/api/me")) { sessionExpired(); }
  return r;
};
const json = async (path, opt) => { try { return await (await api(path, opt)).json(); } catch { return null; } };

let screenId = "boot";
const RED = new Set(["boot", "login"]);
function show(id) {
  screenId = id;
  document.querySelectorAll(".screen").forEach(s => s.classList.toggle("active", s.id === id));
  document.body.classList.toggle("crt-on", RED.has(id));
  document.body.classList.toggle("homed", id === "home");
}
function toast(msg) {
  const t = document.createElement("div"); t.textContent = msg; $("#toast").appendChild(t); setTimeout(() => t.remove(), 3500);
}

/* ---------- audio: synthesised blips, only after a user gesture ---------- */
let AC; const ac = () => { try { return AC || (AC = new (window.AudioContext || window.webkitAudioContext)()); } catch { return null; } };
function tone(f, d, type = "square", v = .04, f2) {
  try { const a = ac(); if (!a) return; const o = a.createOscillator(), g = a.createGain();
    o.type = type; o.frequency.setValueAtTime(f, a.currentTime);
    if (f2) o.frequency.exponentialRampToValueAtTime(f2, a.currentTime + d);
    g.gain.setValueAtTime(v, a.currentTime); g.gain.exponentialRampToValueAtTime(.0001, a.currentTime + d);
    o.connect(g); g.connect(a.destination); o.start(); o.stop(a.currentTime + d); } catch {}
}
const click = () => tone(900 + Math.random() * 400, .03, "square", .03, 200);
const blip = () => { tone(880, .08, "sine", .05); setTimeout(() => tone(1320, .12, "sine", .05), 70); };

/* ---------- SCREEN 1: boot (red on black) ---------- */
const rnd = n => Math.floor(Math.random() * n);
const fakeIP = () => `${10 + rnd(200)}.${rnd(256)}.${rnd(256)}.${1 + rnd(254)}`;
const fakeMAC = () => Array.from({ length: 6 }, () => rnd(256).toString(16).padStart(2, "0")).join(":").toUpperCase();
const GL = "▓▒░#@%&$?!/\\|<>";
const garble = s => s.replace(/[A-Za-z0-9]/g, c => Math.random() < .7 ? GL[rnd(GL.length)] : c);
let skipBoot = false;

async function boot() {
  show("boot");
  const me = json("/api/me");                                       // start early, used after the animation
  await new Promise(res => {                                        // gate: browsers only allow audio after a gesture
    const go = () => { removeEventListener("keydown", go); $("#gate").removeEventListener("pointerdown", go); res(); };
    addEventListener("keydown", go); $("#gate").addEventListener("pointerdown", go);
  });
  $("#gate").classList.add("gone"); try { ac()?.resume(); } catch {}
  addEventListener("keydown", () => { skipBoot = true; }, { once: true });
  addEventListener("pointerdown", () => { skipBoot = true; }, { once: true });
  const log = $("#log"); log.textContent = "";
  const lines = ["DUKEYOS BIOS v1.0", "[ OK ] Initializing kernel modules", "[ OK ] Probing memory banks",
    "[ OK ] Mounting /DATA", "[ OK ] Starting network stack", `[ OK ] Link up  ${fakeIP()}  ${fakeMAC()}`,
    "[ OK ] Loading packet engine", "[ OK ] Calibrating display", "[ OK ] Loading app engine",
    "[ OK ] Sealing session keys", "[ WARN ] Unknown user detected", "[ OK ] Handing off to login"];
  const glitchIdx = new Set([3, 6, 10]);
  for (let i = 0; i < lines.length && !skipBoot; i++) {
    const row = document.createElement("div"); log.appendChild(row);
    while (log.children.length > 40) log.firstChild.remove();
    if (glitchIdx.has(i)) { row.className = "garb"; for (let k = 0; k < 4 && !skipBoot; k++) { row.textContent = garble(lines[i]); await sleep(60); } row.className = ""; }
    row.textContent = lines[i]; await sleep(70 + rnd(120));
  }
  if (!skipBoot) {
    await sleep(250);
    const t = $("#title"); t.classList.add("show", "g"); tone(60, .5, "sawtooth", .05, 30);
    await sleep(800); t.classList.remove("g"); await sleep(skipBoot ? 0 : 1000); t.classList.remove("show");
  }
  const m = (await me) || await json("/api/me") || {};
  m.ok ? enterHome(false) : loginScreen(m.setup);
}

/* ---------- SCREEN 2: login (red on black) ---------- */
let locked = false, setupMode = false, busy = false;
async function loginScreen(setup) {
  setupMode = !!setup; show("login"); const pw = $("#pw"); pw.value = ""; renderDots();
  const w = $("#welcome"); w.textContent = ""; $("#pwwrap").style.visibility = "hidden"; $("#msg").textContent = "";
  $("#hint").textContent = "";
  for (const c of "Welcome Dukey") { w.textContent += c; click(); await sleep(85); }
  await sleep(250); $("#pwwrap").style.visibility = "visible";
  if (setupMode) { $("#msg").textContent = "FIRST RUN"; $("#hint").textContent = "CHOOSE A PASSWORD · 10+ CHARACTERS · PRESS ENTER"; }
  pw.focus();
}
function renderDots() { $("#dots").textContent = "•".repeat($("#pw").value.length); }
$("#pw").addEventListener("input", () => { click(); renderDots(); });
document.addEventListener("pointerdown", () => { if (screenId === "login") setTimeout(() => $("#pw").focus(), 0); });
$("#pw").addEventListener("keydown", async e => {
  if (e.key !== "Enter" || locked || busy) return;
  const password = $("#pw").value; if (!password) return;
  busy = true; $("#pw").value = ""; renderDots();
  const m = $("#msg");
  let r, j = {};
  try { r = await api("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) });
        j = await r.json().catch(() => ({})); }
  catch { m.textContent = "SERVER UNREACHABLE"; busy = false; return; }
  if (j.ok) { m.textContent = j.first ? "PASSWORD SET · ACCESS GRANTED" : "ACCESS GRANTED"; blip(); await sleep(700); busy = false; enterHome(true); return; }
  const f = $("#flash"); f.classList.add("on"); setTimeout(() => f.classList.remove("on"), 60);
  const box = $("#pwwrap"); box.classList.remove("shake"); void box.offsetWidth; box.classList.add("shake");
  tone(120, .3, "sawtooth", .06, 60);
  if (j.locked) {
    locked = true; let left = j.locked;
    const tick = () => { m.textContent = `LOCKED OUT · ${left}s`; if (left-- <= 0) { locked = false; m.textContent = ""; clearInterval(iv); } };
    const iv = setInterval(tick, 1000); tick();
  } else if (j.error) { m.textContent = j.error.toUpperCase(); }
  else { m.textContent = "ACCESS DENIED"; if (typeof j.left === "number") $("#hint").textContent = `${j.left} ATTEMPT${j.left === 1 ? "" : "S"} LEFT`; }
  busy = false;
});

/* ---------- session handling ---------- */
function stopHome() { homeActive = false; sockets.forEach(s => s.close()); sockets.clear(); }
function sessionExpired() { if (screenId !== "home") return; stopHome(); started = false; loginScreen(false); toast("SESSION ENDED"); }
$("#logout").onclick = async () => { await api("/api/logout", { method: "POST" }); stopHome(); started = false; loginScreen(false); };

/* ---------- SCREEN 3: home (white on black) ---------- */
const fmtUp = s => { s = Math.floor(s || 0); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60); return `UP ${d}d ${h}h ${m}m`; };
const kb = b => b >= 1048576 ? (b / 1048576).toFixed(1) + " MB/s" : (b / 1024).toFixed(0) + " KB/s";
const gb = b => b >= 1e12 ? (b / 1e12).toFixed(1) + " TB" : (b / 1e9).toFixed(0) + " GB";
const N = 60, hist = { cpu: [], ram: [], rx: [], tx: [] };
const push = (a, v) => { a.push(v); if (a.length > N) a.shift(); };
let started = false, homeActive = false;
const sockets = new Set(), timers = new Set();
const every = (fn, ms) => { fn(); const id = setInterval(() => homeActive && !document.hidden && fn(), ms); timers.add(id); return id; };

function plot(cv, series, max, shades) {
  const dpr = devicePixelRatio || 1, w = cv.width = Math.max(1, cv.clientWidth * dpr), h = cv.height = Math.max(1, cv.clientHeight * dpr), x = cv.getContext("2d");
  x.strokeStyle = "rgba(255,255,255,.1)"; x.lineWidth = 1;
  for (let i = 1; i < 4; i++) { x.beginPath(); x.moveTo(0, h * i / 4); x.lineTo(w, h * i / 4); x.stroke(); }
  const m = max || Math.max(1, ...series.flat()) * 1.2;
  series.forEach((s, k) => {
    if (!s.length) return;
    const step = w / (N - 1), off = (N - s.length) * step;
    x.beginPath(); s.forEach((v, i) => { const px = off + i * step, py = h - Math.min(1, v / m) * h * .92 - 2; i ? x.lineTo(px, py) : x.moveTo(px, py); });
    x.strokeStyle = shades[k]; x.lineWidth = 1.6 * dpr; x.stroke();
    if (k === 0) { x.lineTo(w, h); x.lineTo(off, h); x.closePath(); x.fillStyle = "rgba(255,255,255,.08)"; x.fill(); }
  });
}
const redraw = () => { plot($("#cpuc"), [hist.cpu], 100, ["#fff"]); plot($("#ramc"), [hist.ram], 100, ["#fff"]);
  plot($("#netc"), [hist.rx, hist.tx], 0, ["#fff", "#8a8a8a"]); };

function enterHome(anim) {
  show("home"); homeActive = true;
  if (anim) { const h = $("#home"); h.classList.remove("in"); void h.offsetWidth; h.classList.add("in"); }
  if (started) return; started = true;
  every(() => { const d = new Date(); const c = $("#clock"); c.textContent = d.toTimeString().slice(0, 8); c.classList.add("t"); setTimeout(() => c.classList.remove("t"), 90); }, 1000);
  statsWS(); packetsWS(); every(camPoll, 15000); every(netPoll, 5000); every(procPoll, 3000); every(redraw, 1000);
  loadApps(); setTimeout(initGlobe, 250);
}
document.addEventListener("visibilitychange", () => { if (!document.hidden && homeActive) { loadApps(); } });

function ws(path, onmsg) {
  let delay = 1000, sock, dead = false;
  const handle = { close() { dead = true; try { sock && sock.close(); } catch {} } };
  sockets.add(handle);
  (function open() {
    if (dead) return;
    sock = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + path);
    sock.onopen = () => { delay = 1000; };
    sock.onmessage = e => { try { onmsg(JSON.parse(e.data)); } catch {} };
    sock.onclose = async () => {
      if (dead) return;
      const me = await json("/api/me");                              // closed because the session died?
      if (me && !me.ok) return sessionExpired();
      setTimeout(open, delay); delay = Math.min(delay * 2, 15000);
    };
  })();
}

let lastLoad = null;
function statsWS() {
  ws("/ws/stats", s => {
    push(hist.cpu, s.cpu); push(hist.ram, s.ram); push(hist.rx, s.rx); push(hist.tx, s.tx);
    $("#cpuv").textContent = `${s.cpu.toFixed(0)}% · ${Array.isArray(s.cores) ? s.cores.length : (s.cores || "?")} CORES`;
    $("#ramv").textContent = `${s.ram.toFixed(0)}% · ${(s.ram_used / 1073741824).toFixed(1)}/${(s.ram_total / 1073741824).toFixed(1)} GB`;
    $("#uptime").textContent = fmtUp(s.uptime); $("#host").textContent = "HOST " + String(s.host || "").toUpperCase();
    $("#temp").textContent = s.temp == null ? "CPU --°C" : `CPU ${Math.round(s.temp)}°C`;
    $("#traf").textContent = `▼${kb(s.rx)} ▲${kb(s.tx)}`;
    if (s.load != null && s.load !== lastLoad) { lastLoad = s.load; $("#load").textContent = "LOAD " + Number(s.load).toFixed(2); }
    if (s.disk) { $("#diskv").textContent = `${s.disk.percent.toFixed(0)}% · ${gb(s.disk.free)} FREE`; $("#diskb").style.width = s.disk.percent + "%"; }
  });
}
async function procPoll() {
  const p = await json("/api/procs"); if (!Array.isArray(p)) return;
  $("#procs").innerHTML = p.map(x => `<tr><td>${esc(x.name)}</td><td>${x.cpu.toFixed(1)}</td><td>${x.mem.toFixed(1)}</td></tr>`).join("");
}
async function netPoll() {
  const n = await json("/api/net"); if (!n) return;
  $("#ns").innerHTML = `LINK <b class="${n.online ? "ok" : "bad"}">${n.online ? "ONLINE" : "OFFLINE"}</b><br>` +
    `PING ${n.ping == null ? "--" : n.ping + " ms"}<br>IPV4 ${esc(n.ipv4 || "--")}<br>VPN ${esc(n.vpn || "--")}<br>IFACE ${esc(n.iface || "--")}`;
}

/* webcam: SERVER camera only, streamed as MJPEG by the backend. There is no getUserMedia anywhere in this app. */
let camOn = false;
async function camPoll() {
  const c = await json("/api/cam/status"); const on = !!(c && c.online), img = $("#cam");
  $("#camOff").style.display = on ? "none" : "block"; img.style.display = on ? "block" : "none";
  $("#camBox").title = on ? (c.name || "camera") : (c && c.reason ? "OFFLINE: " + c.reason : "OFFLINE");
  if (on && !camOn) img.src = "/api/cam?" + Date.now();
  if (!on && camOn) { img.removeAttribute("src"); }
  camOn = on;
}
$("#cam").addEventListener("error", () => { camOn = false; $("#cam").removeAttribute("src"); });   // stream dropped: camPoll re-attaches

/* packets: real tshark rows, or OFFLINE with the reason. View-only. */
let paused = false, filt = "", rows = [], dirty = false;
$("#ppause").onclick = e => { paused = !paused; e.target.textContent = paused ? "RESUME" : "PAUSE"; if (!paused) drawPk(); };
$("#pfilter").oninput = e => { filt = e.target.value.toLowerCase(); drawPk(); };
function drawPk() {
  const r = rows.filter(x => !filt || `${x.src} ${x.dst} ${x.proto} ${x.info}`.toLowerCase().includes(filt)).slice(-80);
  $("#pk tbody").innerHTML = r.map(x => `<tr class="p-${esc(String(x.proto).split(",")[0].replace(/[^A-Za-z0-9]/g, ""))}"><td>${esc(x.no)}</td><td>${esc(x.t)}</td><td title="${esc(x.src)} → ${esc(x.dst)}">${esc(x.src)} → ${esc(x.dst)}</td><td>${esc(x.proto)}</td><td>${esc(x.len)}</td><td title="${esc(x.info)}">${esc(x.info)}</td></tr>`).join("");
  const box = $("#ptable"); box.scrollTop = box.scrollHeight;
}
function packetsWS() {
  ws("/ws/packets", m => {
    const st = m.status || {}, live = st.state === "live" || st.state === "starting";
    $("#poff").classList.toggle("on", st.state === "offline");
    $("#preason").textContent = st.state === "offline" ? (st.reason || "") : "";
    $("#pstat").textContent = st.state === "offline" ? "OFFLINE" : live ? (st.iface ? `LIVE · ${st.iface}` : "STARTING…") : "IDLE";
    if (st.state === "offline") { rows = []; $("#pk tbody").innerHTML = ""; return; }
    if (m.rows && m.rows.length) { rows = rows.concat(m.rows).slice(-400); if (!paused) drawPk(); }
  });
}

/* globe: eDEX encom-globe. COSMETIC ONLY - not wired to any real location data. Hyderabad pin, purple→blue grid. */
const HYD = { lat: 17.385, lon: 78.4867 };
let globe = null, globeRun = false;
const lerp = (a, b, t) => a + (b - a) * t;
function paintGrid(g, tiles) {
  const col = g.hexGrid && g.hexGrid.geometry.attributes.color; if (!col) return;
  const A = [0x9b, 0x5c, 0xff], B = [0x2f, 0x8b, 0xff], arr = col.array;
  tiles.forEach((t, i) => {
    const k = Math.max(0, Math.min(1, ((t.lon - 10) / 140) * .8 + ((t.lat + 50) / 120) * .2 + (Math.sin(t.lat * 1.7 + t.lon * .9) * .03)));   // purple (west) → blue (east), visible hemisphere
    const r = lerp(A[0], B[0], k) / 255, gg = lerp(A[1], B[1], k) / 255, b = lerp(A[2], B[2], k) / 255, o = i * 36;
    for (let j = 0; j < 36 && o + j < arr.length; j += 3) { arr[o + j] = r; arr[o + j + 1] = gg; arr[o + j + 2] = b; }
  });
  col.needsUpdate = true;
}
async function initGlobe() {
  const el = $("#globe");
  try {
    if (!window.ENCOM || !window.WebGLRenderingContext) throw new Error("no webgl");
    if (!el.clientWidth || !el.clientHeight) return setTimeout(initGlobe, 400);
    const geo = await (await fetch("assets/grid.json")).json();
    const g = new ENCOM.Globe(el.clientWidth, el.clientHeight, { font: "monospace", data: [], tiles: geo.tiles,
      baseColor: "#8a5cff", markerColor: "#7aa7ff", pinColor: "#7aa7ff", satelliteColor: "#9b5cff",
      scale: 1.3, viewAngle: .3, dayLength: 1e12, introLinesDuration: 2500, introLinesColor: "#2f8bff", maxPins: 3, maxMarkers: 3 });
    el.appendChild(g.domElement); globe = g;
    g.init("#000000", () => {
      try { paintGrid(g, geo.tiles); } catch (e) { console.warn("grid recolour failed", e); }
      g.addPin(HYD.lat, HYD.lon, "HYD", 1.25);
      globeRun = true; let last = 0; const base = Math.PI - HYD.lon * Math.PI / 180;
      (function loop(ts) {
        requestAnimationFrame(loop);
        if (!globeRun || document.hidden || !homeActive || ts - last < 1000 / 24) return;
        last = ts;
        g.cameraAngle = base + Math.sin(ts / 9000) * .22;           // slow sway, always facing Hyderabad
        g.viewAngle = .3 + Math.sin(ts / 13000) * .04;
        g.tick();
      })(0);
    });
    addEventListener("resize", () => { if (!globe || !el.clientWidth) return; g.camera.aspect = el.clientWidth / el.clientHeight; g.camera.updateProjectionMatrix(); g.renderer.setSize(el.clientWidth, el.clientHeight); });
  } catch (e) {
    console.warn("globe unavailable:", e); el.innerHTML = `<div class="empty">GLOBE UNAVAILABLE · WEBGL NOT SUPPORTED</div>`;
  }
}

/* apps: local dukeyos-appmanagement, reached only through the backend's allow-listed proxy */
const APPS = "/api/svc/v2/app_management";
const title = a => (a && a.title && (a.title.en_us || a.title.custom || Object.values(a.title)[0])) || (a && a.name) || "app";
const init = s => esc(String(s || "?").trim().slice(0, 1).toUpperCase());
const iconHTML = (a, cls) => a.icon ? `<img src="${esc(a.icon)}" alt="" loading="lazy" onerror="this.outerHTML='<div class=&quot;fb&quot;>${init(title(a))}</div>'">` : `<div class="fb">${init(title(a))}</div>`;
function appURL(a) {
  if (a.app_type === "v1app" && a.url) return a.url;
  const host = a.hostname || location.hostname, scheme = a.scheme || "http";
  return `${scheme}://${host}${a.port ? ":" + a.port : ""}${a.index || ""}`;
}
let appsBusy = new Set();
async function loadApps() {
  const grid = $("#grid"), j = await json(`${APPS}/web/appgrid`);
  if (!j || !Array.isArray(j.data)) { grid.innerHTML = `<div class="empty">APP ENGINE OFFLINE</div>`; return; }
  if (!j.data.length) { grid.innerHTML = `<div class="empty">NOTHING INSTALLED · OPEN THE APP STORE</div>`; return; }
  grid.innerHTML = "";
  for (const a of j.data) {
    const d = document.createElement("div"), id = a.name; d.className = "app" + (a.status && a.status !== "running" ? " down" : "") + (appsBusy.has(id) ? " busy" : "");
    d.title = title(a) + (a.status && a.status !== "running" ? " (" + a.status + ")" : "");
    d.innerHTML = `${iconHTML(a)}<span>${esc(title(a))}</span>${a.app_type === "v2app" ? '<b class="dots" title="actions">⋯</b>' : ""}`;
    d.onclick = e => { if (e.target.classList.contains("dots")) { e.stopPropagation(); return menu(e, a); } open(appURL(a), "_blank", "noopener"); };
    d.oncontextmenu = e => { if (a.app_type === "v2app") { e.preventDefault(); menu(e, a); } };
    grid.appendChild(d);
  }
}
function menu(e, a) {
  const m = $("#menu"), running = !a.status || a.status === "running";
  m.innerHTML = [running ? ["stop", "STOP"] : ["start", "START"], ["restart", "RESTART"], ["remove", "UNINSTALL"]].map(([k, l]) => `<button data-k="${k}">${l}</button>`).join("");
  m.style.left = Math.min(e.clientX, innerWidth - 150) + "px"; m.style.top = Math.min(e.clientY, innerHeight - 110) + "px"; m.classList.add("on");
  m.onclick = async ev => {
    const k = ev.target.dataset.k; if (!k) return; m.classList.remove("on");
    if (k === "remove" && !confirm(`Uninstall ${title(a)}?\n\nIts container is removed. Its data in /DATA/AppData is kept.`)) return;
    appsBusy.add(a.name); loadApps();
    const r = k === "remove" ? await api(`${APPS}/compose/${encodeURIComponent(a.name)}?delete_config_folder=false`, { method: "DELETE" })
      : await api(`${APPS}/compose/${encodeURIComponent(a.name)}/status`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(k) });
    appsBusy.delete(a.name); toast(r.ok ? `${k.toUpperCase()} · ${title(a)}` : `FAILED · ${title(a)}`); setTimeout(loadApps, 600);
  };
}
addEventListener("pointerdown", e => { if (!e.target.closest("#menu") && !e.target.classList.contains("dots")) $("#menu").classList.remove("on"); });

/* app store */
let storeList = [], installed = new Set();
$("#store").onclick = async () => {
  $("#modal").classList.add("on"); $("#ssearch").value = ""; const g = $("#sgrid"); g.innerHTML = `<div class="empty">LOADING CATALOG…</div>`;
  const j = await json(`${APPS}/apps`);
  if (!j || !j.data || !j.data.list) { g.innerHTML = `<div class="empty">APP STORE UNAVAILABLE · THE SERVER MAY BE OFFLINE</div>`; return; }
  const l = j.data.list; storeList = Object.keys(l).map(k => ({ id: l[k].store_app_id || k, ...l[k] })).sort((a, b) => title(a).localeCompare(title(b)));
  installed = new Set(j.data.installed || []); drawStore(); $("#ssearch").focus();
};
function drawStore() {
  const q = $("#ssearch").value.toLowerCase().trim(), g = $("#sgrid");
  const list = storeList.filter(a => !q || `${title(a)} ${a.category || ""} ${(a.tagline && (a.tagline.en_us || "")) || ""}`.toLowerCase().includes(q)).slice(0, 120);
  g.innerHTML = ""; if (!list.length) { g.innerHTML = `<div class="empty">NO MATCHES</div>`; return; }
  for (const a of list) {
    const d = document.createElement("div"), have = installed.has(a.id); d.className = "sa";
    d.innerHTML = `${iconHTML(a)}<span>${esc(title(a))}</span><small>${esc((a.tagline && a.tagline.en_us) || a.category || "")}</small><button ${have ? "disabled" : ""}>${have ? "INSTALLED" : "INSTALL"}</button>`;
    d.querySelector("button").onclick = ev => install(a, ev.target);
    g.appendChild(d);
  }
}
$("#ssearch").oninput = drawStore;
async function install(a, btn) {
  btn.disabled = true; btn.textContent = "FETCHING…";
  try {
    const y = await api(`${APPS}/apps/${encodeURIComponent(a.id)}/compose`, { headers: { Accept: "application/yaml" } });   // the store's compose file
    if (!y.ok) throw new Error("compose");
    const r = await api(`${APPS}/compose`, { method: "POST", headers: { "Content-Type": "application/yaml" }, body: await y.text() });
    if (!r.ok) throw new Error("install");
    blip(); btn.textContent = "INSTALLING…"; installed.add(a.id); toast(`INSTALLING · ${title(a)}`);
    [4000, 12000, 30000, 60000].forEach(ms => setTimeout(() => homeActive && loadApps(), ms));       // it installs asynchronously
  } catch { btn.disabled = false; btn.textContent = "RETRY"; toast(`INSTALL FAILED · ${title(a)}`); }
}
$("#mx").onclick = () => $("#modal").classList.remove("on");
$("#modal").addEventListener("pointerdown", e => { if (e.target.id === "modal") $("#modal").classList.remove("on"); });
addEventListener("keydown", e => { if (e.key === "Escape") { $("#modal").classList.remove("on"); $("#pwmodal").classList.remove("on"); $("#menu").classList.remove("on"); } });

/* password change */
$("#chpw").onclick = () => { $("#pwmodal").classList.add("on"); $("#pwmsg").textContent = ""; $("#pwcur").value = $("#pwnew").value = ""; $("#pwcur").focus(); };
$("#pwx").onclick = () => $("#pwmodal").classList.remove("on");
$("#pwsave").onclick = async () => {
  const r = await api("/api/password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ current: $("#pwcur").value, new: $("#pwnew").value }) });
  const j = await r.json().catch(() => ({}));
  if (j.ok) { $("#pwmodal").classList.remove("on"); toast("PASSWORD CHANGED · OTHER SESSIONS ENDED"); } else $("#pwmsg").textContent = (j.error || "FAILED").toUpperCase();
};

boot();
