/** Launched by DeliveryAPI.test_browser_with_postgres against its loopback FastAPI server. */
import assert from "node:assert/strict";
import { chromium } from "playwright";
import { buildCandidateShell } from "./browser/build.mjs";

const [publicDir, origin, ownerId, peerId] = process.argv.slice(2);
await buildCandidateShell(publicDir);
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const json = { headers: { Accept: "application/json" } };

async function signedInContext(id, token) {
  const context = await browser.newContext({ viewport: { width: 360, height: 800 } });
  await context.addCookies([{ url: origin, name: "delivery_test_session", value: token, httpOnly: true }]);
  await context.addInitScript(account => sessionStorage.setItem("fixture-account-id", account), id);
  return context;
}

try {
  const owner = await signedInContext(ownerId, process.env.DELIVERY_OWNER_COOKIE);
  const page = await owner.newPage();
  page.setDefaultTimeout(8000);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const document = await page.goto(origin + "/me/exams");
  assert.match(document.headers()["content-type"], /text\/html/);
  await page.getByRole("button", { name: "Start exam" }).click();
  await page.waitForURL(/\/attempts\/[\da-f-]{36}$/);
  const url = page.url();
  const response = await owner.request.get(url, json);
  assert.match(response.headers()["content-type"], /application\/json/);
  const paper = await response.json();
  const single = paper.items.find(item => item.kind === "single");
  const written = paper.items.find(item => item.kind === "written");
  await page.getByRole("button", { name: `Question ${single.display_no}, unanswered` }).click();
  const singleUrl = url + "/items/" + single.slot;
  // Let FastAPI commit the edit, then drop only the acknowledgment to this browser.
  await page.route(singleUrl, async route => {
    const upstream = await route.fetch();
    assert.equal(upstream.status(), 200);
    await route.abort("connectionreset");
  }, { times: 1 });
  await page.getByRole("radio", { name: "1", exact: true }).check();
  await page.getByText("On this device", { exact: true }).waitFor();
  const recovered = page.waitForResponse(r => r.url() === singleUrl && r.status() === 200);
  await page.reload();
  assert.equal((await (await recovered).json()).revision, 1);
  await page.getByText("Saved on server", { exact: true }).waitFor();
  assert.equal(await page.getByRole("radio", { name: "1", exact: true }).isChecked(), true);

  await page.getByRole("button", { name: `Question ${written.display_no}, unanswered` }).click();
  await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
  await owner.setOffline(true);
  await page.getByLabel("Your answer").fill("Saved after reconnecting.");
  await page.getByText("On this device", { exact: true }).waitFor();
  await page.reload();
  assert.equal(await page.getByLabel("Your answer").inputValue(), "Saved after reconnecting.");
  const device = await signedInContext(ownerId, process.env.DELIVERY_OWNER_COOKIE);
  const writtenUrl = url + "/items/" + written.slot;
  const remote = await device.request.put(writtenUrl, {
    data: { base_revision: 0, flagged: false, written_answer: "Answer from another device." },
  });
  assert.equal((await remote.json()).revision, 1);
  await device.close();
  // An already-open document can miss the connectivity notification during reload.
  await page.evaluate(() => window.addEventListener("online", e => e.stopImmediatePropagation(),
    { capture: true, once: true }));
  // Reconnection can be announced before the first API read reaches the server.
  await page.route(url, route => route.abort("internetdisconnected"), { times: 1 });
  const conflict = page.waitForResponse(r => r.url() === writtenUrl && r.status() === 409);
  await owner.setOffline(false);
  assert.equal((await (await conflict).json()).code, "stale_revision");
  await page.getByText("Answer conflict", { exact: true }).waitFor();
  const replay = page.waitForResponse(r => r.url() === writtenUrl && r.status() === 200);
  await page.getByRole("button", { name: "Keep my draft" }).click();
  assert.equal((await (await replay).json()).revision, 2);
  await page.getByText("Saved on server", { exact: true }).waitFor();

  const peer = await signedInContext(peerId, process.env.DELIVERY_PEER_COOKIE);
  const otherPage = await peer.newPage();
  await otherPage.goto(url);
  await otherPage.getByText("Access to this attempt has ended.").waitFor();
  assert.equal((await peer.request.get(url, json)).status(), 404);
  assert.equal(await otherPage.getByLabel("Your answer").count(), 0);
  await peer.clearCookies();
  assert.equal((await peer.request.get(url, json)).status(), 401);

  await page.getByRole("button", { name: "Review answers", exact: true }).last().click();
  await page.getByText("2 answered · 1 unanswered · 0 flagged").waitFor();
  const submitted = page.waitForResponse(r => r.url() === url + "/submit" && r.status() === 200);
  await page.getByRole("button", { name: "Confirm submission" }).click();
  const receipt = await (await submitted).json();
  assert.equal(receipt.close_reason, "submitted");
  assert.equal(receipt.attempt_id, paper.attempt_id);
  await page.getByRole("heading", { name: "Final receipt" }).waitFor();
  await page.getByRole("link", { name: "Return to my exams" }).click();
  await page.getByRole("link", { name: "View receipt" }).click();
  await page.getByRole("heading", { name: "Final receipt" }).waitFor();
  assert.equal(await page.locator(".dv-reference").textContent(), receipt.attempt_id);
  assert.deepEqual(await (await owner.request.post(url + "/submit", json)).json(), receipt);

  const shortSitting = await signedInContext(peerId, process.env.DELIVERY_PEER_COOKIE);
  const expiringPage = await shortSitting.newPage();
  await expiringPage.goto(origin + "/me/exams");
  await expiringPage.getByRole("button", {name:"Start exam"}).click();
  await expiringPage.waitForURL(/\/attempts\/[\da-f-]{36}$/);
  const expiringUrl = expiringPage.url();
  const shortPaper = await (await shortSitting.request.get(expiringUrl, json)).json();
  const essay = shortPaper.items.find(item => item.kind === "written");
  await expiringPage.getByRole("button", {name:`Question ${essay.display_no}, unanswered`}).click();
  await expiringPage.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
  await shortSitting.setOffline(true);
  await expiringPage.getByLabel("Your answer").fill("Local only before cutoff.");
  await expiringPage.getByText("On this device", {exact:true}).waitFor();
  await expiringPage.close();
  await new Promise(resolve => setTimeout(resolve, Math.max(0, Date.parse(shortPaper.deadline_at) - Date.now()) + 500));
  const reopened = await shortSitting.newPage();
  await reopened.goto(expiringUrl);
  await reopened.getByText("Time is up. Waiting for the server receipt.").waitFor();
  await shortSitting.setOffline(false);
  await reopened.getByRole("heading", {name:"Time expired"}).waitFor();
  await reopened.getByText(`Unconfirmed local changes on question ${essay.display_no}.`, {exact:false}).waitFor();
  assert.equal(await reopened.getByRole("button", {name:"Confirm submission"}).count(), 0);
  assert.deepEqual(errors, []);
} finally {
  await browser.close();
}
