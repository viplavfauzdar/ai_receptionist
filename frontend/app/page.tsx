async function getCalls() {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const res = await fetch(`${base}/api/calls`, { cache: "no-store" });
  return res.ok ? res.json() : [];
}

async function getAppointments() {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const res = await fetch(`${base}/api/appointments`, { cache: "no-store" });
  return res.ok ? res.json() : [];
}

export default async function HomePage() {
  const calls = await getCalls();
  const appointments = await getAppointments();

  return (
    <>
      <div className="card">
        <div className="h1">AI Receptionist Dashboard</div>
        <div className="muted">Minimal business-facing UI for the MVP.</div>
      </div>

      <div className="grid grid-3">
        <div className="card">
          <div className="muted">Recent Calls</div>
          <div className="stat">{calls.length}</div>
        </div>
        <div className="card">
          <div className="muted">Appointment Requests</div>
          <div className="stat">{appointments.length}</div>
        </div>
        <div className="card">
          <div className="muted">Status</div>
          <div className="stat">Live</div>
        </div>
      </div>

      <div className="card">
        <div className="h2">Latest Calls</div>
        <table className="table">
          <thead>
            <tr>
              <th>From</th>
              <th>Speech</th>
              <th>AI Response</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {calls.slice(0, 8).map((row: any) => (
              <tr key={row.id}>
                <td>{row.from_number || "-"}</td>
                <td>{row.speech_input || "-"}</td>
                <td>{row.ai_response || "-"}</td>
                <td>{new Date(row.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
