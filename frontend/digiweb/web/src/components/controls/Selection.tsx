/**
 * Checkbox / Radio / Switch — the shared selection controls. Behavior comes
 * from @base-ui/react's Checkbox / Radio / Switch primitives (roving focus
 * for radio groups, keyboard toggle, `data-checked` / `data-disabled`
 * state); this file only skins them to the form-fields specimen grammar
 * (16px box / dot, hairline, accent check, accent focus ring). All dress
 * lives in styles/controls-core.css (`.ctl-check*`, `.ctl-radio*`,
 * `.ctl-switch*`, import once app-wide); this file carries no Tailwind
 * utilities, so no `@source` line is needed for it.
 *
 * Pair with a plain <label> (wrapping or htmlFor) — the controls own no
 * label of their own, same as the native inputs they replace.
 */
import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox";
import { Radio as RadioPrimitive } from "@base-ui/react/radio";
import { RadioGroup as RadioGroupPrimitive } from "@base-ui/react/radio-group";
import { Switch as SwitchPrimitive } from "@base-ui/react/switch";

import { cxBase } from "./cx";

export type CheckboxProps = CheckboxPrimitive.Root.Props;
export type RadioGroupProps = RadioGroupPrimitive.Props;
export type RadioProps = RadioPrimitive.Root.Props;
export type SwitchProps = SwitchPrimitive.Root.Props;

export function Checkbox({ className, ...props }: CheckboxProps) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cxBase("ctl-check", className)}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="ctl-check-indicator"
      />
    </CheckboxPrimitive.Root>
  );
}

export function RadioGroup({ className, ...props }: RadioGroupProps) {
  return (
    <RadioGroupPrimitive
      data-slot="radio-group"
      className={cxBase("ctl-radio-group", className)}
      {...props}
    />
  );
}

export function Radio({ className, ...props }: RadioProps) {
  return (
    <RadioPrimitive.Root
      data-slot="radio"
      className={cxBase("ctl-radio", className)}
      {...props}
    >
      <RadioPrimitive.Indicator data-slot="radio-indicator" className="ctl-radio-dot" />
    </RadioPrimitive.Root>
  );
}

export function Switch({ className, ...props }: SwitchProps) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cxBase("ctl-switch", className)}
      {...props}
    >
      <SwitchPrimitive.Thumb data-slot="switch-thumb" className="ctl-switch-knob" />
    </SwitchPrimitive.Root>
  );
}
