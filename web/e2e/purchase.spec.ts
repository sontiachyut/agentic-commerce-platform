import { test, expect } from "@playwright/test";

import { login } from "./support";

test("exact approval, confirmed purchase, and persistent history", async ({
  page,
}) => {
  await login(page);
  await page
    .getByLabel("Shopping request")
    .fill("Find a cocoa protein bar under $4 at Kiosk A");
  await page.getByRole("button", { name: "Find an item" }).click();
  await expect(
    page.getByRole("button", { name: "Approve & purchase · $3.50" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/purchase-review-desktop.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Approve & purchase · $3.50" })
    .click();
  await expect(
    page.getByText("Payment & delivery confirmed", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await page.reload();
  await page.getByRole("button", { name: "Purchase history" }).click();
  await expect(
    page
      .getByRole("button", { name: /Find a cocoa protein bar under \$4/ })
      .first(),
  ).toBeVisible();
});

test("lost payment response recovers without a second purchase", async ({
  page,
}) => {
  await login(page);
  await page.getByText("Failure lab", { exact: true }).click();
  await page
    .getByLabel("Scenario", { exact: true })
    .selectOption("payment_response_lost");
  await page
    .getByLabel("Shopping request")
    .fill("Find a peanut protein bar under $4 at Kiosk A");
  await page.getByRole("button", { name: "Find an item" }).click();
  await page
    .getByRole("button", { name: "Approve & purchase · $3.75" })
    .click();
  await expect(
    page.getByText("Payment & delivery confirmed", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await page.getByText("View purchase activity").click();
  await expect(
    page.getByText("source · unresolved", { exact: true }),
  ).toBeVisible();
});

test("ambiguous request asks a question without a purchase", async ({
  page,
}) => {
  await login(page);
  await page.getByLabel("Shopping request").fill("Buy something");
  await page.getByRole("button", { name: "Find an item" }).click();
  await expect(
    page.getByText("clarification required", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Approve & purchase/ }),
  ).toHaveCount(0);
});

test("mobile workspace has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await expect(page.getByLabel("Shopping request")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/workspace-mobile.png",
    fullPage: true,
  });
});
