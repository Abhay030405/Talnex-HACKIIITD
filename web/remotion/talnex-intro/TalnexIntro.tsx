import { AbsoluteFill, Series } from "remotion";
import { C } from "./theme";
import { ColdOpen } from "./scenes/ColdOpen";
import { NobodyChecks } from "./scenes/NobodyChecks";
import { Enter } from "./scenes/Enter";
import { Strip, STRIP_DURATION } from "./scenes/Strip";
import { FairCheck, FAIR_DURATION } from "./scenes/FairCheck";
import { ProofCard, PROOF_DURATION } from "./scenes/ProofCard";
import { Close, CLOSE_DURATION } from "./scenes/Close";

export const SCENES = [
  { name: "Cold open", duration: 80, Component: ColdOpen },
  { name: "Nobody checks", duration: 90, Component: NobodyChecks },
  { name: "TalNex enters", duration: 150, Component: Enter },
  { name: "Film strip", duration: STRIP_DURATION, Component: Strip },
  { name: "Fair check", duration: FAIR_DURATION, Component: FairCheck },
  { name: "Proof card", duration: PROOF_DURATION, Component: ProofCard },
  { name: "Close", duration: CLOSE_DURATION, Component: Close },
];

export const TOTAL_DURATION = SCENES.reduce((a, s) => a + s.duration, 0);

export const TalnexIntro: React.FC = () => (
  <AbsoluteFill style={{ background: C.paper }}>
    <Series>
      {SCENES.map(({ name, duration, Component }) => (
        <Series.Sequence key={name} name={name} durationInFrames={duration}>
          <Component />
        </Series.Sequence>
      ))}
    </Series>
  </AbsoluteFill>
);
