"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AlertTriangle, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { FlagStripe, SunMark } from "@/components/brand";
import { SideRail } from "@/components/SideRail";
import { DEFAULT_PROFILE, LGU, useCompliance, type BusinessProfile } from "@/lib/compliance-store";
import { startCompliance } from "@/lib/api";
import { DISTRICTS } from "@/data/offices";
import { cn } from "@/lib/utils";

const STEPS = [
  { nav: "Business", title: "About your business" },
  { nav: "Location", title: "Where will it be?" },
  { nav: "Money", title: "Size and trade" },
  { nav: "Setup", title: "Any of these apply?" },
];
const LAST = STEPS.length - 1;

const ENTITIES = ["Sole Proprietorship", "Partnership", "One Person Corporation", "Corporation"];
const SPACES = ["Leased", "Owned", "Home-based"];
const INDUSTRIES = ["Small Café / Food Service", "Retail Store", "Online Selling", "Personal Services", "Light Manufacturing"];

const TOGGLES = [
  ["servesFood", "We serve food or drinks", "Adds a sanitary permit and health cards"],
  ["signage", "We will put up a signboard", "Adds a signage permit fee"],
  ["renovating", "We are renovating the space", "Adds a building and occupancy review"],
] as const;

/** BMBE (RA 9178) covers businesses with assets under ₱3M. */
const BMBE_LIMIT = 3_000_000;

/** Pause between the first two checks ticking off on the build screen. */
const TICK_MS = 1100;

const FIELD = "h-14 rounded-2xl border-input bg-card px-4 text-base shadow-none md:text-base";

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <Label className="text-sm font-semibold">
        {label}
        {hint && <span className="font-normal text-muted-foreground"> {hint}</span>}
      </Label>
      {children}
    </div>
  );
}

function Choice({ value, options, onChange, disabled }: {
  value: string;
  options: readonly string[];
  onChange?: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger className={cn(FIELD, "disabled:opacity-100")}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o} value={o}>{o}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** Blue track with the yellow sun as its thumb, as in the design. */
function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-9 w-16 shrink-0 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        checked ? "bg-primary" : "bg-input",
      )}
    >
      <span
        className={cn(
          "absolute top-1 size-7 rounded-full shadow transition-all",
          checked ? "left-8 bg-gold" : "left-1 bg-card",
        )}
      />
    </button>
  );
}

function BuildScreen({ district, checksDone, ready, warning, onContinue }: {
  district: string;
  checksDone: number;
  ready: boolean;
  warning: string | null;
  onContinue: () => void;
}) {
  const checks = [`Zoning for ${district}`, "DTI and BIR requirements", "Fees and BMBE eligibility"];
  return (
    <main className="flex min-h-screen flex-col bg-primary text-primary-foreground">
      <div className="grid flex-1 place-items-center px-5 py-16">
        <div className="w-full max-w-md text-center">
          <SunMark className={cn("mx-auto size-24", !ready && "animate-[spin_12s_linear_infinite]")} />
          <h1 className="mt-8 text-4xl font-extrabold sm:text-5xl">Building your roadmap</h1>
          <p className="mt-3 text-lg text-primary-foreground/75">Three checks, running side by side.</p>

          <ul className="mx-auto mt-10 w-fit space-y-4 text-left text-lg">
            {checks.map((c, i) => (
              <li key={c} className="flex items-center gap-3">
                {i < checksDone ? (
                  <span className="grid size-7 place-items-center rounded-full bg-gold text-gold-foreground">
                    <Check className="size-4" strokeWidth={3} />
                  </span>
                ) : (
                  <span className="size-7 rounded-full border-2 border-dashed border-primary-foreground/50" />
                )}
                <span className={cn(i >= checksDone && "text-primary-foreground/75")}>{c}</span>
              </li>
            ))}
          </ul>

          <div className="mt-10 h-2 overflow-hidden rounded-full bg-primary-foreground/20">
            <div
              className="h-full rounded-full bg-gold transition-all duration-700"
              style={{ width: `${Math.max(8, (checksDone / checks.length) * 100)}%` }}
            />
          </div>

          {warning && (
            <p className="mt-6 flex items-start gap-2 rounded-2xl bg-primary-foreground/10 p-4 text-left text-sm">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-gold" />
              <span>
                {warning}. You will get the standard Manila roadmap: the steps are still
                correct, just not tailored to your answers yet.
              </span>
            </p>
          )}

          <Button
            onClick={onContinue}
            disabled={!ready}
            className="mt-10 h-14 rounded-full bg-gold px-10 text-base font-bold text-gold-foreground hover:bg-gold/90 disabled:opacity-60"
          >
            {ready ? "See my roadmap" : "Working on it…"}
          </Button>
        </div>
      </div>
      <FlagStripe />
    </main>
  );
}

