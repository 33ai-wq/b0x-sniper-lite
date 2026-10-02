// Slug resolver using OpenSea API
// Source: adapted from solotop999/opensea-nft-public-mint

import { fetch } from "undici";

export async function resolveSlug(slug: string, apiKey?: string): Promise<string | null> {
  if (!apiKey) return null;

  try {
    const url = `https://api.opensea.io/api/v2/collections/${slug}`;
    const headers: Record<string, string> = {
      "Accept": "application/json",
      "X-API-KEY": apiKey,
    };

    const response = await fetch(url, { headers });

    if (!response.ok) {
      if (response.status === 404) return null;
      if (response.status === 429) throw new Error("OpenSea API rate limited");
      throw new Error(`OpenSea API error: ${response.status}`);
    }

    const data = await response.json() as { collection?: { primary_asset_contracts?: { address?: string }[] } };
    const contract = data.collection?.primary_asset_contracts?.[0]?.address;
    return contract?.toLowerCase() || null;
  } catch (err: any) {
    console.error(`Slug resolution failed: ${err.message}`);
    return null;
  }
}

export async function createOpenSeaApiKey(): Promise<string | null> {
  try {
    const response = await fetch("https://api.opensea.io/api/v2/auth/keys", {
      method: "POST",
      headers: { "Accept": "application/json" },
    });

    if (!response.ok) return null;

    const data = await response.json() as { api_key?: string };
    return data.api_key || null;
  } catch {
    return null;
  }
}