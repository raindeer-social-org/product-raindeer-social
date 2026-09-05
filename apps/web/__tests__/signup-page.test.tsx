import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SignupPage from "@/app/signup/page";
import { AuthProvider } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const registerMock = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    register: (...args: unknown[]) => registerMock(...args),
  };
});

function renderPage() {
  return render(
    <AuthProvider>
      <SignupPage />
    </AuthProvider>
  );
}

describe("SignupPage", () => {
  beforeEach(() => {
    push.mockClear();
    registerMock.mockReset();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("registers, stores the token, and continues to the brand step", async () => {
    registerMock.mockResolvedValue({ access_token: "new-token", token_type: "bearer" });
    const user = userEvent.setup();

    renderPage();

    await user.type(screen.getByLabelText("First name"), "Ananya");
    await user.type(screen.getByLabelText("Last name"), "Rao");
    await user.type(screen.getByLabelText("Work email"), "ananya@lexstart.in");
    await user.type(screen.getByLabelText("Password"), "correct horse battery staple");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await vi.waitFor(() => {
      expect(registerMock).toHaveBeenCalledWith({
        first_name: "Ananya",
        last_name: "Rao",
        email: "ananya@lexstart.in",
        password: "correct horse battery staple",
      });
    });

    expect(window.localStorage.getItem("raindeer.auth.token")).toBe("new-token");
    expect(push).toHaveBeenCalledWith("/signup/brand");
  });

  it("shows the backend's error message and doesn't navigate when the email is already taken", async () => {
    registerMock.mockRejectedValue(new ApiError("An account with this email already exists", 409));
    const user = userEvent.setup();

    renderPage();

    await user.type(screen.getByLabelText("First name"), "Ananya");
    await user.type(screen.getByLabelText("Last name"), "Rao");
    await user.type(screen.getByLabelText("Work email"), "taken@lexstart.in");
    await user.type(screen.getByLabelText("Password"), "correct horse battery staple");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("An account with this email already exists")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
    expect(window.localStorage.getItem("raindeer.auth.token")).toBeNull();
  });
});
