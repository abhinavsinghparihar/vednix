/**
 * Vednix AI — landing identity ("The Living Core").
 * Synthesized from the studio-hero genre (cinematic dark, staggered type,
 * floating glass) but owned end-to-end: the centerpiece is the actual
 * 8-state Vednix Orb performing live, not a stock video. The workspace
 * itself lives at /chat.
 * Layers: neural background · mouse glow · floating nav · hero (manifesto +
 * Living Core) · capabilities · enter · footer.
 */

import { NeuralBackground } from "@/components/background/NeuralBackground";
import { MouseGlow } from "@/components/background/MouseGlow";
import { LandingNav } from "@/components/landing/LandingNav";
import { Hero } from "@/components/landing/Hero";
import { Capabilities } from "@/components/landing/Capabilities";
import { EnterSection } from "@/components/landing/EnterSection";
import { LandingFooter } from "@/components/landing/LandingFooter";

export default function LandingPage() {
  return (
    <main className="relative min-h-dvh w-full overflow-x-clip bg-void text-cream">
      <NeuralBackground />
      <MouseGlow />
      <LandingNav />
      <Hero />
      <Capabilities />
      <EnterSection />
      <LandingFooter />
    </main>
  );
}
