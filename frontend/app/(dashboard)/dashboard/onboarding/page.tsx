"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function OnboardingPage() {
  const router = useRouter();
  const [form, setForm] = useState({ name: "", hours: "", greeting: "", knowledge: "" });
  const [checking, setChecking] = useState(true);

  // Redirect away if onboarding already completed; otherwise pre-fill name from Google
  useEffect(() => {
    fetch(`${BASE}/api/businesses/me`, { credentials: "include" })
      .then((r) => r.json())
      .then((b) => {
        if (b?.onboarding_completed) {
          router.replace("/dashboard");
        } else {
          setForm((f) => ({ ...f, name: b?.name ?? "" }));
          setChecking(false);
        }
      })
      .catch(() => setChecking(false));
  }, [router]);
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  async function save() {
    setIsSaving(true);
    setError("");
    try {
      const res = await fetch(`${BASE}/api/businesses/me`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name,
          greeting: form.greeting || null,
          business_hours: form.hours || null,
          booking_enabled: true,
          knowledge_text: form.knowledge || null,
        }),
      });
      if (!res.ok) throw new Error();
      router.push("/dashboard");
    } catch {
      setError("Something went wrong. Please try again.");
      setIsSaving(false);
    }
  }

  if (checking) return null;

  return (
    <div className="max-w-[560px]">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-900">Set up your receptionist</h1>
        <p className="text-sm text-gray-500 mt-1">Just the basics — you can update everything later in Settings.</p>
      </div>

      {error && (
        <div className="mb-5 bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1.5">
            Business name <span className="text-red-400">*</span>
          </label>
          <input
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            placeholder="Acme Dental"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1.5">Business hours</label>
          <input
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            placeholder="Mon–Fri 9am–5pm, Sat 9am–1pm"
            value={form.hours}
            onChange={(e) => setForm({ ...form, hours: e.target.value })}
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1.5">Opening greeting</label>
          <textarea
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
            rows={2}
            placeholder="Thank you for calling Acme Dental. How can I help you today?"
            value={form.greeting}
            onChange={(e) => setForm({ ...form, greeting: e.target.value })}
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1.5">What should Reeva know?</label>
          <textarea
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
            rows={4}
            placeholder="Services, pricing, FAQs, anything callers commonly ask about…"
            value={form.knowledge}
            onChange={(e) => setForm({ ...form, knowledge: e.target.value })}
          />
        </div>
      </div>

      <button
        className="mt-5 w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2.5 rounded-lg transition-colors"
        disabled={isSaving || !form.name.trim()}
        onClick={save}
      >
        {isSaving ? "Saving…" : "Continue →"}
      </button>
    </div>
  );
}
