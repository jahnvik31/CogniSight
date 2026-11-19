// Simple line icons. Decorative: the text label next to each carries the meaning.
const base = {
  width: 24,
  height: 24,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  "stroke-width": 1.8,
  "stroke-linecap": "round",
  "stroke-linejoin": "round",
  "aria-hidden": "true",
  focusable: "false",
};

export const LiveIcon = () => (
  <svg {...base}>
    <path d="M2.5 12s3.5-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.5 6.5-9.5 6.5S2.5 12 2.5 12Z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

export const PeopleIcon = () => (
  <svg {...base}>
    <circle cx="9" cy="8.5" r="3.2" />
    <path d="M3 19.5c.6-3.3 3-5 6-5s5.4 1.7 6 5" />
    <path d="M15.5 5.6a3 3 0 0 1 0 5.8" />
    <path d="M17.6 14.8c1.8.6 3 2.2 3.4 4.7" />
  </svg>
);

export const PlaceIcon = () => (
  <svg {...base}>
    <path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11Z" />
    <circle cx="12" cy="10" r="2.4" />
  </svg>
);

export const DeviceIcon = () => (
  <svg {...base}>
    <rect x="5" y="5" width="14" height="14" rx="2" />
    <rect x="9" y="9" width="6" height="6" rx="1" />
    <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" />
  </svg>
);

export const UnknownFace = () => (
  <svg {...base} viewBox="0 0 24 24">
    <circle cx="12" cy="9" r="4" />
    <path d="M4.5 21c.9-4 3.8-6 7.5-6s6.6 2 7.5 6" />
  </svg>
);
