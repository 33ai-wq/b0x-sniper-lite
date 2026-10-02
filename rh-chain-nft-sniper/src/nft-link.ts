// NFT link parsing utilities
// Source: adapted from solotop999/opensea-nft-public-mint

export function parseNftLink(raw: string): { type: "opensea" | "slug" | "address"; value: string } {
  const value = raw.trim();
  // OpenSea collection/item URL
  if (value.startsWith("https://opensea.io/") || value.startsWith("https://testnets.opensea.io/")) {
    return { type: "opensea", value };
  }
  // Contract address
  if (/^0x[0-9a-fA-F]{40}$/.test(value)) {
    return { type: "address", value: value.toLowerCase() };
  }
  // Slug (collection identifier)
  return { type: "slug", value };
}

export function extractSlugFromOpenseaUrl(url: string): string | null {
  try {
    const u = new URL(url);
    const parts = u.pathname.split("/").filter(Boolean);
    // Collection overview: /collection/<slug>
    // Item: /assets/<chain>/<contract>/<tokenId> or /item/<slug>
    if (parts[0] === "collection" && parts[1]) return parts[1];
    if (parts[0] === "assets" && parts[3]) return parts[3]; // slug sometimes in path
    if (parts[0] === "item" && parts[1]) return parts[1];
    return null;
  } catch {
    return null;
  }
}