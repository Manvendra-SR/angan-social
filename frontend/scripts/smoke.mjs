// End-to-end smoke test of the running app in a real (headless) browser.
// No dependencies: drives Edge/Chrome over the DevTools protocol (Node 22+).
//
//   npm run smoke -- [--browser "C:/path/to/msedge.exe"]
//
// Needs the backend (VITE_API_URL, default http://127.0.0.1:8080) and Vite
// (http://localhost:5173) running. It registers two throwaway users (smoke_*),
// creates posts (deleted again at the end) and one Cloudinary upload.
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import zlib from "node:zlib";

const APP = process.env.SMOKE_APP_URL || "http://localhost:5173";
const API = process.env.VITE_API_URL || "http://127.0.0.1:8080";
const PORT = 9341;
const argBrowser = process.argv.indexOf("--browser");
const BROWSER = argBrowser > 0 ? process.argv[argBrowser + 1] : [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "/usr/bin/google-chrome", "/usr/bin/chromium", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].find(existsSync);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let passed = 0;
const failures = [];
function check(label, cond, extra = "") {
  if (cond) { passed++; console.log("ok    " + label); }
  else { failures.push(label); console.log("FAIL  " + label + (extra ? "  " + extra : "")); }
}

// ---------- a small real PNG for the upload
function png(w = 48, h = 48) {
  const table = Array.from({ length: 256 }, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  const crc = (b) => { let c = 0xffffffff; for (const x of b) c = table[(c ^ x) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  const chunk = (t, d) => { const l = Buffer.alloc(4); l.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t), d]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([l, td, c]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  const rows = []; for (let y = 0; y < h; y++) { rows.push(0); for (let x = 0; x < w; x++) rows.push((x * 5) & 255, (y * 5) & 255, 170); }
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(Buffer.from(rows))), chunk("IEND", Buffer.alloc(0))]);
}

// ---------- REST helpers (for the second user and cleanup)
async function rest(method, path, tokenValue, body) {
  const headers = tokenValue ? { Authorization: `Bearer ${tokenValue}` } : {};
  let payload;
  if (body instanceof URLSearchParams) payload = body;
  else if (body) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(API + path, { method, headers, body: payload });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  return { status: res.status, data };
}
async function apiUser(name) {
  const email = `${name}@example.com`;
  await rest("POST", "/auth/register", null, { username: name, email, password: "password123" });
  const login = await rest("POST", "/auth/login", null, new URLSearchParams({ username: email, password: "password123" }));
  const me = await rest("GET", "/users/me", login.data.access_token);
  return { ...me.data, token: login.data.access_token, email };
}

