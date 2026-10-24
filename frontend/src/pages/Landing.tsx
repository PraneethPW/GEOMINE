import { lazy, Suspense, useState } from "react";
import { motion, useReducedMotion, useScroll, useSpring } from "framer-motion";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Fingerprint,
  Orbit,
  Radio,
  Pause,
  Play,
} from "lucide-react";
import { Link } from "react-router";
import Brand from "../components/Brand";

const Globe = lazy(() => import("../components/Globe"));

export default function Landing() {
  const reduced = useReducedMotion();
  const [paused, setPaused] = useState(false);
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 100, damping: 30 });
  const reveal = {
    initial: { opacity: 0, y: reduced ? 0 : 24 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, amount: 0.2 },
    transition: { duration: reduced || paused ? 0 : 0.7 },
  };
  return (
    <div className={`landing ${paused ? "motion-paused" : ""}`}>
      <motion.div className="scroll-progress" style={{ scaleX }} />
      <a className="skip-link" href="#earth-story">
        Skip introduction
      </a>
      <header className="header public-header">
        <Brand />
        <nav aria-label="Public navigation">
          <a href="#earth-story">Perspective</a>
          <a href="#evidence-story">The approach</a>
          <Link to="/login">
            Log in <ArrowUpRight size={14} />
          </Link>
          <Link to="/signup" className="button primary small">
            Get started <ArrowRight size={15} />
          </Link>
          <button
            className="icon-button"
            aria-label={paused ? "Resume decorative motion" : "Pause decorative motion"}
            aria-pressed={paused}
            onClick={() => setPaused((value) => !value)}
          >
            {paused ? <Play size={16} /> : <Pause size={16} />}
          </button>
        </nav>
      </header>
      <main>
        <section className="hero">
          <div className="hero-grid" />
          <div className="hero-copy">
            <motion.div {...reveal} className="hero-tag">
              <span className="live-dot" /> GEOMINE-XNET{" "}
              <span className="tag-divider" /> ENVIRONMENTAL OBSERVATORY
            </motion.div>
            <motion.h1 {...reveal}>
              A clearer view.
              <br />A living <span>planet.</span>
            </motion.h1>
            <motion.p {...reveal}>
              See beyond the surface. Bring radar, optical imagery,
              <br className="desktop-break" /> and geospatial evidence into one field of
              view.
            </motion.p>
            <motion.div {...reveal} className="hero-buttons">
              <Link className="button primary" to="/signup">
                Start your observatory <ArrowUpRight size={16} />
              </Link>
              <a className="button text-button" href="#earth-story">
                A different perspective <ArrowDown size={15} />
              </a>
            </motion.div>
            <motion.div {...reveal} className="hero-spec">
              <span>
                <Orbit size={14} /> SENTINEL-1 + 2
              </span>
              <span>
                <Fingerprint size={14} /> EVIDENCE FIRST
              </span>
              <span>
                <Radio size={14} /> ACQUISITION DRIVEN
              </span>
            </motion.div>
          </div>
          <div className="hero-earth">
            <div className="earth-glow" />
            <Suspense fallback={<div className="globe-fallback" />}>
              <Globe paused={paused} />
            </Suspense>
            <div className="orbital-label">
              <span className="live-dot" /> MULTIMODAL OBSERVATION{" "}
              <small>OPTICAL × SYNTHETIC APERTURE RADAR</small>
            </div>
            <span className="earth-coordinate top">06° 03′ 00″ N</span>
            <span className="earth-coordinate bottom">
              OBSERVE. UNDERSTAND. PROTECT.
            </span>
          </div>
          <div className="hero-bottom">
            <span>01 / A CHANGE IN PERSPECTIVE</span>
            <span>
              The story continues below. <ArrowDown size={13} />
            </span>
          </div>
        </section>

        <section
          id="earth-story"
          className="earth-story editorial-section"
          tabIndex={-1}
        >
          <motion.div {...reveal} className="editorial-index">
            <span>01 / THE SURFACE NEVER STANDS STILL</span>
            <span>EARTH, OBSERVED.</span>
          </motion.div>
          <div className="editorial-split">
            <motion.h2 {...reveal}>
              Change leaves
              <br />a trace.
              <br />
              <span>Look closer.</span>
            </motion.h2>
            <motion.div {...reveal} className="editorial-copy">
              <p>
                Forests thin. Riverbanks shift. Land is opened, worked, and reshaped.
                From the ground, the wider pattern can be difficult to see.
              </p>
              <p>
                GeoMine brings another perspective: repeated satellite observations,
                connected across time, with the evidence behind every change kept in
                view.
              </p>
              <span className="editorial-caption">
                A place. Two moments. More context.
              </span>
            </motion.div>
          </div>
          <div className="terrain-ribbon" aria-hidden="true">
            <svg viewBox="0 0 1200 280" preserveAspectRatio="none">
              {Array.from({ length: 18 }, (_, i) => (
                <path
                  key={i}
                  d={`M -80 ${90 + i * 10} C 180 ${-120 + i * 13}, 260 ${390 - i * 5}, 530 ${120 + i * 8} S 840 ${20 + i * 10}, 1280 ${150 + i * 7}`}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={i % 5 === 0 ? 1.3 : 0.5}
                />
              ))}
            </svg>
            <span>THE LAND HOLDS THE STORY.</span>
          </div>
        </section>

        <section id="evidence-story" className="evidence-story editorial-section">
          <div className="editorial-index">
            <span>02 / TWO SIGNALS, A WIDER PICTURE</span>
            <span>OPTICAL × RADAR</span>
          </div>
          <div className="signal-story">
            <motion.div {...reveal} className="signal-illustration" aria-hidden="true">
              <div className="signal-orbit orbit-a" />
              <div className="signal-orbit orbit-b" />
              <div className="signal-core">
                <Orbit size={72} strokeWidth={0.8} />
              </div>
              <div className="signal-wave wave-a" />
              <div className="signal-wave wave-b" />
              <span className="signal-label optical-label">REFLECTED LIGHT</span>
              <span className="signal-label radar-label">SURFACE BACKSCATTER</span>
            </motion.div>
            <motion.div {...reveal} className="editorial-copy">
              <h2>
                One landscape.
                <br />
                <span>Different ways to see.</span>
              </h2>
              <p>
                Optical imagery reveals vegetation and visible land cover. Radar adds a
                different signal, responding to the structure and properties of the
                surface.
              </p>
              <p>
                Read together, these observations help surface changes worth
                investigating. Human review gives that evidence its meaning.
              </p>
              <div className="editorial-rule">
                <span>OBSERVE</span>
                <ArrowRight size={17} />
                <span>COMPARE</span>
                <ArrowRight size={17} />
                <span>UNDERSTAND</span>
              </div>
            </motion.div>
          </div>
        </section>

        <section className="source-statement editorial-section">
          <div className="editorial-index">
            <span>03 / EVIDENCE BEFORE ASSUMPTION</span>
            <Fingerprint size={22} />
          </div>
          <motion.h2 {...reveal}>
            The observation matters.
            <br />
            <span>So does where it came from.</span>
          </motion.h2>
          <div className="source-bottom">
            <p>
              Built around dated Sentinel acquisitions, traceable processing, and the
              boundaries you supply. Observed disturbance invites investigation; it does
              not establish illegal mining.
            </p>
            <div>
              <a
                href="https://www.esa.int/Applications/Observing_the_Earth/Copernicus"
                target="_blank"
                rel="noreferrer"
              >
                ESA / Copernicus <ArrowUpRight size={13} />
              </a>
              <a
                href="https://docs.digitalearthafrica.org/en/latest/data_specs/Sentinel-1_specs.html"
                target="_blank"
                rel="noreferrer"
              >
                Digital Earth Africa <ArrowUpRight size={13} />
              </a>
              <small>
                The public radar source covers Africa. New observations follow satellite
                revisits and data availability.
              </small>
            </div>
          </div>
        </section>

        <section className="landing-invitation editorial-section">
          <motion.span {...reveal} className="eyebrow">
            YOUR CORNER OF A CHANGING PLANET
          </motion.span>
          <motion.h2 {...reveal}>
            Bring it
            <br />
            into <span>focus.</span>
          </motion.h2>
          <motion.div {...reveal}>
            <Link to="/signup" className="button primary">
              Create your workspace <ArrowUpRight size={18} />
            </Link>
            <p>
              Already observing?{" "}
              <Link to="/login">
                Log in <ArrowRight size={13} />
              </Link>
            </p>
          </motion.div>
          <div className="invitation-orbit" aria-hidden="true" />
        </section>
      </main>
      <footer className="public-footer">
        <Brand />
        <span>Earth intelligence. Human perspective.</span>
        <span>GEOMINE-XNET / OBSERVATORY</span>
      </footer>
    </div>
  );
}
