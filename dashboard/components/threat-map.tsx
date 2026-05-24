"use client";

import { useEffect, useState, useRef } from "react";
import { Radio } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// Coordinates on a 500x230 SVG canvas
const REGIONS: Record<
  string,
  { x: number; y: number; name: string; label: string; align: "start" | "end" | "middle" | "left" | "right" }
> = {
  NA: { x: 80, y: 65, name: "North America", label: "NA", align: "end" },
  SA: { x: 130, y: 175, name: "South America", label: "SA", align: "end" },
  EU: { x: 230, y: 50, name: "Europe", label: "EU", align: "middle" },
  AF: { x: 250, y: 150, name: "Africa", label: "AF", align: "start" },
  AS: { x: 390, y: 75, name: "Asia / Middle East", label: "AS", align: "start" },
  OC: { x: 420, y: 190, name: "Oceania", label: "OC", align: "start" },
  LO: { x: 250, y: 200, name: "Local Area / LAN", label: "Local", align: "middle" },
};

const CX = 250;
const CY = 105;

interface Particle {
  id: number;
  type: "block" | "pass";
  path: string;
}

interface Ripple {
  id: number;
  type: "block" | "pass";
}

interface RegionStats {
  blocks: number;
  passes: number;
  lastActive: number;
}

export function ThreatMap() {
  const [particles, setParticles] = useState<Particle[]>([]);
  const [ripples, setRipples] = useState<Ripple[]>([]);
  const [stats, setStats] = useState<Record<string, RegionStats>>({
    NA: { blocks: 0, passes: 0, lastActive: 0 },
    SA: { blocks: 0, passes: 0, lastActive: 0 },
    EU: { blocks: 0, passes: 0, lastActive: 0 },
    AF: { blocks: 0, passes: 0, lastActive: 0 },
    AS: { blocks: 0, passes: 0, lastActive: 0 },
    OC: { blocks: 0, passes: 0, lastActive: 0 },
    LO: { blocks: 0, passes: 0, lastActive: 0 },
  });
  const [hoveredRegion, setHoveredRegion] = useState<string | null>(null);
  const [, setTotalLivePackets] = useState(0);
  // Tick every 500ms so the "active in the last 4s" indicator updates
  // without calling impure Date.now() during render.
  const [now, setNow] = useState<number>(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, []);

  const particleIdCounter = useRef(0);
  const rippleIdCounter = useRef(0);

  // Helper to map country code to region
  const getRegion = (cc: string | null): string => {
    if (!cc) return "LO";
    const c = cc.toUpperCase();
    if (c === "LO" || c === "LAN" || c === "LOCAL" || c === "127") return "LO";

    const NorthAmerica = ["US", "CA", "MX", "PR", "GL"];
    const SouthAmerica = ["BR", "AR", "CL", "CO", "PE", "VE", "EC", "BO", "PY", "UY"];
    const Europe = [
      "GB", "DE", "FR", "IT", "ES", "NL", "PL", "SE", "NO", "FI", 
      "CH", "AT", "BE", "DK", "IE", "UA", "RU", "RO", "HU", "GR"
    ];
    const Oceania = ["AU", "NZ", "FJ", "PG"];
    const Africa = ["ZA", "NG", "KE", "EG", "DZ", "MA", "GH", "ET", "TZ", "UG", "SD", "AO"];

    if (NorthAmerica.includes(c)) return "NA";
    if (SouthAmerica.includes(c)) return "SA";
    if (Europe.includes(c)) return "EU";
    if (Oceania.includes(c)) return "OC";
    if (Africa.includes(c)) return "AF";
    return "AS"; // Default to Asia
  };

  useEffect(() => {
    const es = new EventSource("/api/alerts/stream");

    es.addEventListener("alert", (raw) => {
      try {
        const data = JSON.parse((raw as MessageEvent).data) as Record<string, unknown>;
        const type = data.type === "block" ? ("block" as const) : ("pass" as const);
        const cc = (data.country_code as string | null) ?? null;
        const regionKey = getRegion(cc);
        const region = REGIONS[regionKey] || REGIONS.LO;

        // 1. Trigger Particle
        const pid = ++particleIdCounter.current;
        const ctrlX = (region.x + CX) / 2;
        const ctrlY = Math.min(region.y, CY) - 30; // arc bend upwards
        const path = `M ${region.x} ${region.y} Q ${ctrlX} ${ctrlY} ${CX} ${CY}`;

        setParticles((prev) => [...prev, { id: pid, type, path }]);
        setTotalLivePackets((c) => c + 1);

        // Remove particle after animation duration (1.2s)
        setTimeout(() => {
          setParticles((prev) => prev.filter((p) => p.id !== pid));

          // 2. Trigger Ripple at Center Node on Arrival
          const rid = ++rippleIdCounter.current;
          setRipples((prev) => [...prev, { id: rid, type }]);
          setTimeout(() => {
            setRipples((prev) => prev.filter((r) => r.id !== rid));
          }, 1000);
        }, 1200);

        // 3. Update Region Stats
        setStats((prev) => {
          const current = prev[regionKey] || { blocks: 0, passes: 0, lastActive: 0 };
          return {
            ...prev,
            [regionKey]: {
              blocks: current.blocks + (type === "block" ? 1 : 0),
              passes: current.passes + (type === "pass" ? 1 : 0),
              lastActive: Date.now(),
            },
          };
        });
      } catch {
        // Ignore JSON errors
      }
    });

    return () => {
      es.close();
    };
  }, []);

  return (
    <Card className="relative overflow-hidden group">
      <style>{`
        @keyframes ping-ripple-red {
          0% { r: 4; opacity: 0.9; stroke-width: 2px; }
          100% { r: 35; opacity: 0; stroke-width: 0.5px; }
        }
        @keyframes ping-ripple-green {
          0% { r: 4; opacity: 0.9; stroke-width: 2px; }
          100% { r: 35; opacity: 0; stroke-width: 0.5px; }
        }
        .animate-ripple-red {
          animation: ping-ripple-red 1s cubic-bezier(0.1, 0.8, 0.3, 1) forwards;
          stroke: oklch(0.65 0.22 18);
        }
        .animate-ripple-green {
          animation: ping-ripple-green 1s cubic-bezier(0.1, 0.8, 0.3, 1) forwards;
          stroke: oklch(0.72 0.16 165);
        }
        @keyframes dash-flow {
          to { stroke-dashoffset: -20; }
        }
        .animate-dash-flow {
          stroke-dasharray: 4 6;
          animation: dash-flow 1.5s linear infinite;
        }
      `}</style>

      <CardHeader className="pb-1 flex flex-row items-center justify-between">
        <div>
          <CardTitle className="text-base flex items-center gap-2">
            <Radio className="h-4 w-4 text-emerald-400 animate-pulse" />
            Live Threat Vector Map
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Visualizing telemetry packets intercepted by Heimdall gateway.
          </p>
        </div>
        <div className="flex gap-4 text-[10px] uppercase font-mono tracking-wider">
          <span className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.6)]" />
            Block
          </span>
          <span className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(45,212,191,0.6)]" />
            Pass
          </span>
        </div>
      </CardHeader>

      <CardContent className="pt-2">
        <div className="grid grid-cols-1 xl:grid-cols-[1fr_200px] gap-4 items-center">
          {/* Map canvas */}
          <div className="relative border border-white/[0.04] bg-black/30 rounded-xl overflow-hidden flex justify-center p-2">
            <svg
              viewBox="0 0 500 230"
              className="w-full max-w-[500px] h-auto drop-shadow-lg select-none"
            >
              {/* Background grid */}
              <defs>
                <pattern id="grid-pattern" width="16" height="16" patternUnits="userSpaceOnUse">
                  <path d="M 16 0 L 0 0 0 16" fill="none" stroke="rgba(255,255,255,0.015)" strokeWidth="1" />
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#grid-pattern)" />

              {/* Ambient radial gradient behind central core */}
              <radialGradient id="center-glow" r="40%" cx="50%" cy="45%">
                <stop offset="0%" stopColor="oklch(0.68 0.18 245 / 0.12)" />
                <stop offset="100%" stopColor="transparent" />
              </radialGradient>
              <circle cx={CX} cy={CY} r={100} fill="url(#center-glow)" />

              {/* Threat Arcs / Connections */}
              {Object.entries(REGIONS).map(([key, reg]) => {
                if (key === "LO") return null;
                const isRegionActive = now - stats[key].lastActive < 4000;
                return (
                  <path
                    key={`arc-${key}`}
                    d={`M ${reg.x} ${reg.y} Q ${(reg.x + CX) / 2} ${Math.min(reg.y, CY) - 30} ${CX} ${CY}`}
                    fill="none"
                    stroke={
                      isRegionActive
                        ? "oklch(0.68 0.18 245 / 0.25)"
                        : "oklch(0.30 0.015 260 / 0.12)"
                    }
                    strokeWidth={isRegionActive ? 1.5 : 1}
                    className={cn(isRegionActive && "animate-dash-flow")}
                    style={{ transition: "stroke 500ms, stroke-width 500ms" }}
                  />
                );
              })}

              {/* Ripples at Center Gateway */}
              {ripples.map((rip) => (
                <circle
                  key={`ripple-${rip.id}`}
                  cx={CX}
                  cy={CY}
                  r={5}
                  fill="none"
                  className={cn(
                    rip.type === "block" ? "animate-ripple-red" : "animate-ripple-green"
                  )}
                />
              ))}

              {/* Animated Flying Particles */}
              {particles.map((p) => (
                <circle
                  key={`particle-${p.id}`}
                  r={p.type === "block" ? 4.5 : 3.5}
                  fill={
                    p.type === "block" 
                      ? "oklch(0.65 0.22 18)" 
                      : "oklch(0.72 0.16 165)"
                  }
                  className="drop-shadow"
                  style={{
                    filter: p.type === "block" 
                      ? "drop-shadow(0 0 6px oklch(0.65 0.22 18))" 
                      : "drop-shadow(0 0 6px oklch(0.72 0.16 165))"
                  }}
                >
                  <animateMotion path={p.path} dur="1.2s" repeatCount="1" fill="freeze" />
                </circle>
              ))}

              {/* Central Core Shield Node */}
              <g className="cursor-pointer">
                {/* External rotating dash ring */}
                <circle
                  cx={CX}
                  cy={CY}
                  r={22}
                  fill="none"
                  stroke="oklch(0.68 0.18 245 / 0.3)"
                  strokeWidth={1}
                  strokeDasharray="4 6"
                  className="animate-[spin_40s_linear_infinite]"
                />
                {/* Core back glow */}
                <circle
                  cx={CX}
                  cy={CY}
                  r={15}
                  fill="oklch(0.68 0.18 245 / 0.15)"
                  stroke="oklch(0.68 0.18 245 / 0.5)"
                  strokeWidth={1}
                />
                {/* Core inner node */}
                <circle
                  cx={CX}
                  cy={CY}
                  r={8}
                  fill="oklch(0.68 0.18 245)"
                  className="animate-pulse"
                />
              </g>

              {/* Regional Node Constellation */}
              {Object.entries(REGIONS).map(([key, reg]) => {
                const regStat = stats[key] || { blocks: 0, passes: 0, lastActive: 0 };
                const isRecentActive = now - regStat.lastActive < 4000;
                const hasBlocks = regStat.blocks > 0;

                return (
                  <g
                    key={`node-${key}`}
                    className="cursor-pointer group/node"
                    onMouseEnter={() => setHoveredRegion(key)}
                    onMouseLeave={() => setHoveredRegion(null)}
                  >
                    {/* Ring for active states */}
                    {isRecentActive && (
                      <circle
                        cx={reg.x}
                        cy={reg.y}
                        r={hasBlocks ? 10 : 8}
                        fill="none"
                        stroke={hasBlocks ? "oklch(0.65 0.22 18 / 0.5)" : "oklch(0.72 0.16 165 / 0.5)"}
                        strokeWidth={1}
                        className="animate-ping"
                      />
                    )}

                    {/* Outer node dot */}
                    <circle
                      cx={reg.x}
                      cy={reg.y}
                      r={hasBlocks ? 5 : 4}
                      fill={
                        hasBlocks 
                          ? "oklch(0.65 0.22 18)" 
                          : "oklch(0.72 0.16 165)"
                      }
                      className={cn(
                        "transition-all duration-300 group-hover/node:r-6 border border-black/40",
                        isRecentActive && "animate-pulse"
                      )}
                    />

                    {/* Regional Label */}
                    <text
                      x={reg.x}
                      y={reg.y + 16}
                      textAnchor="middle"
                      fontSize={8}
                      fontWeight={600}
                      fill={isRecentActive ? "oklch(0.97 0.005 250)" : "oklch(0.66 0.015 255)"}
                      fontFamily="var(--font-mono)"
                      className="opacity-70 group-hover/node:opacity-100"
                    >
                      {reg.label}
                    </text>
                  </g>
                );
              })}
            </svg>

            {/* Float details panel on map node hover */}
            {hoveredRegion && (
              <div 
                className="absolute top-2 left-2 px-3 py-2 rounded-lg glass-card border border-white/10 text-xs shadow-2xl fade-in-up"
                style={{ backdropFilter: "blur(8px)" }}
              >
                <div className="font-semibold text-foreground">
                  {REGIONS[hoveredRegion].name}
                </div>
                <div className="grid grid-cols-2 gap-x-4 mt-1 text-[10px] font-mono">
                  <span className="text-rose-400">Blocked:</span>
                  <span className="text-right text-rose-200">
                    {stats[hoveredRegion].blocks}
                  </span>
                  <span className="text-emerald-400">Passed:</span>
                  <span className="text-right text-emerald-200">
                    {stats[hoveredRegion].passes}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Region list & summary table */}
          <div className="space-y-2 border-t xl:border-t-0 xl:border-l border-white/[0.06] pt-4 xl:pt-0 xl:pl-4">
            <div className="text-[10px] uppercase font-mono tracking-wider text-muted-foreground">
              Regional Active Nodes
            </div>
            <div className="space-y-1.5 max-h-[160px] overflow-y-auto pr-1">
              {Object.entries(REGIONS).map(([key, reg]) => {
                const regStat = stats[key] || { blocks: 0, passes: 0 };
                const total = regStat.blocks + regStat.passes;
                const isHovered = hoveredRegion === key;
                return (
                  <div
                    key={`list-${key}`}
                    className={cn(
                      "flex items-center justify-between text-xs py-1 px-1.5 rounded transition-colors duration-150 cursor-pointer",
                      isHovered ? "bg-white/[0.04]" : "hover:bg-white/[0.02]"
                    )}
                    onMouseEnter={() => setHoveredRegion(key)}
                    onMouseLeave={() => setHoveredRegion(null)}
                  >
                    <span className="font-mono text-muted-foreground flex items-center gap-1.5">
                      <span
                        className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          regStat.blocks > 0 
                            ? "bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.6)]" 
                            : total > 0 
                              ? "bg-emerald-500" 
                              : "bg-muted-foreground/30"
                        )}
                      />
                      {reg.name}
                    </span>
                    <span className="font-mono tabular-nums text-muted-foreground text-[10px]">
                      <span className="text-rose-400/80">{regStat.blocks}</span>
                      {" / "}
                      <span className="text-emerald-400/80">{regStat.passes}</span>
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
