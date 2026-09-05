import type { ReactNode } from "react";

// The 5-agent roster shown on the right rail, matching the tailwind
// "agent" color tokens (apps/web/tailwind.config.ts) 1:1 — same identity
// colors used for avatars/badges/node headers everywhere else in the app.
const AGENTS: { initial: string; name: string; role: string; from: string; to: string }[] = [
  { initial: "A", name: "Aarav", role: "Onboarding & strategy", from: "#1B4DFF", to: "#8FC4FF" },
  { initial: "V", name: "Ved", role: "Research", from: "#0B2A6B", to: "#3C7BFF" },
  { initial: "K", name: "Keshav", role: "Creative direction", from: "#6B32C9", to: "#B58BFF" },
  { initial: "K", name: "Kavi", role: "Content generation", from: "#0E7A4E", to: "#5AD1A6" },
  { initial: "N", name: "Neer", role: "Review & analytics", from: "#B46A00", to: "#FFC46B" },
];

/**
 * The two-pane signup shell (form left, gradient agent-roster rail right)
 * from "Raindeer Social.dc.html"'s isAuth/isSignup/isBrand blocks. Shared
 * by app/signup/page.tsx (step 1/3) and app/signup/brand/page.tsx (step
 * 2/3) — the Aarav interview (step 3/3) is full-bleed and doesn't use it.
 */
export function AuthSplitLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-screen grid-cols-1 bg-canvas lg:grid-cols-[minmax(0,1fr)_460px]">
      <div className="flex min-w-0 flex-col px-6 py-8 sm:px-11 sm:py-9">
        <div className="flex items-center gap-3">
          <div className="flex h-[34px] w-[34px] items-center justify-center rounded-[10px] bg-gradient-to-br from-brand-600 to-brand-300 text-[15px] font-extrabold text-white">
            R
          </div>
          <div className="flex flex-col leading-none">
            <span className="text-[17px] font-bold tracking-tight text-ink-950">
              raindeer<span className="text-brand-600">.</span>
            </span>
            <span className="mt-[3px] text-[9px] tracking-[.42em] text-ink-300">SOCIAL</span>
          </div>
        </div>

        <div className="flex flex-1 items-center justify-center py-6">{children}</div>

        <p className="text-[11.5px] text-ink-200">
          © 2026 Raindeer Social · Everything exists somewhere. Nothing exists together.
        </p>
      </div>

      <div className="relative hidden overflow-hidden border-l border-line-soft bg-gradient-to-br from-[#DFF6F2] via-[#E4ECFF] to-[#EFE6FF] px-10 py-11 lg:flex lg:flex-col lg:justify-center">
        <div
          className="pointer-events-none absolute -right-[180px] -top-[120px] h-[520px] w-[520px] rounded-full opacity-70 blur-[10px]"
          style={{ background: "radial-gradient(circle, rgba(27,77,255,.18), transparent 62%)" }}
          aria-hidden="true"
        />
        <div className="relative">
          <p className="mb-7 font-serif text-[26px] italic leading-tight text-ink-950">
            Your AI marketing team
          </p>
          <div className="flex flex-col gap-3.5">
            {AGENTS.map((agent) => (
              <div
                key={agent.name}
                className="flex items-center gap-3 rounded-[14px] border border-white/90 bg-white/70 p-3.5 backdrop-blur"
              >
                <div
                  className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-full text-[13px] font-extrabold text-white"
                  style={{ background: `linear-gradient(135deg, ${agent.from}, ${agent.to})` }}
                >
                  {agent.initial}
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-bold tracking-tight text-ink-950">{agent.name}</div>
                  <div className="text-xs text-ink-500">{agent.role}</div>
                </div>
              </div>
            ))}
          </div>
          <p className="mt-6 text-[12.5px] leading-relaxed text-ink-600">
            Five agents. One brand memory. They research, write, design, review and publish — you
            approve.
          </p>
        </div>
      </div>
    </div>
  );
}
