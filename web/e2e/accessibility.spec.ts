import { test, expect } from "@playwright/test";
import { createRequire } from "node:module";
import { login } from "./support";
const require = createRequire(import.meta.url);
test.use({ bypassCSP: true }); // Audit injection only; runtime CSP stays enabled.
test("WCAG automated checks across shopper screens", async ({ page }) => {
  const audit = async () => {
    await page.addScriptTag({ path: require.resolve("axe-core/axe.js") });
    const violations = await page.evaluate(async () => {
      const result = await (window as any).axe.run(document, {
        runOnly: {
          type: "tag",
          values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"],
        },
      });
      return result.violations.map((v: any) => ({
        id: v.id,
        nodes: v.nodes.map((n: any) => ({
          target: n.target,
          summary: n.failureSummary,
        })),
      }));
    });
    expect(violations).toEqual([]);
  };
  await page.goto("/");
  await page.getByRole("heading", { name: "A purchase, with proof." }).waitFor();
  await audit();
  await login(page);
  await audit();
  for (const section of ["Spending permissions", "Purchase history"]) {
    await page.getByRole("button", { name: section, exact: true }).click();
    await audit();
  }
});
