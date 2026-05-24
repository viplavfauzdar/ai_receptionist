"use client";

import { useState } from "react";

export default function OnboardingPage() {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const [form, setForm] = useState({
    businessName: "",
    twilioNumber: "",
    forwardingNumber: "",
    hours: "",
    greeting: "",
    services: "",
  });
  const [status, setStatus] = useState<"success" | "error" | "">("");
  const [isSaving, setIsSaving] = useState(false);

  async function saveBusiness() {
    setIsSaving(true);
    setStatus("");

    try {
      const res = await fetch(`${base}/api/businesses`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.businessName,
          twilio_number: form.twilioNumber,
          forwarding_number: form.forwardingNumber || null,
          greeting: form.greeting || null,
          business_hours: form.hours || null,
          booking_enabled: true,
          knowledge_text: form.services || null,
        }),
      });

      if (!res.ok) {
        throw new Error("Failed to save business");
      }

      setStatus("success");
      setForm({
        businessName: "",
        twilioNumber: "",
        forwardingNumber: "",
        hours: "",
        greeting: "",
        services: "",
      });
    } catch {
      setStatus("error");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <>
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-900">Set up your AI receptionist</h1>
      </div>

      {/* Progress indicator */}
      <div className="max-w-[560px] mb-8">
        <div className="flex items-center">
          {[
            { n: 1, label: "Your business" },
            { n: 2, label: "Your receptionist" },
            { n: 3, label: "Connect your number" },
          ].map(({ n, label }, i) => {
            const isActive = n === 1;
            const isDone = n < 1;
            return (
              <div key={n} className="flex items-center flex-1 last:flex-none">
                <div className="flex flex-col items-center gap-1.5">
                  <div
                    className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold border transition-colors ${
                      isActive
                        ? "bg-indigo-600 border-indigo-600 text-white"
                        : isDone
                        ? "bg-indigo-600 border-indigo-600 text-white"
                        : "bg-white border-gray-300 text-gray-400"
                    }`}
                  >
                    {isDone ? (
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="2,6 5,9 10,3" />
                      </svg>
                    ) : n}
                  </div>
                  <span className={`text-xs font-medium whitespace-nowrap ${isActive ? "text-gray-900" : "text-gray-400"}`}>
                    {label}
                  </span>
                </div>
                {i < 2 && (
                  <div className={`flex-1 h-px mx-3 mb-5 ${isDone ? "bg-indigo-600" : "bg-gray-200"}`} />
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex flex-col lg:flex-row lg:items-start gap-8">
      <div className="w-full max-w-[560px] space-y-5 flex-shrink-0">
        {status === "success" && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-5 py-4 text-sm text-emerald-700">
            Business saved successfully.
          </div>
        )}
        {status === "error" && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4 text-sm text-red-700">
            Could not save business. Please check your inputs and try again.
          </div>
        )}

        {/* Business Info */}
        <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">Business Info</h2>
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">
                Business name <span className="text-red-500">*</span>
              </label>
              <input
                className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                placeholder="Acme Dental"
                value={form.businessName}
                onChange={(e) => setForm({ ...form, businessName: e.target.value })}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">Hours</label>
              <input
                className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                placeholder="Mon–Fri 9am–5pm, Sat 9am–1pm"
                value={form.hours}
                onChange={(e) => setForm({ ...form, hours: e.target.value })}
              />
            </div>
          </div>
        </div>

        {/* Contact Numbers */}
        <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">Contact Numbers</h2>
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">
                AI receptionist phone number <span className="text-red-500">*</span>
              </label>
              <input
                className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm text-gray-900 placeholder-gray-400 font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                placeholder="+15551234567"
                value={form.twilioNumber}
                onChange={(e) => setForm({ ...form, twilioNumber: e.target.value })}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">Your personal number</label>
              <input
                className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm text-gray-900 placeholder-gray-400 font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                placeholder="+15559876543"
                value={form.forwardingNumber}
                onChange={(e) => setForm({ ...form, forwardingNumber: e.target.value })}
              />
              <p className="text-xs text-gray-400 mt-1.5">We&apos;ll transfer calls here when the caller needs a human.</p>
            </div>
          </div>
        </div>

        {/* Configuration */}
        <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">Configuration</h2>
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">Opening greeting</label>
              <textarea
                className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
                rows={3}
                placeholder="Thank you for calling Acme Dental. How can I help you today?"
                value={form.greeting}
                onChange={(e) => setForm({ ...form, greeting: e.target.value })}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">What should your receptionist know?</label>
              <textarea
                className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
                rows={4}
                placeholder="List your services, pricing, FAQs, or anything callers commonly ask about."
                value={form.services}
                onChange={(e) => setForm({ ...form, services: e.target.value })}
              />
            </div>
          </div>
        </div>

        <button
          className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2.5 rounded-lg transition-colors"
          disabled={isSaving || !form.businessName || !form.twilioNumber}
          onClick={saveBusiness}
        >
          {isSaving ? "Saving..." : "Save Business"}
        </button>
      </div>

      {/* Live preview panel */}
      <div className="w-full lg:w-72 lg:sticky lg:top-8 flex-shrink-0">
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Caller hears this first</span>
          </div>

          <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed shadow-sm min-h-[72px]">
            {form.greeting ? (
              <span className="text-gray-800">{form.greeting}</span>
            ) : (
              <span className="text-gray-300">Thank you for calling Acme Dental. How can I help you today?</span>
            )}
          </div>

          <p className="text-xs text-gray-400 mt-4 text-center">Powered by your AI receptionist</p>
        </div>
      </div>

      </div>
    </>
  );
}
