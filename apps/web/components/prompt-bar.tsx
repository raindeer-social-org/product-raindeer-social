"use client";

import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AGENTS, DEFAULT_AGENT, type Agent } from "@/lib/agents";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";

type Push = ReturnType<typeof useToast>["push"];

// --- Integration point -----------------------------------------------
// This is the one seam to swap when a real agent-dispatch endpoint exists:
// replace the toast below with the API call, keep the same signature.
function dispatchPrompt(agent: Agent, text: string, push: Push) {
  push(`Routing to ${agent.name}: "${text.trim()}"`, "info");
}
// -----------------------------------------------------------------------

/**
 * Global, keyboard-first command palette. Floats a trigger pill above the
 * app shell (mounted once from AuthGate) and opens with Cmd/Ctrl+K from
 * anywhere. Lets a user type a free-form instruction or jump straight to
 * one of the five pipeline agents; submitting today only surfaces a toast
 * (see `dispatchPrompt` above) — the parsing/selection UX is otherwise
 * exactly what a real dispatch call would need.
 */
export function PromptBar() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);
  const [mounted, setMounted] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { push } = useToast();

  useEffect(() => setMounted(true), []);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setActiveIndex(-1);
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
  }, [open]);

  const submit = useCallback(
    (agent: Agent) => {
      dispatchPrompt(agent, query, push);
      close();
    },
    [query, push, close],
  );

  function onPaletteKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % AGENTS.length);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => (current <= 0 ? AGENTS.length - 1 : current - 1));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (!query.trim() && activeIndex === -1) return;
      submit(activeIndex >= 0 ? AGENTS[activeIndex] : DEFAULT_AGENT);
    }
  }

  if (!mounted) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className={cn(
          "fixed bottom-6 left-1/2 z-40 flex -translate-x-1/2 items-center gap-2.5 rounded-full",
          "border border-ink-700 bg-ink-900/90 px-4 py-2.5 text-sm font-medium text-ink-200",
          "shadow-chrome backdrop-blur transition-all duration-150",
          "hover:-translate-y-0.5 hover:border-accent-500/60 hover:text-white",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500",
        )}
      >
        <span aria-hidden="true" className="font-mono text-accent-400">
          ›_
        </span>
        Ask anything
        <kbd className="rounded border border-ink-600 bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] text-ink-400">
          {"⌘"}K
        </kbd>
      </button>

      {open
        ? createPortal(
            <div
              className="fixed inset-0 z-50 flex items-start justify-center bg-ink-950/70 px-4 pt-[14vh] backdrop-blur-sm animate-fade-in"
              onClick={close}
            >
              <div
                role="dialog"
                aria-modal="true"
                aria-label="Prompt bar"
                onClick={(event) => event.stopPropagation()}
                onKeyDown={onPaletteKeyDown}
                className="w-full max-w-xl animate-slide-up overflow-hidden rounded-2xl border border-ink-700 bg-ink-900 shadow-chrome"
              >
                <div className="flex items-center gap-3 border-b border-ink-800 px-4 py-3.5">
                  <span aria-hidden="true" className="font-mono text-lg text-accent-400">
                    ›
                  </span>
                  <input
                    ref={inputRef}
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Type an instruction, or jump to an agent…"
                    aria-label="Instruction"
                    className="flex-1 bg-transparent text-[15px] text-ink-100 placeholder:text-ink-500 focus:outline-none"
                  />
                  <kbd className="shrink-0 rounded border border-ink-700 bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] text-ink-400">
                    Esc
                  </kbd>
                </div>

                <ul role="listbox" aria-label="Agents" className="max-h-80 overflow-y-auto scrollbar-thin py-2">
                  {AGENTS.map((agent, index) => {
                    const isActive = index === activeIndex;
                    return (
                      <li key={agent.id}>
                        <button
                          type="button"
                          role="option"
                          aria-selected={isActive}
                          onMouseEnter={() => setActiveIndex(index)}
                          onClick={() => submit(agent)}
                          className={cn(
                            "flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors",
                            isActive ? "bg-ink-800" : "hover:bg-ink-800/60",
                          )}
                        >
                          <span
                            aria-hidden="true"
                            className={cn(
                              "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg font-mono text-xs font-semibold transition-colors",
                              isActive ? "bg-accent-500 text-ink-950" : "bg-ink-800 text-accent-400",
                            )}
                          >
                            {agent.initial}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="flex items-baseline gap-2">
                              <span className="text-sm font-semibold text-ink-100">{agent.name}</span>
                              <span className="font-mono text-[10px] uppercase tracking-wider text-ink-500">
                                {agent.stage}
                              </span>
                            </span>
                            <span className="block truncate text-xs text-ink-400">{agent.role}</span>
                          </span>
                          {isActive ? (
                            <kbd className="hidden shrink-0 rounded border border-ink-600 bg-ink-900 px-1.5 py-0.5 font-mono text-[10px] text-ink-400 sm:block">
                              Enter
                            </kbd>
                          ) : null}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
