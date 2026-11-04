import { test, expect, type Page } from "@playwright/test";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
test.use({ bypassCSP: true });
async function login(page: Page, staff = false, persona = "alex") {
  await page.goto("/");
  await page
    .getByRole("button", {
      name: staff ? "Open the pharmacy desk" : "Explore family pickup",
    })
    .waitFor();
  if (!staff && persona !== "alex") {
    const response = await page.request.post("/api/v1/auth/demo", {
      data: { persona },
    });
    expect(response.ok()).toBeTruthy();
    await page.reload();
  } else
    await page
      .getByRole("button", {
        name: staff ? "Open the pharmacy desk" : "Explore family pickup",
      })
      .click();
  await expect(
    page.getByRole("heading", {
      name: staff
        ? "A clear queue. A considered handoff."
        : "Tell us what to take care of.",
    }),
  ).toBeVisible();
}
async function permission(page: Page) {
  await page.getByRole("button", { name: "Set pickup permission" }).click();
  await page.getByRole("button", { name: "Allow these saved items" }).click();
  await expect(
    page.getByText("Permission active", { exact: true }),
  ).toBeVisible();
}

test("customer and pharmacy team complete one authorized family pickup", async ({
  page,
  browser,
}) => {
  await login(page);
  await permission(page);
  await page
    .getByLabel("Family pickup request")
    .fill("Order regular medicines for my family nearest home, up to $50");
  await page
    .getByRole("button", { name: "Arrange pickup", exact: true })
    .click();
  await expect(
    page.getByText("Your family pickup order is accepted.", { exact: false }),
  ).toBeVisible({ timeout: 20000 });
  await expect(page.getByText("$40.98", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByText("Asterfield Cedar Square", { exact: true }),
  ).toBeVisible();
  const staffContext = await browser.newContext(),
    staff = await staffContext.newPage();
  await login(staff, true);
  await staff
    .getByLabel("I reviewed eligibility and prepared every saved item.")
    .check();
  await staff.getByRole("button", { name: "Confirm prepared & ready" }).click();
  await expect(
    page.getByText(
      "Your complete family order is ready for pickup. Payment is confirmed.",
      { exact: true },
    ),
  ).toBeVisible({ timeout: 15000 });
  const code = await page.locator(".ph-pickup-pass strong").innerText();
  await staff.getByRole("textbox", { name: /Pickup code for/ }).fill(code);
  await staff.getByRole("button", { name: "Confirm collected" }).click();
  await expect(
    page.getByText("Pickup confirmed. Your family order is complete.", {
      exact: true,
    }),
  ).toBeVisible({ timeout: 15000 });
  await page.reload();
  await page
    .getByRole("button", { name: "Pickup history", exact: true })
    .click();
  await expect(page.getByText("picked up", { exact: true })).toBeVisible();
  await staffContext.close();
});

test("strict budget and incomplete voice-style request do not order", async ({
  page,
}) => {
  await login(page, false, "sam");
  await page
    .getByLabel("Family pickup request")
    .fill("Order my family regulars under $40.98");
  await page
    .getByRole("button", { name: "Arrange pickup", exact: true })
    .click();
  await expect(
    page.getByText(
      /The complete basket is \$40.98, above your requested limit/,
    ),
  ).toBeVisible({ timeout: 15000 });
  await expect(
    page.getByText("Your family pickup order is accepted.", { exact: false }),
  ).toHaveCount(0);
  await page
    .getByLabel("Family pickup request")
    .fill("Order the regular medicines");
  await page
    .getByRole("button", { name: "Arrange pickup", exact: true })
    .click();
  await expect(
    page.getByText("Who should I include: you, Dad, Mom or your sister?", {
      exact: true,
    }),
  ).toBeVisible({ timeout: 15000 });
});

test("accessible pharmacy screens, permission keyboard trap and mobile layout", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Explore family pickup" }).waitFor();
  const audit = async () => {
    await page.addScriptTag({ path: require.resolve("axe-core/axe.js") });
    const result = await page.evaluate(async () => {
      const r = await (window as any).axe.run(document, {
        runOnly: {
          type: "tag",
          values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"],
        },
      });
      return r.violations.map((v: any) => ({
        id: v.id,
        targets: v.nodes.map((n: any) => n.target),
      }));
    });
    expect(result).toEqual([]);
  };
  await audit();
  await login(page, false, "sam");
  await audit();
  await page.getByRole("button", { name: "Set pickup permission" }).click();
  await audit();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "My household", exact: true }).click();
  await audit();
  await page
    .getByRole("button", { name: "Pickup history", exact: true })
    .click();
  await audit();
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "Family pickup", exact: true })
    .click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("microphone WAV capture reaches the real local recognizer and workflow", async ({
  page,
  context,
}) => {
  test.skip(
    process.env.COMMERCE_TEST_VOICE !== "1",
    "Local speech runtime is provisioned separately.",
  );
  await context.grantPermissions(["microphone"]);
  await login(page, false, "sam");
  await permission(page);
  const naturalSpeech =
    process.env.COMMERCE_TEST_NEURAL_VOICE === "1"
      ? page.waitForResponse((r) => r.url().endsWith("/speech") && r.ok(), {
          timeout: 90000,
        })
      : null;
  await page.getByRole("button", { name: "Start voice request" }).click();
  await expect(
    page.getByText("Your family pickup order is accepted.", { exact: false }),
  ).toBeVisible({ timeout: 45000 });
  await expect(page.locator(".ph-original-request")).toContainText(/50|fifty/);
  if (naturalSpeech) {
    const speech = await (await naturalSpeech).json();
    await expect(
      page.getByText("Speaking your update…", { exact: true }),
    ).toBeVisible();
    expect(speech.engine).toBe("qwen3-tts-0.6b-8bit-mlx");
    expect(speech.voice).toBe("Ryan");
    expect(speech.text).toContain("Cedar Square");
    expect(speech.duration_seconds).toBeGreaterThan(1);
    expect(Buffer.from(speech.audio, "base64").subarray(0, 4).toString()).toBe(
      "RIFF",
    );
  }
});
