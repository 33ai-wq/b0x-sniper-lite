// Time formatting utilities for IST (Asia/Kolkata)
// Source: adapted from solotop999/opensea-nft-public-mint

export const IST_OFFSET = 5.5 * 60 * 60 * 1000; // UTC+5:30

export function toIST(date: Date): string {
  const ist = new Date(date.getTime() + IST_OFFSET);
  return ist.toISOString().replace("T", " ").slice(0, 19);
}

export function istTimeToDate(input: string): Date {
  const [hh, mm] = input.split(":").map(Number);
  if (Number.isNaN(hh) || Number.isNaN(mm) || hh < 0 || hh > 23 || mm < 0 || mm > 59) {
    throw new Error("Invalid time format. Use HH:MM (24-hour).");
  }
  const now = new Date();
  const ist = new Date(now.getTime() + IST_OFFSET);
  const target = new Date(ist);
  target.setUTCHours(hh, mm, 0, 0);
  // If target is in the past (IST), assume next day
  if (target.getTime() <= ist.getTime()) {
    target.setUTCDate(target.getUTCDate() + 1);
  }
  // Convert back to UTC
  return new Date(target.getTime() - IST_OFFSET);
}