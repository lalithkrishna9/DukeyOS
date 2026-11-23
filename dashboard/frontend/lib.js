"use strict";
/* Pure helpers for the DukeyOS front end. No DOM access, so they can be unit-tested with node
   (see tests/test_frontend_lib.py). In the browser they live on window.DK. */
(function (root) {
  const DK = {};

  /* Docker Compose reports a project's status as e.g. "running(1)", "exited(2)", "paused(1)",
     "running(1), exited(1)". The v1 apps just say "running" / "exited". The old UI compared the
     whole string with "running", so every real app looked stopped and was drawn greyed out.
     Returns { key: "up" | "part" | "down" | "unknown", text } */
  DK.appState = function (status) {
    if (status == null || status === "") return { key: "up", text: "" };
    const text = String(status).trim();
    if (text.toLowerCase() === "unknown") return { key: "unknown", text };
    const parts = text.toLowerCase().split(",").map(p => p.trim()).filter(Boolean);
    const names = parts.map(p => p.replace(/\(\d+\)$/, "").trim());
    const up = names.filter(n => n === "running").length;
    if (up && up === names.length) return { key: "up", text };
    if (up || names.includes("restarting")) return { key: "part", text };
    return { key: "down", text };
  };

  /* Turn an error response from the app engine into one short, readable line. */
  DK.errorText = function (j, status, fallback) {
    let msg = j && typeof j.message === "string" ? j.message : "";
    const pu = j && j.data && j.data.ports_in_use;
    if (pu) {
      const tcp = Array.isArray(pu.TCP) ? pu.TCP : [], udp = Array.isArray(pu.UDP) ? pu.UDP : [];
      const bits = [];
      if (tcp.length) bits.push("TCP " + tcp.join(","));
      if (udp.length) bits.push("UDP " + udp.join(","));
      if (bits.length) msg = "PORTS ALREADY IN USE · " + bits.join(" · ");
    }
    if (!msg) msg = fallback || (status ? "HTTP " + status : "FAILED");
    msg = msg.replace(/\s+/g, " ").trim();
    return msg.length > 110 ? msg.slice(0, 107) + "…" : msg;
  };

  DK.fmtElapsed = function (ms) {
    const s = Math.max(0, Math.floor(ms / 1000)), m = Math.floor(s / 60);
    return m + ":" + String(s % 60).padStart(2, "0");
  };

  /* Is the store app `id` present in the app grid yet? A store app's compose project name is its
     store id, so match on either the grid name or the recorded store_app_id. */
  DK.inGrid = function (items, id) {
    if (!Array.isArray(items)) return false;
    return items.some(a => a && (a.name === id || a.store_app_id === id));
  };

  /* Has an install we started finished? The compose project name normally equals the store id, but not
     always (case, renamed projects), so besides an exact match this also accepts: a grid item with the same
     title, or - when this is the only install in flight - exactly one new app that wasn't there when we
     started. `snap` is the list of grid names recorded at click time. */
  DK.installDone = function (items, id, title, snap, pending) {
    if (!Array.isArray(items)) return false;
    const lid = String(id).toLowerCase(), lt = String(title || "").toLowerCase();
    const names = a => [a.name, a.store_app_id].filter(Boolean).map(x => String(x).toLowerCase());
    if (items.some(a => names(a).includes(lid))) return true;
    const ttl = a => a.title && typeof a.title === "object" ? Object.values(a.title).map(x => String(x).toLowerCase()) : [];
    if (lt && items.some(a => ttl(a).includes(lt))) return true;
    if (Array.isArray(snap) && pending === 1) {
      const fresh = items.filter(a => a && !snap.includes(a.name));
      if (fresh.length === 1) return true;
    }
    return false;
  };

  /* The app grid's `data` is null (not []) when nothing is installed, so "no array" must not be
     confused with "app engine offline". */
  DK.gridItems = function (j) {
    if (!j || typeof j !== "object") return null;
    if (Array.isArray(j.data)) return j.data;
    if (j.data == null && !("error" in j)) return [];
    return null;
  };

  DK.fmtBytes = function (b) {
    return b >= 1e12 ? (b / 1e12).toFixed(1) + " TB" : b >= 1e9 ? (b / 1e9).toFixed(1) + " GB" : (b / 1e6).toFixed(0) + " MB";
  };

  if (typeof module !== "undefined" && module.exports) module.exports = DK; else root.DK = DK;
})(typeof window !== "undefined" ? window : globalThis);
