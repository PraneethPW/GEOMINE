import { useEffect, useState } from "react";
import { Loader2, MoveHorizontal } from "lucide-react";
import { API, accessToken } from "../api";
import type { Job } from "../api";

export default function EvidenceCompare({ job }: { job: Job }) {
  const [images, setImages] = useState<string[]>([]),
    [error, setError] = useState(""),
    [position, setPosition] = useState(50);
  useEffect(() => {
    const controller = new AbortController(),
      urls: string[] = [];
    const load = async () => {
      try {
        const output = await Promise.all(
          ["before", "after"].map(async (epoch) => {
            const response = await fetch(`${API}/api/jobs/${job.id}/imagery/${epoch}`, {
              headers: { Authorization: `Bearer ${await accessToken()}` },
              signal: controller.signal,
            });
            if (!response.ok)
              throw new Error(
                "Dated imagery could not be loaded. Retry provider access.",
              );
            const url = URL.createObjectURL(await response.blob());
            urls.push(url);
            return url;
          }),
        );
        if (!controller.signal.aborted) setImages(output);
      } catch (e) {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "Unable to load source imagery.");
      }
    };
    load();
    return () => {
      controller.abort();
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [job.id]);
  if (error) return <p className="form-error">{error}</p>;
  if (images.length !== 2)
    return (
      <div className="evidence-loading">
        <Loader2 className="spin" size={18} /> Reading dated Sentinel-2 evidence…
      </div>
    );
  const scenes =
    job.result?.scenes.filter((s) => s.collection === "sentinel-2-l2a") || [];
  return (
    <div className="evidence">
      <div className="evidence-viewport">
        <img
          src={images[1]}
          alt={`After Sentinel-2 acquisition ${scenes[1]?.datetime.slice(0, 10)}`}
          loading="lazy"
        />
        <img
          className="evidence-before"
          src={images[0]}
          style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}
          alt={`Before Sentinel-2 acquisition ${scenes[0]?.datetime.slice(0, 10)}`}
          loading="lazy"
        />
        <div className="evidence-divider" style={{ left: `${position}%` }}>
          <span>
            <MoveHorizontal size={18} />
          </span>
        </div>
        <span className="evidence-date before">
          BEFORE · {scenes[0]?.datetime.slice(0, 10)}
        </span>
        <span className="evidence-date after">
          AFTER · {scenes[1]?.datetime.slice(0, 10)}
        </span>
        <input
          type="range"
          min="0"
          max="100"
          value={position}
          onChange={(e) => setPosition(Number(e.target.value))}
          aria-label="Compare before and after Sentinel imagery"
        />
      </div>
      <p>
        Actual optical acquisitions on the same {job.result?.resolution_m ?? 10} m
        analysis grid. Drag to compare. A fixed reflectance stretch is used for both
        dates; clouds remain visible.
      </p>
    </div>
  );
}
