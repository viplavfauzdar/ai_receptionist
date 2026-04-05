import "./globals.css";
import { Inter } from "next/font/google";
import Sidebar from "./components/Sidebar";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata = {
  title: "AI Receptionist Dashboard",
  description: "Onboarding and dashboard for AI receptionist MVP",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="bg-gray-50 text-gray-900 antialiased">
        <Sidebar />
        <main className="ml-60 min-h-screen">
          <div className="max-w-6xl px-8 py-8">
            {children}
          </div>
        </main>
      </body>
    </html>
  );
}
