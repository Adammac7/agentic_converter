"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";

// ── Icons ─────────────────────────────────────────────────────────────────────

function SpinnerIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}

function WandIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M15 4V2" /><path d="M15 16v-2" /><path d="M8 9h2" />
      <path d="M20 9h2" /><path d="M17.8 11.8L19 13" /><path d="M15 9h.01" />
      <path d="M17.8 6.2L19 5" /><path d="M3 21l9-9" /><path d="M12.2 6.2L11 5" />
    </svg>
  );
}

function RefineIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <polyline points="1 4 1 10 7 10" />
      <path d="M3.51 15a9 9 0 1 0 .49-3.34" />
    </svg>
  );
}

// ── Inner page (uses useSearchParams — must be inside <Suspense>) ─────────────

function DiagramReviewContent() {
  const params    = useSearchParams();
  const taskId    = params.get("task_id") ?? "";
  const initialImgUrl = params.get("img_url") ?? "";

  // img_url is the full URL (e.g. http://localhost:8000/static/output/<id>.svg)
  // built by the upload page so we can drop it straight into <img src>.
  const [imgSrc,         setImgSrc]         = useState(initialImgUrl);
  const [imgLoadError,   setImgLoadError]   = useState(false);

  // Regeneration form
  const [feedback,       setFeedback]       = useState("");
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [regenError,     setRegenError]     = useState("");

  // Current task id (updated after each regeneration so future regen calls
  // are chained against the most-recent task's stored state).
  const [currentTaskId, setCurrentTaskId] = useState(taskId);

  // ── Regenerate handler ────────────────────────────────────────────────────

  const handleRegenerate = async () => {
    if (!feedback.trim()) return;

    setIsRegenerating(true);
    setRegenError("");

    try {
      const res = await fetch(`/backend/regenerate/${currentTaskId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ edit_prompt: feedback }),
      });

      // Read body ONCE — avoids "body stream already read" if JSON parse fails.
      const rawText = await res.text();

      if (!res.ok) {
        let message = `Server error ${res.status}`;
        try {
          const errData = JSON.parse(rawText);
          message = errData?.detail ?? rawText;
        } catch {
          message = rawText || message;
        }
        throw new Error(message);
      }

      const { task_id, svg_url }: { task_id: string; svg_url: string } =
        JSON.parse(rawText);

      setCurrentTaskId(task_id);
      setImgSrc(`http://localhost:8000${svg_url}`);
      setImgLoadError(false);
      setFeedback("");
    } catch (err) {
      setRegenError(err instanceof Error ? err.message : "Unexpected error.");
    } finally {
      setIsRegenerating(false);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <main className="min-h-screen bg-[#F4F4F4] flex items-start justify-center px-4 py-12">
      <div className="w-full max-w-3xl">

        {/* ── Header ── */}
        <div className="mb-8 flex items-center gap-4">
          <div
            className="flex items-center justify-center rounded-md px-3 py-1.5"
            style={{ backgroundColor: "#FF8200" }}
          >
            <span className="text-white font-extrabold text-lg tracking-tight leading-none">NXP</span>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-[#002D54] leading-tight">Diagram Editor</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Review the generated diagram and request refinements
            </p>
          </div>
        </div>

        {/* ── Card ── */}
        <div className="rounded-2xl bg-white shadow-md ring-1 ring-gray-200 p-8 space-y-7">

          {/* ── Diagram preview ── */}
          <section>
            <h2 className="text-sm font-semibold uppercase tracking-widest text-[#002D54] mb-3">
              Generated Diagram
            </h2>

            {imgLoadError ? (
              <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                Could not load diagram image. Make sure the backend is running on port 8000.
              </div>
            ) : imgSrc ? (
              /* <object> renders SVG with full fidelity (text, links, styles).
                 The inner <img> is a fallback for browsers that block objects. */
              <div className="rounded-xl border border-gray-200 bg-white p-4 overflow-auto shadow-sm">
                <object
                  data={imgSrc}
                  type="image/svg+xml"
                  className="w-full"
                  onError={() => setImgLoadError(true)}
                  aria-label="Generated RTL architecture diagram"
                >
                  <img
                    src={imgSrc}
                    alt="Generated RTL architecture diagram"
                    className="w-full h-auto"
                    onError={() => setImgLoadError(true)}
                  />
                </object>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center gap-3 min-h-[320px] rounded-xl border-2 border-dashed border-gray-200 bg-gray-50">
                <SpinnerIcon className="h-8 w-8 text-[#FF8200] animate-spin" />
                <p className="text-sm text-gray-400">Loading diagram&hellip;</p>
              </div>
            )}
          </section>

          {/* ── Divider ── */}
          <div className="flex items-center gap-3" aria-hidden>
            <div className="flex-1 h-px bg-gray-100" />
            <WandIcon className="w-4 h-4 text-gray-300" />
            <div className="flex-1 h-px bg-gray-100" />
          </div>

          {/* ── Feedback / regeneration ── */}
          <section className="space-y-4">
            <div>
              <label
                htmlFor="feedback"
                className="block text-sm font-semibold text-[#002D54] mb-1.5"
              >
                Customization Feedback
              </label>
              <p className="text-xs text-gray-400 mb-2">
                Describe what to change. The AI will regenerate the diagram based on your
                instructions — the RTL parsing step is skipped for speed.
              </p>
              <textarea
                id="feedback"
                rows={4}
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder='e.g. "Change the controller to red and use dotted lines for data paths."'
                className={[
                  "w-full resize-none rounded-lg border border-gray-300 px-4 py-3",
                  "text-sm text-gray-800 placeholder-gray-400",
                  "outline-none transition-shadow duration-150",
                  "focus:ring-2 focus:ring-[#FF8200] focus:border-[#FF8200]",
                ].join(" ")}
              />
            </div>

            {regenError && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                {regenError}
              </div>
            )}

            <button
              type="button"
              onClick={handleRegenerate}
              disabled={isRegenerating || !feedback.trim()}
              className={[
                "w-full flex items-center justify-center gap-2",
                "rounded-lg px-6 py-3 text-sm font-semibold text-white",
                "transition-colors duration-200",
                "focus-visible:outline-none focus-visible:ring-2",
                "focus-visible:ring-[#FF8200] focus-visible:ring-offset-2",
                isRegenerating || !feedback.trim()
                  ? "bg-[#FF8200]/60 cursor-not-allowed"
                  : "bg-[#FF8200] hover:bg-[#d96e00] active:bg-[#c06200]",
              ].join(" ")}
            >
              {isRegenerating ? (
                <>
                  <SpinnerIcon className="w-4 h-4 animate-spin" />
                  Agent is regenerating&hellip;
                </>
              ) : (
                <>
                  <RefineIcon className="w-4 h-4" />
                  Refine &amp; Regenerate
                </>
              )}
            </button>
          </section>

        </div>

        {/* Footer */}
        <p className="mt-6 text-center text-xs text-gray-400">
          SDSU CTRL x NXP Semiconductors Agentic AI in the Cloud Bootcamp 2026
        </p>
      </div>
    </main>
  );
}

// ── Page export (wraps inner component in Suspense as required by Next.js) ────

export default function DiagramReviewPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-[#F4F4F4] flex items-center justify-center">
          <SpinnerIcon className="h-10 w-10 text-[#FF8200] animate-spin" />
        </main>
      }
    >
      <DiagramReviewContent />
    </Suspense>
  );
}
