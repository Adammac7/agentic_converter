"use client";

import { useEffect, useRef, useState } from "react";

interface User {
  id: string;
  email: string;
}

export default function UserMenu() {
  const [user, setUser] = useState<User | null>(null);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("http://localhost:8000/auth/me", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!cancelled && data?.email) setUser(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const handleLogout = async () => {
    try {
      await fetch("http://localhost:8000/auth/logout", {
        method: "POST",
        credentials: "include",
      });
    } finally {
      window.location.href = "http://localhost:8000/auth/login";
    }
  };

  if (!user) return null;

  const initial = user.email.charAt(0).toUpperCase();

  return (
    <div ref={wrapRef} className="fixed top-4 left-4 z-50">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="Account menu"
        aria-expanded={open}
        className={[
          "h-10 w-10 rounded-full flex items-center justify-center",
          "bg-[#002D54] text-white font-semibold text-sm",
          "shadow-md ring-2 ring-white hover:ring-[#FF8200]",
          "transition-all duration-150 cursor-pointer",
        ].join(" ")}
      >
        {initial}
      </button>

      {open && (
        <div
          role="menu"
          className={[
            "absolute left-0 mt-2 w-64 origin-top-left",
            "rounded-xl bg-white shadow-lg ring-1 ring-gray-200",
            "p-4 text-sm",
          ].join(" ")}
        >
          <div className="flex items-center gap-3 pb-3 border-b border-gray-100">
            <div className="h-10 w-10 rounded-full bg-[#002D54] text-white font-semibold flex items-center justify-center">
              {initial}
            </div>
            <div className="min-w-0">
              <p className="text-xs text-gray-400">Signed in as</p>
              <p
                className="text-sm font-medium text-[#002D54] truncate"
                title={user.email}
              >
                {user.email}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleLogout}
            className={[
              "mt-3 w-full rounded-lg px-3 py-2 text-sm font-semibold",
              "text-white bg-[#FF8200] hover:bg-[#d96e00] active:bg-[#c06200]",
              "transition-colors duration-150 cursor-pointer",
            ].join(" ")}
          >
            Log out
          </button>
        </div>
      )}
    </div>
  );
}
