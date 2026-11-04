import { test, expect } from "@playwright/test";
import { login } from "./support";
test("browser login, CSRF, and revocation on logout", async ({ page }) => {
  await login(page);
  const before = await (await page.request.get("/api/v1/auth/me")).json();
  const token = (await page.context().cookies()).find(
    (cookie) => cookie.name === "commerce_session",
  )!.value;
  expect((await page.request.post("/api/v1/auth/logout")).status()).toBe(403);
  expect(
    (
      await page.request.post("/api/v1/auth/logout", {
        headers: { "X-CSRF-Token": before.csrf_token },
      })
    ).status(),
  ).toBe(200);
  expect(
    (
      await page.request.get("/api/v1/catalog", {
        headers: { Authorization: "Bearer " + token },
      })
    ).status(),
  ).toBe(401);
});
