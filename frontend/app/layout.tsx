import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Genesis — AI Game Master",
  description: "Cinematic AI-powered tabletop RPG experience",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
