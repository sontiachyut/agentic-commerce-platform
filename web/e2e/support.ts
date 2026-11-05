import { expect, type Page } from "@playwright/test";
import fs from "node:fs";
export async function login(page: Page, persona = "alex") {
  await page.goto("/");
  const origin = new URL(page.url()).origin;
  const mode = await (await page.request.get("/api/v1/auth/config")).json();
  if (mode.mode === "oidc") {
    const credentials = JSON.parse(
      fs.readFileSync("../.local/identity/credentials.json", "utf8"),
    );
    await page.getByRole("button", { name: "Sign in securely" }).click();
    await page.locator("#username").fill(persona);
    await page.locator("#password").fill(credentials[persona]);
    await page.locator("#kc-login").click();
    await page.waitForURL(origin + "/", { timeout: 15000 });
  } else {
    await page
      .getByRole("button", {
        name:
          persona === "operator"
            ? "Open operations console"
            : `Enter ${persona === "alex" ? "Alex" : "Sam"}’s workspace`,
      })
      .click();
  }
  await expect(
    page.getByRole("button", { name: "Spending permissions", exact: true }),
  ).toBeVisible();
}
