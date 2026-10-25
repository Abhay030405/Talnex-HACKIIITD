import { VerdictBadge } from "@/components/ui/VerdictBadge";

// What actually happens to one project, in order. Each step shows the thing TalNex really produces at that point.
export function Process() {
  return (
    <section className="process wrap" id="how" aria-labelledby="how-title">
      <h2 className="display-2" id="how-title">
        How a check runs
      </h2>

      <ol className="process__steps">
        <li className="process__step">
          <span className="process__num">1</span>
          <div className="process__text">
            <h3 className="process__name">Read what the project claims</h3>
            <p>From the README, the resume or the submission. Every promise becomes something to test.</p>
          </div>
          <blockquote className="process__artifact readme">
            CaptionBuddy lets you <mark className="readme__claim">upload any image and get a caption</mark>, then{" "}
            <mark className="readme__claim">search all your past captions</mark> and{" "}
            <mark className="readme__claim">share one with a link</mark>.
          </blockquote>
        </li>

        <li className="process__step">
          <span className="process__num">2</span>
          <div className="process__text">
            <h3 className="process__name">Use it like a real person</h3>
            <p>An agent opens the live site, signs up, clicks and types. Test data is always labelled “TalNex test”.</p>
          </div>
          <ol className="process__artifact runlog">
            <li>
              <time>22:17:06</time> Opened caption-buddy.app, loaded in 0.4 s
            </li>
            <li>
              <time>22:17:11</time> Uploaded dog.jpg, caption: “A brown dog on grass”
            </li>
            <li>
              <time>22:17:24</time> Searched “dog”, server error 500
            </li>
            <li>
              <time>22:18:31</time> Waited a minute, tried another search, error 500
            </li>
          </ol>
        </li>

        <li className="process__step">
          <span className="process__num">3</span>
          <div className="process__text">
            <h3 className="process__name">Check before calling anything broken</h3>
            <p>
              Three tries, then a second model that sees only the screenshots. If they disagree, it says “could not
              confirm”, never broken.
            </p>
          </div>
          <div className="process__artifact checks">
            <span className="checks__row">
              First look <VerdictBadge kind="broken" />
            </span>
            <span className="checks__row">
              Second look, screenshots only <VerdictBadge kind="broken" />
            </span>
            <span className="checks__row checks__row--result">Both agree: search is broken.</span>
          </div>
        </li>

        <li className="process__step">
          <span className="process__num">4</span>
          <div className="process__text">
            <h3 className="process__name">Hand over the proof</h3>
            <p>A score for every feature, the reason in one line, and every screenshot one click away.</p>
            <a className="text-link" href="#proof">
              See a sample result
            </a>
          </div>
        </li>
      </ol>
    </section>
  );
}
