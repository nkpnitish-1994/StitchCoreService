/* Live restricted-beta journey. Credentials stay in memory; never record traces. */
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const region = "ap-southeast-2";
function aws(...args) {
  return JSON.parse(execFileSync("aws", [...args, "--region", region, "--output", "json"], { encoding: "utf8" }));
}
async function main() {
  const stack = aws("cloudformation", "describe-stacks", "--stack-name", "StitchCore-beta").Stacks[0];
  const outputs = Object.fromEntries(stack.Outputs.map(o => [o.OutputKey, o.OutputValue]));
  const base = outputs.WebsiteUrl;
  assert.match(base, /^https:\/\/[a-z0-9]+\.cloudfront\.net$/);
  const config = await fetch(base + "/api/v1/auth/config").then(r => r.json());
  assert.equal(config.beta_sign_in, true, "Run only against restricted beta");
  function account(key) { return JSON.parse(aws("secretsmanager", "get-secret-value", "--secret-id", outputs[key]).SecretString); }
  const customer = account("BetaCustomerSecretArn");
  const admin = account("BetaAdminSecretArn");
  const browser = await chromium.launch({ headless: true, args: ["--no-sandbox"] });
  const failures = [];
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  page.on("pageerror", error => failures.push(error.message));
  try {
    await page.goto(base + "/login");
    await page.getByLabel("Test account").fill(customer.username);
    await page.getByLabel("Password", { exact: true }).fill(customer.password);
    await page.getByRole("button", { name: "Sign in to beta" }).click();
    await page.waitForURL("**/order/new");
    await page.getByRole("heading", { name: "1. Pickup address" }).waitFor();
    if (!(await page.getByLabel("Street and apartment").isVisible())) await page.getByText("Add a pickup address", { exact: true }).click();
    await page.getByLabel("Street and apartment").fill("Synthetic browser test · no collection");
    await page.getByLabel("City", { exact: true }).fill("Beta test");
    await page.getByLabel("PIN code").fill("560001");
    await page.getByRole("button", { name: "Save address" }).click();
    await page.getByRole("status").filter({ hasText: "Pickup address saved" }).waitFor();
    await page.getByLabel("Alteration", { exact: true }).selectOption("trousers.reduce_waist");
    await page.getByLabel("Colour", { exact: true }).fill("Navy");
    await page.getByRole("button", { name: "Review price" }).click();
    await page.getByRole("heading", { name: "Total: ₹199" }).waitFor();
    await page.getByRole("button", { name: "Confirm pickup request" }).click();
    await page.waitForURL(/\/orders\/[0-9a-f-]+$/);
    const detailUrl = page.url();
    const orderId = detailUrl.split("/").pop();
    const orderNumber = await page.getByRole("heading", { level: 1 }).textContent();
    assert.match(orderNumber, /^ORD-/);
    await page.getByRole("heading", { name: "Order timeline" }).waitFor();
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.waitForURL("**/login");
    await page.getByLabel("Test account").fill(admin.username);
    await page.getByLabel("Password", { exact: true }).fill(admin.password);
    await page.getByRole("button", { name: "Sign in to beta" }).click();
    await page.waitForURL("**/operations");
    const card = page.locator("article").filter({ has: page.getByRole("heading", { name: orderNumber }) });
    await card.getByLabel("Logistics partner").selectOption({ label: "Beta logistics" });
    await card.getByLabel("Alteration vendor").selectOption({ label: "Beta alteration partner" });
    await card.getByRole("button", { name: "Save assignment" }).click();
    await card.getByRole("status").filter({ hasText: "Saved to the order timeline" }).waitFor();
    for (const status of ["picked_up", "at_vendor", "alteration_complete", "ready_for_delivery", "out_for_delivery", "delivered"]) {
      await card.getByLabel("Next status").selectOption(status);
      await card.getByLabel("Custody / quality notes").fill("Synthetic browser journey; no physical garments.");
      const response = page.waitForResponse(r => r.url().endsWith(`/orders/${orderId}/status/`) && r.request().method() === "POST");
      await card.getByRole("button", { name: "Record status" }).click();
      assert.equal((await response).status(), 200);
      await card.getByRole("status").filter({ hasText: "Saved to the order timeline" }).waitFor();
      await page.waitForFunction(({ id, status }) => document.querySelector(`a[href='/orders/${id}']`)?.closest("article")?.querySelector(".eyebrow")?.textContent === status.replaceAll("_", " "), { id: orderId, status });
    }
    await page.screenshot({ path: "/tmp/stitchcore-beta-operations.png", fullPage: true });
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.waitForURL("**/login");
    await page.getByLabel("Test account").fill(customer.username);
    await page.getByLabel("Password", { exact: true }).fill(customer.password);
    await page.getByRole("button", { name: "Sign in to beta" }).click();
    await page.waitForURL("**/order/new");
    await page.goto(detailUrl);
    await page.getByRole("heading", { name: orderNumber }).waitFor();
    await page.locator(".eyebrow").filter({ hasText: /^delivered$/ }).waitFor();
    assert.equal(await page.locator(".timeline li").count(), 9);
    await page.screenshot({ path: "/tmp/stitchcore-beta-customer.png", fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, "Mobile layout should fit viewport");
    const result = await page.evaluate(async () => {
      const token = localStorage.getItem("stitchcore_access");
      return {
        unauthenticated: (await fetch("/api/v1/orders/")).status,
        operations: (await fetch("/api/v1/operations/options", { headers: { Authorization: `Bearer ${token}` } })).status,
      };
    });
    assert.deepEqual(result, { unauthenticated: 401, operations: 403 });
    assert.deepEqual(failures, [], "No browser runtime errors");
    console.log(JSON.stringify({ website: base, order: orderNumber, status: "delivered", timeline_events: 9, mobile: "passed", authorization: "passed", browser_errors: 0 }));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.message); process.exit(1); });
