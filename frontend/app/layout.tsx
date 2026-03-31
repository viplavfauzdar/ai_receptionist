import "./globals.css";
import Link from "next/link";

export const metadata = {
  title: "AI Receptionist Dashboard",
  description: "Onboarding and dashboard for AI receptionist MVP",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="page">
          <nav className="nav">
            <Link href="/">Overview</Link>
            <Link href="/onboarding">Onboarding</Link>
            <Link href="/calls">Calls</Link>
            <Link href="/settings">Settings</Link>
          </nav>
          {children}
        </div>
      </body>
    </html>
  );
}
