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
