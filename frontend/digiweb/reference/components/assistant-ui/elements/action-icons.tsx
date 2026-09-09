import type { FC } from "react";

import { DotMatrix, type DotMatrixState } from "@/components/ui/dot-matrix";

const Cube: FC<{ state: DotMatrixState; className?: string; label: string }> = ({
  state,
  className,
  label,
}) => <DotMatrix state={state} label={label} className={className} />;

export const CopyActionIcon: FC<{ className?: string }> = ({ className }) => (
  <Cube state="copy" label="Copy" className={className} />
);

export const CheckActionIcon: FC<{ className?: string }> = ({ className }) => (
  <Cube state="success" label="Copied" className={className} />
);

export const CloseActionIcon: FC<{ className?: string }> = ({ className }) => (
  <Cube state="remove" label="Close" className={className} />
);

export const PlusActionIcon: FC<{ className?: string }> = ({ className }) => (
  <Cube state="attach" label="Add" className={className} />
);
