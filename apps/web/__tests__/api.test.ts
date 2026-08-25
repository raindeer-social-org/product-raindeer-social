import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { ApiError, fetchBrands, login } from "@/lib/api";

describe("api client", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = vi.fn();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("login posts credentials and returns the access token", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: "abc123", token_type: "bearer" }),
    });

    const result = await login("user@example.com", "hunter2");

    expect(result.access_token).toBe("abc123");
    const [url, options] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/auth/login");
    expect(JSON.parse(options.body)).toEqual({ email: "user@example.com", password: "hunter2" });
  });

  it("login throws ApiError with the backend's detail message on failure", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Invalid credentials" }),
    });

    await expect(login("user@example.com", "wrong")).rejects.toMatchObject({
      message: "Invalid credentials",
      status: 401,
    });
  });

  it("fetchBrands sends the bearer token and returns the brand list", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => [{ id: "brand-1", name: "Acme Co" }],
    });

    const result = await fetchBrands("test-token");

    expect(result).toHaveLength(1);
    const [url, options] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/brands");
    expect(options.headers.Authorization).toBe("Bearer test-token");
  });

  it("fetchBrands raises ApiError on non-OK responses", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("not json");
      },
    });

    await expect(fetchBrands("test-token")).rejects.toBeInstanceOf(ApiError);
  });
});
