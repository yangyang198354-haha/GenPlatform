/**
 * Shared E2E helpers — registration, login, navigation.
 */

let _counter = 0;

/**
 * Generate a unique test email to avoid collisions between parallel worker
 * processes (workers=2 in CI).  Each Playwright worker runs in its own Node
 * process, so a plain module-level counter would reset to 0 in every worker,
 * producing identical emails when two workers happen to call uniqueEmail() in
 * the same millisecond.
 *
 * Fix: include process.pid in the email so worker-1 (pid 12345) and worker-2
 * (pid 12346) can never generate the same address even at identical timestamps.
 */
export function uniqueEmail() {
  return `e2e_${process.pid}_${Date.now()}_${++_counter}@test.internal`;
}

/**
 * Register a new user via the UI registration form and land on the workspace.
 */
export async function registerAndLogin(page, email, password = 'E2eTest123!') {
  await page.goto('/register');
  await page.getByPlaceholder(/至少 2 个字符/).fill(email.split('@')[0]);
  await page.getByPlaceholder(/your@email\.com/).fill(email);
  await page.getByPlaceholder(/至少 8 位/).fill(password);
  await page.getByPlaceholder(/再次输入/).fill(password);
  await page.getByRole('button', { name: /创建账号/ }).click();
  // After registration, should redirect to login
  await page.waitForURL(/\/login/);
  await page.getByPlaceholder(/your@email\.com/).fill(email);
  await page.getByPlaceholder(/输入密码/).fill(password);
  await page.getByRole('button', { name: /登录/ }).click();
  await page.waitForURL(/\/(workspace|knowledge)/);
}

/**
 * Login with an existing account.
 */
export async function login(page, email, password = 'E2eTest123!') {
  await page.goto('/login');
  await page.getByPlaceholder(/your@email\.com/).fill(email);
  await page.getByPlaceholder(/输入密码/).fill(password);
  await page.getByRole('button', { name: /登录/ }).click();
  await page.waitForURL(/\/(workspace|knowledge)/);
}
