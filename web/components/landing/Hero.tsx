import { HeroFilm } from "@/components/landing/HeroFilm";
import { ButtonLink } from "@/components/ui/Button";

export function Hero() {
  return (
    <section className="hero-sheet">
      <div className="wrap hero-sheet__copy">
        <h1 className="hero-sheet__title">“It works,” says the README.</h1>
        <div className="hero-sheet__side">
          <p className="hero-sheet__lead">
            Paste a project link. An agent opens it, uses it like a real person and keeps a screenshot of every step, so
            organizers and recruiters get proof of what works, not a promise.
          </p>
          <div className="hero-sheet__actions">
            <ButtonLink href="/login" variant="primary" size="lg" magnetic>
              Check a project
            </ButtonLink>
            <ButtonLink href="#proof" variant="secondary" size="lg">
              See a sample result
            </ButtonLink>
          </div>
        </div>
      </div>
      <div className="wrap">
        <HeroFilm />
      </div>
    </section>
  );
}
