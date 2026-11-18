import { test } from "@playwright/test";

import { expectAccessible } from "./helpers";
import { APP_PAGES, openPage } from "./pages";

test.use({ colorScheme: "dark" });

// Dark mode follows the system setting; axe checks colour contrast against the dark tokens as well.
for (const name of APP_PAGES) {
  test(`${name}: accessible in dark mode`, async ({ page }) => {
    await openPage(page, name);
    await expectAccessible(page);
  });
}
