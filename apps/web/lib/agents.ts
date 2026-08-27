// Product-facing names for the five pipeline stages in `packages/agents/`.
// The backend module names stay plain and descriptive (research_engine.py,
// creative_engine.py, ...) — these personas are UI branding only, used by
// the global prompt bar to let a user address a stage by name instead of
// only interacting with it through a dedicated page.
export interface Agent {
  id: string;
  name: string;
  stage: string;
  role: string;
  /** Single letter shown in the prompt bar's agent badge. */
  initial: string;
}

export const AGENTS: Agent[] = [
  {
    id: "aarav",
    name: "Aarav",
    stage: "Onboarding",
    role: "Scrapes the brand's website, asks clarifying questions, captures logo/theme, and produces the brand report every other agent works from.",
    initial: "A",
  },
  {
    id: "ved",
    name: "Ved",
    stage: "Research",
    role: "Researches what's working right now in the brand's niche, on demand or on a schedule.",
    initial: "V",
  },
  {
    id: "keshav",
    name: "Keshav",
    stage: "Creative",
    role: "Turns Ved's research into a concrete creative brief — format, angle, hook, CTA.",
    initial: "K",
  },
  {
    id: "kavi",
    name: "Kavi",
    stage: "Generative",
    role: "Writes the post copy and generates the accompanying image(s) from Keshav's brief.",
    initial: "K",
  },
  {
    id: "neer",
    name: "Neer",
    stage: "Reviewer",
    role: "Reviews each draft for brand hygiene, logo placement, and platform fit before it reaches a human.",
    initial: "N",
  },
];

// Free-form instructions that aren't explicitly routed to one agent (no
// arrow-key selection made before Enter) fall back to Ved — most ad hoc
// asks ("what's trending", "research X") start with research, and it's the
// same agent the issue's own example ("research competitor X") points to.
export const DEFAULT_AGENT = AGENTS[1];
