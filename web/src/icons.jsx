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

export const HomeIcon = () => (
  <svg {...base}>
    <path d="M3.5 11 12 4l8.5 7" />
    <path d="M5.5 9.5V20h13V9.5" />
    <path d="M10 20v-5.5h4V20" />
  </svg>
);

// Floor plan editor tools. Smaller, and always next to a text label.
const tool = { ...base, width: 20, height: 20 };

export const SelectToolIcon = () => (
  <svg {...tool}>
    <path d="M5 3.5 18.5 11l-6 1.6-2.6 5.9Z" />
  </svg>
);

export const WallToolIcon = () => (
  <svg {...tool}>
    <path d="M4 19 20 5" stroke-width="3.2" />
  </svg>
);

export const DoorToolIcon = () => (
  <svg {...tool}>
    <path d="M3 20h4M17 20h4" stroke-width="3" />
    <path d="M7 20V8" />
    <path d="M7 8a12 12 0 0 1 10 12" stroke-dasharray="2 2.4" />
  </svg>
);

export const LabelToolIcon = () => (
  <svg {...tool}>
    <path d="M5 6.5V5h14v1.5M12 5v14M9 19h6" />
  </svg>
);

export const SignToolIcon = () => (
  <svg {...tool}>
    <rect x="5" y="5" width="14" height="14" rx="1.5" />
    <path d="M9 9h2.5v2.5H9zM12.5 12.5H15V15h-2.5z" fill="currentColor" stroke="none" />
  </svg>
);

export const PanToolIcon = () => (
  <svg {...tool}>
    <path d="M12 3v18M3 12h18M12 3 9.5 5.5M12 3l2.5 2.5M12 21l-2.5-2.5M12 21l2.5-2.5M3 12l2.5-2.5M3 12l2.5 2.5M21 12l-2.5-2.5M21 12l-2.5 2.5" />
  </svg>
);

export const UndoIcon = () => (
  <svg {...tool}>
    <path d="M8 5 4 9l4 4" />
    <path d="M4 9h10a5.5 5.5 0 0 1 0 11h-3" />
  </svg>
);

export const ZoomInIcon = () => (
  <svg {...tool}>
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="M15.5 15.5 20 20M10.5 7.5v6M7.5 10.5h6" />
  </svg>
);

export const ZoomOutIcon = () => (
  <svg {...tool}>
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="M15.5 15.5 20 20M7.5 10.5h6" />
  </svg>
);

export const FitIcon = () => (
  <svg {...tool}>
    <path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" />
  </svg>
);

export const RotateIcon = () => (
  <svg {...tool}>
    <path d="M19 5v5h-5" />
    <path d="M19 10a7.5 7.5 0 1 0 .5 5" />
  </svg>
);
