/**
 * Gloomberb candlestick mark — from gloom-sh/gloomberb (MIT); used to link to the Gloomberb terminal.
 */

export function GloomberbMark({ size = 18, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 512 512"
      aria-hidden="true"
      focusable="false"
      className={['gloomberb-mark', className].filter(Boolean).join(' ')}
    >
      <defs>
        <linearGradient
          id="gloomberb-mark-green-body"
          x1="143.5"
          y1="173"
          x2="206.5"
          y2="323"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#bdff34" />
          <stop offset="0.58" stopColor="#8ff014" />
          <stop offset="1" stopColor="#5fd60d" />
        </linearGradient>
        <linearGradient
          id="gloomberb-mark-green-wick"
          x1="168"
          y1="130"
          x2="182"
          y2="366"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#c8ff3f" />
          <stop offset="1" stopColor="#67df12" />
        </linearGradient>
        <linearGradient
          id="gloomberb-mark-white-body"
          x1="220.9"
          y1="149"
          x2="291.1"
          y2="347"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="0.62" stopColor="#f3f3f0" />
          <stop offset="1" stopColor="#dfdfda" />
        </linearGradient>
        <linearGradient
          id="gloomberb-mark-white-wick"
          x1="249"
          y1="106"
          x2="263"
          y2="390"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#e5e5e1" />
        </linearGradient>
        <linearGradient
          id="gloomberb-mark-red-body"
          x1="305.5"
          y1="173"
          x2="368.5"
          y2="323"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#ff5f66" />
          <stop offset="0.55" stopColor="#ff2631" />
          <stop offset="1" stopColor="#ff1421" />
        </linearGradient>
        <linearGradient
          id="gloomberb-mark-red-wick"
          x1="330"
          y1="130"
          x2="344"
          y2="366"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#ff686e" />
          <stop offset="1" stopColor="#ff1421" />
        </linearGradient>
      </defs>

      <rect width="512" height="512" fill="#252628" />

      <g transform="translate(256 248) scale(1.15) translate(-256 -248)">
        <g fill="#000000">
          <g opacity="0.035">
            <rect x="173" y="140" width="22" height="246" rx="11" />
            <rect x="146.2" y="181" width="75.6" height="164" rx="13" />
            <rect x="254" y="116" width="22" height="294" rx="11" />
            <rect x="223.6" y="157" width="82.8" height="212" rx="13" />
            <rect x="335" y="140" width="22" height="246" rx="11" />
            <rect x="308.2" y="181" width="75.6" height="164" rx="13" />
          </g>
          <g opacity="0.06">
            <rect x="173" y="138" width="18" height="242" rx="9" />
            <rect x="146.9" y="180" width="70.2" height="160" rx="11" />
            <rect x="254" y="114" width="18" height="290" rx="9" />
            <rect x="224.3" y="156" width="77.4" height="206" rx="11" />
            <rect x="335" y="138" width="18" height="242" rx="9" />
            <rect x="308.9" y="180" width="70.2" height="160" rx="11" />
          </g>
          <g opacity="0.08">
            <rect x="172" y="137" width="14" height="236" rx="7" />
            <rect x="147.5" y="180" width="63" height="150" rx="8" />
            <rect x="253" y="113" width="14" height="284" rx="7" />
            <rect x="224.9" y="156" width="70.2" height="198" rx="8" />
            <rect x="334" y="137" width="14" height="236" rx="7" />
            <rect x="309.5" y="180" width="63" height="150" rx="8" />
          </g>
        </g>

        <g>
          <rect
            x="168"
            y="130"
            width="14"
            height="236"
            rx="7"
            fill="url(#gloomberb-mark-green-wick)"
          />
          <rect
            x="143.5"
            y="173"
            width="63"
            height="150"
            rx="8"
            fill="url(#gloomberb-mark-green-body)"
          />
          <rect
            x="249"
            y="106"
            width="14"
            height="284"
            rx="7"
            fill="url(#gloomberb-mark-white-wick)"
          />
          <rect
            x="220.9"
            y="149"
            width="70.2"
            height="198"
            rx="8"
            fill="url(#gloomberb-mark-white-body)"
          />
          <rect
            x="330"
            y="130"
            width="14"
            height="236"
            rx="7"
            fill="url(#gloomberb-mark-red-wick)"
          />
          <rect
            x="305.5"
            y="173"
            width="63"
            height="150"
            rx="8"
            fill="url(#gloomberb-mark-red-body)"
          />
        </g>
      </g>
    </svg>
  );
}