export default function Page() {
  const router = useRouter();
  const { finishOnboarding, setBackendRoadmap, profile, setProfile } = useCompliance();
  const [step, setStep] = useState(0);
  const [data, setData] = useState<BusinessProfile>(profile ?? DEFAULT_PROFILE);
  const [building, setBuilding] = useState(false);
  const [checksDone, setChecksDone] = useState(0);
  const [ready, setReady] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);

  const set = <K extends keyof BusinessProfile>(k: K, v: BusinessProfile[K]) =>
    setData((d) => ({ ...d, [k]: v }));

  const underage = data.ownerAge !== "" && Number(data.ownerAge) < 18;
  const capital = Number(data.capital);

  // Tick the first two checks on a timer; the last one waits for the backend.
  useEffect(() => {
    if (!building || checksDone >= 2) return;
    const t = setTimeout(() => setChecksDone((n) => n + 1), TICK_MS);
    return () => clearTimeout(t);
  }, [building, checksDone]);

  // Create a session and generate the roadmap. On failure the bundled Manila
  // roadmap is used rather than trapping the user on this screen.
  useEffect(() => {
    if (!building) return;
    let cancelled = false;
    (async () => {
      try {
        const { sessionId, roadmap } = await startCompliance(data);
        if (cancelled) return;
        // This roadmap is final
        setBackendRoadmap(sessionId, roadmap.roadmap, roadmap.source ?? "template");
      } catch (err) {
        if (cancelled) return;
        setWarning(err instanceof Error ? err.message : "Could not reach the compliance service");
      }
      if (!cancelled) setReady(true);
    })();
    return () => {
      cancelled = true;
    };
    // Intentionally keyed only on `building` - this must run once per submit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [building]);

  if (building) {
    return (
      <BuildScreen
        district={data.district}
        // The last check is the backend itself, so it completes with it.
        checksDone={ready && checksDone >= 2 ? 3 : checksDone}
        ready={ready && checksDone >= 2}
        warning={warning}
        onContinue={() => {
          finishOnboarding(data);
          router.push("/dashboard");
        }}
      />
    );
  }

  const canContinue = !(step === 0 && underage);

  return (
    <main className="flex min-h-screen flex-col lg:flex-row">
      <SideRail
        steps={STEPS.map((s) => s.nav)}
        current={step}
        completedThrough={step - 1}
        onWhereToGo={() => {
          // Keep the answers so far: the map uses the district, and coming
          // back restores the form from the stored profile.
          setProfile(data);
          router.push("/where-to-go");
        }}
      />

      <section className="flex flex-1 items-start px-5 py-10 sm:px-10 lg:items-center lg:px-[8%]">
        <div className="w-full max-w-xl">
          <p className="text-sm font-semibold uppercase tracking-[0.14em] text-flag-red">
            Step {step + 1} of {STEPS.length}
          </p>
          <h1 className="mt-2 text-4xl font-extrabold sm:text-5xl">{STEPS[step]!.title}</h1>

          <div className="mt-9 space-y-7">
            {step === 0 && (
              <>
                <Field label="Business name">
                  <Input value={data.businessName} onChange={(e) => set("businessName", e.target.value)}
                    placeholder="e.g. Manila Artisanal Café" className={FIELD} />
                </Field>
                <Field label="Business type">
                  <Choice value={data.entity} options={ENTITIES} onChange={(v) => set("entity", v)} />
                </Field>
                <Field label="Your age" hint="(owners must be 18 or older)">
                  <Input type="number" min={0} value={data.ownerAge}
                    onChange={(e) => set("ownerAge", e.target.value)} className={cn(FIELD, "w-40")} />
                </Field>
                {underage && (
                  <p className="border-l-4 border-flag-red pl-4 text-sm text-muted-foreground">
                    DTI only registers business names for owners who are 18 or older.
                  </p>
                )}
              </>
            )}

            {step === 1 && (
              <>
                {/* Scoped to the City of Manila: the ordinances, permit sequence
                    and fee table are all Manila's. */}
                <Field label="City">
                  <Choice value={LGU} options={[LGU]} disabled />
                </Field>
                <Field label="District and barangay">
                  <Choice value={data.district} options={DISTRICTS} onChange={(v) => set("district", v)} />
                </Field>
                <Field label="Do you own the space?">
                  <Choice value={data.physicalStatus} options={SPACES} onChange={(v) => set("physicalStatus", v)} />
                </Field>
                {data.physicalStatus === "Leased" && (
                  <p className="border-l-4 border-flag-red pl-4 text-sm leading-relaxed text-muted-foreground">
                    Leased spaces need a notarized lease contract and the lessor&apos;s real property tax receipt.
                  </p>
                )}
                {data.physicalStatus === "Home-based" && (
                  <p className="border-l-4 border-flag-red pl-4 text-sm leading-relaxed text-muted-foreground">
                    Home-based businesses still need a barangay clearance and a zoning check for the address.
                  </p>
                )}
              </>
            )}

            {step === 2 && (
              <>
                <Field label="Starting capital (₱)">
                  <Input type="number" min={0} value={data.capital}
                    onChange={(e) => set("capital", e.target.value)} className={FIELD} />
                </Field>
                {capital > 0 && capital < BMBE_LIMIT && (
                  <p className="rounded-2xl bg-gold-soft px-4 py-3 text-sm text-gold-foreground">
                    Under ₱3M, so you likely qualify for BMBE (RA 9178) income tax exemption.
                  </p>
                )}
                <Field label="What kind of business?">
                  <Choice value={data.industry} options={INDUSTRIES} onChange={(v) => set("industry", v)} />
                </Field>
                <Field label="Number of employees">
                  <Input type="number" min={0} value={data.employees}
                    onChange={(e) => set("employees", e.target.value)} className={cn(FIELD, "w-40")} />
                </Field>
              </>
            )}

            {step === 3 && (
              <ul className="divide-y divide-border border-y border-border">
                {TOGGLES.map(([key, title, note]) => (
                  <li key={key} className="flex items-center justify-between gap-6 py-6">
                    <span>
                      <span className="block text-lg font-semibold">{title}</span>
                      <span className="block text-muted-foreground">{note}</span>
                    </span>
                    <Toggle checked={data[key]} onChange={(v) => set(key, v)} label={title} />
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="mt-10 flex items-center justify-between">
            <button
              type="button"
              className="text-lg font-semibold text-muted-foreground hover:text-foreground"
              onClick={() => (step === 0 ? router.push("/") : setStep((s) => s - 1))}
            >
              Back
            </button>
            <Button
              disabled={!canContinue}
              className="h-14 rounded-full px-10 text-lg font-bold"
              onClick={() => (step < LAST ? setStep((s) => s + 1) : setBuilding(true))}
            >
              {step < LAST ? "Continue" : "Build my roadmap"}
            </Button>
          </div>
        </div>
      </section>
    </main>
  );
}
