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
  const [status, setStatus] = useState<string>("");
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

      setStatus("Business saved.")
      setForm({
        businessName: "",
        twilioNumber: "",
        forwardingNumber: "",
        hours: "",
        greeting: "",
        services: "",
      });
    } catch {
      setStatus("Could not save business.")
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="card">
      <div className="h1">Business Onboarding</div>
      <div className="muted" style={{ marginBottom: 16 }}>
        Create a business record used by the backend to resolve calls by Twilio number.
      </div>

      <div className="grid">
        <input
          className="input"
          placeholder="Business name"
          value={form.businessName}
          onChange={(e) => setForm({ ...form, businessName: e.target.value })}
        />
        <input
          className="input"
          placeholder="Twilio number"
          value={form.twilioNumber}
          onChange={(e) => setForm({ ...form, twilioNumber: e.target.value })}
        />
        <input
          className="input"
          placeholder="Forwarding number"
          value={form.forwardingNumber}
          onChange={(e) => setForm({ ...form, forwardingNumber: e.target.value })}
        />
        <input
          className="input"
          placeholder="Business hours"
          value={form.hours}
          onChange={(e) => setForm({ ...form, hours: e.target.value })}
        />
        <textarea
          className="textarea"
          placeholder="Greeting"
          value={form.greeting}
          onChange={(e) => setForm({ ...form, greeting: e.target.value })}
        />
        <textarea
          className="textarea"
          placeholder="Services / FAQs"
          value={form.services}
          onChange={(e) => setForm({ ...form, services: e.target.value })}
        />
        <button
          className="button"
          disabled={isSaving || !form.businessName || !form.twilioNumber}
          onClick={saveBusiness}
        >
          {isSaving ? "Saving..." : "Save Onboarding"}
        </button>
        {status ? <div className="muted">{status}</div> : null}
      </div>
    </div>
  );
}
