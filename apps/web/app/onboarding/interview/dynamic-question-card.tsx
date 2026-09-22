"use client";

// Renders one Aarav-generated follow-up question (Issue #153) — the
// adaptive half of the interview that runs after the fixed QUESTIONS
// array in page.tsx. Self-contained (including its own voice recorder)
// so it doesn't need to touch page.tsx's static-question state at all.
// Every free-text question (whether Aarav tagged it "text" or "voice")
// gets the same voice-first DynamicVoiceAnswer widget, with typing always
// one tap away — a brand shouldn't have to hope Aarav happened to pick
// "voice" to answer by speaking.

import { useRef, useState } from "react";
import { ApiError, transcribeOnboardingVoiceAnswer, type DynamicQuestion } from "@/lib/api";
import { ChipButton } from "./chip-button";

function toggleListValue(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

function DynamicVoiceAnswer({
  question,
  value,
  onChange,
  token,
  brandId,
}: {
  question: DynamicQuestion;
  value: string;
  onChange: (value: string) => void;
  token: string | null;
  brandId: string | null;
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [useTextFallback, setUseTextFallback] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  async function startRecording() {
    setError(null);
    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      setUseTextFallback(true);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : undefined;
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      audioChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onstop = () => stream.getTracks().forEach((track) => track.stop());
      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecording(true);
    } catch {
      setUseTextFallback(true);
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;
    if (!recorder) return;

    const finished = new Promise<Blob>((resolve) => {
      recorder.addEventListener(
        "stop",
        () => resolve(new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" })),
        { once: true }
      );
    });
    recorder.stop();
    setIsRecording(false);

    if (!token || !brandId) return;
    setIsTranscribing(true);
    finished
      .then((blob) => transcribeOnboardingVoiceAnswer(token, brandId, question.id, blob))
      .then((answer) => onChange(answer.transcript))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Couldn't transcribe that — try again, or type your answer.");
      })
      .finally(() => setIsTranscribing(false));
  }

  if (useTextFallback) {
    return (
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Type your answer."
        className="h-[110px] w-full resize-none rounded-[13px] border border-line bg-white p-3.5 text-sm leading-relaxed outline-none focus:border-brand-500"
      />
    );
  }

  return (
    <div>
      <div className="flex items-center gap-3.5 rounded-[14px] border border-brand-100 bg-brand-50 p-4">
        <button
          type="button"
          onClick={isRecording ? stopRecording : startRecording}
          disabled={isTranscribing}
          aria-pressed={isRecording}
          aria-label={isRecording ? "Stop recording" : "Start recording"}
          className={
            "flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-lg text-white transition-colors " +
            (isRecording ? "bg-danger animate-rd-pulse" : "bg-brand-600 hover:bg-brand-700")
          }
        >
          {isRecording ? "■" : "●"}
        </button>
        <p className="text-xs text-ink-500">
          {isTranscribing ? "Transcribing…" : isRecording ? "Recording — tap to stop." : "Tap the mic to answer by voice."}{" "}
          <button type="button" className="font-semibold text-brand-600" onClick={() => setUseTextFallback(true)}>
            Prefer typing?
          </button>
        </p>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-xs font-medium text-danger">
          {error}
        </p>
      )}
      {value.trim() && (
        <div className="mt-3 rounded-[13px] border border-line-soft bg-white p-3.5 text-sm leading-relaxed text-ink-800">
          {value}
        </div>
      )}
    </div>
  );
}

export function DynamicQuestionCard({
  question,
  value,
  onChange,
  token,
  brandId,
}: {
  question: DynamicQuestion;
  value: string | string[];
  onChange: (value: string | string[]) => void;
  token: string | null;
  brandId: string | null;
}) {
  return (
    <div className="rounded-[15px] border border-line-soft bg-white p-5">
      <h3 className="mb-1 text-base font-bold leading-snug text-ink-950">{question.title}</h3>
      {question.sub && <p className="mb-3.5 text-xs leading-relaxed text-ink-400">{question.sub}</p>}

      {question.type === "chips" && (
        <div className="flex flex-wrap gap-2.5">
          {(question.options ?? []).map((option) => {
            const selected = Array.isArray(value) && value.includes(option);
            return (
              <ChipButton
                key={option}
                label={option}
                selected={selected}
                onClick={() => onChange(toggleListValue(Array.isArray(value) ? value : [], option))}
              />
            );
          })}
        </div>
      )}

      {question.type === "select" && (
        <div className="flex flex-wrap gap-2.5">
          {(question.options ?? []).map((option) => (
            <ChipButton
              key={option}
              label={option}
              selected={typeof value === "string" && value === option}
              onClick={() => onChange(option)}
            />
          ))}
        </div>
      )}

      {(question.type === "text" || question.type === "voice") && (
        <DynamicVoiceAnswer
          question={question}
          value={typeof value === "string" ? value : ""}
          onChange={onChange}
          token={token}
          brandId={brandId}
        />
      )}
    </div>
  );
}
