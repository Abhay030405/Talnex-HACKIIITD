import { HeroFilm } from "@/components/landing/HeroFilm";
import { ButtonLink } from "@/components/ui/Button";
import { MagnetIcon } from "@/components/ui/Icons";
import { Magnetic } from "@/components/ui/Magnetic";

export function Hero() {
  return (
    <section className="hero-sheet">
      <div className="wrap hero-sheet__copy">
        <div className="hero-sheet__main">
          <h1 className="hero-sheet__title">“It works,” says the README.</h1>
          {/* Signed-out visitors start at sign-in; the link they paste is not sent anywhere (the input has no name). */}
          <form className="hero-sheet__paste" action="/login">
            <label className="hero-sheet__paste-label" htmlFor="hero-project">
              Paste a project
            </label>
            <div className="hero-sheet__paste-row">
              <input
                id="hero-project"
                className="input hero-sheet__paste-input"
                type="url"
                inputMode="url"
                placeholder="https://your-project.app"
                autoComplete="off"
              />
              <Magnetic>
                <button type="submit" className="btn btn--primary btn--lg">
                  <MagnetIcon size={16} />
                  Check project
                </button>
              </Magnetic>
            </div>
            <ButtonLink href="#proof" variant="ghost">
              See a sample result
            </ButtonLink>
          </form>
        </div>
        <div className="hero-sheet__film">
          <HeroFilm />
        </div>
      </div>
    </section>
  );
}
