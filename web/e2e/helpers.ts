import { expect, type Page } from "@playwright/test";
import fixture from "./fixtures/chat-events.json";

const API = process.env.E2E_API_URL ?? "http://localhost:8000";

/** Collects console errors and uncaught page errors; assert it is empty at the end of a test. */
export function trackConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(String(e)));
  return errors;
}

// route.fulfill bypasses the API's own CORS middleware, so mocked responses must carry CORS headers themselves.
const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "authorization, content-type",
  "access-control-allow-methods": "GET, POST, OPTIONS",
};

/**
 * The chat endpoint needs an LLM key, which CI does not have. Replay a real recorded agent run
 * (events captured from the live MCP + Cube pipeline) so the whole chat UI is exercised.
 */
export async function mockChat(page: Page) {
  await page.route(`${API}/health`, (route) =>
    route.fulfill({
      headers: CORS,
      json: { status: "ok", tools: [], llm_configured: true, llm: { provider: "replay", model: "recorded" } },
    }),
  );
  await page.route(`${API}/chat`, (route) => {
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
    const body = fixture.events.map((e) => `event: ${(e as { type: string }).type}\ndata: ${JSON.stringify(e)}\n\n`).join("");
    return route.fulfill({ status: 200, headers: { ...CORS, "content-type": "text/event-stream" }, body });
  });
}

const BANNERS = { CMO: "Chief Marketing Officer", "Branch manager": "Narayanganj", Analyst: "Analyst" } as const;

/** Signs in with a demo account from the sign-in page (the test stack runs with DEMO_LOGINS enabled). */
export async function signIn(page: Page, label: keyof typeof BANNERS) {
  await page.goto("/login");
  await page.getByTestId("demo-accounts").getByRole("button", { name: label, exact: true }).click();
  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.getByTestId("role-banner")).toContainText(BANNERS[label]);
}

/** Signs out and back in as another role, then returns to the page the test was on. */
export async function switchRole(page: Page, label: keyof typeof BANNERS) {
  const url = page.url();
  await page.getByTestId("sign-out").click();
  await signIn(page, label);
  await page.goto(url);
  await expect(page.getByTestId("role-banner")).toContainText(BANNERS[label]);
}
