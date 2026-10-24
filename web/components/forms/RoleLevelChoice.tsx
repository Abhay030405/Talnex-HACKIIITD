import { ROLE_LEVELS, type RoleLevel } from "@/lib/types";

/** Four cards to pick how strictly projects are judged. */
export function RoleLevelChoice({ defaultValue = "fresher" }: { defaultValue?: RoleLevel }) {
  return (
    <fieldset className="field fieldset">
      <legend className="field__label">Role level</legend>
      <span className="field__hint">
        Decides how features are scored. A fresher is judged on how it is implemented, not on design.
      </span>
      <div className="choice-grid">
        {ROLE_LEVELS.map((level) => (
          <label className="choice" key={level.value}>
            <input
              className="choice__input"
              type="radio"
              name="role_level"
              value={level.value}
              defaultChecked={level.value === defaultValue}
              required
            />
            <span className="choice__title">{level.label}</span>
            <span className="choice__text">{level.hint}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
