// ────────────────────────────────────────────
//  LitCount Contract ABIs (for frontend use)
// ────────────────────────────────────────────

export const ZKLTC_ABI = [
  // Read
  "function balanceOf(address) view returns (uint256)",
  "function allowance(address owner, address spender) view returns (uint256)",
  "function symbol() view returns (string)",
  "function decimals() view returns (uint8)",
  "function lastFaucetClaim(address) view returns (uint256)",
  // Write
  "function approve(address spender, uint256 amount) returns (bool)",
  "function faucet()",
  // Events
  "event FaucetClaimed(address indexed user, uint256 amount)",
] as const;

export const POOL_ABI = [
  // Constants
  "function STAKE_AMOUNT() view returns (uint256)",
  "function POOL_DURATION() view returns (uint256)",
  "function MIN_USERS() view returns (uint256)",
  "function WINNER_PCT() view returns (uint256)",
  "function STAKER_PCT() view returns (uint256)",
  // Read
  "function currentRound() view returns (uint256)",
  "function isDrawPhase() view returns (bool)",
  "function getCurrentRoundInfo() view returns (uint256 id, uint256 startTime, uint256 userCount, uint256 totalPool, bool inDrawPhase, uint256 timeUntilDraw, bool canTriggerDraw)",
  "function isUserInCurrentPool(address) view returns (bool)",
  "function getPoolProgress() view returns (uint256 current, uint256 minimum, uint256 percentage)",
  "function getRoundWinner(uint256) view returns (address, uint256)",
  "function getParticipants(uint256) view returns (address[])",
  "function userInfo(uint256, address) view returns (bool isActive, uint256 roundJoined, bool rewardClaimed)",
  // Write
  "function joinPool()",
  "function triggerDrawPhase()",
  "function executeDraw()",
  "function claimStakerReward(uint256 roundId)",
  // Events
  "event PoolJoined(address indexed user, uint256 indexed round, uint256 timestamp)",
  "event WinnerSelected(uint256 indexed round, address indexed winner, uint256 reward)",
  "event DrawSkipped(uint256 indexed round, uint256 userCount, string reason)",
  "event RoundSettled(uint256 indexed round, uint256 totalPool, address winner)",
  "event NewRoundStarted(uint256 indexed round, uint256 startTime)",
  "event StakerRewardClaimed(address indexed user, uint256 indexed round, uint256 amount)",
] as const;
