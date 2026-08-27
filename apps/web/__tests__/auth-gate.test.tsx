import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { AuthGate } from "@/components/auth-gate";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import { ToastProvider } from "@/components/ui/Toast";

const replace = vi.fn();
let mockPathname = "/calendar";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => mockPathname,
}));

vi.mock("@/lib/api", () => ({
  fetchBrands: vi.fn().mockResolvedValue([]),
}));

function renderGate() {
  return render(
    <ToastProvider>
      <AuthProvider>
        <BrandProvider>
          <AuthGate>
            <div>protected content</div>
          </AuthGate>
        </BrandProvider>
      </AuthProvider>
    </ToastProvider>
  );
}

describe("AuthGate", () => {
  beforeEach(() => {
    replace.mockClear();
    mockPathname = "/calendar";
    window.localStorage.clear();
  });

  it("redirects to /login when there is no token on a protected route", async () => {
    renderGate();

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/login?from=%2Fcalendar");
    });
    expect(screen.queryByText("protected content")).not.toBeInTheDocument();
  });

  it("renders protected content once a token is present", async () => {
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    renderGate();

    await waitFor(() => {
      expect(screen.getByText("protected content")).toBeInTheDocument();
    });
    expect(replace).not.toHaveBeenCalled();
  });

  it("never redirects when already on the public /login route", async () => {
    mockPathname = "/login";

    renderGate();

    await waitFor(() => {
      expect(screen.getByText("protected content")).toBeInTheDocument();
    });
    expect(replace).not.toHaveBeenCalled();
  });

  it("redirects on every protected route, not just one", async () => {
    mockPathname = "/analytics";

    renderGate();

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/login?from=%2Fanalytics");
    });
  });
});
