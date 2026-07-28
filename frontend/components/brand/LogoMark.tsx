/**
 * LogoMark — the Vednix sigil: THE NEURAL V. Three golden nodes (two top
 * corners, one bottom vertex) joined by synapse lines, signal pulses riding
 * those lines forever while the nodes breathe. Chosen by the founder over
 * every alphabet-bound mark — an AI constellation, not a letter.
 *
 * Motion is SMIL + gradient, deliberately: zero JS, zero hydration cost —
 * it animates in server components, loading screens and the boot gate alike.
 */
import { cn } from "@/lib/utils";

const NODES: [number, number, number][] = [
  [13, 13, 0],   // top-left
  [35, 13, 0.8], // top-right
  [24, 35, 1.6], // bottom vertex
];

const PATH_L = "M13,13 C17,20 20.5,27.5 24,35";
const PATH_R = "M35,13 C31,20 27.5,27.5 24,35";

export function LogoMark({
  size = 32,
  tile = true,
  className,
}: {
  size?: number;
  /** render within the glass squircle (true) or bare (false) */
  tile?: boolean;
  className?: string;
}) {
  const inner = Math.max(12, Math.round(size * (tile ? 0.68 : 1)));
  return (
    <span
      role="img"
      aria-label="Vednix — the neural V"
      className={cn(
        "inline-flex shrink-0 items-center justify-center",
        tile &&
          "rounded-[10px] border border-gold/40 bg-gradient-to-br from-gold/20 to-ember/10 shadow-glow-gold",
        className,
      )}
      style={tile ? { width: size, height: size } : { width: inner, height: inner }}
    >
      <svg viewBox="0 0 48 48" width={inner} height={inner} fill="none" aria-hidden>
        <defs>
          <linearGradient id="vn-stroke" x1="8" y1="8" x2="40" y2="40" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#f4d68a" />
            <stop offset="1" stopColor="#d9a83f" />
          </linearGradient>
          <radialGradient id="vn-glow">
            <stop offset="0" stopColor="#f4d68a" stopOpacity="0.85" />
            <stop offset="1" stopColor="#f4d68a" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* the synapse V */}
        <path d={PATH_L} stroke="url(#vn-stroke)" strokeWidth="2" strokeLinecap="round" />
        <path d={PATH_R} stroke="url(#vn-stroke)" strokeWidth="2" strokeLinecap="round" />
        {/* constellation echoes — the double-line energy of the concept */}
        <path d="M13,13 C18.8,21.5 21.2,28 24,35" stroke="#f4d68a" strokeWidth="0.7" opacity="0.22" />
        <path d="M35,13 C29.2,21.5 26.8,28 24,35" stroke="#f4d68a" strokeWidth="0.7" opacity="0.22" />

        {/* signal pulses riding the lines (phase-shifted riders) */}
        <circle r="1.7" fill="#ffe9b0">
          <animateMotion dur="2.2s" repeatCount="indefinite" path={PATH_L} />
        </circle>
        <circle r="1.7" fill="#ffe9b0" opacity="0.85">
          <animateMotion dur="2.2s" begin="-1.1s" repeatCount="indefinite" path={PATH_R} />
        </circle>

        {/* breathing nodes */}
        {NODES.map(([cx, cy, begin]) => (
          <g key={`${cx}-${cy}`}>
            <circle cx={cx} cy={cy} r="7" fill="url(#vn-glow)">
              <animate attributeName="opacity" values="0.4;1;0.4" dur="2.4s" begin={`${begin}s`} repeatCount="indefinite" />
            </circle>
            <circle cx={cx} cy={cy} r="2.7" fill="#f4d68a" stroke="#fff3d6" strokeWidth="0.6">
              <animate attributeName="r" values="2.4;3.1;2.4" dur="2.4s" begin={`${begin}s`} repeatCount="indefinite" />
            </circle>
          </g>
        ))}
      </svg>
    </span>
  );
}
