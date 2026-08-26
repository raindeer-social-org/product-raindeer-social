import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup, configure } from "@testing-library/react";

// Several pages chain multiple sequential async hops before their first
// meaningful render (e.g. AuthProvider's localStorage-read effect ->
// BrandProvider's fetchBrands -> a page's own data fetch) — comfortably
// fast locally but has flaked under slower CI runners with the 1000ms
// default. Raised globally rather than passing a timeout to every
// individual findBy*/waitFor call.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
