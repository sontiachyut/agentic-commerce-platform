/** Record the real customer/staff journey; never mock network responses or states. */
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, writeFileSync, copyFileSync } from "node:fs";
import { resolve, join } from "node:path";
import { execFileSync } from "node:child_process";
import { performance } from "node:perf_hooks";
const require = createRequire(resolve("web/package.json"));
const { chromium, expect } = require("@playwright/test");
const output = resolve(
  ".local/demos",
  new Date().toISOString().replace(/[:.]/g, "-"),
);
mkdirSync(output, { recursive: true, mode: 0o700 });
const narration = [
  [
    "intro",
    "Asterfield Family Pickup turns a household request into one confirmed pharmacy pickup. This is the working local product, using fictional people and pharmacy records, simulated payments, and a real local AI interpreter.",
  ],
  [
    "household",
    "The family organizer already has approved access to four saved routines. Prescription items use existing refill records and confirmed demonstration prices. The agent does not select treatments or change prescriptions.",
  ],
  [
    "permission",
    "Before ordering, Alex explicitly allows these saved items, up to fifty dollars per order. That permission has a separate total allowance, order limit and expiry. A spoken request cannot grant itself extra authority.",
  ],
  [
    "blocked",
    "First, a request with a thirty five dollar limit. The full family basket costs forty dollars and ninety eight cents. The system stops. It does not remove somebody's item or use the larger standing allowance to ignore the request.",
  ],
  [
    "voice",
    "Now Alex speaks the request. This recorded voice goes through the browser microphone pipeline and the real local speech recognizer, then into the AI workflow.",
  ],
  [
    "accepted",
    "The backend checks family access, refill eligibility, stock and budget. Cedar Square is selected because the closer store cannot fill the complete basket. Payment is authorized. The order is accepted, but it is not ready and has not yet been charged.",
  ],
  [
    "staff",
    "The pharmacy team sees the same order in its own facility queue. A staff member reviews eligibility and prepares every saved item. Only after that confirmation does the backend capture payment and mark the pickup ready.",
  ],
  [
    "ready",
    "Back in Alex's account, the ready message and pickup code come from the recorded order status. The complete basket, pickup address and confirmed payment are visible together.",
  ],
  [
    "handover",
    "At the pharmacy desk, the customer supplies the pickup code. The handover is confirmed through the fulfillment service. Repeated commands resolve to the same order rather than creating another purchase.",
  ],
  [
    "complete",
    "The customer history now shows a completed pickup. One request, four family members, one location, and a verified outcome. This browser product is a standalone foundation for a future in car interface. It is not a native CarPlay application or a live pharmacy integration.",
  ],
];
writeFileSync(join(output, "narration-input.json"), JSON.stringify(narration));
if (process.env.COMMERCE_DEMO_NARRATION_DIR) {
  const previous = resolve(process.env.COMMERCE_DEMO_NARRATION_DIR);
  const clips = JSON.parse(
    readFileSync(join(previous, "narration.json"), "utf8"),
  );
  if (
    JSON.stringify(clips.map((c) => [c.key, c.text])) !==
    JSON.stringify(narration)
  )
    throw new Error(
      "Cached narration differs from the current script; generate it again.",
    );
  for (const clip of clips) {
    const target = join(output, clip.key + ".wav");
    copyFileSync(clip.path, target);
    clip.path = target;
  }
  writeFileSync(join(output, "narration.json"), JSON.stringify(clips, null, 2));
} else {
  execFileSync(
    "uv",
    ["run", "python", "tools/prepare_demo_narration.py", output],
    { stdio: "inherit" },
  );
}
const audio = new Map(
  JSON.parse(readFileSync(join(output, "narration.json"), "utf8")).map(
    (item) => [item.key, item],
  ),
);
const browser = await chromium.launch({
  channel: "chromium",
  headless: true,
  args: [
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    "--use-file-for-fake-audio-capture=" + process.env.COMMERCE_TEST_AUDIO,
  ],
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  recordVideo: { dir: output, size: { width: 1440, height: 1000 } },
  baseURL: process.env.COMMERCE_BROWSER_BASE_URL,
  permissions: ["microphone"],
  reducedMotion: "reduce",
});
const page = await context.newPage();
const started = performance.now(),
  scenes = [],
  receipts = [],
  spokenUpdates = [];
