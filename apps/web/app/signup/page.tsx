"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ApiError, register as registerRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Input";
import { AuthSplitLayout } from "./auth-split-layout";

const ROLE_OPTIONS = ["Founder", "Marketing lead", "Agency owner"];
const TEAM_SIZE_OPTIONS = ["1–5", "6–20", "21–100", "100+"];

// role/team_size aren't sent to the backend today (POST /auth/register only
// accepts first_name/last_name/email/password — see apps/api/auth/router.py)
// — there's no schema field for either on User/Organization yet. They're
// still collected here to match the design mockup's step 1/3 form and kept
// in local state so a later step of the wizard (or a future profile
// endpoint) can pick them up without re-asking the question.
export default function SignupPage() {
  const { login } = useAuth();
  const router = useRouter();

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(ROLE_OPTIONS[0]);
  const [teamSize, setTeamSize] = useState(TEAM_SIZE_OPTIONS[0]);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const result = await registerRequest({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
        password,
      });
      login(result.access_token);
      // role/team_size ride along in the URL's state via sessionStorage so
      // the brand step (and later, the interview) can reference them
      // without a shared form-state library for a 3-screen wizard.
      window.sessionStorage.setItem("raindeer.signup.role", role);
      window.sessionStorage.setItem("raindeer.signup.teamSize", teamSize);
      router.push("/signup/brand");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthSplitLayout>
      <div className="w-full max-w-[452px]">
        <div className="mb-2.5 flex items-center gap-2 text-[11.5px] font-bold tracking-[.12em] text-brand-600">
          STEP 1 OF 3 · ABOUT YOU
        </div>
        <h1 className="mb-1.5 text-[31px] font-bold leading-[1.12] tracking-tight text-ink-950">
          Create your account
        </h1>
        <p className="mb-6 text-sm text-ink-400">Two minutes of typing, then Aarav takes over.</p>

        <form onSubmit={handleSubmit} noValidate className="space-y-3">
          {error ? (
            <p role="alert" className="rounded-lg bg-danger-bg px-3 py-2 text-sm font-medium text-danger">
              {error}
            </p>
          ) : null}

          <div className="grid grid-cols-2 gap-3">
            <Field label="First name" htmlFor="first-name">
              <Input
                id="first-name"
                autoComplete="given-name"
                required
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
              />
            </Field>
            <Field label="Last name" htmlFor="last-name">
              <Input
                id="last-name"
                autoComplete="family-name"
                required
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
              />
            </Field>
          </div>

          <Field label="Work email" htmlFor="signup-email">
            <Input
              id="signup-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>

          <Field label="Password" htmlFor="signup-password">
            <Input
              id="signup-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3 pb-2">
            <Field label="Your role" htmlFor="signup-role">
              <Select id="signup-role" value={role} onChange={(e) => setRole(e.target.value)}>
                {ROLE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Team size" htmlFor="signup-team-size">
              <Select id="signup-team-size" value={teamSize} onChange={(e) => setTeamSize(e.target.value)}>
                {TEAM_SIZE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <div className="flex gap-2.5">
            <Button type="button" variant="outline" onClick={() => router.push("/login")}>
              Back
            </Button>
            <Button type="submit" className="flex-1" isLoading={isSubmitting}>
              Continue
            </Button>
          </div>
        </form>

        <p className="mt-6 text-[13.5px] text-ink-400">
          Already have an account?{" "}
          <a href="/login" className="font-bold text-brand-600 hover:text-brand-700">
            Log in
          </a>
        </p>
      </div>
    </AuthSplitLayout>
  );
}
