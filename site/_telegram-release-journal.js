import { currentReleaseVersions, isNewerRelease, releaseCursorFromStorage, serializeReleaseCursor,
  releaseNotificationText, releaseLinksKeyboard } from "./_telegram-support.js";
import { pilotCredentialRole } from "./_telegram-pilot-credentials.js";

export const RELEASE_DISPATCH_PATH = "/api/telegram/releases/dispatch";
export const RELEASE_PILOT_PATH = "/api/telegram/releases/pilot";
const ORIGIN = "https://outpost.com.ua";
const MAX_BYTES = 25 * 1024 * 1024;
const MAX_BATCH = 3; // Conservative D1/HTTP subrequest budget on Workers Free.
const LEASE_MS = 120000;
const MAX_ATTEMPTS = 8;
const PRODUCTS = new Set(["outpost", "accounting"]);

function require(ok, code) { if (!ok) throw new Error(code); }
function ready(env) {
  return String(env?.TELEGRAM_CONFIRMED_RELEASES_ENABLED || "") === "1" &&
    String(env?.TELEGRAM_PUBLIC_ENABLED || "") === "1" &&
    String(env?.OUTPOST_PREVIEW_ONLY || "") !== "1" &&
    Boolean(env?.ANALYTICS_DB && env?.ASSETS?.fetch && env?.TELEGRAM_BOT_TOKEN);
}
function database(env) {
  require(ready(env), "confirmed_release_disabled");
  const policy = deliveryPolicy(env);
  const db = env.ANALYTICS_DB.withSession ? env.ANALYTICS_DB.withSession("first-primary") : env.ANALYTICS_DB;
  // Fixed technical-table namespace, never supplied by a request. Pilot evidence
  // cannot seed a real audience or suppress a future subscriber announcement.
  return {
    policy,
    prepare(sql) {
      if (policy.mode === "pilot") sql = sql
        .replace(/\btelegram_release_(events|deliveries|dispatch_control)\b/g, "telegram_release_pilot_$1")
        .replace(/\bidx_telegram_release_due\b/g, "idx_telegram_release_pilot_due");
      return db.prepare(sql);
    },
    batch(statements) { return db.batch(statements); }
  };
}
export function deliveryPolicy(env) {
  const mode = String(env?.TELEGRAM_RELEASE_DELIVERY_MODE || "off");
  require(mode === "pilot" || mode === "subscribers", "release_delivery_disabled");
  const chat = String(env?.TELEGRAM_ADMIN_CHAT_ID || "");
  if (mode === "pilot") require(/^[1-9]\d{0,15}$/.test(chat) && Number.isSafeInteger(Number(chat)), "pilot_recipient_invalid");
  return { mode, chat: mode === "pilot" ? chat : null };
}
function changed(result) { return Number(result?.meta?.changes || 0) === 1; }
function equal(left, right) {
  left = String(left || ""); right = String(right || "");
  if (left.length < 32 || left.length !== right.length) return false;
  let diff = 0; for (let i = 0; i < left.length; i++) diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
  return diff === 0;
}
function reply(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: {
    "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex, nofollow"
  }});
}
export function validateRelease(input) {
  require(PRODUCTS.has(input?.product) && /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/.test(input.version), "invalid_release");
  require(input.version.split('.').every(x=>Number.isSafeInteger(Number(x))),"invalid_release");
  require(/^[A-Fa-f0-9]{64}$/.test(input.sha256) && /^[a-f0-9]{40}$/.test(input.source_sha), "invalid_release");
  require(Number.isSafeInteger(input.size_bytes) && input.size_bytes >= 1024 && input.size_bytes <= MAX_BYTES, "invalid_release");
  const installer = `OutPOSt-${input.product === "accounting" ? "Accounting-" : ""}Setup-v${input.version}.exe`;
  return { product: input.product, version: input.version, sha256: input.sha256.toUpperCase(),
    size_bytes: input.size_bytes, source_sha: input.source_sha, installer };
}

