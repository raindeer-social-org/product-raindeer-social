import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  ApiError,
  createBrand,
  fetchArenaRunForEvent,
  fetchBrands,
  fetchLatestArenaRun,
  login,
  uploadBrandLogo,
} from "@/lib/api";

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

  it("createBrand posts the payload as JSON with the bearer token", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ id: "brand-1", name: "Acme Co" }),
    });

    await createBrand("test-token", { name: "Acme Co", industry: "Retail" });

    const [url, options] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/brands");
    expect(options.method).toBe("POST");
    expect(options.headers.Authorization).toBe("Bearer test-token");
    expect(JSON.parse(options.body)).toEqual({ name: "Acme Co", industry: "Retail" });
  });

  it("uploadBrandLogo PUTs a multipart form with the file under the 'file' field", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ id: "brand-1", logo_url: "https://cdn.example.com/logo.png" }),
    });
    const file = new File(["bytes"], "logo.png", { type: "image/png" });

    await uploadBrandLogo("test-token", "brand-1", file);

    const [url, options] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/brands/brand-1/logo");
    expect(options.method).toBe("PUT");
    expect(options.headers.Authorization).toBe("Bearer test-token");
    expect(options.body).toBeInstanceOf(FormData);
    expect((options.body as FormData).get("file")).toBe(file);
  });

  it("fetchArenaRunForEvent hits the by-event endpoint with the bearer token", async () => {
    const run = { calendar_event_id: "event-1", post: null, agent_runs: [], review_feedback: [] };
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => run,
    });

    const result = await fetchArenaRunForEvent("test-token", "brand-1", "event-1");

    expect(result).toEqual(run);
    const [url, options] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/brands/brand-1/arena/by-event/event-1");
    expect(options.headers.Authorization).toBe("Bearer test-token");
  });

  it("fetchArenaRunForEvent raises ApiError on non-OK responses", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Calendar event not found" }),
    });

    await expect(fetchArenaRunForEvent("test-token", "brand-1", "missing")).rejects.toMatchObject({
      message: "Calendar event not found",
      status: 404,
    });
  });

  it("fetchLatestArenaRun hits the latest endpoint with the bearer token", async () => {
    const run = { calendar_event_id: null, post: null, agent_runs: [], review_feedback: [] };
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => run,
    });

    const result = await fetchLatestArenaRun("test-token", "brand-1");

    expect(result).toEqual(run);
    const [url, options] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/brands/brand-1/arena/latest");
    expect(options.headers.Authorization).toBe("Bearer test-token");
  });
});
