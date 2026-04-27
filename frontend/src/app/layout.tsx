import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Rett Repurposing",
  description:
    "In-silico drug repurposing for Rett syndrome — Phase 1 (target-based strategy).",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">{children}</body>
    </html>
  );
}
