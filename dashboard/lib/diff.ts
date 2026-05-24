/**
 * Tiny character-level diff. Produces a flat list of {op, text} spans for
 * rendering inline diffs in the alert drawer.
 *
 * Algorithm: classic Myers-style LCS table. Quadratic in input length, fine
 * for prompts up to a few KB. Anything bigger and we fall back to a coarser
 * line-level diff.
 */

export type DiffOp = "equal" | "insert" | "delete";
export interface DiffSpan {
  op: DiffOp;
  text: string;
}

const MAX_CHAR_DIFF = 4000;

export function diffChars(a: string, b: string): DiffSpan[] {
  if (a === b) return [{ op: "equal", text: a }];
  if (Math.max(a.length, b.length) > MAX_CHAR_DIFF) {
    return diffLines(a, b);
  }
  return _diff(Array.from(a), Array.from(b));
}

export function diffLines(a: string, b: string): DiffSpan[] {
  const aLines = a.split(/(\n)/);
  const bLines = b.split(/(\n)/);
  return _diff(aLines, bLines);
}

function _diff(a: string[], b: string[]): DiffSpan[] {
  const m = a.length;
  const n = b.length;
  // Build LCS table.
  const dp: Uint32Array[] = Array.from({ length: m + 1 }, () => new Uint32Array(n + 1));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = a[i - 1] === b[j - 1]
        ? dp[i - 1][j - 1] + 1
        : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  // Walk back, emitting ops.
  const out: DiffSpan[] = [];
  let i = m;
  let j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
      out.push({ op: "equal", text: a[i - 1] });
      i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      out.push({ op: "insert", text: b[j - 1] });
      j--;
    } else {
      out.push({ op: "delete", text: a[i - 1] });
      i--;
    }
  }
  out.reverse();
  // Merge consecutive spans of the same op.
  const merged: DiffSpan[] = [];
  for (const span of out) {
    const last = merged[merged.length - 1];
    if (last && last.op === span.op) last.text += span.text;
    else merged.push({ ...span });
  }
  return merged;
}
