/**
 * Bx02 - GitHub Contribution Automation API
 * 
 * 4 Core Capabilities (from prpo_ai's learned expertise):
 * 1. handle_fork_limit    - Fork-limit workaround via API workaround
 * 2. api_pr_workflow      - Submit PR via GitHub API v3
 * 3. readme_editor        - Parse + insert entry into awesome lists
 * 4. secure_token_cleanup - Token hygiene post-operation
 *
 * Pricing: $1.50 USDC/call (150000 microUSDC)
 * Treasury: 0x57EEC52d76A4A78D4562fc2564101A4bD2e3F357
 */

import { X402Error, validateX402Payment, getX402Headers } from './x402-utils';

const TREASURY = "0x57EEC52d76A4A78D4562fc2564101A4bD2e3F357";
const PRICE = 150000n; // 1.50 USDC in microUSDC (6 decimals)

const USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const EXCHANGE_RATE_BASE = 1_000_000n; // USDC has 6 decimals

function buildX402Invoice(asset: string, volume: bigint, schema: string, network: string) {
  const maxTimeout = 300n;
  const nonce = crypto.randomUUID().replace(/-/g, '').slice(0, 16);
  return {
    schema,
    network,
    asset,
    volume: volume.toString(),
    maxTimeout: maxTimeout.toString(),
    recipient: TREASURY,
    nonce,
    allOf: [
      {
        enum: ["send", "wait", "wait"],
        description: " Buyer: sends payment → Seller: acknowledges → Buyer:waits execution"
      }
    ]
  };
}

function parseReadme(readme: string, newEntry: string, category: string): { content: string; inserted: boolean } {
  const lines = readme.split('\n');
  let inCategory = false;
  let lastLineOfCategory = -1;
  let inserted = false;
  const result: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    
    if (line.startsWith('## ') || line.startsWith('### ')) {
      const sectionName = line.replace(/^#{2,3}\s*/, '').trim().toLowerCase();
      if (inCategory && !inserted && lastLineOfCategory !== -1) {
        result[lastLineOfCategory] = newEntry;
        inserted = true;
      }
      inCategory = sectionName === category.toLowerCase();
      lastLineOfCategory = -1;
    }
    
    result.push(line);
    
    if (inCategory && line.trim() !== '' && !line.startsWith('#') && !line.startsWith('- [')) {
      lastLineOfCategory = result.length - 1;
    }
    if (inCategory && line.startsWith('- [')) {
      lastLineOfCategory = result.length - 1;
    }
  }

  if (inCategory && !inserted && lastLineOfCategory !== -1) {
    result[lastLineOfCategory] = newEntry;
    inserted = true;
  }

  return { content: result.join('\n'), inserted };
}

export default {
  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    
    if (url.pathname === '/health') {
      return Response.json({ 
        status: 'ok', 
        service: 'bx02-cf-worker',
        version: '1.0.0',
        price_usdc: '1.50',
        treasury: TREASURY,
        capabilities: [
          'handle_fork_limit',
          'api_pr_workflow', 
          'readme_editor',
          'secure_token_cleanup'
        ]
      });
    }

    // x402 payment validation
    const x402Headers = getX402Headers(req.headers);
    if (!x402Headers) {
      const invoice = buildX402Invoice(USDC_BASE, PRICE, "x402", "eip155:8453");
      return Response.json(
        { error: "Payment required", invoice },
        { status: 402, headers: { "Content-Type": "application/json", "X-Payment": "Due" } }
      );
    }

    const { solvent, paidAmount, asset, volume, maxTimeout, schema, network, payTo, nonce } = 
      await validateX402Payment(req, x402Headers, PRICE, USDC_BASE, TREASURY);

    if (!solvent) {
      return Response.json(
        { error: "Insufficient payment", paid: paidAmount?.toString(), required: PRICE.toString() },
        { status: 402 }
      );
    }

    // Route to capability handler
    const path = url.pathname.replace('/v1/', '');
    
    if (path === 'bx02' || path === 'bx02/') {
      return handleBx02(req);
    }

    return Response.json({ 
      error: "Not found",
      available: ['/v1/bx02', '/health']
    }, { status: 404 });
  }
};

