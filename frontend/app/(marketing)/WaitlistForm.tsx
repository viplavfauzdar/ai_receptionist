"use client";

import { useState } from "react";

export default function WaitlistForm() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email) return;
    setStatus("submitting");
    try {
      // TODO: wire to a real waitlist endpoint
      await new Promise((res) => setTimeout(res, 800));
      setStatus("success");
      setEmail("");
    } catch {
      setStatus("error");
    }
  }

  if (status === "success") {
    return (
      <p style={{ color: "#10b981", fontWeight: 600, fontSize: "1rem" }}>
        You&apos;re on the list! We&apos;ll reach out soon.
      </p>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="hero-cta" style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", justifyContent: "center" }}>
      <input
        type="email"
        required
        placeholder="your@email.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        disabled={status === "submitting"}
        style={{
          padding: "0.75rem 1.25rem",
          borderRadius: "0.5rem",
          border: "1px solid #d1d5db",
          fontSize: "1rem",
          minWidth: "260px",
          outline: "none",
        }}
      />
      <button
        type="submit"
        disabled={status === "submitting"}
        className="btn-primary"
      >
        {status === "submitting" ? "Joining…" : "Join Waitlist"}
      </button>
      {status === "error" && (
        <p style={{ color: "#ef4444", width: "100%", textAlign: "center", fontSize: "0.875rem" }}>
          Something went wrong. Please try again.
        </p>
      )}
    </form>
  );
}
