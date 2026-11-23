"use strict";
const assert = require("assert");
const DK = require("../frontend/lib.js");

// docker compose "ls" statuses: this was the greyscale bug - "running(1)" !== "running"
assert.strictEqual(DK.appState("running(1)").key, "up");
assert.strictEqual(DK.appState("running(3)").key, "up");
assert.strictEqual(DK.appState("running").key, "up");
assert.strictEqual(DK.appState("running(1), running(2)").key, "up");
assert.strictEqual(DK.appState("running(1), exited(1)").key, "part");
assert.strictEqual(DK.appState("restarting(1)").key, "part");
assert.strictEqual(DK.appState("exited(1)").key, "down");
assert.strictEqual(DK.appState("paused(1)").key, "down");
assert.strictEqual(DK.appState("created(1)").key, "down");
assert.strictEqual(DK.appState("stopped").key, "down");
assert.strictEqual(DK.appState("unknown").key, "unknown");
assert.strictEqual(DK.appState(undefined).key, "up");
assert.strictEqual(DK.appState("").key, "up");

// error text
assert.strictEqual(DK.errorText({ message: "boom" }, 500), "boom");
assert.strictEqual(DK.errorText(null, 502), "HTTP 502");
assert.strictEqual(DK.errorText(null, 0, "NETWORK"), "NETWORK");
assert.strictEqual(DK.errorText({ message: "there are ports in use", data: { ports_in_use: { TCP: ["8080", "80"], UDP: [] } } }, 400),
  "PORTS ALREADY IN USE · TCP 8080,80");
assert.ok(DK.errorText({ message: "x".repeat(500) }, 500).length <= 110);

// elapsed
assert.strictEqual(DK.fmtElapsed(0), "0:00");
assert.strictEqual(DK.fmtElapsed(65000), "1:05");
assert.strictEqual(DK.fmtElapsed(-5), "0:00");

// grid: null data means "nothing installed", not "engine offline"
assert.deepStrictEqual(DK.gridItems({ message: "ok", data: null }), []);
assert.deepStrictEqual(DK.gridItems({ data: [{ name: "a" }] }), [{ name: "a" }]);
assert.strictEqual(DK.gridItems(null), null);
assert.strictEqual(DK.gridItems("nope"), null);
assert.ok(DK.inGrid([{ name: "jellyfin" }, { name: "x", store_app_id: "nginx" }], "nginx"));
assert.ok(!DK.inGrid([{ name: "jellyfin" }], "nginx"));
assert.ok(!DK.inGrid(null, "nginx"));

// install completion: exact id, different case, same title, or the single new app
const base = [{ name: "jellyfin" }];
assert.ok(DK.installDone([...base, { name: "nginx" }], "nginx", "Nginx", ["jellyfin"], 1));
assert.ok(DK.installDone([...base, { name: "Nginx" }], "nginx", "Nginx", ["jellyfin"], 2));
assert.ok(DK.installDone([...base, { name: "web", title: { en_us: "Nginx" } }], "nginx", "Nginx", ["jellyfin"], 2));
assert.ok(DK.installDone([...base, { name: "demo" }], "nginx", "Nginx", ["jellyfin"], 1));      // renamed project, only one install running
assert.ok(!DK.installDone([...base, { name: "demo" }], "nginx", "Nginx", ["jellyfin"], 2));     // ambiguous with two installs: keep waiting
assert.ok(!DK.installDone(base, "nginx", "Nginx", ["jellyfin"], 1));
assert.ok(!DK.installDone(null, "nginx", "Nginx", [], 1));
assert.strictEqual(DK.fmtBytes(5e9), "5.0 GB");
assert.strictEqual(DK.fmtBytes(5e8), "500 MB");
console.log("frontend lib ok");
