import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir:
    process.env.COMMERCE_BROWSER_PRODUCT === "pharmacy"
      ? "./pharmacy-e2e"
      : "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: process.env.COMMERCE_BROWSER_BASE_URL || "http://127.0.0.1:8510",
    screenshot: "only-on-failure",
    channel: process.env.COMMERCE_TEST_AUDIO ? "chromium" : undefined,
    launchOptions: {
      args: process.env.COMMERCE_TEST_AUDIO
        ? [
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            "--use-file-for-fake-audio-capture=" +
              process.env.COMMERCE_TEST_AUDIO,
          ]
        : [],
    },
    trace: "retain-on-failure",
  },
  reporter: [["list"], ["html", { open: "never" }]],
});
