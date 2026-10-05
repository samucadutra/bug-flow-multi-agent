import test from "node:test";
import assert from "node:assert/strict";
import { createNames, toPackageSlug } from "../naming.mjs";

test("sanitizes project names for npm scopes", () => {
  assert.equal(toPackageSlug("Minha API"), "minha-api");
  assert.equal(toPackageSlug("123 CRM!"), "app-123-crm");
  assert.equal(toPackageSlug("clean_arch_demo"), "clean-arch-demo");
});

test("creates package and database names", () => {
  const names = createNames("Minha API");
  assert.equal(names.backendPackage, "@minha-api/backend");
  assert.equal(names.webPackage, "@minha-api/web");
  assert.equal(names.dbPrefix, "minha_api");
});
