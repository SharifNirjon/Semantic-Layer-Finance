import { expect, test } from "@playwright/test";
import { mockChat, signIn, switchRole, trackConsoleErrors } from "./helpers";

test.describe("sign-in", () => {
  test("pages require sign-in and come back after it", async ({ page }) => {
    await page.goto("/trust");
    await expect(page).toHaveURL(/\/login\?next=%2Ftrust/);
    await page.getByTestId("login-username").fill("cmo");
    await page.getByTestId("login-password").fill("wrong-password");
    await page.getByTestId("login-submit").click();
    await expect(page.getByTestId("login-error")).toBeVisible();
    await page.getByTestId("login-password").fill("demo123");
    await page.getByTestId("login-submit").click();
    await expect(page).toHaveURL(/\/trust$/);
    await expect(page.getByTestId("role-banner")).toContainText("Chief Marketing Officer");
  });

  test("sign out returns to the sign-in page; non-admins have no user management", async ({ page }) => {
    await signIn(page, "Analyst");
    await expect(page.getByRole("link", { name: /Users/ })).toHaveCount(0);
    await page.getByTestId("sign-out").click();
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe("demo script", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page, "CMO");
  });

  test("executive dashboard shows KPIs, trends and tables with no console errors", async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await page.goto("/dashboard");
    await expect(page.getByTestId("kpi-card")).toHaveCount(6);
    for (const card of await page.getByTestId("kpi-value").all()) await expect(card).not.toHaveText("");
    await expect(page.getByTestId("chart-deposits")).toBeVisible();
    await expect(page.getByTestId("chart-churn").locator("svg").first()).toBeVisible();
    await expect(page.getByTestId("table-campaigns")).toContainText("Student Referral Rewards");
    await expect(page.getByTestId("table-branches")).toContainText("Gazipur");
    await expect(page.getByTestId("as-of")).toContainText("2026-09-30");
    expect(errors).toEqual([]);
  });

  test("copilot answers with chart, table, definition and calculation panels", async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await mockChat(page);
    await page.goto("/copilot");
    await expect(page.getByTestId("copilot-empty")).toBeVisible();
    await expect(page.getByTestId("suggestions").getByRole("button")).not.toHaveCount(0);
    await page.getByTestId("suggestions").getByRole("button").first().click();
    await expect(page.getByTestId("tool-step").first()).toBeVisible();
    await expect(page.getByTestId("answer-text")).toContainText("Definition");
    await expect(page.getByTestId("chat-chart")).toBeVisible();
    await expect(page.getByTestId("chat-table").first()).toContainText("Young Professionals");
    await page.getByTestId("panel-definition").locator("summary").click();
    await expect(page.getByTestId("panel-definition")).toContainText("churn");
    await page.getByTestId("panel-calculation").locator("summary").click();
    await expect(page.getByTestId("cube-query")).toContainText("customers.churn_rate");
    expect(errors).toEqual([]);
  });

  test("switching role visibly changes results", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.getByTestId("kpi-card")).toHaveCount(6);
    const cmoDeposits = await page.getByTestId("kpi-value").first().innerText();
    const cmoBranchRows = await page.getByTestId("table-branches").locator("tbody tr").count();
    expect(cmoBranchRows).toBeGreaterThan(20);

    await switchRole(page, "Branch manager");
    await expect(page.getByTestId("table-branches").locator("tbody tr")).toHaveCount(1);
    await expect(page.getByTestId("table-branches")).toContainText("Narayanganj");
    expect(await page.getByTestId("kpi-value").first().innerText()).not.toBe(cmoDeposits);

    await switchRole(page, "CMO");
    await expect(page.getByTestId("table-branches").locator("tbody tr")).toHaveCount(cmoBranchRows);
  });

  test("trust center: audit log, reconciliation break and dictionary", async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await page.goto("/trust");
    await expect(page.getByTestId("audit-row").first()).toBeVisible();
    await expect(page.getByTestId("audit-log")).toContainText("query_metrics");

    await page.getByTestId("tab-recon").click();
    await expect(page.getByTestId("recon-status")).toContainText("Reconciled");
    await page.getByTestId("recon-toggle").click();
    await expect(page.getByTestId("recon-status")).toContainText("break detected");
    await expect(page.getByTestId("recon-deposits")).toContainText("Fail");
    await page.getByTestId("recon-toggle").click();
    await expect(page.getByTestId("recon-status")).toContainText("Reconciled");

    await page.getByTestId("tab-dictionary").click();
    await page.getByLabel("Search metrics").fill("churn");
    await expect(page.getByTestId("metric-card").filter({ hasText: "Churn rate (monthly)" })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("branch manager is denied reconciliation; dark mode works", async ({ page }) => {
    await page.goto("/trust");
    await switchRole(page, "Branch manager");
    await page.getByTestId("tab-recon").click();
    await expect(page.locator("[role=alert]", { hasText: "not available to branch managers" })).toBeVisible();
    await page.getByRole("button", { name: /switch to dark theme/i }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  });
});
