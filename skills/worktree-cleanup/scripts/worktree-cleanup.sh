#!/usr/bin/env bash
# worktree-cleanup.sh — clean up local git worktrees whose commits are already
# merged into <base>. Classifies every linked worktree of the current repo via
# the fast-rebase detector (MESSAGE+TIME+STATE triangulation), then removes only
# the fully-merged, clean ones.
#
# SAFETY CONTRACT (never violated):
#   - removes WORKTREE working copies only; branches & commits are NEVER deleted
#   - only the REMOVE-SAFE bucket is touched: clean tree AND 0 commits to replay
#   - dirty WIP, unmerged work, and detached-unmerged tips are always kept
#   - default is dry-run; --apply is required to mutate anything
#
# Usage:
#   worktree-cleanup.sh [--base <ref>]            # dry-run: classify + list targets
#   worktree-cleanup.sh [--base <ref>] --apply    # remove the REMOVE-SAFE worktrees
#   FR=/path/to/fast-rebase.sh worktree-cleanup.sh ...   # override engine path
#
# base defaults to the LOCAL `master` branch (the integration target), not
# origin/master. Analysis is offline and deterministic; no fetch.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
DEFAULT_FR="$SCRIPT_DIR/../../fast-rebase/scripts/fast-rebase.sh"
[ -f "$DEFAULT_FR" ] || DEFAULT_FR="$(command -v fast-rebase.sh || true)"

BASE="master"
FR="${FR:-$DEFAULT_FR}"
JOBS="${JOBS:-8}"
APPLY=0
REPORT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE="$2"; shift 2;;
    --apply) APPLY=1; shift;;
    --report) REPORT="$2"; shift 2;;
    -h|--help) sed -n '2,30p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

[ -n "$FR" ] && [ -f "$FR" ] || { echo "fast-rebase engine not found; set FR=/path/to/fast-rebase.sh" >&2; exit 2; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "not a git repo" >&2; exit 2; }
git rev-parse --verify -q "$BASE^{commit}" >/dev/null || { echo "base ref not found: $BASE" >&2; exit 2; }

MAIN="$(git worktree list --porcelain | awk '/^worktree /{print substr($0,10); exit}')"

# classify one worktree → "BUCKET<TAB>path<TAB>branch<TAB>info"
# buckets: REMOVE-SAFE REMOVE-DIRTYWIP KEEP-BRANCH-UNMERGED KEEP-DETACHED-UNMERGED MAIN GONE ERROR
classify() {
  local path="$1" head="$2" branch="$3"
  [ "$path" = "$MAIN" ] && { printf 'MAIN\t%s\t%s\t-\n' "$path" "$branch"; return; }
  [ -d "$path" ] || { printf 'GONE\t%s\t%s\t-\n' "$path" "$branch"; return; }
  local dirty=clean
  [ -n "$(git -C "$path" status --porcelain=v1 2>/dev/null)" ] && dirty=dirty
  local det=branch; [ "$branch" = "(detached)" ] && det=detached
  local out unmerged review toReplay
  out="$(bash "$FR" --base "$BASE" --head "$head" 2>&1 || true)"
  if echo "$out" | grep -q '^nothing to rebase'; then
    toReplay=0
  elif echo "$out" | grep -q '^summary:'; then
    unmerged="$(echo "$out" | grep -c 'UNMERGED' || true)"
    review="$(echo "$out" | grep -c 'REVIEW' || true)"
    toReplay=$(( unmerged + review ))
  else
    # engine errored / unrecognized output → never treat as safe
    printf 'ERROR\t%s\t%s\t%s\n' "$path" "$branch" "$(echo "$out" | head -1)"; return
  fi
  local bucket
  if [ "$toReplay" -eq 0 ]; then
    [ "$dirty" = dirty ] && bucket=REMOVE-DIRTYWIP || bucket=REMOVE-SAFE
  else
    [ "$det" = detached ] && bucket=KEEP-DETACHED-UNMERGED || bucket=KEEP-BRANCH-UNMERGED
  fi
  printf '%s\t%s\t%s\t%s,%s,replay=%d\n' "$bucket" "$path" "$branch" "$dirty" "$det" "$toReplay"
}

TMP="$(mktemp -d "${TMPDIR:-/tmp}/wtcleanup.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

# enumerate worktrees → classify in parallel (each worker writes its own file: no race)
i=0
while IFS=$'\t' read -r p h b; do
  i=$(( i + 1 ))
  classify "$p" "$h" "$b" > "$TMP/r.$i" &
  while [ "$(jobs -r | wc -l)" -ge "$JOBS" ]; do sleep 0.2; done
