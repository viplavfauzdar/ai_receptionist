async function getSettings() {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const res = await fetch(`${base}/api/settings`, { cache: "no-store" });
  return res.ok ? res.json() : {};
}

export default async function SettingsPage() {
  const settings = await getSettings();

  return (
    <div className="card">
      <div className="h1">Settings</div>
      <div className="grid grid-2">
        <div>
          <div className="muted">Business Name</div>
          <div>{settings.business_name || "-"}</div>
        </div>
        <div>
          <div className="muted">Business Hours</div>
          <div>{settings.business_hours || "-"}</div>
        </div>
      </div>
      <div style={{ marginTop: 16 }}>
        <div className="muted">Greeting</div>
        <div>{settings.business_greeting || "-"}</div>
      </div>
      <div style={{ marginTop: 16 }}>
        <div className="muted">Booking Enabled</div>
        <div>{String(settings.booking_enabled)}</div>
      </div>
    </div>
  );
}
