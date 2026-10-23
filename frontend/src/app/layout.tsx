import type { Metadata } from "next";
import { Bricolage_Grotesque, DM_Sans } from "next/font/google";
import "./globals.css";
import { ComplianceProvider } from "../lib/compliance-store";
import { Toaster } from "@/components/ui/sonner";

// Display face for headings; DM Sans for everything else.
const bricolage = Bricolage_Grotesque({
  variable: "--font-bricolage",
  subsets: ["latin"],
  weight: ["600", "700", "800"],
});

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Sellyo - Open your Manila business",
  description:
    "Answer four short questions and get a personal, step-by-step permit roadmap for your City of Manila business.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${bricolage.variable} ${dmSans.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ComplianceProvider>
          {children}
          <Toaster />
        </ComplianceProvider>
      </body>
    </html>
  );
}