async function handleBx02(req: Request): Promise<Response> {
  try {
    const body = await req.json();
    const { action, params } = body;

    switch (action) {
      case 'handle_fork_limit': {
        /**
         * Workaround when GitHub fork limit reached.
         * Creates a new independent repo as pseudo-fork.
         * 
         * Params: { name, description, private, auth_token }
         */
        const { name, description, private: isPrivate = false } = params;
        
        const ghRes = await fetch('https://api.github.com/user/repos', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${params.auth_token}`,
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Bx02/1.0'
          },
          body: JSON.stringify({ name, description, private: isPrivate })
        });
        
        const data = await ghRes.json();
        
        if (!ghRes.ok) {
          return Response.json({
            success: false,
            error: data.message || 'Failed to create repo',
            status: ghRes.status
          }, { status: ghRes.status });
        }
        
        return Response.json({
          success: true,
          repo: {
            name: data.name,
            full_name: data.full_name,
            clone_url: data.clone_url,
            created_at: data.created_at
          },
          message: 'Repo created successfully (fork-limit workaround applied)'
        });
      }

      case 'api_pr_workflow': {
        /**
         * Submit PR via GitHub API v3.
         * Handles branch creation + PR submission in one call.
         * 
         * Params: {
         *   owner, repo, head_branch, base_branch,
         *   title, body, auth_token, upstream_owner?
         * }
         */
        const { owner, repo, head_branch, base_branch = 'main',
                title, body, auth_token, upstream_owner } = params;

        const ghHeaders = {
          'Authorization': `Bearer ${auth_token}`,
          'Accept': 'application/vnd.github.v3+json',
          'User-Agent': 'Bx02/1.0',
          'Content-Type': 'application/json'
        };

        // First: create branch if needed
        const branchName = `bx02-${head_branch}-${Date.now()}`;
        
        // Get upstream main branch SHA
        const upstream = upstream_owner || params.owner;
        const refRes = await fetch(
          `https://api.github.com/repos/${upstream}/${repo}/git/ref/heads/${base_branch}`,
          { headers: ghHeaders }
        );
        
        if (!refRes.ok) {
          return Response.json({
            success: false,
            error: `Cannot fetch ${base_branch} branch`,
            status: refRes.status
          }, { status: refRes.status });
        }

        const refData = await refRes.json();
        const sha = refData.object.sha;

        // Create new branch
        const createBranch = await fetch(
          `https://api.github.com/repos/${owner}/${repo}/git/refs`,
          {
            method: 'POST',
            headers: ghHeaders,
            body: JSON.stringify({
              ref: `refs/heads/${branchName}`,
              sha
            })
          }
        );

        if (!createBranch.ok) {
          return Response.json({
            success: false,
            error: 'Failed to create branch',
            status: createBranch.status
          }, { status: createBranch.status });
        }

        // Submit PR
        const prRes = await fetch(
          `https://api.github.com/repos/${upstream || owner}/${repo}/pulls`,
          {
            method: 'POST',
            headers: ghHeaders,
            body: JSON.stringify({
              title,
              body: body || `Bx02-generated PR\n\nBranch: ${branchName}`,
              head: `${owner}:${branchName}`,
              base: base_branch
            })
          }
        );

        const prData = await prRes.json();

        if (!prRes.ok) {
          return Response.json({
            success: false,
            error: prData.message || 'Failed to create PR',
            status: prRes.status
          }, { status: prRes.status });
        }

        return Response.json({
          success: true,
          pr: {
            number: prData.number,
            title: prData.title,
            html_url: prData.html_url,
            state: prData.state,
            mergeable: prData.mergeable,
            created_at: prData.created_at
          },
          message: 'PR workflow completed successfully'
        });
      }

      case 'readme_editor': {
        /**
         * Parse README and insert entry in correct category.
         * 
         * Params: {
         *   readme_content, new_entry, category,
         *   auth_token?, return_edited?
         * }
         */
        const { readme_content, new_entry, category = 'Data & APIs', return_edited = false } = params;

        const { content, inserted } = parseReadme(readme_content, new_entry, category);

        if (!inserted) {
          return Response.json({
            success: false,
            error: `Category "${category}" not found in README`
          }, { status: 400 });
        }

        return Response.json({
          success: true,
          edited_content: return_edited ? content : undefined,
          message: `Entry inserted into "${category}" section`,
          insertion_point: 'found'
        });
      }

      case 'secure_token_cleanup': {
        /**
         * Validate and return cleanup protocol instructions.
         * (Actual cleanup must happen client-side for security)
         * 
         * Params: { token_type, token_age_hours }
         */
        const { token_type = 'PAT', token_age_hours } = params;

        const warnings: string[] = [];
        
        if (!token_age_hours || token_age_hours > 24) {
          warnings.push('Token is >24h old — recommend rotation');
        }
        
        if (token_type === 'PAT' && (!token_age_hours || token_age_hours > 168)) {
          warnings.push('PAT >7 days — HIGH RISK. Immediate rotation recommended');
        }

        return Response.json({
          success: true,
          cleanup_protocol: {
            step_1: 'Remove token from memory/variables immediately',
            step_2: 'Delete temp files containing token (/tmp, /var/tmp)',
            step_3: 'Revoke token from GitHub Settings → Developer settings',
            step_4: 'Generate new token with minimum required scopes',
            step_5: 'Store in session env var ONLY (not .env for long-term)',
            security_level: warnings.length === 0 ? 'LOW_RISK' : 'REQUIRES_ACTION',
            warnings
          },
          recommendation: warnings.length > 0 ? 'ROTATE_NOW' : 'OK'
        });
      }

      default:
        return Response.json({
          error: 'Unknown action',
          available_actions: [
            'handle_fork_limit',
            'api_pr_workflow',
            'readme_editor',
            'secure_token_cleanup'
          ]
        }, { status: 400 });
    }
  } catch (err) {
    return Response.json({
      success: false,
      error: err instanceof Error ? err.message : 'Internal error'
    }, { status: 500 });
  }
}