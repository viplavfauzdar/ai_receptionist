async function getCalls() {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const res = await fetch(`${base}/api/calls`, { cache: "no-store" });
  return res.ok ? res.json() : [];
}

export default async function CallsPage() {
  const calls = await getCalls();

  return (
    <div className="card">
      <div className="h1">Calls</div>
      <table className="table">
        <thead>
          <tr>
            <th>From</th>
            <th>To</th>
            <th>Speech</th>
            <th>AI Response</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {calls.map((row: any) => (
            <tr key={row.id}>
              <td>{row.from_number || "-"}</td>
              <td>{row.to_number || "-"}</td>
              <td>{row.speech_input || "-"}</td>
              <td>{row.ai_response || "-"}</td>
              <td>{new Date(row.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
