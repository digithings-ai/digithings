export function DigiChatMark({ size = 18, title }: { size?: number; title?: string }) {
  return (
    <svg
      viewBox="0 0 56 56"
      width={size}
      height={size}
      fill="none"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {title ? <title>{title}</title> : null}
      <rect x="5" y="8" width="46" height="33" rx="10" stroke="currentColor" strokeWidth="2.6" />
      <path
        d="M17 41 L17 50 L28 41"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M16 18 L23 24.5 L16 31"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <rect x="27" y="29" width="12" height="2.6" rx="1.3" fill="currentColor" />
    </svg>
  );
}

export function DigiChatWordmark({ cursor = false }: { cursor?: boolean }) {
  return (
    <span className="dc-wordmark">
      <span className="dc-wm-d">digi</span>
      <span className="dc-wm-s">chat</span>
      {cursor ? <span className="dt-cur" aria-hidden="true" /> : null}
    </span>
  );
}
