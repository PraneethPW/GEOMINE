import { Suspense, useRef, useMemo, useState, useEffect, Component } from "react";
import type { ReactNode } from "react";
import { Canvas, useFrame, useLoader } from "@react-three/fiber";
import { TextureLoader, AdditiveBlending, BackSide, Group, Color } from "three";
import { useReducedMotion } from "framer-motion";

class SceneBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? <div className="globe-fallback" /> : this.props.children;
  }
}
function Earth() {
  const group = useRef<Group>(null);
  const reduced = useReducedMotion();
  const texture = useLoader(TextureLoader, "/earth.jpg");
  const [hovered, setHovered] = useState(false);
  const points = useMemo(() => {
    const list: number[] = [];
    for (let i = 0; i < 750; i++) {
      const phi = Math.acos(-1 + (2 * i) / 750);
      const theta = Math.sqrt(750 * Math.PI) * phi;
      list.push(
        2.35 * Math.cos(theta) * Math.sin(phi),
        2.35 * Math.sin(theta) * Math.sin(phi),
        2.35 * Math.cos(phi),
      );
    }
    return new Float32Array(list);
  }, []);
  useFrame((_, dt) => {
    if (group.current && !reduced)
      group.current.rotation.y += Math.min(dt, 0.05) * (hovered ? 0.025 : 0.055);
  });
  return (
    <group
      ref={group}
      rotation={[0.18, -0.7, 0.16]}
      onPointerOver={() => setHovered(true)}
      onPointerOut={() => setHovered(false)}
    >
      <mesh>
        <sphereGeometry args={[1.8, 80, 80]} />
        <meshStandardMaterial
          map={texture}
          roughness={0.95}
          metalness={0.05}
          color="#b6c3b1"
        />
      </mesh>
      <mesh scale={1.022}>
        <sphereGeometry args={[1.8, 48, 48]} />
        <shaderMaterial
          side={BackSide}
          transparent
          blending={AdditiveBlending}
          uniforms={{ glowColor: { value: new Color("#a3f5b5") } }}
          vertexShader={
            "varying vec3 n; varying vec3 p; void main(){n=normalize(normalMatrix*normal); vec4 mv=modelViewMatrix*vec4(position,1.0); p=normalize(-mv.xyz); gl_Position=projectionMatrix*mv;}"
          }
          fragmentShader={
            "uniform vec3 glowColor; varying vec3 n; varying vec3 p; void main(){float a=pow(1.0-abs(dot(n,p)),3.0); gl_FragColor=vec4(glowColor,a*.45);}"
          }
        />
      </mesh>
      {[0, 1, 2].map((i) => (
        <mesh key={i} rotation={[Math.PI / 2 + i * 0.35, i * 0.6, 0.3]}>
          <torusGeometry args={[2.15 + i * 0.09, 0.002, 4, 180]} />
          <meshBasicMaterial color="#b4f36d" transparent opacity={0.2} />
        </mesh>
      ))}
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[points, 3]} />
        </bufferGeometry>
        <pointsMaterial size={0.008} color="#c6e5c1" transparent opacity={0.45} />
      </points>
    </group>
  );
}
export default function Globe({ paused = false }: { paused?: boolean }) {
  const container = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    let intersecting = false;
    const update = () =>
      setVisible(intersecting && document.visibilityState !== "hidden");
    const observer = new IntersectionObserver(
      ([entry]) => {
        intersecting = entry.isIntersecting;
        update();
      },
      { rootMargin: "100px" },
    );
    if (container.current) observer.observe(container.current);
    document.addEventListener("visibilitychange", update);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", update);
    };
  }, []);
  return (
    <div ref={container} className="globe-canvas-container">
      <SceneBoundary>
        <Canvas
          camera={{ position: [0, 0, 6.5], fov: 42 }}
          dpr={[1, 1.5]}
          frameloop={!visible ? "never" : paused || reduced ? "demand" : "always"}
          gl={{ alpha: true, antialias: true, powerPreference: "low-power" }}
          aria-label="Decorative rotating Earth. Satellite observations are available inside your workspace."
        >
          <ambientLight intensity={0.3} />
          <directionalLight position={[4, 3, 5]} intensity={2} />
          <directionalLight position={[-3, -1, 1]} color="#7eaa82" intensity={0.35} />
          <Suspense fallback={null}>
            <Earth />
          </Suspense>
        </Canvas>
      </SceneBoundary>
    </div>
  );
}
