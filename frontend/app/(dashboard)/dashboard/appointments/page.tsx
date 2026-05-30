import { authHeaders } from "@/lib/server-auth";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function getAppointments() {
  try {
    const res = await fetch(`${BASE}/api/appointments`, {
      cache: "no-store",
      headers: authHeaders(),
    });
    return res.ok ? res.json() : [];
  } catch {
    return [];
  }
}

function StatusBadge({ confirmed, calendarLink }: { confirmed: boolean; calendarLink?: string }) {
  if (confirmed && calendarLink) {
    return (
      <a
        href={calendarLink}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 transition-colors"
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
        Booked
      </a>
    );
  }
  if (confirmed) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
        Confirmed
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
      Pending
    </span>
  );
}

function formatScheduled(start?: string, end?: string) {
  if (!start) return null;
  const s = new Date(start);
  const e = end ? new Date(end) : null;
  const date = s.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  const startTime = s.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const endTime = e ? e.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : null;
  return endTime ? `${date} · ${startTime}–${endTime}` : `${date} · ${startTime}`;
}

export default async function AppointmentsPage() {
  const appointments = await getAppointments();

  return (
    <>
      <div className="mb-8 flex items-center gap-3">
        <h1 className="text-xl font-semibold text-gray-900">Appointments</h1>
        <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200">
          {appointments.length}
        </span>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Caller</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Phone</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Requested</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Scheduled</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Notes</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Received</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {appointments.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center">
                    <div className="text-gray-500 font-medium">No appointments yet.</div>
                    <div className="text-gray-400 text-xs mt-1">Appointments requested by callers will appear here.</div>
                  </td>
                </tr>
              ) : (
                appointments.map((appt: any) => (
                  <tr key={appt.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-3 text-gray-800 font-medium whitespace-nowrap">{appt.caller_name || "—"}</td>
                    <td className="px-6 py-3 font-mono text-xs text-gray-600 whitespace-nowrap">{appt.caller_phone || "—"}</td>
                    <td className="px-6 py-3 text-gray-600 whitespace-nowrap">{appt.requested_time || "—"}</td>
                    <td className="px-6 py-3 text-gray-600 whitespace-nowrap text-xs">
                      {formatScheduled(appt.scheduled_start, appt.scheduled_end) || <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-6 py-3 text-gray-500 max-w-[200px] truncate">{appt.notes || <span className="text-gray-300">—</span>}</td>
                    <td className="px-6 py-3">
                      <StatusBadge confirmed={appt.confirmed} calendarLink={appt.calendar_event_link} />
                    </td>
                    <td className="px-6 py-3 text-gray-400 whitespace-nowrap text-xs">{new Date(appt.created_at).toLocaleString()}</td>
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
