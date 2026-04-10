/**
 * Parse per-trial scores from MIPROv2 and GEPA optimizer log messages.
 *
 * Both optimizers emit their progress as free-text log lines; this parses
 * the known patterns into a structured series suitable for charting.
 */

export interface ScorePoint {
  trial: number;
  score: number;
  best: number;
}

export function extractScoresFromLogs(logs: { message: string }[]): ScorePoint[] {
  const points: ScorePoint[] = [];
  let currentTrial = 0;
  let bestSoFar = -1;

  for (const log of logs) {
    const msg = log.message;

    // MIPROv2: "===== Trial N / M =====" or "== Trial N / M"
    const trialMatch = msg.match(/Trial (\d+)\s*\/\s*\d+/);
    if (trialMatch) {
      currentTrial = parseInt(trialMatch[1]!, 10);
    }

    // MIPROv2: "Score: 85.0 with parameters ..."
    const scoreMatch = msg.match(/^Score:\s*([\d.]+)\s+(?:with parameters|on minibatch)/);
    if (scoreMatch && currentTrial > 0) {
      const score = parseFloat(scoreMatch[1]!);
      bestSoFar = Math.max(bestSoFar, score);
      points.push({ trial: currentTrial, score, best: bestSoFar });
      continue;
    }

    // MIPROv2: "Default program score: 85.0"
    const defaultMatch = msg.match(/Default program score:\s*([\d.]+)/);
    if (defaultMatch) {
      const score = parseFloat(defaultMatch[1]!);
      bestSoFar = Math.max(bestSoFar, score);
      points.push({ trial: currentTrial || 1, score, best: bestSoFar });
      continue;
    }

    // GEPA: "Iteration N: Full valset score for new program: 0.78"
    const gepaScoreMatch = msg.match(/Iteration (\d+):\s*Full valset score for new program:\s*([\d.]+)/);
    if (gepaScoreMatch) {
      const iter = parseInt(gepaScoreMatch[1]!, 10);
      const score = parseFloat(gepaScoreMatch[2]!);
      bestSoFar = Math.max(bestSoFar, score);
      points.push({ trial: iter, score, best: bestSoFar });
      continue;
    }

    // GEPA: "Iteration N: Base program full valset score: 0.65"
    const gepaBaseMatch = msg.match(/Iteration (\d+):\s*Base program full valset score:\s*([\d.]+)/);
    if (gepaBaseMatch) {
      const iter = parseInt(gepaBaseMatch[1]!, 10);
      const score = parseFloat(gepaBaseMatch[2]!);
      bestSoFar = Math.max(bestSoFar, score);
      points.push({ trial: iter, score, best: bestSoFar });
    }
  }

  return points;
}
