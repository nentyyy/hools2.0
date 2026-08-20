/** Line icons. Emoji render differently on every platform and read as clip art. */

type IconProps = { size?: number };

const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function Svg({ size = 22, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      {children}
    </svg>
  );
}

export function SwordsIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path {...stroke} d="M14.5 14.5 20 20M4 4l5.5 5.5M20 4l-9 9M4 20l9-9" />
      <path {...stroke} d="M17.5 4H20v2.5M6.5 20H4v-2.5" />
    </Svg>
  );
}

export function DiceIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect {...stroke} x="3.5" y="3.5" width="17" height="17" rx="4.5" />
      <circle cx="8.75" cy="8.75" r="1.35" fill="currentColor" />
      <circle cx="15.25" cy="15.25" r="1.35" fill="currentColor" />
      <circle cx="12" cy="12" r="1.35" fill="currentColor" />
    </Svg>
  );
}

export function GiftIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path {...stroke} d="M3.5 10.5h17V19a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19z" />
      <path {...stroke} d="M2.8 7h18.4v3.5H2.8zM12 7v13.5" />
      <path {...stroke} d="M12 7S10.6 3.5 8.6 3.5a2 2 0 0 0 0 4M12 7s1.4-3.5 3.4-3.5a2 2 0 0 1 0 4" />
    </Svg>
  );
}

export function UserIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle {...stroke} cx="12" cy="8.5" r="3.75" />
      <path {...stroke} d="M4.5 20c.9-3.6 3.9-5.6 7.5-5.6s6.6 2 7.5 5.6" />
    </Svg>
  );
}

export function HistoryIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path {...stroke} d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1" />
      <path {...stroke} d="M3.2 4.6v4h4M12 7.6V12l3 1.8" />
    </Svg>
  );
}

export function UsersIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle {...stroke} cx="9" cy="8.5" r="3.2" />
      <path {...stroke} d="M2.8 19.5c.8-3 3.2-4.7 6.2-4.7s5.4 1.7 6.2 4.7" />
      <path {...stroke} d="M16 5.6a3.2 3.2 0 0 1 0 5.9M17.4 14.9c2.1.5 3.4 1.9 3.9 4.1" />
    </Svg>
  );
}


export function BagIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path {...stroke} d="M4.2 8.5h15.6l-1.1 10.2a1.6 1.6 0 0 1-1.6 1.4H6.9a1.6 1.6 0 0 1-1.6-1.4z" />
      <path {...stroke} d="M8.6 8.5V7a3.4 3.4 0 0 1 6.8 0v1.5" />
    </Svg>
  );
}

export function PlinkoIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="4.5" r="1.5" fill="currentColor" />
      <circle cx="8" cy="10" r="1.2" fill="currentColor" opacity="0.5" />
      <circle cx="16" cy="10" r="1.2" fill="currentColor" opacity="0.5" />
      <circle cx="6" cy="15" r="1.2" fill="currentColor" opacity="0.5" />
      <circle cx="12" cy="15" r="1.2" fill="currentColor" opacity="0.5" />
      <circle cx="18" cy="15" r="1.2" fill="currentColor" opacity="0.5" />
      <path {...stroke} d="M3.5 20h17" />
    </Svg>
  );
}

export function UpgradeIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path {...stroke} d="M12 19.5V5.5M12 4.5l5 5M12 4.5l-5 5" />
      <path {...stroke} d="M5 21h14" />
    </Svg>
  );
}

export function CardsIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect {...stroke} x="8.5" y="5.5" width="11" height="14" rx="2.5" />
      <path {...stroke} d="M6 8v9.5A2.5 2.5 0 0 0 8.5 20" opacity="0.7" />
      <path {...stroke} d="M14 9.5l1.6 3 1.6-3M14 15.5h3.2" />
    </Svg>
  );
}

export function IceIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path {...stroke} d="M12 3v18M4 7.5l16 9M20 7.5l-16 9" />
      <path {...stroke} d="M12 6.5 10 5m2 1.5L14 5m-2 12.5L10 19m2-1.5L14 19" />
    </Svg>
  );
}

export function ShieldIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path {...stroke} d="M12 3.5 19 6v5.6c0 4-2.8 7.4-7 8.9-4.2-1.5-7-4.9-7-8.9V6z" />
      <path {...stroke} d="m9 12 2.2 2.2L15.5 10" />
    </Svg>
  );
}
