import { Layers3 } from "lucide-react";
import { Link } from "react-router";

export default function Brand({ to = "/" }: { to?: string }) {
  return (
    <Link className="brand" to={to} aria-label="GeoMine home">
      <span className="brand-mark">
        <Layers3 size={22} strokeWidth={1.8} />
      </span>
      <span>
        geo<span className="brand-light">mine</span>
        <sup>®</sup>
      </span>
    </Link>
  );
}
