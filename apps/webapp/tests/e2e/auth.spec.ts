import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.clear());
  await page.route("**/health", async (route) => {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status: "ok", apiVersion: "1.0.0" })
    });
  });
});

test("пользователь видит успешную авторизацию при валидном initData", async ({ page }) => {
  await page.route("**/v1/auth/telegram", async (route) => {
    const responsePayload = {
      accessToken: "jwt-token",
      tokenType: "Bearer",
      expiresIn: 900,
      issuedAt: new Date().toISOString(),
      user: {
        id: 123,
        is_bot: false,
        first_name: "Test",
        last_name: "User",
        username: "test_user"
      },
      chat: null
    };
    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify(responsePayload)
    });
  });

  const authResponsePromise = page.waitForResponse(
    (resp) => resp.url().includes("/v1/auth/telegram") && resp.status() === 200
  );
  await page.goto("/?initData=fake-init-data");
  await authResponsePromise;
  await page.waitForLoadState("networkidle");
  await page.waitForSelector("main.app");

  await expect(page.getByRole("heading", { name: "Авторизация" })).toBeVisible();
  await expect(page.getByText(/Вход выполнен/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Функции" })).toBeVisible();
});

test("без initData отображается уведомление", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  await expect(page.getByRole("heading", { name: "Авторизация" })).toBeVisible();
  await expect(page.getByText("Не авторизован. Откройте Mini App из Telegram.")).toBeVisible();
});
