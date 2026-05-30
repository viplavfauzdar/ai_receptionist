import Sidebar from "../components/Sidebar";

export const metadata = {
  title: "Reeva Dashboard",
};

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-gray-50 text-gray-900 min-h-screen">
      <Sidebar />
      <main className="ml-60 min-h-screen">
        <div className="max-w-6xl px-8 py-8">
          {children}
        </div>
      </main>
    </div>
  );
}