export async function ensureReleaseJournal(db) {
  // Additive, isolated technical tables. Never alter/reset subscriber cursors.
  await db.batch([
    db.prepare(`CREATE TABLE IF NOT EXISTS telegram_release_events (
      product TEXT NOT NULL, version TEXT NOT NULL, installer TEXT NOT NULL, sha256 TEXT NOT NULL,
      size_bytes INTEGER NOT NULL, source_sha TEXT NOT NULL, confirmed_at TEXT NOT NULL,
      PRIMARY KEY(product,version))`),
    db.prepare(`CREATE TABLE IF NOT EXISTS telegram_release_deliveries (
      product TEXT NOT NULL, version TEXT NOT NULL, chat_id TEXT NOT NULL,
      state TEXT NOT NULL CHECK(state IN ('pending','sending','retry','sent','cancelled','failed','unknown')),
      attempts INTEGER NOT NULL DEFAULT 0, not_before INTEGER NOT NULL DEFAULT 0,
      lease_nonce TEXT, lease_until INTEGER, message_id INTEGER, error_kind TEXT,
      cursor_synced INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(product,version,chat_id))`),
    db.prepare(`CREATE INDEX IF NOT EXISTS idx_telegram_release_due ON telegram_release_deliveries(state,not_before)`),
    db.prepare(`CREATE TABLE IF NOT EXISTS telegram_release_dispatch_control (
      id INTEGER PRIMARY KEY CHECK(id=1), not_before INTEGER NOT NULL DEFAULT 0)`),
    db.prepare(`INSERT OR IGNORE INTO telegram_release_dispatch_control(id,not_before) VALUES(1,0)`)
  ]);
}

async function boundedBytes(response, limit) {
  require(response.body, "live_body_missing");
  const reader = response.body.getReader(); const bytes = new Uint8Array(limit); let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read(); if (done) break;
      require(size + value.length <= limit, "live_size_mismatch"); bytes.set(value, size); size += value.length;
    }
  } finally { await reader.cancel().catch(() => {}); }
  return bytes.subarray(0, size);
}
async function liveFetch(path, fetcher) {
  const response = await fetcher(ORIGIN + path, { redirect: "manual", headers: { Accept: "*/*" }, signal: AbortSignal.timeout(15000) });
  require(response.status === 200, "live_unavailable"); return response;
}
export async function verifyConfirmedReleaseLive(env, release, fetcher = fetch) {
  const r = validateRelease(release);
  const own = await currentReleaseVersions(env);
  require(own[r.product] === r.version, "source_release_mismatch");
  const page = await liveFetch("/download", fetcher);
  const html = new TextDecoder().decode(await boundedBytes(page, 512 * 1024));
  const prefix = r.product === "accounting" ? "OutPOSt-Accounting-Setup-v" : "OutPOSt-Setup-v";
  const versions = new Set([...html.matchAll(new RegExp(prefix + "(\\d+\\.\\d+\\.\\d+)\\.exe", "g"))].map(x => x[1]));
  require(versions.size === 1 && versions.has(r.version), "live_release_mismatch");
  const sumResponse = await liveFetch("/downloads/" + r.installer.replace(".exe", ".sha256.txt"), fetcher);
  const sum = new TextDecoder().decode(await boundedBytes(sumResponse, 1024)).trim();
  const match = sum.match(/^([A-Fa-f0-9]{64})\s+\*?([^\s]+)$/);
  require(match && match[1].toUpperCase() === r.sha256 && match[2] === r.installer, "live_checksum_mismatch");
  const response = await liveFetch("/downloads/" + r.installer, fetcher);
  const bytes = await boundedBytes(response, r.size_bytes);
  require(bytes.length === r.size_bytes && bytes[0] === 77 && bytes[1] === 90, "live_size_mismatch");
  const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map(x => x.toString(16).padStart(2,"0")).join("").toUpperCase();
  require(hash === r.sha256, "live_hash_mismatch");
  return { ...r, current: own };
}

