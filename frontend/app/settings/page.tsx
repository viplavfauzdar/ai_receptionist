async function getSettings() {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  try {
    const res = await fetch(`${base}/api/settings`, { cache: "no-store" });
    return res.ok ? res.json() : {};
  } catch {
    return {};
  }
}

function SettingField({ label, value }: { label: string; value?: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">{label}</span>
        <span className="text-xs text-gray-400 bg-gray-50 px-2 py-0.5 rounded border border-gray-200">read-only</span>
      </div>
      <div className="text-sm text-gray-800 break-words">{value || <span className="text-gray-300">—</span>}</div>
    </div>
  );
}

export default async function SettingsPage() {
  const settings = await getSettings();

  return (
    <>
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-900">Settings</h1>
        <p className="text-sm text-gray-500 mt-1">Current business configuration from the backend.</p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <SettingField label="Business Name" value={settings.business_name} />
        <SettingField label="Business Hours" value={settings.business_hours} />
        <SettingField label="Booking Enabled" value={String(settings.booking_enabled ?? "—")} />
        <SettingField label="Greeting" value={settings.business_greeting} />
      </div>
    </>
  );
}
