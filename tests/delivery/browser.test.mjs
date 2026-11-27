/** Uses Vite, React and Playwright. CHROME_PATH can select a local Chromium executable. */
import assert from "node:assert/strict";
import test from "node:test";
import { createServer } from "node:http";
import { mkdtemp, readFile, mkdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, extname } from "node:path";
import { chromium } from "playwright";
import { buildCandidateShell } from "./browser/build.mjs";

const common = { flagged:false, revision:0, selected_option_ids:[], written_answer:"", max_marks:2 };
const items = [
  {kind:"single",prompt:"Which measurement estimates species richness?", options:["Number of species","Population density","Mean canopy height"]},
  {kind:"multiple",prompt:"Select the observations recorded in a quadrat survey.", options:["Species count","Ground cover","River discharge"]},
  {kind:"written",prompt:"Describe one source of sampling bias.",options:[]},
].map((q,i)=>({...common,...q,slot:i+1,display_no:i+1,options:q.options.map((label,n)=>({id:n+1,label}))}));

test("dashboard, offline reload, replay, conflict, account preferences and local cleanup", async t => {
  const out = await mkdtemp(join(tmpdir(),"folio-delivery-"));
  t.after(()=>rm(out,{recursive:true,force:true}));
  const assets = await buildCandidateShell(out);
  let receipt;
  let prefs = {font_percent:100, workspace_layout:"standard"};
  const deadline = new Date(Date.now()+1800000).toISOString();
  const dashboard = [{id:"exam",title:"Field ecology",instructions:"Review every response before submitting.",
    opens_at:new Date().toISOString(),closes_at:deadline,deadline_at:deadline,duration_seconds:1800,attempt_id:"sample",status:"available"},
    {id:"next",title:"Conservation genetics",instructions:"Read the population study before answering.",
     opens_at:new Date(Date.now()+86400000).toISOString(),closes_at:new Date(Date.now()+90000000).toISOString(),duration_seconds:3600,status:"upcoming"},
    {id:"prior",title:"Population dynamics",instructions:"",opens_at:new Date(Date.now()-86400000).toISOString(),
     closes_at:new Date(Date.now()-84000000).toISOString(),duration_seconds:2400,attempt_id:"prior-attempt",status:"completed"}];
  ["Soil science", "Plant communities", "Conservation methods", "Wetland systems"].forEach((title, i) => {
    const starts = Date.now() + (i + 2) * 86400000;
    dashboard.push({...dashboard[1], id:"upcoming-" + i, title,
      opens_at:new Date(starts).toISOString(), closes_at:new Date(starts + 3600000).toISOString()});
  });
  const server = createServer(async(req,res)=>{
    const path = req.url;
    const send = (data,status=200) => { res.writeHead(status,{"Content-Type":"application/json"}); res.end(JSON.stringify(data)); };
    if (req.headers.accept?.includes("text/html") || path === "/shell.html") {
      res.writeHead(200,{"Content-Type":"text/html"});return res.end(await readFile(join(out,"index.html")));
    }
    if (assets.includes(path)) {
      res.writeHead(200,{"Content-Type":extname(path)===".js"?"application/javascript":"text/css"});
      return res.end(await readFile(join(out,path)));
    }
    if (path==="/sw.js") {
      res.writeHead(200,{"Content-Type":"application/javascript"});
      return res.end(await readFile(join(out,"sw.js")));
    }
    if(path==="/me/exams") return send(dashboard);
    if(path==="/attempts/sample" || path==="/exams/exam/attempts") return send({
      attempt_id:"sample",title:"Field ecology",items,preferences:prefs,deadline_at:deadline,
      server_time:new Date().toISOString(),...receipt});
    let content="";
    for await(const chunk of req) content+=chunk;
    const body = content && JSON.parse(content);
    if(path.startsWith("/attempts/sample/items/")) {
      const item=items[Number(path.split("/").pop())-1];
      if (body.base_revision!==item.revision) return send({code:"stale_revision",item},409);
      Object.assign(item,body,{revision:item.revision+1});
      return send({revision:item.revision,saved_at:new Date().toISOString()});
    }
    if(path==="/me/preferences") { prefs=body;return send(prefs); }
    if(path==="/attempts/sample/submit") {
      receipt={attempt_id:"sample",finalized_at:new Date().toISOString(),close_reason:"submitted"};return send(receipt);
    }
    send({},404);
  });
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  t.after(()=>server.close());
  const browser=await chromium.launch({executablePath:process.env.CHROME_PATH || undefined});
  t.after(()=>browser.close());
  const origin="http://127.0.0.1:"+server.address().port;
  const context=await browser.newContext({viewport:{width:1280,height:820}});
  const page=await context.newPage();
  page.setDefaultTimeout(8000);
  const shot=async name=>{
    if(process.env.DELIVERY_SCREENSHOTS) {
      await mkdir(process.env.DELIVERY_SCREENSHOTS,{recursive:true});
      await page.screenshot({path:join(process.env.DELIVERY_SCREENSHOTS,name+".png"),fullPage:true});
    }
  };
  await page.goto(origin+"/me/exams");
  await page.getByText("Field ecology").waitFor();
  const plate = page.locator(".dv-ticket .dv-engraving");
  const animationName = locator => locator.evaluate(el => getComputedStyle(el).animationName);
  assert.equal(await animationName(plate), "dv-register-plate");
  await page.emulateMedia({reducedMotion:"reduce"});
  assert.equal(await animationName(plate), "none");
  assert.equal(await animationName(page.locator(".dv-plate-bed")), "none");
  await page.emulateMedia({reducedMotion:"no-preference"});
  await shot("dashboard-desktop");
  const bed = page.locator(".dv-plate-bed");
  const initialTransform = await bed.evaluate(el => getComputedStyle(el).transform);
  await page.locator(".dv-ticket").evaluate(el => scrollBy(0, el.getBoundingClientRect().top + el.offsetHeight / 2));
  await page.waitForFunction(before => getComputedStyle(document.querySelector(".dv-plate-bed")).transform !== before,
    initialTransform);
  const register = page.getByRole("navigation", {name:"Exam register sections"});
  await register.getByRole("link", {name:"Completed"}).focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.activeElement.id === "register-completed" &&
    document.querySelector('.dv-index-tabs [aria-current="location"]')?.textContent === "Completed");
  assert.equal(await page.locator(".dv-calendar-reading b").textContent(),
    await page.locator(".dv-group-completed time").evaluate(el =>
      new Date(el.dateTime).toLocaleString(undefined, {month:"short",day:"numeric",weekday:"short"})));
  await register.getByRole("link", {name:"Available"}).click();
  await page.waitForFunction(() => document.activeElement.id === "register-available" &&
    document.querySelector(".dv-counter")?.getAttribute("aria-label")?.startsWith("Exam 1 of "));
  await page.evaluate(() => scrollTo(0, 0));
  await page.waitForFunction(() => document.querySelector('.dv-index-tabs [aria-current]')?.textContent === "Available");
  await page.getByRole("button", {name:/, 1 exam$/}).first().click();
  assert.equal(await page.locator(".dv-entry").count(),1);
  await page.getByRole("button",{name:"Show all exams"}).click();
  assert.equal(await page.locator(".dv-entry").count(),dashboard.length);
  await page.setViewportSize({width:360,height:800});
  await shot("dashboard-mobile");
  await page.getByRole("button",{name:"Resume attempt"}).click();
  await page.getByRole("radio").first().waitFor();
  await page.evaluate(async()=>{await navigator.serviceWorker.ready;});
  await page.waitForFunction(()=>!!navigator.serviceWorker.controller);
  await shot("attempt-mobile");
  await page.setViewportSize({width:1280,height:820});
  await shot("attempt-desktop");
  await page.getByRole("radio").first().check();
  await page.getByText("Saved on server",{exact:true}).waitFor();
  assert.deepEqual(items[0].selected_option_ids,[1]);
  // A candidate can move straight from a page turn into the response field.
  const keepsFocus = await page.evaluate(async () => {
    document.querySelector('button[aria-label="Question 3, unanswered"]').click();
    await Promise.resolve();
    const input = document.querySelector(".dv-written");
    input.focus();
    await new Promise(resolve => requestAnimationFrame(resolve));
    return document.activeElement === input;
  });
  assert.equal(keepsFocus, true);
  await page.getByRole("button", {name:"Question 1, answered"}).click();
  await page.setViewportSize({width:360,height:800});
  await page.getByText("Workspace settings",{exact:true}).click();
  await page.getByLabel("Text size").selectOption("200");
  await page.getByLabel("Focus layout").click();
  await page.waitForFunction(()=>document.querySelector("main.focus"));
  assert.ok(await page.evaluate(()=>document.body.scrollWidth<=innerWidth));
  await page.getByText("Scratchpad",{exact:true}).click();
  await page.getByLabel("Private rough work").fill("Private note");
  await context.setOffline(true);
  await page.emulateMedia({reducedMotion:"reduce"});
  await page.getByRole("button",{name:"Question 3, unanswered"}).focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction(()=>document.activeElement?.id==="delivery-prompt");
  assert.equal(await animationName(page.locator(".dv-folio-no b span")), "none");
  await page.getByLabel("Your answer").fill("My offline draft");
  await page.getByText("On this device",{exact:true}).waitFor();
  assert.equal(await page.getByLabel("Your answer").evaluate(el=>el===document.activeElement),true);
  await page.reload();
  await page.getByLabel("Your answer").waitFor();
  assert.equal(await page.getByRole("button",{name:"Question 3, answered"}).getAttribute("aria-current"),"step");
  assert.equal(await page.getByLabel("Your answer").inputValue(),"My offline draft");
  await page.getByText("Scratchpad",{exact:true}).click();
  assert.equal(await page.getByLabel("Private rough work").inputValue(),"Private note");
  items[2].written_answer="Accepted on another device";
  items[2].revision++;
  await context.setOffline(false);
  await page.getByText("Answer conflict",{exact:true}).waitFor();
  await shot("conflict-mobile");
  await page.getByRole("button",{name:"Keep my draft"}).click();
  await page.getByText("Saved on server",{exact:true}).waitFor();
  assert.equal(items[2].written_answer,"My offline draft");
  const replacement = await chromium.launch({executablePath:process.env.CHROME_PATH || undefined});
  t.after(()=>replacement.close());
  const device=await replacement.newPage();
  await device.goto(origin+"/attempts/sample");
  await device.waitForSelector("main.focus");
  await device.getByText("Scratchpad",{exact:true}).click();
  assert.equal(await device.getByLabel("Private rough work").inputValue(),"");
  await device.getByLabel("Private rough work").fill("Second device note");
  await device.evaluate(()=>window.fixtureLogout());
  async function localCount(p) {
    return p.evaluate(()=>new Promise(resolve=>{
      const db=indexedDB.open("folio-delivery");
      db.onsuccess=()=>{const r=db.result.transaction("attempts").objectStore("attempts").count();
        r.onsuccess=()=>resolve(r.result);};
    }));
  }
  assert.equal(await localCount(device),0);
  await page.getByRole("button",{name:"Review answers",exact:true}).last().click();
  const lastRow = page.locator(".dv-review-list li").last();
  const marginTransform = () => lastRow.evaluate(el => getComputedStyle(el, "::after").transform);
  assert.equal(await marginTransform(), "none");
  await page.emulateMedia({reducedMotion:"no-preference"});
  await page.evaluate(() => window.scrollTo(0,0));
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const startingMargin = await marginTransform();
  await lastRow.evaluate(el => el.scrollIntoView({block:"start"}));
  await page.waitForFunction(before => getComputedStyle(document.querySelector(".dv-review-list li:last-child"), "::after").transform !== before,
    startingMargin);
  await page.emulateMedia({reducedMotion:"reduce"});
  await page.getByRole("button",{name:"Confirm submission"}).click();
  await page.getByRole("heading",{name:"Final receipt"}).waitFor();
  assert.equal(await animationName(page.locator(".dv-imprint")),"none");
  assert.equal(await page.evaluate(()=>document.activeElement?.id),"receipt-title");
  assert.equal(await localCount(page),0);
  await shot("receipt-mobile");
});
