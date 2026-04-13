"use client";

import { useCallback, useRef, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface FormState {
  file: File | null;
  stylePrompt: string;
  editPrompt: string;
}

type Status = "idle" | "loading" | "success" | "error";

interface ApiResponse {
  svg_output: string;
  dot_source: string;
}

// ── Icons (inline SVG — no external dependencies) ─────────────────────────────

function CloudUploadIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M4.5 16.5A4.5 4.5 0 0 1 7 8a5.5 5.5 0 0 1 10.957 1.5A4 4 0 0 1 20 17.5H7" />
      <polyline points="12 12 12 20" />
      <polyline points="9 15 12 12 15 15" />
    </svg>
  );
}

function PaperclipIcon({ className }: { className?: string }) {
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
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

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

// ── Drop Zone ─────────────────────────────────────────────────────────────────

interface DropZoneProps {
  file: File | null;
  onFile: (f: File) => void;
}

function DropZone({ file, onFile }: DropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      const dropped = e.dataTransfer.files[0];
      if (dropped) onFile(dropped);
    },
    [onFile]
  );

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files?.[0];
    if (picked) onFile(picked);
  };

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Upload RTL file"
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      className={[
        "relative flex flex-col items-center justify-center gap-3",
        "rounded-xl border-2 border-dashed px-6 py-10 cursor-pointer",
        "transition-colors duration-200 select-none",
        isDragging
          ? "border-[#FF8200] bg-orange-50"
          : "border-gray-300 bg-gray-50 hover:border-[#FF8200] hover:bg-orange-50",
      ].join(" ")}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".sv,.v,.vh,.svh"
        className="sr-only"
        onChange={handleChange}
      />

      {file ? (
        <>
          <PaperclipIcon className="h-9 w-9 text-[#FF8200]" />
          <p className="text-sm font-medium text-[#002D54] truncate max-w-xs">
            {file.name}
          </p>
          <p className="text-xs text-gray-400">
            {(file.size / 1024).toFixed(1)} KB &mdash; click to replace
          </p>
        </>
      ) : (
        <>
          <CloudUploadIcon className="h-10 w-10 text-gray-400" />
          <p className="text-sm font-semibold text-gray-600">
            Drag &amp; drop your RTL file here
          </p>
          <p className="text-xs text-gray-400">
            or{" "}
            <span className="text-[#FF8200] underline">browse</span>
            {" "}&mdash; .sv, .v, .svh accepted
          </p>
        </>
      )}
    </div>
  );
}

// ── SVG Preview ───────────────────────────────────────────────────────────────

function SvgPreview({ svg }: { svg: string }) {
  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold uppercase tracking-widest text-[#002D54] mb-3">
        Generated Diagram
      </h2>
      <div
        className="rounded-xl border border-gray-200 bg-white p-4 overflow-auto shadow-sm"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </section>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Page() {
  const [form, setForm] = useState<FormState>({
    file: null,
    stylePrompt: "",
    editPrompt: "",
  });

  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<ApiResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");

  // ── Handlers ────────────────────────────────────────────────────────────────

  const setFile = useCallback(
    (f: File) => setForm((prev) => ({ ...prev, file: f })),
    []
  );

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (!form.file) {
      setErrorMsg("Please attach an RTL source file before submitting.");
      setStatus("error");
      return;
    }

    setStatus("loading");
    setErrorMsg("");
    setResult(null);

    try {
      const body = new FormData();
      body.append("rtl_file", form.file);
      body.append("style_prompt", form.stylePrompt);
      body.append("edit_prompt", form.editPrompt);

      const res = await fetch("/api/convert", { method: "POST", body });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Server error ${res.status}`);
      }

      const data: ApiResponse = await res.json();
      setResult(data);
      setStatus("success");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Unexpected error.");
      setStatus("error");
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────

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
              System Configuration
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Convert SystemVerilog RTL to AI-generated architecture diagrams
            </p>
          </div>
        </div>

        {/* ── Card ── */}
        <div className="rounded-2xl bg-white shadow-md ring-1 ring-gray-200 p-8">
          <form onSubmit={handleSubmit} noValidate className="space-y-7">

            {/* File upload */}
            <fieldset>
              <legend className="block text-sm font-semibold text-[#002D54] mb-2">
                RTL Source File
                <span className="ml-1 text-[#FF8200]">*</span>
              </legend>
              <DropZone file={form.file} onFile={setFile} />
            </fieldset>

            {/* Style prompt */}
            <div>
              <label
                htmlFor="style-prompt"
                className="block text-sm font-semibold text-[#002D54] mb-1.5"
              >
                Customization Prompt
                <span className="ml-1 text-[#FF8200]">*</span>
              </label>
              <p className="text-xs text-gray-400 mb-2">
                Describe how the diagram should look — colors, layout, emphasis.
              </p>
              <textarea
                id="style-prompt"
                rows={3}
                placeholder='e.g. "Make the controller blue, use dashed lines for clock signals."'
                value={form.stylePrompt}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, stylePrompt: e.target.value }))
                }
                required
                className={[
                  "w-full resize-none rounded-lg border px-4 py-3 text-sm",
                  "text-gray-800 placeholder-gray-400",
                  "outline-none transition-shadow duration-150",
                  "focus:ring-2 focus:ring-[#FF8200] focus:border-[#FF8200]",
                  "border-gray-300",
                ].join(" ")}
              />
            </div>

            {/* Error banner */}
            {status === "error" && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                {errorMsg}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={status === "loading"}
              className={[
                "w-full flex items-center justify-center gap-2",
                "rounded-lg px-6 py-3 text-sm font-semibold text-white",
                "transition-colors duration-200",
                "focus-visible:outline-none focus-visible:ring-2",
                "focus-visible:ring-[#FF8200] focus-visible:ring-offset-2",
                status === "loading"
                  ? "bg-[#FF8200]/70 cursor-not-allowed"
                  : "bg-[#FF8200] hover:bg-[#d96e00] active:bg-[#c06200]",
              ].join(" ")}
            >
              {status === "loading" ? (
                <>
                  <SpinnerIcon className="h-4 w-4 animate-spin" />
                  Processing pipeline&hellip;
                </>
              ) : (
                "Generate Diagram"
              )}
            </button>
          </form>

          {/* SVG result */}
          {status === "success" && result?.svg_output && (
            <SvgPreview svg={result.svg_output} />
          )}
        </div>

        {/* Footer */}
        <p className="mt-6 text-center text-xs text-gray-400">
          SDSU CTRL x NXP Semiconductors Agentic AI in the Cloud Bootcamp 2026
        </p>
      </div>
    </main>
  );
}
