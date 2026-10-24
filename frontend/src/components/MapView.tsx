import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
maplibregl.setWorkerUrl(workerUrl);
import type { Map as MapInstance, GeoJSONSource } from "maplibre-gl";
import {
  Crosshair,
  Layers3,
  Maximize2,
  MapPin,
  Minus,
  Plus,
} from "lucide-react";
import type { Area, Alert, Scene, Geometry } from "../api";
import { center, rectangle } from "../api";
import "maplibre-gl/dist/maplibre-gl.css";
type Props = {
  areas: Area[];
  alerts: Alert[];
  scenes: Scene[];
  selected: Area | null;
  onSelect: (area: Area) => void;
  onDraw: (geometry: Geometry) => void;
  onAlert: (alert: Alert) => void;
};
function features(
  items: { id: string; geometry: Geometry; name?: string; status?: string }[],
) {
  return {
    type: "FeatureCollection" as const,
    features: items.map((i) => ({
      type: "Feature" as const,
      id: i.id,
      geometry: i.geometry,
      properties: { id: i.id, name: i.name || "", status: i.status || "" },
    })),
  };
}
export default function MapView({
  areas,
  alerts,
  scenes,
  selected,
  onSelect,
  onDraw,
  onAlert,
}: Props) {
  const container = useRef<HTMLDivElement>(null),
    map = useRef<MapInstance | null>(null);
  const [loaded, setLoaded] = useState(false),
    [satellite, setSatellite] = useState(true),
    [drawing, setDrawing] = useState(false),
    [error, setError] = useState("");
  const latest = useRef({ areas, alerts, onSelect, onDraw, onAlert, drawing });
  latest.current = { areas, alerts, onSelect, onDraw, onAlert, drawing };
  useEffect(() => {
    if (!container.current) return;
    const m = new maplibregl.Map({
      container: container.current,
      center: [-1.93, 6.05],
      zoom: 8,
      pitch: 28,
      maxPitch: 60,
      attributionControl: { compact: true },
      style: {
        version: 8,
        sources: {
          satellite: {
            type: "raster",
            tiles: [
              "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            ],
            tileSize: 256,
            attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
          },
          dark: {
            type: "raster",
            tiles: ["https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors © CARTO",
          },
        },
        layers: [
          { id: "dark", type: "raster", source: "dark" },
          {
            id: "satellite",
            type: "raster",
            source: "satellite",
            paint: {
              "raster-saturation": -0.25,
              "raster-brightness-max": 0.72,
            },
          },
        ],
      },
    });
    map.current = m;
    const resize = new ResizeObserver(() => m.resize());
    resize.observe(container.current);
    m.on("load", () => {
      for (const name of ["areas", "alerts", "scenes"])
        m.addSource(name, {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
      m.addLayer({
        id: "scene-fill",
        type: "fill",
        source: "scenes",
        paint: { "fill-color": "#99c8f4", "fill-opacity": 0.035 },
      });
      m.addLayer({
        id: "scene-line",
        type: "line",
        source: "scenes",
        paint: {
          "line-color": "#99c8f4",
          "line-width": 1,
          "line-opacity": 0.4,
          "line-dasharray": [3, 3],
        },
      });
      m.addLayer({
        id: "area-fill",
        type: "fill",
        source: "areas",
        paint: { "fill-color": "#b4f36d", "fill-opacity": 0.12 },
      });
      m.addLayer({
        id: "area-line",
        type: "line",
        source: "areas",
        paint: { "line-color": "#b4f36d", "line-width": 2 },
      });
      m.addLayer({
        id: "alert-fill",
        type: "fill",
        source: "alerts",
        paint: {
          "fill-color": [
            "match",
            ["get", "status"],
            "dismissed",
            "#8c9d97",
            "confirmed",
            "#ee745b",
            "#f3bb66",
          ],
          "fill-opacity": 0.5,
        },
      });
      m.addLayer({
        id: "alert-line",
        type: "line",
        source: "alerts",
        paint: { "line-color": "#f3bb66", "line-width": 1.5 },
      });
      setLoaded(true);
    });
    m.on("click", (e) => {
      if (latest.current.drawing) {
        latest.current.onDraw(rectangle(e.lngLat.lng, e.lngLat.lat));
        setDrawing(false);
        return;
      }
      if (!m.getLayer("alert-fill")) return;
      const candidates = m.queryRenderedFeatures(e.point, {
        layers: ["alert-fill"],
      });
      if (candidates.length) {
        const item = latest.current.alerts.find(
          (a) => a.id === candidates[0].properties?.id,
        );
        if (item) latest.current.onAlert(item);
        return;
      }
      const found = m.queryRenderedFeatures(e.point, { layers: ["area-fill"] });
      if (found.length) {
        const area = latest.current.areas.find(
          (a) => a.id === found[0].properties?.id,
        );
        if (area) latest.current.onSelect(area);
      }
    });
    m.on("error", () =>
      setError("Some map tiles could not load. Check your connection."),
    );
    return () => {
      resize.disconnect();
      m.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    if (!loaded || !map.current) return;
    (map.current.getSource("areas") as GeoJSONSource).setData(features(areas));
    (map.current.getSource("alerts") as GeoJSONSource).setData(
      features(alerts),
    );
    (map.current.getSource("scenes") as GeoJSONSource).setData(
      features(scenes),
    );
  }, [loaded, areas, alerts, scenes]);
  useEffect(() => {
    if (loaded && selected && map.current) {
      const [lon, lat] = center(selected.geometry);
      map.current.flyTo({
        center: [lon, lat],
        zoom: 12,
        pitch: 25,
        duration: 1000,
        essential: false,
      });
    }
  }, [selected, loaded]);
  useEffect(() => {
    if (loaded && map.current)
      map.current.setLayoutProperty(
        "satellite",
        "visibility",
        satellite ? "visible" : "none",
      );
  }, [satellite, loaded]);
  useEffect(() => {
    if (map.current)
      map.current.getCanvas().style.cursor = drawing ? "crosshair" : "";
  }, [drawing]);
  return (
    <div className="map-shell">
      <div ref={container} className="map-canvas" />
      <div className="map-top">
        <span className="map-label">
          <span className="live-dot" /> EXPLORER{" "}
          <span className="muted">
            / {selected?.name || "Ghana · 6.05° N, 1.93° W"}
          </span>
        </span>
        <span className="map-basemap">REFERENCE BASEMAP</span>
      </div>
      <div className="map-controls">
        <button title="Zoom in" onClick={() => map.current?.zoomIn()}>
          <Plus size={17} />
        </button>
        <button title="Zoom out" onClick={() => map.current?.zoomOut()}>
          <Minus size={17} />
        </button>
        <span />
        <button title="Switch basemap" onClick={() => setSatellite(!satellite)}>
          <Layers3 size={17} />
        </button>
        <button
          title="Return to selected area"
          onClick={() =>
            map.current?.flyTo({
              center: selected ? center(selected.geometry) : [-1.93, 6.05],
              zoom: selected ? 12 : 8,
            })
          }
        >
          <Crosshair size={17} />
        </button>
        <button
          title="Expand map"
          onClick={() => {
            if (!document.fullscreenElement)
              container.current?.parentElement?.requestFullscreen();
            else document.exitFullscreen();
          }}
        >
          <Maximize2 size={16} />
        </button>
      </div>
      <button
        className={`draw-control ${drawing ? "active" : ""}`}
        onClick={() => setDrawing(!drawing)}
      >
        <MapPin size={15} />
        {drawing ? "Click map to place a study box" : "Define study area"}
      </button>
      <div className="map-legend">
        <span>
          <i className="lime" />
          Study area
        </span>
        <span>
          <i className="amber" />
          Change candidate
        </span>
        <span>
          <i className="blue" />
          Scene footprint
        </span>
      </div>
      {error && (
        <button className="map-error" onClick={() => setError("")}>
          {error} ×
        </button>
      )}
    </div>
  );
}
