"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowLeft, ArrowUpRight, Globe } from "lucide-react";
import { FlagStripe, SunMark } from "@/components/brand";
import { OfficeMap } from "@/components/OfficeMap";
import { SideRail } from "@/components/SideRail";
import { DISTRICTS, directionsUrl, officesFor, openStatus } from "@/data/offices";
import { useCompliance } from "@/lib/compliance-store";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

/** Same labels as the onboarding rail */
const ONBOARDING_STEPS = ["Business", "Location", "Money", "Setup"];

export default function Page() {
  const router = useRouter();
  const { profile, onboarded } = useCompliance();
  // Starts on the business's own district; browsing others doesn't change the profile.
  const [picked, setPicked] = useState<string | null>(null);
  const district = picked ?? profile.district;
  const offices = useMemo(() => officesFor(district), [district]);
  const here = offices.filter((o) => o.inDistrict);
  const elsewhere = offices.filter((o) => !o.inDistrict);
  const mapped = useMemo(() => offices.filter((o) => o.inDistrict && o.position), [offices]);

  const [chosenId, setChosenId] = useState<string | null>(null);
  // Fall back to the first pinned office when the choice is not in this district.
  const selectedId = mapped.some((o) => o.id === chosenId) ? chosenId! : mapped[0]?.id ?? "";
  const status = openStatus();

  const showElsewhere = (officeDistrict: string, id: string) => {
    setPicked(officeDistrict);
    setChosenId(id);
  };

  const goBack = () => {
    if (window.history.length > 1) router.back();
    else router.push(onboarded ? "/dashboard" : "/onboarding");
  };

  return (
    <div className="flex min-h-screen bg-surface">
      <SideRail
        compact
        steps={ONBOARDING_STEPS}
        current={null}
        completedThrough={onboarded ? ONBOARDING_STEPS.length - 1 : -1}
        whereToGoActive
        onWhereToGo={() => {}}
        onStep={onboarded ? undefined : () => router.push("/onboarding")}
      />
      <div className="min-w-0 flex-1">
      <FlagStripe />
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-4 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-full bg-primary">
              <SunMark className="size-7" />
            </span>
            <div className="min-w-0">
              <p className="truncate font-display text-lg font-bold leading-tight">
                {profile.businessName || "Your business"}
              </p>
              <p className="truncate text-sm text-muted-foreground">
                {profile.district} · {profile.entity}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={goBack}
            className="flex shrink-0 items-center gap-1.5 font-semibold text-primary hover:underline"
          >
            <ArrowLeft className="size-4" /> {onboarded ? "Back to roadmap" : "Back"}
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 pb-16 pt-10 sm:px-8">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <h1 className="text-4xl font-extrabold sm:text-5xl">Where to go</h1>
            <p className="mt-2 text-muted-foreground">
              Confirm days and hours with each office before you visit. Pins marked ≈ are approximate.
            </p>
          </div>
          <div className="w-full space-y-2 sm:w-[380px]">
            <Label htmlFor="district" className="text-sm font-semibold">District and barangay</Label>
            <Select value={district} onValueChange={(v: string) => { setPicked(v); setChosenId(null); }}>
              <SelectTrigger id="district" className="h-14 rounded-2xl border-input bg-card px-4 text-base shadow-none md:text-base">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DISTRICTS.map((d) => (
                  <SelectItem key={d} value={d}>
                    {d}{d === profile.district ? " (your business)" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="isolate h-[420px] overflow-hidden rounded-[2rem] bg-panel shadow-soft lg:sticky lg:top-6 lg:h-[600px]">
            {/* Remount for a different district so the pins and bounds rebuild */}
            <OfficeMap key={district} offices={mapped} selectedId={selectedId} onSelect={setChosenId} />
          </div>

          <ol className="space-y-4">
            {here.map((office) => {
              const selected = office.id === selectedId;
              return (
                <li key={office.id}>
                  <div
                    role={office.position ? "button" : undefined}
                    tabIndex={office.position ? 0 : undefined}
                    onClick={() => office.position && setChosenId(office.id)}
                    onKeyDown={(e) => {
                      if (office.position && (e.key === "Enter" || e.key === " ")) {
                        e.preventDefault();
                        setChosenId(office.id);
                      }
                    }}
                    aria-pressed={office.position ? selected : undefined}
                    className={cn(
                      "rounded-3xl border-2 bg-card p-6 transition-colors",
                      selected ? "border-primary" : "border-transparent",
                      office.position && "cursor-pointer hover:border-primary/30",
                    )}
                  >
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-flag-red">
                      Stage {office.stage} · {office.stageLabel}
                    </p>
                    <h2 className="mt-1 text-xl font-bold leading-snug">{office.name}</h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {office.approximate && "≈ "}
                      {office.address}
                    </p>
                    <p className="text-sm text-muted-foreground">{office.hours}</p>
                    {office.note && <p className="mt-2 text-sm leading-relaxed">{office.note}</p>}

                    <div className="mt-4 flex items-center justify-between gap-3">
                      {office.online ? (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-sage-soft px-3 py-1 text-xs font-semibold text-primary">
                          <Globe className="size-3.5" /> Online
                        </span>
                      ) : (
                        <span className={cn(
                          "rounded-full px-3 py-1 text-xs font-semibold",
                          status.open ? "bg-sage-soft text-primary" : "bg-red-50 text-flag-red",
                        )}>
                          {status.open ? "Open now" : status.label}
                        </span>
                      )}
                      <a
                        href={office.online ? office.online.url : directionsUrl(office.directionsQuery!)}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
                      >
                        {office.online ? office.online.label : "Get directions"}
                        <ArrowUpRight className="size-4" />
                      </a>
                    </div>
                  </div>
                </li>
              );
            })}

            {elsewhere.map((office) => (
              <li key={office.id}>
                <div className="rounded-3xl border-2 border-dashed border-input p-6">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-flag-red">
                    Stage {office.stage} · {office.stageLabel}
                  </p>
                  <p className="mt-2 leading-relaxed">
                    {office.pinLabel} is in {office.homeDistrict}, not in this zone.
                  </p>
                  <button
                    type="button"
                    onClick={() => showElsewhere(office.homeDistrict!, office.id)}
                    className="mt-4 h-12 rounded-full bg-primary px-6 font-semibold text-primary-foreground hover:bg-primary/90"
                  >
                    Show {office.pinLabel}
                  </button>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </main>
      </div>
    </div>
  );
}
