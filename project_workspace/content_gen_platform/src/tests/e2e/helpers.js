/**
 * Shared E2E helpers — registration, login, navigation.
 */

let _counter = 0;

/**
 * Generate a unique test email to avoid collisions between parallel runs.
 */
export function uniqueEmail() {
  return `e2e_${Date.now()}_${++_counter}@test.internal`;
}

/**
 * Register a new user via the UI registration form and land on the workspace.
 */
export async function registerAndLogin(page, email, password = 'E2eTest123!') {
  await page.goto('/register');
  await page.getByPlaceholder(/用户名/).fill(email.split('@')[0]);
  await page.getByPlaceholder(/邮箱/).fill(email);
  await page.getByPlaceholder(/密码/).fill(password);
  await page.getByRole('button', { name: /注册/ }).click();
  // After registration, should redirect to login
  await page.waitForURL(/\/login/);
  await page.getByPlaceholder(/邮箱/).fill(email);
  await page.getByPlaceholder(/密码/).fill(password);
  await page.getByRole('button', { name: /登录/ }).click();
  await page.waitForURL(/\/(workspace|knowledge)/);
}

/**
 * Login with an existing account.
 */
export async function login(page, email, password = 'E2eTest123!') {
  await page.goto('/login');
  await page.getByPlaceholder(/邮箱/).fill(email);
  await page.getByPlaceholder(/密码/).fill(password);
  await page.getByRole('button', { name: /登录/ }).click();
  await page.waitForURL(/\/(workspace|knowledge)/);
}