page.on("response", async (response) => {
  if (!response.url().endsWith("/speech") || !response.ok()) return;
  const result = await response.json();
  const path = join(output, `spoken-update-${spokenUpdates.length + 1}.wav`);
  writeFileSync(path, Buffer.from(result.audio, "base64"));
  spokenUpdates.push({
    path,
    start: elapsed(),
    text: result.text,
    duration: result.duration_seconds,
    engine: result.engine,
    voice: result.voice,
  });
});
const elapsed = () => (performance.now() - started) / 1000;
const pause = (seconds) => page.waitForTimeout(Math.max(0, seconds) * 1000);
async function scene(key, action) {
  const item = { key, start: elapsed(), ...audio.get(key) };
  scenes.push(item);
  console.log("Recording scene:", key);
  await action();
  await pause(item.duration + 1 - (elapsed() - item.start));
  item.end = elapsed();
}
async function signOut() {
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
}
async function customer() {
  await page
    .getByRole("button", { name: "Explore family pickup", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Tell us what to take care of." }),
  ).toBeVisible();
}
async function staff() {
  await page
    .getByRole("button", { name: "Open the pharmacy desk", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "A clear queue. A considered handoff." }),
  ).toBeVisible();
}
async function receipt() {
  const response = await page.request.get("/api/v1/pharmacy/workspace");
  expect(response.ok()).toBeTruthy();
  const workspace = await response.json();
  const latest = workspace.requests[0];
  const result = await page.request.get(
    "/api/v1/pharmacy/requests/" + latest.id,
  );
  const data = await result.json();
  receipts.push({ at_seconds: elapsed(), ...data });
  return data;
}
let voiceStart = null,
  videoPath;
