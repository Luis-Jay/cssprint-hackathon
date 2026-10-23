"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FlagStripe, Logo } from "@/components/brand";
import { useCompliance } from "@/lib/compliance-store";
import { getToken as hasStoredToken } from "@/lib/api";
import { useRouter } from "next/navigation";

const STATS = [
  { value: "4", label: "quick questions", color: "text-primary" },
  { value: "5", label: "permit stages, in order", color: "text-flag-red" },
  { value: "1", label: "clear fee estimate", color: "text-foreground" },
];

const FIELD = "h-14 rounded-2xl border-input bg-card px-4 text-base shadow-none md:text-base";

export default function Page() {
  const router = useRouter();
  const { signIn, signUp, onboarded, signedIn, authLoading } = useCompliance();
  const [mode, setMode] = useState<"signup" | "login">("signup");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Already signed in: go straight through, without waiting for the token round trip
  useEffect(() => {
    if (signedIn) router.replace(onboarded ? "/dashboard" : "/onboarding");
  }, [signedIn, onboarded, router]);

  // A stored token that has not resolved yet means we do not know who this is
  const resolvingSession = authLoading && hasStoredToken();

  const switchMode = (next: "signup" | "login") => {
    setMode(next);
    setError(null);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "signup") await signUp(email, password, name);
      else await signIn(email, password);
      router.push(onboarded ? "/dashboard" : "/onboarding");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen flex-col bg-background">
      <FlagStripe />

      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-6 sm:px-8">
        <Logo />
        <nav className="flex items-center gap-6 text-sm">
          <span className="hidden text-muted-foreground sm:inline">City of Manila pilot</span>
          <button
            type="button"
            onClick={() => switchMode(mode === "login" ? "signup" : "login")}
            className="font-semibold text-primary hover:underline"
          >
            {mode === "login" ? "Sign up" : "Log in"}
          </button>
        </nav>
      </header>

      <section className="mx-auto grid w-full max-w-6xl flex-1 items-center gap-12 px-5 py-10 sm:px-8 lg:grid-cols-[1.3fr_minmax(0,420px)] lg:gap-16">
        <div>
          <h1 className="text-5xl font-extrabold leading-[0.98] text-foreground sm:text-6xl lg:text-[4.25rem]">
            Open your Manila business.
            <span className="mt-1 block text-flag-red">Skip the red tape.</span>
          </h1>
          <p className="mt-7 max-w-md text-lg leading-relaxed text-muted-foreground">
            Answer four short questions and get a personal, step-by-step permit roadmap.
          </p>
        </div>

        {resolvingSession || signedIn ? (
          <div className="grid min-h-[360px] place-items-center rounded-[2rem] bg-panel p-8">
            <div className="text-center">
              <Loader2 className="mx-auto size-6 animate-spin text-primary" />
              <p className="mt-3 font-semibold">Restoring your session…</p>
              <p className="mt-1 text-sm text-muted-foreground">Picking up where you left off.</p>
            </div>
          </div>
        ) : (
          <div className="rounded-[2rem] bg-panel p-7 sm:p-9">
            <h2 className="text-2xl font-extrabold">
              {mode === "signup" ? "Start free" : "Welcome back"}
            </h2>
            <form onSubmit={submit} className="mt-6 space-y-5">
              {error && (
                <p className="flex items-start gap-2 rounded-xl bg-destructive/10 p-3 text-sm font-medium text-destructive">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  <span>{error}</span>
                </p>
              )}
              {mode === "signup" && (
                <div className="space-y-2">
                  <Label htmlFor="name" className="text-sm font-semibold">Full name</Label>
                  <Input id="name" required autoComplete="name" value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Juan Dela Cruz" className={FIELD} />
                </div>
              )}
              <div className="space-y-2">
                <Label htmlFor="email" className="text-sm font-semibold">Email</Label>
                <Input id="email" type="email" required autoComplete="email" value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="juan@email.com" className={FIELD} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password" className="text-sm font-semibold">Password</Label>
                <Input id="password" type="password" required
                  minLength={mode === "signup" ? 8 : undefined}
                  autoComplete={mode === "signup" ? "new-password" : "current-password"}
                  value={password} onChange={(e) => setPassword(e.target.value)}
                  placeholder={mode === "signup" ? "At least 8 characters" : "Your password"}
                  className={FIELD} />
              </div>
              <Button type="submit" disabled={busy}
                className="h-14 w-full rounded-full text-base font-bold">
                {busy ? (
                  <><Loader2 className="size-4 animate-spin" />
                    {mode === "signup" ? "Creating account…" : "Logging in…"}</>
                ) : mode === "signup" ? "Create account" : "Log in"}
              </Button>
              <p className="text-center text-sm text-muted-foreground">
                {mode === "signup" ? (
                  "Prototype only. Nothing is sent to any government office."
                ) : (
                  <>
                    New here?{" "}
                    <button type="button" onClick={() => switchMode("signup")}
                      className="font-semibold text-primary hover:underline">
                      Create an account
                    </button>
                  </>
                )}
              </p>
            </form>
          </div>
        )}
      </section>

      <section className="mx-auto grid w-full max-w-6xl gap-6 px-5 pb-14 pt-4 sm:grid-cols-3 sm:px-8">
        {STATS.map((s) => (
          <p key={s.label} className="flex items-baseline gap-3">
            <span className={`font-display text-5xl font-extrabold ${s.color}`}>{s.value}</span>
            <span className="text-muted-foreground">{s.label}</span>
          </p>
        ))}
      </section>
    </main>
  );
}
