async function getCalls() {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  try {
    const res = await fetch(`${base}/api/calls`, { cache: "no-store" });
    return res.ok ? res.json() : [];
  } catch {
    return [];
  }
}

async function getAppointments() {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  try {
    const res = await fetch(`${base}/api/appointments`, { cache: "no-store" });
    return res.ok ? res.json() : [];
  } catch {
    return [];
  }
}

const intentColors: Record<string, string> = {
  BOOK_APPOINTMENT: "bg-indigo-50 text-indigo-700 border border-indigo-200",
  BUSINESS_HOURS: "bg-amber-50 text-amber-700 border border-amber-200",
  CALLBACK_REQUEST: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  GENERAL_QUESTION: "bg-gray-100 text-gray-600 border border-gray-200",
};

function IntentBadge({ intent }: { intent?: string }) {
  if (!intent) return <span className="text-gray-300">—</span>;
  const classes = intentColors[intent] ?? "bg-gray-100 text-gray-600 border border-gray-200";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${classes}`}>
      {intent.replace(/_/g, " ")}
    </span>
  );
}

export default async function HomePage() {
  const calls = await getCalls();
  const appointments = await getAppointments();

  return (
    <>
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-900">Overview</h1>
        <p className="text-sm text-gray-500 mt-1">AI receptionist activity at a glance.</p>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="bg-white border border-gray-200 rounded-xl p-5 border-l-4 border-l-indigo-500">
          <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Recent Calls</div>
          <div className="text-3xl font-bold text-gray-900">{calls.length}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-5 border-l-4 border-l-indigo-500">
          <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Appointment Requests</div>
          <div className="text-3xl font-bold text-gray-900">{appointments.length}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-5 border-l-4 border-l-indigo-500">
          <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Status</div>
          <div className="flex items-center gap-2 mt-1">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
            </span>
            <span className="text-xl font-bold text-emerald-600">Live</span>
          </div>
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-900">Latest Calls</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">From</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Speech</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">AI Response</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Intent</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {calls.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-10 text-center text-gray-400 text-sm">No calls yet.</td>
                </tr>
              ) : (
                calls.slice(0, 8).map((row: any) => (
                  <tr key={row.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-3 font-mono text-xs text-gray-700 whitespace-nowrap">{row.from_number || "—"}</td>
                    <td className="px-6 py-3 text-gray-600 max-w-[200px] truncate">{row.speech_input || "—"}</td>
                    <td className="px-6 py-3 text-gray-600 max-w-[240px] truncate">{row.ai_response || "—"}</td>
                    <td className="px-6 py-3"><IntentBadge intent={row.intent} /></td>
                    <td className="px-6 py-3 text-gray-400 whitespace-nowrap text-xs">{new Date(row.created_at).toLocaleString()}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
