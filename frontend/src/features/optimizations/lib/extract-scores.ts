/**
 * Parse per-trial scores from GEPA optimizer log messages.
 *
 * GEPA emits its progress as free-text log lines; this parses
 * the known patterns into a structured series suitable for charting.
 */

export interface ScorePoint {
  trial: number;
  score: number;
  best: number;
}

export function extractScoresFromLogs(logs: { message: string }[]): ScorePoint[] {
  const points: ScorePoint[] = [];
  let bestSoFar = -1;

  for (const log of logs) {
    const msg = log.message;

    // GEPA: "Iteration N: Full valset score for new program: 0.78"
    const gepaScoreMatch = msg.match(
      /Iteration (\d+):\s*Full valset score for new program:\s*([\d.]+)/,
    );
    if (gepaScoreMatch) {
      const iter = parseInt(gepaScoreMatch[1]!, 10);
      const score = parseFloat(gepaScoreMatch[2]!);
      bestSoFar = Math.max(bestSoFar, score);
      points.push({ trial: iter, score, best: bestSoFar });
      continue;
    }

    // GEPA: "Iteration N: Base program full valset score: 0.65"
    const gepaBaseMatch = msg.match(
      /Iteration (\d+):\s*Base program full valset score:\s*([\d.]+)/,
    );
    if (gepaBaseMatch) {
      const iter = parseInt(gepaBaseMatch[1]!, 10);
      const score = parseFloat(gepaBaseMatch[2]!);
      bestSoFar = Math.max(bestSoFar, score);
      points.push({ trial: iter, score, best: bestSoFar });
    }
  }

  return points;
}
