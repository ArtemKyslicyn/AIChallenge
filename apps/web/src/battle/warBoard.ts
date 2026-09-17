/**
 * Local model war board — practices from LMSYS / Open Model Arena:
 * always attribute model_id, record W/L, simple Elo (K=32).
 */

export type WarBoardRow = {
  model_id: string;
  wins: number;
  losses: number;
  runs: number;
  elo: number;
};

export type WarBoard = {
  version: 1;
  updated_at: string;
  rows: WarBoardRow[];
};

const KEY = "aichallenge.battle_war_board.v1";
const K = 32;
const DEFAULT_ELO = 1000;

function emptyBoard(): WarBoard {
  return { version: 1, updated_at: new Date().toISOString(), rows: [] };
}

export function loadWarBoard(): WarBoard {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return emptyBoard();
    const parsed = JSON.parse(raw) as WarBoard;
    if (parsed?.version === 1 && Array.isArray(parsed.rows)) return parsed;
  } catch {
    /* ignore */
  }
  return emptyBoard();
}

export function saveWarBoard(board: WarBoard): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(board));
  } catch {
    /* ignore */
  }
}

export function clearWarBoard(): WarBoard {
  const board = emptyBoard();
  saveWarBoard(board);
  return board;
}

function ensureRow(board: WarBoard, modelId: string): WarBoardRow {
  const id = modelId.trim() || "unknown";
  let row = board.rows.find((r) => r.model_id === id);
  if (!row) {
    row = { model_id: id, wins: 0, losses: 0, runs: 0, elo: DEFAULT_ELO };
    board.rows.push(row);
  }
  return row;
}

function expectedScore(a: number, b: number): number {
  return 1 / (1 + 10 ** ((b - a) / 400));
}

/** Record a finished war: winner model gains Elo vs other participants. */
export function recordWarResult(
  board: WarBoard,
  args: { winnerModelId: string; participantModelIds: string[] },
): WarBoard {
  const { winnerModelId, participantModelIds } = args;
  const next: WarBoard = {
    version: 1,
    updated_at: new Date().toISOString(),
    rows: board.rows.map((r) => ({ ...r })),
  };
  const winner = ensureRow(next, winnerModelId);
  const others = [...new Set(participantModelIds.map((m) => m.trim() || "unknown"))].filter(
    (m) => m !== winner.model_id,
  );

  winner.wins += 1;
  winner.runs += 1;

  for (const mid of others) {
    const loser = ensureRow(next, mid);
    loser.losses += 1;
    loser.runs += 1;
    const expW = expectedScore(winner.elo, loser.elo);
    const expL = expectedScore(loser.elo, winner.elo);
    winner.elo += K * (1 - expW);
    loser.elo += K * (0 - expL);
  }
  if (!others.length) {
    winner.elo += K * 0.1;
  }
  next.rows.sort((a, b) => b.elo - a.elo || b.wins - a.wins);
  saveWarBoard(next);
  return next;
}

export function sortedWarBoard(board: WarBoard): WarBoardRow[] {
  return [...board.rows].sort((a, b) => b.elo - a.elo || b.wins - a.wins);
}
