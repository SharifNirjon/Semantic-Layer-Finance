import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { mockChat, switchRole } from "./helpers";

// Fallback screenshots for the live demo (make screenshots). Skipped unless CAPTURE=1.
const OUT = path.resolve(__dirname, "../../docs/fallback");
const shot = (page: Page, name: string) => page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });

test.skip(!process.env.CAPTURE, "set CAPTURE=1 to record fallback screenshots");

test("record demo steps", async ({ page }) => {
  await mockChat(page);
  await page.goto("/dashboard");
  await expect(page.getByTestId("kpi-card")).toHaveCount(6);
  await page.waitForTimeout(1200);
  await shot(page, "01-dashboard-cmo");

  await page.goto("/copilot");
  await page.getByTestId("suggestions").getByRole("button").first().click();
  await expect(page.getByTestId("chat-chart")).toBeVisible();
  await page.getByTestId("panel-calculation").locator("summary").click();
  await shot(page, "02-copilot-answer-cmo");

  await page.goto("/dashboard");
  await switchRole(page, "Branch manager");
  await expect(page.getByTestId("table-branches").locator("tbody tr")).toHaveCount(1);
  await page.waitForTimeout(1200);
  await shot(page, "03-dashboard-branch-manager");

  await switchRole(page, "CMO");
  await page.goto("/trust");
  await expect(page.getByTestId("audit-row").first()).toBeVisible();
  await shot(page, "04-audit-log");

  await page.getByTestId("tab-recon").click();
  await expect(page.getByTestId("recon-status")).toContainText("Reconciled");
  await shot(page, "05-reconciliation-pass");
  await page.getByTestId("recon-toggle").click();
  await expect(page.getByTestId("recon-status")).toContainText("break detected");
  await shot(page, "06-reconciliation-break");
  await page.getByTestId("recon-toggle").click();
  await expect(page.getByTestId("recon-status")).toContainText("Reconciled");

  await page.getByTestId("tab-dictionary").click();
  await page.getByLabel("Search metrics").fill("nim");
  await shot(page, "07-metric-dictionary");
});
