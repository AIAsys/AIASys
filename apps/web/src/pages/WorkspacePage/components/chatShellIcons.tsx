import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

export function HistoryIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M3 3v5h5" />
      <path d="M3 8a9 9 0 1 0 3-6.7L3 4" />
      <path d="M12 7v5l4 2" />
    </svg>
  );
}

export function Settings2Icon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M14 17H5" />
      <path d="M19 7H10" />
      <circle cx="17" cy="17" r="3" />
      <circle cx="7" cy="7" r="3" />
    </svg>
  );
}

export function PuzzleIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M19.44 12.99a2 2 0 0 0 0-1.98l-1.16-2a2 2 0 0 0-1.73-1H14a2 2 0 0 1-2-2V3.45a2 2 0 0 0-1-1.73l-2-1.16a2 2 0 0 0-1.98 0l-2 1.16a2 2 0 0 0-1 1.73V6a2 2 0 0 1-2 2H-.55a2 2 0 0 0-1.73 1l-1.16 2a2 2 0 0 0 0 1.98l1.16 2a2 2 0 0 0 1.73 1H2a2 2 0 0 1 2 2v2.55a2 2 0 0 0 1 1.73l2 1.16a2 2 0 0 0 1.98 0l2-1.16a2 2 0 0 0 1-1.73V18a2 2 0 0 1 2-2h2.55a2 2 0 0 0 1.73-1l1.16-2Z" transform="translate(2 0.5) scale(.8)" />
      <path d="M8 12h8" />
      <path d="M12 8v8" />
    </svg>
  );
}

export function MoreHorizontalIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="12" cy="12" r="1" />
      <circle cx="19" cy="12" r="1" />
      <circle cx="5" cy="12" r="1" />
    </svg>
  );
}

export function MessageSquareIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z" />
    </svg>
  );
}

export function GitBranchPlusIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M6 3v12" />
      <path d="M18 9a3 3 0 1 0-3-3v9a3 3 0 1 1-3-3H6" />
      <path d="M18 15v6" />
      <path d="M21 18h-6" />
    </svg>
  );
}
