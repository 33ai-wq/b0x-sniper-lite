/**
 * x402 Utilities for Workers
 * Based on 402 V2 protocol
 */

export interface X402Headers {
  'x402': string;
  'x402-asset'?: string;
  'x402-network'?: string;
  'x402-volume'?: string;
  'x402-pay-to'?: string;
  'x402-recipient'?: string;
  'x402-timeout'?: string;
  'x402-nonce'?: string;
  'x402-signature'?: string;
}

export class X402Error extends Error {
  constructor(message: string, public code: string) {
    super(message);
    this.name = 'X402Error';
  }
}

export function getX402Headers(headers: Headers): X402Headers | null {
  const x402 = headers.get('x402');
  if (!x402) return null;

  return {
    'x402': x402,
    'x402-asset': headers.get('x402-asset') || undefined,
    'x402-network': headers.get('x402-network') || undefined,
    'x402-volume': headers.get('x402-volume') || undefined,
    'x402-pay-to': headers.get('x402-pay-to') || undefined,
    'x402-recipient': headers.get('x402-recipient') || undefined,
    'x402-timeout': headers.get('x402-timeout') || undefined,
    'x402-nonce': headers.get('x402-nonce') || undefined,
    'x402-signature': headers.get('x402-signature') || undefined,
  };
}

export async function validateX402Payment(
  req: Request,
  headers: X402Headers,
  expectedPrice: bigint,
  expectedAsset: string,
  expectedRecipient: string
): Promise<{
  solvent: boolean;
  paidAmount?: bigint;
  asset?: string;
  volume?: bigint;
  maxTimeout?: bigint;
  schema?: string;
  network?: string;
  payTo?: string;
  nonce?: string;
}> {
  try {
    const asset = headers['x402-asset'] || '';
    const volumeHex = headers['x402-volume'] || '0';
    const network = headers['x402-network'] || '';
    const payTo = headers['x402-pay-to'] || '';
    const maxTimeoutHex = headers['x402-timeout'] || '0';
    const schema = headers['x402'] || 'x402';

    const paidAmount = BigInt(volumeHex);
    const maxTimeout = BigInt(maxTimeoutHex);

    // Validate payment
    if (asset.toLowerCase() !== expectedAsset.toLowerCase()) {
      return { solvent: false };
    }

    if (paidAmount < expectedPrice) {
      return { solvent: false, paidAmount, asset, volume: paidAmount };
    }

    if (payTo.toLowerCase() !== expectedRecipient.toLowerCase()) {
      return { solvent: false };
    }

    return {
      solvent: true,
      paidAmount,
      asset,
      volume: paidAmount,
      maxTimeout,
      schema,
      network,
      payTo,
      nonce: headers['x402-nonce']
    };
  } catch {
    return { solvent: false };
  }
}

export function createX402Invoice(params: {
  schema: string;
  network: string;
  asset: string;
  volume: string;
  maxTimeout: string;
  recipient: string;
  nonce: string;
  allOf?: Array<{enum: string[], description: string}>;
}) {
  const invoice: Record<string, unknown> = {
    schema: params.schema,
    network: params.network,
    asset: params.asset,
    volume: params.volume,
    maxTimeout: params.maxTimeout,
    recipient: params.recipient,
    nonce: params.nonce,
  };

  if (params.allOf) {
    invoice['allOf'] = params.allOf;
  }

  return invoice;
}