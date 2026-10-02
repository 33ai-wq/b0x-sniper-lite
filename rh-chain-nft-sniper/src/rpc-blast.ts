// RPC endpoint parsing and validation
// Source: adapted from solotop999/opensea-nft-public-mint

export interface ParsedRpcEndpoint {
  url: string;
  label: string;
}

export function parseRpcEndpoints(input: string): ParsedRpcEndpoint[] {
  return input
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((url) => {
      let label = url;
      try {
        const u = new URL(url);
        label = `${u.protocol}//${u.hostname}${u.port ? `:${u.port}` : ""}`;
      } catch {
        // Keep original as label
      }
      return { url, label };
    });
}

export function maskRpc(url: string): string {
  try {
    const u = new URL(url);
    if (u.searchParams.has("api_key")) u.searchParams.set("api_key", "***");
    if (u.searchParams.has("key")) u.searchParams.set("key", "***");
    return u.toString();
  } catch {
    return url;
  }
}