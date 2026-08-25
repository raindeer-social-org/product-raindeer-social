// Thin client around the FastAPI backend (apps/api). Kept dependency-free
// (plain fetch) so the app shell doesn't need an HTTP library just to log
// in and list brands.

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

// Mirrors apps/api/schemas/brand.py::BrandRead.
export interface Brand {
  id: string;
  organization_id: string;
  name: string;
  industry: string | null;
  logo_url: string | null;
  target_audience: string | null;
  colors: string[] | null;
  tone_descriptors: string[] | null;
  product_catalog: Record<string, unknown> | null;
  brand_report: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // response wasn't JSON — fall through to the generic message below.
  }
  return `Request failed with status ${res.status}`;
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function fetchBrands(token: string): Promise<Brand[]> {
  const res = await fetch(`${API_URL}/brands`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}