export async function confirmRelease(env, input, deps = {}) {
  const db = database(env); const release = validateRelease(input);
  const verify = deps.verifyLive || verifyConfirmedReleaseLive;
  await verify(env, release); // No journal/queue write before exact live verification.
  await ensureReleaseJournal(db);
  const now = new Date(deps.now?.() ?? Date.now()).toISOString();
  await db.prepare(`INSERT OR IGNORE INTO telegram_release_events
    (product,version,installer,sha256,size_bytes,source_sha,confirmed_at) VALUES(?,?,?,?,?,?,?)`)
    .bind(release.product,release.version,release.installer,release.sha256,release.size_bytes,release.source_sha,now).run();
  const stored = await db.prepare(`SELECT * FROM telegram_release_events WHERE product=? AND version=?`).bind(release.product,release.version).first();
  require(stored && stored.sha256 === release.sha256 && stored.size_bytes === release.size_bytes && stored.installer === release.installer, "immutable_release_conflict");
  if (db.policy.mode === "pilot") {
    await db.prepare(`INSERT OR IGNORE INTO telegram_release_deliveries(product,version,chat_id,state)
      VALUES(?,?,?,'pending')`).bind(release.product,release.version,db.policy.chat).run();
  } else {
    await db.prepare(`INSERT OR IGNORE INTO telegram_release_deliveries(product,version,chat_id,state)
      SELECT ?,?,chat_id,'pending' FROM telegram_update_subscribers
      WHERE julianday(subscribed_at) <= julianday(?)`).bind(release.product,release.version,stored.confirmed_at).run();
  }
  return { ok: true, confirmed: true, audience: db.policy.mode, product: release.product, version: release.version, notification_sent: false };
}

export async function sendJournalMessage(env, payload, fetcher = fetch) {
  let response;
  try {
    response = await fetcher(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload),
      redirect:"error", signal:AbortSignal.timeout(15000)
    });
  } catch { return { kind:"unknown", error:"transport_unconfirmed" }; }
  let data; try { data = JSON.parse(new TextDecoder().decode(await boundedBytes(response, 65536))); }
  catch { return { kind:"unknown", error:"response_unconfirmed" }; }
  if (response.ok && data?.ok === true && Number.isSafeInteger(data.result?.message_id) && data.result.message_id > 0) {
    return { kind:"sent", message_id:data.result.message_id };
  }
  // Telegram's explicit ok:false is a rejected request. A bare 5xx/timeout
  // is NOT proof of rejection and therefore must not be replayed automatically.
  if (data?.ok === false && Number.isInteger(data.error_code)) {
    if (data.error_code === 429) {
      const seconds = Number(data.parameters?.retry_after);
      if (!Number.isSafeInteger(seconds) || seconds < 1 || seconds > 86400) return {kind:"unknown",error:"invalid_retry_after"};
      return {kind:"retry",error:"flood_control",retry_ms:seconds*1000};
    }
    if (data.error_code >= 500 && data.error_code <= 599) return {kind:"retry",error:"server_rejected"};
    return {kind:"failed",error:"api_rejected"};
  }
  return {kind:"unknown",error:"response_unconfirmed"};
}

async function syncCursor(db, job, current) {
  if (db.policy.mode === "pilot") {
    await db.prepare(`UPDATE telegram_release_deliveries SET cursor_synced=1 WHERE product=? AND version=? AND chat_id=? AND state='sent'`)
      .bind(job.product,job.version,job.chat_id).run();
    return; // A test must never advance, reset or create a subscriber cursor.
  }
  for (let attempt = 0; attempt < 1; attempt++) {
    const subscriber = await db.prepare(`SELECT last_notified_version FROM telegram_update_subscribers WHERE chat_id=?`).bind(job.chat_id).first();
    if (!subscriber) break; // Never re-create an unsubscribed user.
    const previous = releaseCursorFromStorage(subscriber.last_notified_version, current);
    if (!isNewerRelease(job.version, previous[job.product])) break;
    const next = serializeReleaseCursor({...previous,[job.product]:job.version});
    const result = await db.prepare(`UPDATE telegram_update_subscribers SET last_notified_version=?,updated_at=?
      WHERE chat_id=? AND last_notified_version=?`).bind(next,new Date().toISOString(),job.chat_id,subscriber.last_notified_version).run();
    if (!changed(result)) continue;
    break;
  }
  // A failed CAS remains repairable; no send is needed for cursor repair.
  const subscriber = await db.prepare(`SELECT last_notified_version FROM telegram_update_subscribers WHERE chat_id=?`).bind(job.chat_id).first();
  if (!subscriber || !isNewerRelease(job.version, releaseCursorFromStorage(subscriber.last_notified_version,current)[job.product])) {
    await db.prepare(`UPDATE telegram_release_deliveries SET cursor_synced=1 WHERE product=? AND version=? AND chat_id=? AND state='sent'`)
      .bind(job.product,job.version,job.chat_id).run();
  }
}

