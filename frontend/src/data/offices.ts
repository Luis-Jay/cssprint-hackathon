/**
 * Offices a Manila business visits, for the "Where to go" map.
 *
 * Only Manila City Hall is pinned at a known location. Barangay halls and BIR
 * Revenue District Offices are pinned near the district they serve and marked
 * approximate; their directions links search Google Maps by name instead, so
 * Google resolves the real address. Hours are the usual government schedule.
 */

/** District and barangay zones the app covers; shared with onboarding. */
export const DISTRICTS = [
  "Sampaloc, Zone 30",
  "Binondo, Zone 27",
  "Ermita, Zone 71",
  "Tondo, Zone 5",
  "Sta. Ana, Zone 84",
] as const;

/** Where Manila City Hall (and its Bureau of Permits) sits. */
export const CITY_HALL_DISTRICT = "Ermita, Zone 71";

export type Office = {
  id: string;
  stage: number;
  stageLabel: string;
  name: string;
  /** Short label under the map pin */
  pinLabel: string;
  address: string;
  /** Hours shown on the card; used for "open now" as Mon-Fri 8:00-17:00 Manila time */
  hours: string;
  note?: string;
  /** No pin; done online */
  online?: { url: string; label: string };
  position?: [number, number];
  approximate?: boolean;
  /** Free-text destination for Google Maps directions */
  directionsQuery?: string;
  /** Whether the office is in (or serves) the district being viewed. Online offices count as in. */
  inDistrict: boolean;
  /** Where the office is, when it is outside the district being viewed */
  homeDistrict?: string;
};

const CITY_HALL: [number, number] = [14.5895, 120.9816];

/** Rough centre of each district offered in onboarding. */
const DISTRICT_CENTRES: Record<string, [number, number]> = {
  Sampaloc: [14.6086, 120.9925],
  Binondo: [14.5995, 120.9745],
  Ermita: [14.5826, 120.984],
  Tondo: [14.619, 120.968],
  "Sta. Ana": [14.581, 121.013],
};

/** BIR Revenue District Office covering each Manila district. Confirm on your COR. */
const RDO_BY_DISTRICT: Record<string, { code: string; area: string }> = {
  Sampaloc: { code: "32", area: "Quiapo, Sampaloc, San Miguel, Sta. Mesa" },
  Binondo: { code: "30", area: "Binondo" },
  Ermita: { code: "33", area: "Intramuros, Ermita, Malate" },
  Tondo: { code: "29", area: "Tondo, San Nicolas" },
  "Sta. Ana": { code: "34", area: "Paco, Pandacan, Sta. Ana, San Andres" },
};

const HOURS = "Mon – Fri · 8:00 AM – 5:00 PM";

/** "Sampaloc, Zone 30" -> "Sampaloc" */
function districtName(district: string) {
  return district.split(",")[0]!.trim();
}

/** Nudge an approximate pin off the district centre so two pins never overlap. */
function offset([lat, lng]: [number, number], dLat: number, dLng: number): [number, number] {
  return [lat + dLat, lng + dLng];
}

export function officesFor(district: string): Office[] {
  const name = districtName(district);
  const centre = DISTRICT_CENTRES[name] ?? CITY_HALL;
  const rdo = RDO_BY_DISTRICT[name];

  return [
    {
      id: "dti",
      stage: 1,
      stageLabel: "DTI business name",
      name: "DTI Business Name Registration",
      pinLabel: "DTI",
      address: "Online, no visit needed",
      hours: "Open 24/7 online",
      online: { url: "https://bnrs.dti.gov.ph", label: "Open bnrs.dti.gov.ph" },
      inDistrict: true,
    },
    {
      id: "barangay",
      stage: 2,
      stageLabel: "Barangay clearance",
      name: `Barangay Hall · ${district}`,
      pinLabel: "Barangay Hall",
      address: `The barangay hall for your business address in ${name}`,
      hours: HOURS,
      position: offset(centre, -0.002, -0.004),
      approximate: true,
      directionsQuery: `Barangay hall ${district}, Manila`,
      inDistrict: true,
    },
    {
      id: "city-hall",
      stage: 4,
      stageLabel: "Mayor's permit",
      name: "Manila City Hall · Bureau of Permits",
      pinLabel: "Manila City Hall",
      address: "Padre Burgos Ave, Ermita, Manila",
      hours: HOURS,
      note: "For Stage 3 (zoning, sanitary and fire clearances), ask the Bureau of Permits which office handles each one.",
      position: CITY_HALL,
      directionsQuery: "Manila City Hall, Padre Burgos Ave, Ermita, Manila",
      inDistrict: district === CITY_HALL_DISTRICT,
      homeDistrict: CITY_HALL_DISTRICT,
    },
    {
      id: "bir",
      stage: 5,
      stageLabel: "BIR registration",
      name: rdo ? `BIR Revenue District Office ${rdo.code}` : "BIR Revenue District Office",
      pinLabel: "BIR District Office",
      address: rdo ? `Covers ${rdo.area}` : "The RDO that covers your business address",
      hours: HOURS,
      position: offset(centre, 0.003, 0.005),
      approximate: true,
      directionsQuery: rdo
        ? `BIR Revenue District Office ${rdo.code} Manila`
        : "BIR Revenue District Office Manila",
      // Each RDO covers its district, so it is listed with the district it serves.
      inDistrict: true,
    },
  ];
}

/** Whether a Mon-Fri 8:00-17:00 office is open right now, in Manila time. */
export function openStatus(now = new Date()): { open: boolean; label: string } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Manila",
    weekday: "short",
    hour: "numeric",
    minute: "numeric",
    hour12: false,
  }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  const day = get("weekday");
  const minutes = (Number(get("hour")) % 24) * 60 + Number(get("minute"));
  const weekday = !["Sat", "Sun"].includes(day);

  if (weekday && minutes >= 8 * 60 && minutes < 17 * 60) {
    return { open: true, label: "Open now · closes 5:00 PM" };
  }
  const opensToday = weekday && minutes < 8 * 60;
  const opensNext = opensToday ? "today" : day === "Fri" || day === "Sat" || day === "Sun" ? "Mon" : "tomorrow";
  return { open: false, label: `Closed · opens ${opensNext} 8:00 AM` };
}

export function directionsUrl(query: string) {
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(query)}`;
}
