const preferredClassColors: Record<string, string> = {
  car: "#3b82f6",
  van: "#8b5cf6",
  truck: "#f97316",
  pedestrian: "#22c55e",
  cyclist: "#ec4899",
  bicycle: "#eab308",
  "vehicle.car": "#06b6d4",
};

function channelToHex(value: number): string {
  return Math.round(value * 255).toString(16).padStart(2, "0");
}

function hslToHex(hue: number, saturation: number, lightness: number): string {
  const saturationRatio = saturation / 100;
  const lightnessRatio = lightness / 100;
  const chroma = (1 - Math.abs(2 * lightnessRatio - 1)) * saturationRatio;
  const section = hue / 60;
  const secondary = chroma * (1 - Math.abs((section % 2) - 1));
  const [red, green, blue] = section < 1
    ? [chroma, secondary, 0]
    : section < 2
      ? [secondary, chroma, 0]
      : section < 3
        ? [0, chroma, secondary]
        : section < 4
          ? [0, secondary, chroma]
          : section < 5
            ? [secondary, 0, chroma]
            : [chroma, 0, secondary];
  const match = lightnessRatio - chroma / 2;
  return `#${channelToHex(red + match)}${channelToHex(green + match)}${channelToHex(blue + match)}`;
}

export function classColorForLabel(label: string): string {
  const normalized = label.trim().toLowerCase() || "unlabeled";
  const preferred = preferredClassColors[normalized];
  if (preferred) return preferred;

  let hash = 2166136261;
  for (const character of normalized) {
    hash ^= character.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16777619);
  }
  return hslToHex((hash >>> 0) % 360, 82, 62);
}
