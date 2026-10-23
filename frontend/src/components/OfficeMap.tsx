"use client";

import { useEffect, useRef } from "react";
import type { Map as LeafletMap, Marker } from "leaflet";
import "leaflet/dist/leaflet.css";
import { openStatus, type Office } from "@/data/offices";

/** Landmark icon (lucide "landmark"), inlined so pins need no image files. */
const LANDMARK_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 18v-7"/><path d="M11.12 2.198a2 2 0 0 1 1.76.006l7.866 3.847c.476.233.31.949-.22.949H3.474c-.53 0-.695-.716-.22-.949z"/><path d="M14 18v-7"/><path d="M18 18v-7"/><path d="M3 22h18"/><path d="M6 18v-7"/></svg>`;

function pinHtml(office: Office, selected: boolean) {
  return `
    <div class="nc-pin ${selected ? "nc-pin--selected" : ""} ${office.approximate ? "nc-pin--approx" : ""}">
      <span class="nc-pin__head">${LANDMARK_SVG}</span>
    </div>`;
}

function popupHtml(office: Office) {
  const status = openStatus();
  return `
    <p class="nc-popup__name">${office.pinLabel}</p>
    <p class="nc-popup__sub">${office.name.split(" · ")[1] ?? office.stageLabel}</p>
    <p class="nc-popup__status ${status.open ? "is-open" : "is-closed"}">${status.label}</p>
    ${office.approximate ? `<p class="nc-popup__approx">Approximate location</p>` : ""}`;
}

export function OfficeMap({
  offices,
  selectedId,
  onSelect,
}: {
  offices: Office[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null);
  const markers = useRef<Map<string, Marker>>(new Map());
  const leaflet = useRef<typeof import("leaflet") | null>(null);

  const pinned = offices.filter((o) => o.position);

  // Build the map once. Leaflet touches `window`, so it is imported here
  // rather than at module load, which would break server rendering.
  useEffect(() => {
    let cancelled = false;
    const pins = markers.current;
    (async () => {
      const L = await import("leaflet");
      if (cancelled || !container.current || map.current) return;
      leaflet.current = L;

      const m = L.map(container.current, { zoomControl: true, scrollWheelZoom: false });
      // OpenStreetMap's own tiles: free with no API key, attribution required.
      // Fine for a prototype; heavy production traffic needs a tile provider
      // (see https://operations.osmfoundation.org/policies/tiles/).
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19,
        className: "nc-tiles",
      }).addTo(m);

      for (const office of pinned) {
        const marker = L.marker(office.position!, {
          icon: L.divIcon({ html: pinHtml(office, false), className: "", iconSize: [44, 52], iconAnchor: [22, 50] }),
          title: office.name,
          keyboard: true,
        })
          .addTo(m)
          .bindTooltip(office.approximate ? `≈ ${office.pinLabel}` : office.pinLabel, {
            permanent: true,
            direction: "bottom",
            offset: [0, 4],
            className: "nc-label",
          })
          .bindPopup(popupHtml(office), { className: "nc-popup", offset: [0, -40], closeButton: false })
          .on("click", () => onSelect(office.id));
        markers.current.set(office.id, marker);
      }

      m.fitBounds(L.latLngBounds(pinned.map((o) => o.position!)), { padding: [70, 70], maxZoom: 15 });
      map.current = m;
      markers.current.get(selectedId)?.openPopup();
    })();

    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
      pins.clear();
    };
    // Offices change only when the district does, which remounts this map.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Restyle the selected pin and fly to it.
  useEffect(() => {
    const L = leaflet.current;
    if (!L || !map.current) return;
    for (const office of offices.filter((o) => o.position)) {
      const marker = markers.current.get(office.id);
      if (!marker) continue;
      const selected = office.id === selectedId;
      marker.setIcon(L.divIcon({ html: pinHtml(office, selected), className: "", iconSize: [44, 52], iconAnchor: [22, 50] }));
      marker.setZIndexOffset(selected ? 1000 : 0);
      if (selected) {
        marker.openPopup();
        map.current.panTo(office.position!, { animate: true });
      }
    }
  }, [selectedId, offices]);

  return <div ref={container} className="size-full" aria-label="Map of offices to visit" />;
}
