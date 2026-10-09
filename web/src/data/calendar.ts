// История — 24 месяца (2023-01…2024-12); на стенде к ним добавляется год вперёд.
export const HIST = 24
export const AHEAD = 12
export const HORIZONS = [1, 3, 6, 12] as const
export type Horizon = (typeof HORIZONS)[number]
