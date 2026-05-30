"use client";

import { useEffect, useState } from "react";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface Business {
  id: number;
  name: string;
  twilio_number: string;
  forwarding_number?: string;
  greeting?: string;
  business_hours?: string;
  booking_enabled: boolean;
  knowledge_text?: string;
  google_calendar_connected: boolean;
  google_account_email?: string;
  google_calendar_id?: string;
}

export default function SettingsPage() {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [selected, setSelected] = useState<Business | null>(null);
  const [form, setForm] = useState<Partial<Business>>({});
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"" | "saved" | "error">("");
  const [connectingCalendar, setConnectingCalendar] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${BASE}/api/businesses/me`, { credentials: "include" })
      .then((r) => r.json())
      .then((data: Business) => {
        setBusinesses([data]);
        setSelected(data);
        setForm(data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function selectBusiness(b: Business) {
    setSelected(b);
    setForm(b);
    setSaveStatus("");
  }

  async function save() {
    if (!selected) return;
    setSaving(true);
    setSaveStatus("");
    try {
      const res = await fetch(`${BASE}/api/businesses/me`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name,
          forwarding_number: form.forwarding_number || null,
          greeting: form.greeting || null,
          business_hours: form.business_hours || null,
          booking_enabled: form.booking_enabled,
          knowledge_text: form.knowledge_text || null,
        }),
      });
      if (!res.ok) throw new Error();
      const updated: Business = await res.json();
      setSelected(updated);
      setForm(updated);
      setBusinesses((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
      setSaveStatus("saved");
    } catch {
      setSaveStatus("error");
    } finally {
      setSaving(false);
    }
  }

  async function connectGoogleCalendar() {
    if (!selected) return;
    setConnectingCalendar(true);
    try {
      const res = await fetch(`${BASE}/api/integrations/google/start?business_id=${selected.id}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      window.open(data.authorization_url, "_blank");
    } catch {
      alert("Could not start Google Calendar authorization. Make sure credentials.json is configured on the backend.");
    } finally {
      setConnectingCalendar(false);
    }
  }

  async function refreshCalendarStatus() {
    const res = await fetch(`${BASE}/api/businesses/me`, { credentials: "include" });
    if (!res.ok) return;
    const updated: Business = await res.json();
    setSelected(updated);
    setForm(updated);
    setBusinesses([updated]);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400 text-sm">Loading…</div>
    );
  }

  if (businesses.length === 0) {
    return (
      <>
        <div className="mb-8">
          <h1 className="text-xl font-semibold text-gray-900">Settings</h1>
        </div>
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 text-sm text-amber-700">
          No businesses found. Go to <a href="/onboarding" className="underline font-medium">Onboarding</a> to create one.
        </div>
      </>
    );
  }

  return (
    <>
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Settings</h1>
          <p className="text-sm text-gray-500 mt-1">Edit your business configuration.</p>
        </div>
        {businesses.length > 1 && (
          <select
            className="text-sm border border-gray-300 rounded-lg px-3 py-2 text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            value={selected?.id}
            onChange={(e) => {
              const b = businesses.find((biz) => biz.id === Number(e.target.value));
              if (b) selectBusiness(b);
            }}
          >
            {businesses.map((b) => (
              <option key={b.id} value={b.id}>{b.name} ({b.twilio_number})</option>
            ))}
          </select>
        )}
      </div>

      {saveStatus === "saved" && (
        <div className="mb-5 bg-emerald-50 border border-emerald-200 rounded-xl px-5 py-3 text-sm text-emerald-700">
          Settings saved.
        </div>
      )}
      {saveStatus === "error" && (
        <div className="mb-5 bg-red-50 border border-red-200 rounded-xl px-5 py-3 text-sm text-red-700">
          Failed to save. Please try again.
        </div>
      )}

      <div className="grid grid-cols-2 gap-5">
        {/* Business Info */}
        <div className="col-span-2 bg-white border border-gray-200 rounded-xl p-6 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">Business Info</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">Business Name</label>
              <input
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={form.name || ""}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">AI Receptionist Number</label>
              <input
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm text-gray-400 font-mono bg-gray-50 cursor-not-allowed"
                value={selected?.twilio_number || ""}
                disabled
              />
              <p className="text-xs text-gray-400 mt-1">Cannot be changed after creation.</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">Business Hours</label>
              <input
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Mon–Fri 9am–5pm"
                value={form.business_hours || ""}
                onChange={(e) => setForm({ ...form, business_hours: e.target.value })}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">Forwarding Number</label>
              <input
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="+15559876543"
                value={form.forwarding_number || ""}
                onChange={(e) => setForm({ ...form, forwarding_number: e.target.value })}
              />
            </div>
          </div>
        </div>

        {/* Greeting & Knowledge */}
        <div className="col-span-2 bg-white border border-gray-200 rounded-xl p-6 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">Receptionist</h2>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1.5">Opening Greeting</label>
            <textarea
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
              rows={2}
              value={form.greeting || ""}
              onChange={(e) => setForm({ ...form, greeting: e.target.value })}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1.5">What should your receptionist know?</label>
            <textarea
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
              rows={4}
              placeholder="Services, pricing, FAQs, anything callers commonly ask about…"
              value={form.knowledge_text || ""}
              onChange={(e) => setForm({ ...form, knowledge_text: e.target.value })}
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs font-medium text-gray-500">Booking Enabled</label>
            <button
              onClick={() => setForm({ ...form, booking_enabled: !form.booking_enabled })}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                form.booking_enabled ? "bg-indigo-600" : "bg-gray-200"
              }`}
            >
              <span
                className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
                  form.booking_enabled ? "translate-x-4.5" : "translate-x-0.5"
                }`}
              />
            </button>
          </div>
        </div>

        {/* Google Calendar */}
        <div className="col-span-2 bg-white border border-gray-200 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-700">Google Calendar</h2>
            {selected?.google_calendar_connected && (
              <button
                onClick={refreshCalendarStatus}
                className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
              >
                Refresh status
              </button>
            )}
          </div>

          {selected?.google_calendar_connected ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
                </span>
                <span className="text-sm font-medium text-emerald-700">Connected</span>
              </div>
              {selected.google_account_email && (
                <p className="text-sm text-gray-600">Account: <span className="font-medium">{selected.google_account_email}</span></p>
              )}
              {selected.google_calendar_id && (
                <p className="text-sm text-gray-600">Calendar ID: <span className="font-mono text-xs bg-gray-50 px-2 py-0.5 rounded border border-gray-200">{selected.google_calendar_id}</span></p>
              )}
              <button
                onClick={connectGoogleCalendar}
                disabled={connectingCalendar}
                className="mt-2 text-xs text-gray-500 hover:text-gray-700 underline"
              >
                Re-authorize
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-gray-500">Connect Google Calendar to automatically book appointments when callers schedule with your AI receptionist.</p>
              <button
                onClick={connectGoogleCalendar}
                disabled={connectingCalendar}
                className="inline-flex items-center gap-2 bg-white border border-gray-300 hover:border-gray-400 text-gray-700 text-sm font-medium px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                </svg>
                {connectingCalendar ? "Opening…" : "Connect Google Calendar"}
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="mt-6 flex items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white text-sm font-medium px-5 py-2.5 rounded-lg transition-colors"
        >
          {saving ? "Saving…" : "Save Changes"}
        </button>
        <button
          onClick={() => { if (selected) { setForm(selected); setSaveStatus(""); } }}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          Reset
        </button>
      </div>
    </>
  );
}
