async function getCalls() {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  try {
    const res = await fetch(`${base}/api/calls`, { cache: "no-store" });
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

export default async function CallsPage() {
  const calls = await getCalls();

  return (
    <>
      <div className="mb-8 flex items-center gap-3">
        <h1 className="text-xl font-semibold text-gray-900">Call Log</h1>
        <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200">
          {calls.length}
        </span>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">From</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">To</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Speech</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">AI Response</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Intent</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {calls.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center">
                    <div className="text-gray-500 font-medium">No calls recorded yet.</div>
                    <div className="text-gray-400 text-xs mt-1">Calls will appear here after callers reach your Twilio number.</div>
                  </td>
                </tr>
              ) : (
                calls.map((row: any) => (
                  <tr key={row.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-3 font-mono text-xs text-gray-700 whitespace-nowrap">{row.from_number || "—"}</td>
                    <td className="px-6 py-3 font-mono text-xs text-gray-500 whitespace-nowrap">{row.to_number || "—"}</td>
                    <td className="px-6 py-3 text-gray-600 max-w-[180px] truncate">{row.speech_input || "—"}</td>
                    <td className="px-6 py-3 text-gray-600 max-w-[220px] truncate">{row.ai_response || "—"}</td>
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
