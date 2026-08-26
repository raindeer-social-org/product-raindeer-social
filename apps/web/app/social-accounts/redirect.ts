// Isolated from page.tsx so tests can mock the actual browser navigation
// (jsdom doesn't perform real page loads, and asserting on a real
// `window.location.href` mutation is awkward) while still exercising the
// real connect-then-redirect flow.
export function redirectToAuthorizeUrl(url: string): void {
  window.location.href = url;
}