export async function pumpReleaseJournal(env, deps = {}) {
  const db = database(env); await ensureReleaseJournal(db);
  const now = deps.now?.() ?? Date.now();
  // A terminated process may have sent its message. Expiry is quarantine, NOT retry.
  await db.prepare(`UPDATE telegram_release_deliveries SET state='unknown',error_kind='lease_expired'
    WHERE state='sending' AND lease_until<=?`).bind(now).run();
  const cooldown = await db.prepare(`SELECT not_before FROM telegram_release_dispatch_control WHERE id=1`).first();
  if (cooldown.not_before > now) return {ok:true,audience:db.policy.mode,cooldown:true,sent:0};
  const current = await currentReleaseVersions(env);
  // Superseded queues must not starve the current release at the front of a
  // bounded batch. This never announces/cancels a forward release on rollback.
  const old = await db.prepare(`SELECT DISTINCT product,version FROM telegram_release_deliveries
    WHERE state IN ('pending','retry') AND version<>CASE product WHEN 'outpost' THEN ? ELSE ? END LIMIT 2`)
    .bind(current.outpost,current.accounting||"").all();
  for (const event of old.results||[]) if(isNewerRelease(current[event.product],event.version)) {
    await db.prepare(`UPDATE telegram_release_deliveries SET state='cancelled',error_kind='superseded'
      WHERE product=? AND version=? AND state IN ('pending','retry')`).bind(event.product,event.version).run();
  }
  const repair = await db.prepare(`SELECT product,version,chat_id FROM telegram_release_deliveries WHERE state='sent' AND cursor_synced=0 LIMIT 1`).first();
  if (repair) await syncCursor(db,repair,current);
  const pending = await db.prepare(`SELECT d.*,e.installer,e.sha256,e.size_bytes,e.source_sha
    FROM telegram_release_deliveries d JOIN telegram_release_events e USING(product,version)
    WHERE d.state IN ('pending','retry') AND d.not_before<=?
    ORDER BY d.not_before,d.product,d.version,d.chat_id LIMIT ?`).bind(now,MAX_BATCH).all();
  const verified = new Set(); const blocked = new Set();
  const result = {ok:true,audience:db.policy.mode,examined:0,sent:0,retry:0,unknown:0,cancelled:0,blocked:0,failed:0};
  for (const job of pending.results || []) {
    result.examined++;
    const event = job.product+":"+job.version;
    if (!verified.has(event) && !blocked.has(event)) {
      try { await (deps.verifyLive || verifyConfirmedReleaseLive)(env,job); verified.add(event); }
      catch { blocked.add(event); }
    }
    if (blocked.has(event)) { result.blocked++; continue; }
    const nonce = deps.uuid?.() || crypto.randomUUID();
    const claim = await db.prepare(`UPDATE telegram_release_deliveries SET state='sending',lease_nonce=?,lease_until=?,attempts=attempts+1
      WHERE product=? AND version=? AND chat_id=? AND state IN ('pending','retry') AND not_before<=?`)
      .bind(nonce,now+LEASE_MS,job.product,job.version,job.chat_id,now).run();
    if (!changed(claim)) continue;
    const pilot = db.policy.mode === "pilot";
    const subscriber = pilot ? null : await db.prepare(`SELECT last_notified_version FROM telegram_update_subscribers WHERE chat_id=?`).bind(job.chat_id).first();
    const previous = subscriber ? releaseCursorFromStorage(subscriber.last_notified_version,current) : null;
    const finish = (state,kind,delay=0,messageId=null) => db.prepare(`UPDATE telegram_release_deliveries
      SET state=?,error_kind=?,not_before=?,message_id=? WHERE product=? AND version=? AND chat_id=? AND state='sending' AND lease_nonce=?`)
      .bind(state,kind,delay,messageId,job.product,job.version,job.chat_id,nonce).run();
    if (pilot ? job.chat_id !== db.policy.chat : (!subscriber || !/^-?\d+$/.test(job.chat_id) || !isNewerRelease(job.version,previous[job.product]))) {
      await finish("cancelled","unsubscribed_or_not_newer"); result.cancelled++; continue;
    }
    let delivered;
    try { delivered = await (deps.send || sendJournalMessage)(env,{chat_id:job.chat_id,
      text:(pilot ? "🧪 Перевірка сповіщень — лише для адміністратора.\n\n" : "") + releaseNotificationText(job.product,job.version),reply_markup:releaseLinksKeyboard(job.product,true)}); }
    catch { delivered = {kind:"unknown",error:"transport_unconfirmed"}; }
    if (delivered.kind === "sent") {
      require(Number.isSafeInteger(delivered.message_id) && delivered.message_id > 0,"invalid_send_ack");
      // Persist the acknowledgement before moving any subscriber cursor. If this
      // write fails the sending lease is quarantined; never repeat a known send.
      require(changed(await finish("sent",null,0,delivered.message_id)),"delivery_ack_store_failed");
      result.sent++; await syncCursor(db,job,current);
    } else if (delivered.kind === "retry" && job.attempts + 1 < MAX_ATTEMPTS) {
      const delay = Math.max(delivered.retry_ms || 0, Math.min(3600000,30000 * (2 ** job.attempts))) + 1000;
      await finish("retry",delivered.error,now+delay); result.retry++;
      if (delivered.error === "flood_control") {
        await db.prepare(`UPDATE telegram_release_dispatch_control SET not_before=MAX(not_before,?) WHERE id=1`).bind(now+delay).run(); break;
      }
    } else {
      const state = delivered.kind === "unknown" ? "unknown" : "failed";
      await finish(state,delivered.error || "attempts_exhausted"); result[state]++;
    }
  }
  return result;
}

