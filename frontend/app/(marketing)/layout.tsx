import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Reeva — AI Receptionist",
  description: "AI receptionist that answers your calls, books appointments, and never misses a lead.",
};

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {/* eslint-disable-next-line @next/next/no-page-custom-font */}
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      {/* eslint-disable-next-line @next/next/no-page-custom-font */}
      <link
        href="https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,300;0,400;1,300;1,400&family=Plus+Jakarta+Sans:wght@300;400;500&display=swap"
        rel="stylesheet"
      />
      {children}
    </>
  );
}
