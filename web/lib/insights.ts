// Profile insights (ai/talnex_ai/coding/insights.py): each is a strength, neutral or worth a look. Evidence only:
// never part of any score, and "worth a look" is a question to ask, not a mark against anyone.
import type { Tone } from "@/lib/format";

const TONES: Record<string, { text: string; badge: Tone }> = {
  strength: { text: "Strength", badge: "success" },
  neutral: { text: "Neutral", badge: "neutral" },
  look: { text: "Worth a look", badge: "warning" },
};

export function insightTone(tone: unknown): { text: string; badge: Tone } {
  return TONES[String(tone)] ?? TONES.neutral;
}