export async function releaseJournalStatus(env) {
  const db=database(env);await ensureReleaseJournal(db);
  const rows=await db.prepare(`SELECT product,version,state,COUNT(*) AS count FROM telegram_release_deliveries GROUP BY product,version,state`).all();
  const deliveries=rows.results||[];
  return {ok:true,audience:db.policy.mode,deliveries,reconciliation_required:deliveries.some(row=>row.state==="unknown")}; // No chat IDs, tokens or raw API errors.
}

export async function handleReleaseDispatch(request, env) {
  const url=new URL(request.url);
  if (url.protocol!=="https:" || url.port || !["outpost.com.ua","www.outpost.com.ua"].includes(url.hostname) || !ready(env)) return reply({ok:false,error:"confirmed_release_disabled"},503);
  if(request.method!=="POST")return reply({ok:false,error:"method_not_allowed"},405);
  const supplied=request.headers.get("x-outpost-release-key");
  if(!equal(supplied,env.TELEGRAM_RELEASE_CONFIRM_KEY) && !equal(supplied,env.TELEGRAM_RELEASE_PUMP_KEY)) return reply({ok:false,error:"unauthorized"},401);
  let body; try {body=JSON.parse(new TextDecoder().decode(await boundedBytes(request,8192)));}
  catch {return reply({ok:false,error:"invalid_request"},400);}
  const confirm=body?.action==="confirm";
  const key=confirm?env.TELEGRAM_RELEASE_CONFIRM_KEY:env.TELEGRAM_RELEASE_PUMP_KEY;
  const privileged=[env.TELEGRAM_SETUP_KEY,env.TELEGRAM_WEBHOOK_SECRET,env.TELEGRAM_BOT_TOKEN];
  if(!key || privileged.includes(key) || env.TELEGRAM_RELEASE_CONFIRM_KEY===env.TELEGRAM_RELEASE_PUMP_KEY || !equal(request.headers.get("x-outpost-release-key"),key)) return reply({ok:false,error:"unauthorized"},401);
  const allowed=confirm?["action","product","version","sha256","size_bytes","source_sha"]:["action"];
  if(!body || Object.keys(body).some(x=>!allowed.includes(x)) || !["confirm","tick","status"].includes(body.action))return reply({ok:false,error:"invalid_request"},400);
  try { deliveryPolicy(env); } catch { return reply({ok:false,error:"release_delivery_disabled"},503); }
  try {
    if(confirm)return reply(await confirmRelease(env,body));
    if(body.action==="status")return reply(await releaseJournalStatus(env));
    return reply(await pumpReleaseJournal(env));
  } catch {return reply({ok:false,error:"release_dispatch_failed"},502);}
}