try {
  await scene("intro", async () => {
    await page.goto("/");
    await expect(
      page.getByRole("button", { name: "Explore family pickup" }),
    ).toBeVisible();
    await page.screenshot({ path: join(output, "cover.png") });
  });
  await scene("household", async () => {
    await customer();
    await expect(
      page.getByText(
        process.env.COMMERCE_MODEL_PROVIDER === "codex"
          ? "Local AI assistant"
          : "Rule-based development demo",
        { exact: true },
      ),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "My household", exact: true })
      .click();
  });
  await scene("permission", async () => {
    await page
      .getByRole("button", { name: "Family pickup", exact: true })
      .click();
    await page.getByRole("button", { name: "Set pickup permission" }).click();
    await pause(4);
    await page.getByRole("button", { name: "Allow these saved items" }).click();
    await expect(
      page.getByText("Permission active", { exact: true }),
    ).toBeVisible();
  });
  await scene("blocked", async () => {
    await page
      .getByLabel("Family pickup request")
      .fill(
        "Order the regular medicines for my family nearest home, up to $35",
      );
    await page
      .getByRole("button", { name: "Arrange pickup", exact: true })
      .click();
    await expect(
      page.getByText(
        /The complete basket is \$40.98, above your requested limit/,
      ),
    ).toBeVisible({ timeout: 130000 });
    const blocked = await receipt();
    expect(blocked.state).toBe("BUDGET_EXCEEDED");
    expect(blocked.order).toBeFalsy();
    await page
      .locator(".ph-request-progress")
      .evaluate((el) => el.scrollIntoView({ block: "center" }));
  });
  await scene("voice", async () => {
    await pause(audio.get("voice").duration + 0.4);
    await page
      .getByRole("button", { name: "Start voice request" })
      .scrollIntoViewIfNeeded();
    voiceStart = elapsed();
    await page.getByRole("button", { name: "Start voice request" }).click();
    await expect(
      page.getByText("Your family pickup order is accepted.", { exact: false }),
    ).toBeVisible({ timeout: 130000 });
    await page
      .locator(".ph-request-progress")
      .evaluate((el) => el.scrollIntoView({ block: "center" }));
    const accepted = await receipt();
    expect(accepted.order.amount_minor).toBe(4098);
    expect(accepted.order.facility.name).toBe("Cedar Square");
    expect(accepted.order.state).toBe("AWAITING_REVIEW");
    expect(accepted.order.payment_state).toBe("AUTHORIZED");
    expect(accepted.order.terms.lines).toHaveLength(4);
    await expect.poll(() => spokenUpdates.length, { timeout: 95000 }).toBe(1);
    await pause(spokenUpdates[0].duration + 1);
  });
  await scene("accepted", async () => {
    await page
      .locator(".ph-request-progress")
      .evaluate((el) => el.scrollIntoView({ block: "center" }));
    await page.screenshot({ path: join(output, "accepted.png") });
  });
  await scene("staff", async () => {
    await signOut();
    await staff();
    await pause(4);
    await page
      .getByLabel("I reviewed eligibility and prepared every saved item.")
      .check();
    await page
      .getByRole("button", { name: "Confirm prepared & ready" })
      .click();
    await expect(
      page.getByRole("textbox", { name: /Pickup code for/ }),
    ).toBeVisible({ timeout: 15000 });
    await page.screenshot({ path: join(output, "staff.png") });
  });
  let pickupCode;
  const openLatest = async () => {
    await page
      .getByRole("button", { name: "Pickup history", exact: true })
      .click();
    await page.locator(".ph-history > button").first().click();
  };
  await scene("ready", async () => {
    await signOut();
    await customer();
    await openLatest();
    await expect(
      page.getByText(
        "Your complete family order is ready for pickup. Payment is confirmed.",
        { exact: true },
      ),
    ).toBeVisible();
    pickupCode = await page.locator(".ph-pickup-pass strong").innerText();
    await page.locator(".ph-pickup-pass").scrollIntoViewIfNeeded();
    const ready = await receipt();
    expect(ready.order.payment_state).toBe("CAPTURED");
    expect(ready.order.fulfillment_state).toBe("READY");
    await pause(
      audio.get("ready").duration + 0.5 - (elapsed() - scenes.at(-1).start),
    );
    await page
      .getByRole("button", { name: "Hear update", exact: true })
      .click();
    await expect.poll(() => spokenUpdates.length, { timeout: 95000 }).toBe(2);
    await pause(spokenUpdates[1].duration + 1);
  });
  await scene("handover", async () => {
    await signOut();
    await staff();
    await page
      .getByRole("textbox", { name: /Pickup code for/ })
      .fill(pickupCode);
    await pause(4);
    await page.getByRole("button", { name: "Confirm collected" }).click();
    await expect(page.getByText("picked up", { exact: true })).toBeVisible({
      timeout: 15000,
    });
  });
  await scene("complete", async () => {
    await signOut();
    await customer();
    await openLatest();
    await expect(
      page.getByText("Pickup confirmed. Your family order is complete.", {
        exact: true,
      }),
    ).toBeVisible();
    await page
      .locator(".ph-request-progress")
      .evaluate((el) => el.scrollIntoView({ block: "center" }));
    const complete = await receipt();
    expect(complete.state).toBe("PICKED_UP");
    expect(complete.order.state).toBe("PICKED_UP");
    expect(complete.order.fulfillment_state).toBe("PICKED_UP");
    await page.screenshot({ path: join(output, "complete.png") });
  });
  videoPath = await page.video().path();
} finally {
  await context.close();
  await browser.close();
  writeFileSync(
    join(output, "recording.json"),
    JSON.stringify(
      {
        title: "Asterfield Pharmacy — Family Pickup",
        created_at: new Date().toISOString(),
        provider: process.env.COMMERCE_MODEL_PROVIDER,
        synthetic: true,
        microphone_source:
          "Locally synthesized prerecorded command, injected at browser microphone capture; real recorder/STT/model/backend/source services.",
        source_video: videoPath,
        voice_start: voiceStart,
        voice_audio: resolve(".local/voice/family-request-padded.wav"),
        scenes,
        spoken_updates: spokenUpdates,
        receipts,
      },
      null,
      2,
    ),
  );
}
console.log("Recording evidence:", output);
execFileSync("uv", ["run", "python", "tools/render_pharmacy_demo.py", output], {
  stdio: "inherit",
});
