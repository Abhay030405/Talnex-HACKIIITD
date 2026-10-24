// The site's icons, from Lucide (lucide-react). Every page imports them from here under these names, so one swap here
// changes them everywhere. They take the colour of the text around them and are hidden from screen readers: the words
// next to them carry the meaning.
import {
  ArrowLeft,
  ArrowRight,
  Briefcase,
  CalendarDays,
  LogOut,
  Magnet,
  Plus,
  ShieldCheck,
  Trophy,
  Users,
  type LucideIcon,
} from "lucide-react";

type IconProps = { size?: number };

function wrap(Glyph: LucideIcon) {
  function Icon({ size = 20 }: IconProps) {
    return <Glyph size={size} strokeWidth={1.75} aria-hidden="true" focusable="false" />;
  }
  return Icon;
}

export const TrophyIcon = wrap(Trophy);
export const BriefcaseIcon = wrap(Briefcase);
export const ShieldIcon = wrap(ShieldCheck);
export const ArrowIcon = wrap(ArrowRight);
export const BackIcon = wrap(ArrowLeft);
export const PlusIcon = wrap(Plus);
export const UsersIcon = wrap(Users);
export const CalendarIcon = wrap(CalendarDays);
export const LogoutIcon = wrap(LogOut);
export const MagnetIcon = wrap(Magnet);