// ---------- browser + pages
if (!BROWSER) { console.error("No Edge/Chrome found; pass --browser <path>"); process.exit(2); }
const profileDir = mkdtempSync(join(tmpdir(), "smoke-"));
const IMG = join(profileDir, "upload.png");
writeFileSync(IMG, png());
const browser = spawn(BROWSER, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profileDir}`, "--no-first-run", "about:blank"], { stdio: "ignore" });

let version;
for (let i = 0; i < 60 && !version; i++) {
  try { version = await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); } catch { await sleep(200); }
}
const socket = new WebSocket(version.webSocketDebuggerUrl);
await new Promise((r) => socket.addEventListener("open", r));
let nextId = 0;
const pending = new Map();
const pages = new Map(); // sessionId -> page
socket.addEventListener("message", (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); return; }
  pages.get(m.sessionId)?.onEvent(m);
});
function send(method, params = {}, sessionId) {
  const id = ++nextId;
  socket.send(JSON.stringify({ id, method, params, sessionId }));
  return new Promise((resolve, reject) => pending.set(id, (m) => (m.error ? reject(new Error(`${method}: ${m.error.message}`)) : resolve(m.result))));
}

async function newPage(name) {
  const { browserContextId } = await send("Target.createBrowserContext"); // separate localStorage = separate user
  const { targetId } = await send("Target.createTarget", { url: "about:blank", browserContextId, newWindow: true });
  const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
  const page = {
    name, requests: [], consoleErrors: [], failed: [], wsFrames: 0,
    cmd: (method, params) => send(method, params, sessionId),
    onEvent(m) {
      const p = m.params;
      if (m.method === "Network.requestWillBeSent") this.requests.push(p.request.method + " " + p.request.url);
      if (m.method === "Network.loadingFailed" && !p.canceled && !this.offline) this.failed.push(p.errorText);
      if (m.method === "Network.webSocketFrameReceived") this.wsFrames++;
      if (m.method === "Runtime.consoleAPICalled" && p.type === "error") this.consoleErrors.push(p.args.map((a) => a.value ?? a.description).join(" ").slice(0, 200));
      if (m.method === "Runtime.exceptionThrown") this.consoleErrors.push("exception: " + (p.exceptionDetails.exception?.description ?? p.exceptionDetails.text).slice(0, 200));
    },
    async js(expr) {
      const r = await this.cmd("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(`[${name}] ${expr} -> ${r.exceptionDetails.exception?.description}`);
      return r.result.value;
    },
    async waitFor(expr, ms = 15000) {
      const end = Date.now() + ms;
      while (Date.now() < end) { try { if (await this.js(expr)) return true; } catch { /* page navigating */ } await sleep(150); }
      return false;
    },
    async goto(path) { await this.cmd("Page.navigate", { url: APP + path }); await sleep(400); },
    async click(selector) {
      await this.js(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block: "center"})`);
      const c = await this.js(`(() => { const r = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return {x: r.x + r.width / 2, y: r.y + r.height / 2}; })()`);
      for (const type of ["mousePressed", "mouseReleased"]) await this.cmd("Input.dispatchMouseEvent", { type, x: c.x, y: c.y, button: "left", clickCount: 1 });
      await sleep(100);
    },
    async clickText(tag, text) {
      // wait for it to render first (buttons change text while busy)
      await this.waitFor(`[...document.querySelectorAll(${JSON.stringify(tag)})].some(e => e.textContent.trim() === ${JSON.stringify(text)})`, 8000);
      await this.js(`(() => { document.querySelectorAll("[data-smoke]").forEach(e => e.removeAttribute("data-smoke"));
        const all = [...document.querySelectorAll(${JSON.stringify(tag)})];
        const el = all.find(e => e.textContent.trim() === ${JSON.stringify(text)});
        if (!el) throw new Error("no ${tag} with text ${text}; have: " + JSON.stringify(all.map(e => e.textContent.trim())));
        el.setAttribute("data-smoke", "1"); })()`);
      await this.click('[data-smoke="1"]');
    },
    async type(selector, text) {
      await this.click(selector);
      await this.cmd("Input.insertText", { text });
    },
    async viewport(width, height = 850) {
      await this.cmd("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width < 640 });
    },
    /** Go offline and drop the socket (DevTools offline mode alone keeps open sockets alive). */
    async dropConnection() {
      await this.setOffline(true);
      // only the app's socket: closing Vite's dev-server socket would make Vite reload the page
      const appSocket = API.replace(/^http/, "ws") + "/ws";
      await this.js(`window.__sockets.filter(s => s.url === ${JSON.stringify(appSocket)}).forEach(s => s.close())`);
    },
    async setOffline(offline) {
      this.offline = offline;
      await this.cmd("Network.emulateNetworkConditions", { offline, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    },
  };
  pages.set(sessionId, page);
  for (const d of ["Network.enable", "Runtime.enable", "Page.enable"]) await page.cmd(d);
  await page.cmd("Emulation.setFocusEmulationEnabled", { enabled: true }); // both windows count as visible
  // test-only hook (the app is unchanged): remember sockets so we can simulate a dropped connection
  await page.cmd("Page.addScriptToEvaluateOnNewDocument", { source: `
    window.__sockets = [];
    const Native = window.WebSocket;
    window.WebSocket = class extends Native { constructor(...a) { super(...a); window.__sockets.push(this); } };
  ` });
  await page.viewport(1280);
  return page;
}

const sfx = Math.floor(Math.random() * 90000) + 10000;
const A = { username: `smoke_a${sfx}`, email: `smoke_a${sfx}@example.com`, password: "password123" };
const createdPosts = [];
let a, b, userA, userB;

try {
  a = await newPage("A");
  b = await newPage("B");

  // ---------- auth pages + password toggle
  for (const path of ["/", "/register"]) {
    await a.goto(path);
    await a.waitFor(`!!document.querySelector(".password-field input")`);
    await a.type(".password-field input", "secret123");
    const shown = await a.js(`(() => { const b = document.querySelector(".password-toggle").getBoundingClientRect(); return b.width > 0 && document.elementFromPoint(b.x + b.width/2, b.y + b.height/2)?.closest(".password-toggle") !== null; })()`);
    await a.click(".password-toggle");
    const revealed = await a.js(`document.querySelector(".password-field input").type === "text" && document.querySelector(".password-field input").value === "secret123"`);
    check(`${path === "/" ? "login" : "register"}: password toggle visible and works`, shown && revealed);
  }

  // ---------- register + login through the UI (user A)
  await a.goto("/register");
  await a.waitFor(`!!document.querySelector("form input")`);
  await a.js(`[...document.querySelectorAll("form input:not([type=checkbox])")].forEach((el, i) => el.setAttribute("data-i", i))`);
  await a.type('[data-i="0"]', A.username);
  await a.type('[data-i="1"]', A.email);
  await a.type('[data-i="2"]', A.password);
  await a.clickText("button", "Sign up");
  check("register via UI", await a.waitFor(`document.body.innerText.includes("Account created")`));
  await a.js(`[...document.querySelectorAll("form input")].forEach((el, i) => el.setAttribute("data-i", i))`);
  await a.type('[data-i="0"]', A.email);
  await a.type('[data-i="1"]', A.password);
  await a.clickText("button", "Log in");
  check("login via UI -> feed", await a.waitFor(`!!document.querySelector(".composer textarea")`));
  check("realtime socket connected (A)", await a.waitFor(`true`) && a.wsFrames > 0 || await a.waitFor(`true`, 3000) && a.wsFrames > 0);
  const tokenA = await a.js(`localStorage.getItem("token")`);
  userA = (await rest("GET", "/users/me", tokenA)).data;
  userA.token = tokenA;

  // ---------- user B (API) watching their notifications page
  userB = await apiUser(`smoke_b${sfx}`);
  await b.goto("/");
  await b.js(`localStorage.setItem("token", ${JSON.stringify(userB.token)})`);
  await b.goto("/notifications");
  check("empty state on a new account's notifications", await b.waitFor(`document.body.innerText.includes("No notifications yet")`));

  // ---------- A follows B -> B sees it live, no reload
  await a.goto(`/users/${userB.id}`);
  await a.waitFor(`[...document.querySelectorAll("button")].some(b => b.textContent.trim() === "Follow")`);
  await a.clickText("button", "Follow");
  check("follow button switches to Following", await a.waitFor(`[...document.querySelectorAll("button")].some(b => b.textContent.trim() === "Following")`));
  check("B gets the follow notification live", await b.waitFor(`document.body.innerText.includes("started following you")`, 5000));
  check("B's bell badge shows 1", await b.waitFor(`[...document.querySelectorAll(".badge-count")].some(x => x.textContent === "1")`, 5000));
  check("opening the page didn't mark it read", (await rest("GET", "/users/me/counts", userB.token)).data.unread_notifications === 1);

  // ---------- posts: text + image (real Cloudinary upload)
  await a.goto("/");
  await a.waitFor(`!!document.querySelector(".composer textarea")`);
  const postText = `Smoke test post ${sfx}`; // unique, so an old post can't satisfy the check
  await a.type(".composer textarea", postText);
  await a.clickText("button", "Post");
  check("text post appears", await a.waitFor(`[...document.querySelectorAll(".post-content")].some(e => e.textContent === ${JSON.stringify(postText)})`));
  await a.waitFor(`!document.querySelector(".composer textarea").value`); // request finished
  const { root } = await a.cmd("DOM.getDocument");
  const { nodeId } = await a.cmd("DOM.querySelector", { nodeId: root.nodeId, selector: ".composer input[type=file]" });
  await a.cmd("DOM.setFileInputFiles", { nodeId, files: [IMG] });
  // wait until the preview has loaded: its height pushes the Post button down
  check("image preview before upload", await a.waitFor(`document.querySelector(".preview img")?.complete && document.querySelector(".preview img").naturalWidth > 0`));
  await a.clickText("button", "Post");
  const imageOk = await a.waitFor(`[...document.querySelectorAll(".post-image")].some(i => i.src.includes("res.cloudinary.com") && i.complete && i.naturalWidth > 0)`, 30000);
  check("image post shows the uploaded image", imageOk, imageOk ? "" : await a.js(`JSON.stringify({
    composerError: document.querySelector(".composer .error")?.textContent ?? null,
    buttons: [...document.querySelectorAll(".composer button")].map(b => b.textContent + (b.disabled ? " (disabled)" : "")),
    preview: !!document.querySelector(".preview img"),
    images: [...document.querySelectorAll(".post-image")].map(i => ({ complete: i.complete, w: i.naturalWidth, src: i.src.slice(0, 90) })),
    path: location.pathname, posts: document.querySelectorAll(".post").length,
    skeleton: !!document.querySelector(".skeleton-post"),
  })`) + " requests: " + JSON.stringify(a.requests.filter((r) => r.includes("/posts")).slice(-6)));
  const myPosts = (await rest("GET", `/users/${userA.id}/posts`, userA.token)).data;
  createdPosts.push(...myPosts.map((p) => p.id));

  // ---------- B likes and comments -> A's badge updates live
  const target = myPosts[0];
  await rest("POST", `/likes/${target.id}`, userB.token);
  await rest("POST", `/comments/posts/${target.id}`, userB.token, { content: "Nice one" });
  check("A's notification badge updates live", await a.waitFor(`[...document.querySelectorAll(".badge-count")].some(x => x.textContent === "2")`, 5000));

  // ---------- A opens notifications, clicks one -> post page, marked read
  await a.click('.sidenav a[href="/notifications"]');
  await a.waitFor(`document.querySelectorAll(".notification.unread").length === 2`);
  await a.js(`document.querySelector(".notification.unread .notification-main").setAttribute("data-n", "1")`);
  await a.click('[data-n="1"]');
  check("clicking a notification opens the post", await a.waitFor(`location.pathname === "/posts/${target.id}" && !!document.querySelector(".comments")`));
  check("...and marks only that one read", await a.waitFor(`[...document.querySelectorAll(".badge-count")].some(x => x.textContent === "1")`, 5000));
  await a.goto("/notifications");
  await a.waitFor(`!!document.querySelector(".notification")`);
  await a.clickText("button", "Mark all as read");
  check("mark all as read clears the badge", await a.waitFor(`!document.querySelector('.sidenav a[href="/notifications"] .badge-count')`, 5000));

  // ---------- like + comment through the UI
  await a.goto(`/posts/${target.id}`);
  await a.waitFor(`!!document.querySelector(".post-actions .action")`);
  await a.click(".post-actions .action");
  check("like button toggles", await a.waitFor(`document.querySelector(".post-actions .action").getAttribute("aria-pressed") === "true"`));
  await a.type(".comment-form input", "Thanks!");
  await a.click(".comment-form button");
  check("comment appears", await a.waitFor(`document.querySelector(".comments").innerText.includes("Thanks!")`));

  // ---------- missing post -> friendly state
  await a.goto("/posts/99999999");
  check("missing post shows 'no longer available'", await a.waitFor(`document.body.innerText.includes("no longer available")`));

  // ---------- chat: live delivery, read state, reconnect + recovery
  await a.goto(`/users/${userB.id}`);
  await a.waitFor(`[...document.querySelectorAll("button")].some(b => b.textContent.trim() === "Message")`);
  await a.clickText("button", "Message");
  check("Message opens the thread with the other user's name", await a.waitFor(`location.pathname.startsWith("/messages/") && document.querySelector(".thread-header")?.innerText.includes(${JSON.stringify(userB.username)})`));
  const conversationId = Number(await a.js(`location.pathname.split("/").pop()`));
  await b.goto(`/messages/${conversationId}`);
  await b.waitFor(`!!document.querySelector(".thread .composer-row input")`);
  // wait for B's socket to be ready: its first resync re-fetches with after_id
  const resynced = () => b.requests.some((r) => r.includes(`/conversations/${conversationId}/messages?`) && r.includes("after_id"));
  for (let i = 0; i < 50 && !resynced(); i++) await sleep(100);
  await sleep(300);

  const before = b.requests.filter((r) => r.includes(`/conversations/${conversationId}/messages?`)).length;
  await a.type(".composer-row input", "Hello B");
  await a.click('.composer-row button');
  check("A's message shows as sent", await a.waitFor(`[...document.querySelectorAll(".bubble.mine:not(.pending)")].some(x => x.innerText.includes("Hello B"))`));
  const t0 = Date.now();
  const arrived = await b.waitFor(`[...document.querySelectorAll(".bubble:not(.mine)")].some(x => x.innerText.includes("Hello B"))`, 5000);
  check(`B receives it over the socket (${Date.now() - t0} ms)`, arrived);
  const after = b.requests.filter((r) => r.includes(`/conversations/${conversationId}/messages?`)).length;
  check("...without polling the messages endpoint", after === before, `${after - before} extra requests`);
  check("B's open thread marked it read", await b.waitFor(`!document.querySelector('.sidenav a[href="/messages"] .badge-count')`, 5000)
    && (await rest("GET", "/users/me/counts", userB.token)).data.unread_messages === 0);

  // B goes offline: the socket drops, a message arrives meanwhile, B recovers it
  await b.dropConnection();
  check("connection lost -> 'Reconnecting…' banner", await b.waitFor(`document.body.innerText.includes("Reconnecting")`, 12000));
  await rest("POST", `/conversations/${conversationId}/messages`, userA.token, { body: "Sent while you were offline" });
  await b.setOffline(false);
  check("back online -> missed message recovered", await b.waitFor(`[...document.querySelectorAll(".bubble")].some(x => x.innerText.includes("Sent while you were offline"))`, 20000));
  check("...and the banner disappears", await b.waitFor(`!document.body.innerText.includes("Reconnecting")`, 10000));
  const dupes = await b.js(`[...document.querySelectorAll(".bubble")].filter(x => x.innerText.includes("Sent while you were offline")).length`);
  check("...exactly once", dupes === 1, `${dupes} copies`);

  // a failed send shows Retry; retrying (same idempotency key) delivers once
  await a.setOffline(true);
  await a.type(".composer-row input", "Retry me");
  await a.click('.composer-row button');
  check("failed send shows 'Not sent · Retry'", await a.waitFor(`document.body.innerText.includes("Not sent")`, 8000));
  await a.setOffline(false);
  await sleep(500);
  await a.clickText("button", "Not sent · Retry");
  check("retry delivers the message", await a.waitFor(`[...document.querySelectorAll(".bubble.mine:not(.pending)")].some(x => x.innerText.includes("Retry me"))`, 8000));
  const history = (await rest("GET", `/conversations/${conversationId}/messages?limit=100`, userA.token)).data;
  check("...and it exists exactly once on the server", history.filter((m) => m.body === "Retry me").length === 1);

  // ---------- responsive layouts
  for (const width of [375, 768, 1280]) {
    await a.viewport(width);
    await a.goto("/");
    await a.waitFor(`!!document.querySelector(".post")`);
    const layout = await a.js(`(() => {
      const nav = document.querySelector(".sidenav").getBoundingClientRect();
      return { noHScroll: document.documentElement.scrollWidth <= innerWidth + 1,
               navVisible: nav.width > 0 && nav.height > 0,
               bottomBar: Math.round(nav.bottom) >= innerHeight - 1 && nav.width >= innerWidth - 1,
               labels: getComputedStyle(document.querySelector(".nav-label")).display !== "none" };
    })()`);
    const expected = width < 640 ? layout.bottomBar && !layout.labels : width < 1024 ? !layout.bottomBar && !layout.labels : layout.labels;
    check(`${width}px: no horizontal scroll, navigation reachable, correct nav style`, layout.noHScroll && layout.navVisible && expected, JSON.stringify(layout));
  }
  await a.viewport(1280);

  // ---------- console / network hygiene
  for (const p of [a, b]) {
    const hosts = [...new Set(p.requests.map((r) => new URL(r.split(" ")[1]))
      .filter((u) => u.protocol.startsWith("http") || u.protocol.startsWith("ws")) // not blob:/data:
      .map((u) => u.host))];
    const allowed = [new URL(APP).host, new URL(API).host, "res.cloudinary.com"];
    check(`${p.name}: only expected hosts contacted`, hosts.every((h) => allowed.includes(h)), hosts.join(", "));
    check(`${p.name}: no console errors`, p.consoleErrors.length === 0, JSON.stringify(p.consoleErrors));
    check(`${p.name}: no unexpected failed requests`, p.failed.length === 0, JSON.stringify(p.failed));
  }
} catch (err) {
  failures.push("crashed: " + err.message);
  console.log("FAIL  crashed: " + err.message);
} finally {
  // cleanup: posts (and their Cloudinary images) go; the two smoke users stay (no delete endpoint)
  for (const id of createdPosts) await rest("DELETE", `/posts/${id}`, userA?.token).catch(() => {});
  socket.close();
  browser.kill();
}

console.log(`\n${passed} passed, ${failures.length} failed`);
if (userA && userB) console.log(`(test accounts left in the database: ${userA.username}, ${userB.username})`);
process.exit(failures.length ? 1 : 0);
