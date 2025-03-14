import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Navigation } from "@/components/navigation";
import { RedisMonitorProvider } from "@/lib/context/RedisMonitorContext";
import "./globals.css";

// Use Inter font as our primary font
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Redis Monitor | EmProps",
  description: "Monitoring and debugging tool for the EmProps Redis system",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${inter.variable} font-sans antialiased min-h-screen bg-gray-50`}
      >
        <RedisMonitorProvider>
          <Navigation />
          <main className="container mx-auto py-6 px-4">
            {children}
          </main>
        </RedisMonitorProvider>
      </body>
    </html>
  );
}
