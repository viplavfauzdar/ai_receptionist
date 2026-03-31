"use client";

import { useState } from "react";

export default function OnboardingPage() {
  const [form, setForm] = useState({
    businessName: "",
    forwardingNumber: "",
    hours: "",
    greeting: "",
    services: "",
  });

  return (
    <div className="card">
      <div className="h1">Business Onboarding</div>
      <div className="muted" style={{ marginBottom: 16 }}>
        This is a functional MVP front end for collecting business setup data.
        Persisting onboarding to the backend can be your next patch.
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
          onClick={() => alert("MVP placeholder: wire this to a POST /api/business endpoint next.")}
        >
          Save Onboarding
        </button>
      </div>
    </div>
  );
}