done < <(git worktree list --porcelain | awk '
  /^worktree /{p=substr($0,10)}
  /^HEAD /{h=substr($0,6)}
  /^branch /{b=$2; sub("refs/heads/","",b); print p"\t"h"\t"b; b=""}
  /^detached/{print p"\t"h"\t(detached)"}')
wait
cat "$TMP"/r.* > "$TMP/all" 2>/dev/null || { echo "no worktrees classified" >&2; exit 1; }

echo "== worktree cleanup (base=$BASE, $(wc -l < "$TMP/all") worktrees) =="
awk -F'\t' '{c[$1]++} END{for(k in c) printf "  %-26s %d\n",k,c[k]}' "$TMP/all" | sort
echo
echo "-- REMOVE-SAFE candidates (worktree removed, branch+commits kept) --"
awk -F'\t' '$1=="REMOVE-SAFE"{printf "  %-42s %s\n",$3,$2}' "$TMP/all"
[ -s "$TMP/all" ] && grep -q '^ERROR' "$TMP/all" && {
  echo; echo "-- ERROR (engine unrecognized; skipped, NOT removed) --"
  awk -F'\t' '$1=="ERROR"{printf "  %-42s %s\n",$3,$2}' "$TMP/all"; }

n=$(awk -F'\t' '$1=="REMOVE-SAFE"' "$TMP/all" | wc -l | tr -d ' ')
echo; echo "REMOVE-SAFE count: $n"

# --report: write a per-worktree deep report for the buckets that need manual
# handling (commit-level merge verdict + file scope of unmerged work + dirty WIP)
if [ -n "$REPORT" ]; then
  {
    echo "# Worktree deep report (base=$BASE)"
    echo
    echo "Buckets below need manual handling. Per worktree: each commit's merge"
    echo "verdict vs \`$BASE\` (fast-rebase), file scope of UNMERGED/REVIEW commits,"
    echo "and any uncommitted changes. MERGED-* commits already live in \`$BASE\`."
    for bk in REMOVE-DIRTYWIP KEEP-BRANCH-UNMERGED KEEP-DETACHED-UNMERGED ERROR; do
      cnt=$(awk -F'\t' -v b="$bk" '$1==b' "$TMP/all" | wc -l | tr -d ' ')
      [ "$cnt" -eq 0 ] && continue
      echo; echo "## $bk ($cnt)"
      awk -F'\t' -v b="$bk" '$1==b{print $2"\t"$3}' "$TMP/all" | while IFS=$'\t' read -r path branch; do
        head="$(git -C "$path" rev-parse HEAD 2>/dev/null || echo)"
        echo; echo "### $branch"
        echo "- path: \`$path\`"
        echo "- HEAD: \`$(git -C "$path" rev-parse --short HEAD 2>/dev/null)\` $(git -C "$path" log -1 --format='%s' 2>/dev/null)"
        if [ -n "$(git -C "$path" status --porcelain=v1 2>/dev/null)" ]; then
          echo "- uncommitted (lost on --force remove):"
          git -C "$path" status --short 2>/dev/null | sed 's/^/    /'
        fi
        [ -z "$head" ] && { echo "- (no HEAD)"; continue; }
        fr="$(bash "$FR" --base "$BASE" --head "$head" 2>&1 || true)"
        echo "- commits vs \`$BASE\`:"
        echo "$fr" | sed -n '/^COMMIT /,/^summary:/p' | sed 's/^/    /'
        echo "$fr" | awk '/  UNMERGED  | REVIEW /{print $1}' | while read -r sh; do
          [ -z "$sh" ] && continue
          full="$(git rev-parse -q --verify "$sh" 2>/dev/null)" || continue
          echo "  - unmerged \`$(git show -s --format='%h' "$full")\` $(git show -s --format='%s' "$full") — files:"
          git show --stat --format='' "$full" 2>/dev/null | grep '|' | sed 's/^/      /' | head -15
        done
      done
    done
  } > "$REPORT"
  echo "deep report written: $REPORT"
  exit 0
fi

if [ "$APPLY" != 1 ]; then
  echo "(dry-run) re-run with --apply to remove them."
  exit 0
fi

echo ">> removing $n worktree(s) — branches & commits preserved..."
fail=0
while IFS= read -r t; do
  [ -z "$t" ] && continue
  if git worktree remove "$t" 2>"$TMP/err"; then
    echo "  removed: $t"
  else
    echo "  FAILED:  $t — $(cat "$TMP/err")"; fail=1
  fi
done < <(awk -F'\t' '$1=="REMOVE-SAFE"{print $2}' "$TMP/all")
git worktree prune
echo ">> prune complete."
[ "$fail" = 0 ] || { echo "!! some removals failed (see above)"; exit 1; }
echo ">> done."
