import { cn } from "@/components/ui/cn";

// Simple, tasteful approximations of each platform's post chrome — not
// pixel-perfect clones — so the preview modal reads as "this is roughly
// what an Instagram/LinkedIn/X post looks like" at a glance. All content
// rendered here (title/body) is the real event title and the real
// Generation Engine draft copy (Post.body_text) when one exists; nothing
// here is a platform API response.
interface PlatformMockProps {
  platform: string;
  brandName: string;
  title: string;
  body: string | null;
}

function initials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  return trimmed.slice(0, 2).toUpperCase();
}

function InstagramMock({ brandName, title, body }: Omit<PlatformMockProps, "platform">) {
  return (
    <div className="w-full max-w-[320px] overflow-hidden rounded-2xl border border-line-soft bg-white shadow-card">
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <div className="rounded-full bg-gradient-to-br from-amber-400 via-pink-500 to-violet-600 p-[2px]">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-ink-950 text-[10px] font-extrabold text-white">
            {initials(brandName)}
          </div>
        </div>
        <div className="flex-1">
          <div className="text-xs font-semibold text-ink-950">{brandName.toLowerCase().replace(/\s+/g, "")}</div>
          <div className="text-[10px] text-ink-300">Scheduled</div>
        </div>
        <span className="text-ink-300">···</span>
      </div>
      <div className="relative flex aspect-[4/5] flex-col justify-end bg-gradient-to-br from-brand-900 via-brand-600 to-brand-300 p-5">
        <p className="font-serif text-xl italic leading-tight text-white text-balance">{title}</p>
      </div>
      <div className="space-y-1.5 px-3 py-2.5">
        <div className="flex gap-3 text-base text-ink-950">
          <span>♡</span>
          <span>○</span>
          <span>➤</span>
        </div>
        <p className="text-xs leading-snug text-ink-800">
          <span className="font-semibold">{brandName.toLowerCase().replace(/\s+/g, "")}</span>{" "}
          {body ?? "Caption pending generation."}
        </p>
      </div>
    </div>
  );
}

function LinkedInMock({ brandName, title, body }: Omit<PlatformMockProps, "platform">) {
  return (
    <div className="w-full max-w-[400px] overflow-hidden rounded-xl border border-line-soft bg-white shadow-card">
      <div className="flex gap-2.5 px-3.5 py-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ink-950 text-xs font-extrabold text-white">
          {initials(brandName)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-ink-950">{brandName}</div>
          <div className="text-[11px] text-ink-300">Scheduled · 🌐</div>
        </div>
      </div>
      <p className="whitespace-pre-line px-3.5 pb-3 text-sm leading-relaxed text-ink-950 text-balance">
        {body ?? "Draft copy pending generation."}
      </p>
      <div className="flex items-center justify-center border-y border-line-faint bg-gradient-to-br from-teal-50 via-brand-50 to-violet-50 p-6">
        <p className="text-center text-lg font-bold leading-tight tracking-tight text-ink-950 text-balance">
          {title}
        </p>
      </div>
      <div className="flex justify-between px-3.5 py-2 text-xs text-ink-500">
        <span>👍💡</span>
        <span>Comments · Reposts</span>
      </div>
    </div>
  );
}

function XMock({ brandName, title, body }: Omit<PlatformMockProps, "platform">) {
  return (
    <div className="w-full max-w-[380px] rounded-2xl border border-line-soft bg-white p-4 shadow-card">
      <div className="flex gap-2.5">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink-950 text-xs font-extrabold text-white">
          {initials(brandName)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 text-sm">
            <b className="text-ink-950">{brandName}</b>
            <span className="text-ink-300">@{brandName.toLowerCase().replace(/\s+/g, "")} · scheduled</span>
          </div>
          <p className="mt-1 whitespace-pre-line text-sm leading-snug text-ink-950 text-balance">{body ?? title}</p>
          <div className="mt-3 flex max-w-[260px] justify-between text-xs text-ink-300">
            <span>💬</span>
            <span>🔁</span>
            <span>♡</span>
            <span>📊</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function GenericMock({ platform, title, body }: PlatformMockProps) {
  return (
    <div className="w-full max-w-[380px] overflow-hidden rounded-2xl border border-line-soft bg-white shadow-card">
      <div className="flex aspect-video items-center justify-center bg-gradient-to-br from-ink-950 to-brand-600 p-6 text-center">
        <p className="font-serif text-xl italic leading-tight text-white text-balance">{title}</p>
      </div>
      <div className="p-3.5">
        <div className="text-xs font-semibold uppercase tracking-wide text-ink-300">{platform}</div>
        <p className="mt-1 text-sm leading-relaxed text-ink-600 text-balance">
          {body ?? "Draft copy pending generation."}
        </p>
      </div>
    </div>
  );
}

export function PlatformMock({ platform, brandName, title, body }: PlatformMockProps) {
  const p = platform.toLowerCase();
  return (
    <div className={cn("flex justify-center")}>
      {p === "instagram" ? (
        <InstagramMock brandName={brandName} title={title} body={body} />
      ) : p === "linkedin" ? (
        <LinkedInMock brandName={brandName} title={title} body={body} />
      ) : p === "x" ? (
        <XMock brandName={brandName} title={title} body={body} />
      ) : (
        <GenericMock platform={platform} brandName={brandName} title={title} body={body} />
      )}
    </div>
  );
}