// An expiring, fixed private-chat capability. No Pages configuration/secret
// changes and no caller-selected audience. Normal subscriber dispatch stays OFF.
export async function handleReleasePilot(request, env, deps = {}) {
  const url = new URL(request.url);
  if (url.protocol !== "https:" || url.port || !["outpost.com.ua","www.outpost.com.ua"].includes(url.hostname) || !ready(env)) return reply({ok:false,error:"confirmed_release_disabled"},503);
  if (request.method !== "POST") return reply({ok:false,error:"method_not_allowed"},405);
  const role = await pilotCredentialRole(request.headers.get("x-outpost-release-key"), deps.verifiers, deps.now?.() ?? Date.now());
  if (!role) return reply({ok:false,error:"unauthorized"},401);
  let body;
  try { body = JSON.parse(new TextDecoder().decode(await boundedBytes(request,8192))); }
  catch { return reply({ok:false,error:"invalid_request"},400); }
  const confirm = body?.action === "confirm";
  const allowed = confirm ? ["action","product","version","sha256","size_bytes","source_sha","expected_admin_chat_id"] : ["action","expected_admin_chat_id"];
  if (!body || Object.keys(body).some(name=>!allowed.includes(name)) || !["confirm","tick","status"].includes(body.action)) return reply({ok:false,error:"invalid_request"},400);
  if ((confirm && role !== "confirm") || (!confirm && role !== "pump")) return reply({ok:false,error:"unauthorized"},401);
  const pilotEnv = {...env, TELEGRAM_RELEASE_DELIVERY_MODE:"pilot"};
  let policy;
  try { policy = deliveryPolicy(pilotEnv); } catch { return reply({ok:false,error:"pilot_recipient_invalid"},503); }
  // Assertion only, not a recipient selector. Wrong/missing IDs cannot send or
  // initialize SQL; the actual recipient is always the configured administrator.
  if (typeof body.expected_admin_chat_id !== "string" || body.expected_admin_chat_id !== policy.chat) return reply({ok:false,error:"pilot_recipient_mismatch"},409);
  try {
    const result = confirm ? await confirmRelease(pilotEnv,body,deps) : body.action === "status" ? await releaseJournalStatus(pilotEnv) : await pumpReleaseJournal(pilotEnv,deps);
    return reply({...result,recipient_verified:true});
  } catch (error) {
    const kinds = new Map([
      ["download_page_unavailable","source_assets_unavailable"], ["assets_binding_unavailable","source_assets_unavailable"],
      ["source_release_mismatch","source_release_mismatch"], ["live_unavailable","live_integrity_unavailable"],
      ["live_checksum_mismatch","live_integrity_mismatch"], ["live_hash_mismatch","live_integrity_mismatch"],
      ["live_release_mismatch","live_integrity_mismatch"], ["live_size_mismatch","live_integrity_mismatch"]
    ]);
    return reply({ok:false,error:"release_dispatch_failed",error_kind:kinds.get(error?.message)||"dispatch_unavailable"},502);
  }
}
