"use client";

// ── Icons (inline SVG — no external dependencies) ─────────────────────────────

function DiagramPlaceholderIcon({ className }: { className?: string }) {
  // Simple flowchart / node-graph SVG
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 80 64"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {/* Top node */}
      <rect x="28" y="2" width="24" height="14" rx="3" />
      {/* Left node */}
      <rect x="4" y="40" width="24" height="14" rx="3" />
      {/* Middle node */}
      <rect x="28" y="40" width="24" height="14" rx="3" />
      {/* Right node */}
      <rect x="52" y="40" width="24" height="14" rx="3" />
      {/* Edges: top → left */}
      <line x1="28" y1="16" x2="16" y2="40" />
      {/* top → middle */}
      <line x1="40" y1="16" x2="40" y2="40" />
      {/* top → right */}
      <line x1="52" y1="16" x2="64" y2="40" />
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
      <path d="M21.5 2l-19 19" />
      <path d="M14.5 2H21.5V9" />
      <path d="M10.5 6.5L17.5 6.5" />
      <path d="M2 14.5l5.5 5.5" />
      <path d="M6.5 10.5L6.5 17.5" />
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
      <path d="M15 4V2" />
      <path d="M15 16v-2" />
      <path d="M8 9h2" />
      <path d="M20 9h2" />
      <path d="M17.8 11.8L19 13" />
      <path d="M15 9h.01" />
      <path d="M17.8 6.2L19 5" />
      <path d="M3 21l9-9" />
      <path d="M12.2 6.2L11 5" />
    </svg>
  );
}


// ── Diagram Preview Area ───────────────────────────────────────────────────────

function DiagramPreview() {
  return (
    <section>
      <h2 className="text-sm font-semibold uppercase tracking-widest text-[#002D54] mb-3">
        Generated Diagram
      </h2>
      <div
        className={[
          "flex flex-col items-center justify-center gap-4",
          "min-h-[360px] w-full rounded-xl",
          "border-2 border-dashed border-gray-300 bg-gray-50",
          "transition-colors duration-200",
        ].join(" ")}
        role="img"
        aria-label="Diagram preview placeholder"
      >
        <DiagramPlaceholderIcon className="w-20 h-16 text-gray-300" />
        <div className="text-center space-y-1">
          <p className="text-sm font-semibold text-gray-400">
            Diagram Preview Area
          </p>
          <p className="text-xs text-gray-300 max-w-[240px]">
            Your generated architecture diagram will render here
          </p>
        </div>
      </div>
    </section>
  );
}

// ── Feedback Form ──────────────────────────────────────────────────────────────

function FeedbackForm() {
  return (
    <section className="space-y-5">
      {/* Divider */}
      <div className="flex items-center gap-3" aria-hidden>
        <div className="flex-1 h-px bg-gray-100" />
        <WandIcon className="w-4 h-4 text-gray-300" />
        <div className="flex-1 h-px bg-gray-100" />
      </div>

      {/* Textarea */}
      <div>
        <label
          htmlFor="feedback"
          className="block text-sm font-semibold text-[#002D54] mb-1.5"
        >
          Customization Feedback
        </label>
        <p className="text-xs text-gray-400 mb-2">
          Describe what to change. The AI will regenerate the diagram based on
          your instructions.
        </p>
        <textarea
          id="feedback"
          rows={4}
          placeholder={`e.g., Change the color theme to blue or add a 'Payment Gateway' node...`}
          className={[
            "w-full resize-none rounded-lg border border-gray-300 px-4 py-3",
            "text-sm text-gray-800 placeholder-gray-400",
            "outline-none transition-shadow duration-150",
            "focus:ring-2 focus:ring-[#FF8200] focus:border-[#FF8200]",
          ].join(" ")}
        />
      </div>

      {/* Action button */}
      <button
        type="button"
        onClick={() => console.log("Regenerate clicked")}
        className={[
          "w-full flex items-center justify-center gap-2",
          "rounded-lg px-6 py-3 text-sm font-semibold text-white",
          "bg-[#FF8200] hover:bg-[#d96e00] active:bg-[#c06200]",
          "transition-colors duration-200",
          "focus-visible:outline-none focus-visible:ring-2",
          "focus-visible:ring-[#FF8200] focus-visible:ring-offset-2",
        ].join(" ")}
      >
        <RefineIcon className="w-4 h-4" />
        Refine &amp; Regenerate
      </button>
    </section>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DiagramReviewPage() {
  return (
    <main className="min-h-screen bg-[#F4F4F4] flex items-start justify-center px-4 py-12">
      <div className="w-full max-w-2xl">

        {/* ── Header ── */}
        <div className="mb-8 flex items-center gap-4">
          <div
            className="flex items-center justify-center rounded-md px-3 py-1.5"
            style={{ backgroundColor: "#FF8200" }}
          >
            <span className="text-white font-extrabold text-lg tracking-tight leading-none">
              NXP
            </span>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-[#002D54] leading-tight">
              Diagram Editor
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Review the generated diagram and request refinements
            </p>
          </div>
        </div>



        {/* ── Card ── */}
        <div className="rounded-2xl bg-white shadow-md ring-1 ring-gray-200 p-8 space-y-7">
          <DiagramPreview />
          <FeedbackForm />
        </div>

        {/* Footer */}
        <p className="mt-6 text-center text-xs text-gray-400">
          SDSU CTRL x NXP Semiconductors Agentic AI in the Cloud Bootcamp 2026
        </p>
      </div>
    </main>
  );
}
