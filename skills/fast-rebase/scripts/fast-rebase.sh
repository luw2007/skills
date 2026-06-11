#!/usr/bin/env bash
# fast-rebase.sh — accelerate rebasing a local branch onto an upstream that has
# squash-merged some of your commits. It identifies "already merged" commits by
# triangulating three independent signals — commit MESSAGE, TIME, and code STATE
# — then (with --apply) rebases while dropping them and verifies the resulting
# tree is byte-identical to a pre-rebase backup (proof no code was lost).
#
# Usage:
#   fast-rebase.sh [--base <ref>] [--head <ref>] [--fetch] [--apply] [--no-backup]
#
#   (default)      analyze only: print per-commit verdict + drop plan, no mutation
#   --base <ref>   upstream ref to compare against        (default: origin/master)
#   --head <ref>   branch tip to analyze, no checkout     (default: HEAD)
#   --fetch        `git fetch` the base's remote/branch before analyzing
#   --apply        backup, rebase -i dropping merged commits, verify tree (HEAD only)
#   --verify       re-check HEAD vs the persisted backup (run after resolving conflicts)
#   --no-backup    skip the safety backup branch (not recommended)
#
# Verdicts:
#   MERGED-EXACT   patch-id identical to an upstream commit (cherry-pick/rebase merge)
#   MERGED-SQUASH  subject listed in an upstream commit body + authored before that
#                  merge + every file it touched is also touched there (squash merge)
#   REVIEW         message matched but time/state disagreed — kept; inspect by hand
#   UNMERGED       not present upstream — kept and replayed
#
# Part of luw2007/skills — MIT License.
set -euo pipefail

BASE="origin/master"
TIP="HEAD"
DO_FETCH=0
DO_APPLY=0
DO_VERIFY=0
DO_BACKUP=1
while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE="$2"; shift 2;;
    --head) TIP="$2"; shift 2;;
    --fetch) DO_FETCH=1; shift;;
    --apply) DO_APPLY=1; shift;;
    --verify) DO_VERIFY=1; shift;;
    --no-backup) DO_BACKUP=0; shift;;
    -h|--help) awk 'NR==1{next} /^#/{sub(/^#( |$)/,"");print;next} {exit}' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "not a git repo" >&2; exit 2; }

BK_FILE="$(git rev-parse --absolute-git-dir)/fast-rebase-backup"

# standalone verification: prove current HEAD == the persisted backup. Run this
# after hand-resolving a conflict and `git rebase --continue`, when the rebase
# paused and the in-script auto-check below was therefore skipped.
if [ "$DO_VERIFY" = 1 ]; then
  [ -f "$BK_FILE" ] || { echo "no backup recorded ($BK_FILE missing) — run --apply first" >&2; exit 2; }
  BK="$(cat "$BK_FILE")"
  git rev-parse --verify -q "$BK^{commit}" >/dev/null || { echo "backup ref gone: $BK" >&2; exit 2; }
  if git diff --quiet "$BK" HEAD; then
    echo ">> VERIFIED: HEAD is byte-identical to $BK — no code lost"; exit 0
  fi
  echo "!! HEAD differs from $BK (expected only if upstream edited the kept files):"
  git diff --stat "$BK" HEAD; exit 1
fi

if [ "$DO_FETCH" = 1 ]; then
  remote="${BASE%%/*}"; branch="${BASE#*/}"
  if [ "$remote" = "$BASE" ]; then remote="origin"; branch="$BASE"; fi
  echo ">> git fetch $remote $branch"
  git fetch "$remote" "$branch"
fi

git rev-parse --verify -q "$BASE^{commit}" >/dev/null || { echo "base ref not found: $BASE" >&2; exit 2; }
git rev-parse --verify -q "$TIP^{commit}"  >/dev/null || { echo "head ref not found: $TIP"  >&2; exit 2; }

LOCALS=(); while IFS= read -r l; do LOCALS+=("$l"); done < <(git rev-list --reverse "$BASE..$TIP")
if [ "${#LOCALS[@]}" -eq 0 ]; then echo "nothing to rebase: $TIP is not ahead of $BASE"; exit 0; fi
UPSTREAM=(); while IFS= read -r l; do UPSTREAM+=("$l"); done < <(git rev-list "$TIP..$BASE")

# exact patch-id equivalences: 'git cherry' marks '-' for commits already upstream
EXACT_SET="$(git cherry "$BASE" "$TIP" | awk '$1=="-"{print $2}')"
is_exact() { printf '%s\n' "$EXACT_SET" | grep -qxF -- "$1"; }

subj()  { git show -s --format=%s "$1"; }
at()    { git show -s --format=%at "$1"; }   # author epoch
ct()    { git show -s --format=%ct "$1"; }   # committer epoch
files() { git diff-tree -r --no-commit-id --name-only "$1" | sort -u; }

# find an upstream commit whose message body lists $1 as a (bullet-prefixed) line
match_upstream() {
  local subject="$1" s
  [ -z "$subject" ] && return 1   # empty subject matches any blank body line via grep -Fxq '' — never auto-drop it
  [ "${#UPSTREAM[@]}" -eq 0 ] && return 1
  for s in "${UPSTREAM[@]}"; do
    if git show -s --format=%B "$s" | sed -E 's/^[[:space:]]*[-*][[:space:]]+//' | grep -Fxq -- "$subject"; then
      echo "$s"; return 0
    fi
  done
  return 1
}

DROP=()
printf '%-10s  %-13s  %s\n' "COMMIT" "VERDICT" "SUBJECT"
printf '%-10s  %-13s  %s\n' "----------" "-------------" "-------"
for c in "${LOCALS[@]}"; do
  short="$(git rev-parse --short "$c")"; s="$(subj "$c")"
  if is_exact "$c"; then
    printf '%-10s  %-13s  %s\n' "$short" "MERGED-EXACT" "$s"; DROP+=("$c"); continue
  fi
  if up="$(match_upstream "$s")"; then
    time_ok=0; if [ "$(at "$c")" -le "$(ct "$up")" ]; then time_ok=1; fi
    extra="$(comm -23 <(files "$c") <(files "$up") | head -1)"
    if [ -z "$extra" ] && [ "$time_ok" = 1 ]; then
      printf '%-10s  %-13s  %s  [<-%s]\n' "$short" "MERGED-SQUASH" "$s" "$(git rev-parse --short "$up")"
      DROP+=("$c")
    else
      reason=""; if [ "$time_ok" = 0 ]; then reason="time"; fi
      if [ -n "$extra" ]; then reason="${reason:+$reason,}state(+$extra)"; fi
      printf '%-10s  %-13s  %s  [msg-only:%s]\n' "$short" "REVIEW" "$s" "$reason"
    fi
  else
    printf '%-10s  %-13s  %s\n' "$short" "UNMERGED" "$s"
  fi
done

KEEP=$(( ${#LOCALS[@]} - ${#DROP[@]} ))
echo
echo "summary: ${#LOCALS[@]} local commit(s), ${#DROP[@]} already-merged (drop), $KEEP to replay; ${#UPSTREAM[@]} upstream-only on $BASE"
if [ "${#DROP[@]}" -eq 0 ]; then echo "no merged commits detected — a plain 'git rebase $BASE' is enough"; exit 0; fi

echo
echo "drop plan:"
for d in "${DROP[@]}"; do echo "  drop $(git rev-parse --short "$d")  $(subj "$d")"; done

if [ "$DO_APPLY" != 1 ]; then
  echo
  echo "re-run with --apply to rebase automatically, or do it by hand:"
  echo "  git rebase -i $BASE   # mark the listed commits as 'drop'"
  exit 0
fi

# ---------------- apply ----------------
if [ "$(git rev-parse "$TIP")" != "$(git rev-parse HEAD)" ]; then
  echo "--apply requires --head to be the checked-out HEAD" >&2; exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "working tree not clean — commit or stash first" >&2; exit 1
fi

HEAD_SHORT="$(git rev-parse --short HEAD)"
BK=""
if [ "$DO_BACKUP" = 1 ]; then
  BK="backup/pre-fast-rebase-$HEAD_SHORT"
  git branch -f "$BK" HEAD
  printf '%s\n' "$BK" > "$BK_FILE"
  echo ">> backup branch: $BK ($HEAD_SHORT)"
fi

# sequence editor: rewrite the rebase todo, flipping 'pick' -> 'drop' for any todo
# hash that is a prefix of a DROP full-sha (handles git's variable abbreviation)
SEQ_ED="$(mktemp "${TMPDIR:-/tmp}/fast-rebase-seq.XXXXXX")"
trap 'rm -f "$SEQ_ED"' EXIT
cat >"$SEQ_ED" <<'PERL'
#!/usr/bin/env perl
my @d = split /\s+/, ($ENV{FR_DROP} // "");
my $f = $ARGV[0];
open my $in, "<", $f or die "$f: $!";
my @lines = <$in>; close $in;
for (@lines) {
  if (/^pick (\S+)/) { my $h=$1; for my $x (@d){ if(index($x,$h)==0){ s/^pick /drop /; last } } }
}
open my $out, ">", $f or die "$f: $!";
print $out @lines; close $out;
PERL

echo ">> git rebase -i $BASE  (auto-dropping ${#DROP[@]} commit(s))"
if FR_DROP="${DROP[*]}" GIT_EDITOR=true GIT_SEQUENCE_EDITOR="perl $SEQ_ED" git rebase -i "$BASE"; then
  echo ">> rebase finished"
else
  echo
  echo "!! rebase paused (conflict). Resolve, then:  git add <files> && git rebase --continue"
  if [ -n "$BK" ]; then echo "   after it completes, prove zero code lost:  bash $0 --verify"; fi
  exit 1
fi

if [ -n "$BK" ]; then
  if git diff --quiet "$BK" HEAD; then
    echo ">> VERIFIED: rebased tree is byte-identical to $BK — no code lost"
  else
    echo "!! tree differs from backup (expected only if upstream edited the kept files):"
    git diff --stat "$BK" HEAD
  fi
fi
git rev-list --left-right --count "$BASE...HEAD" | awk '{print ">> vs '"$BASE"':  behind="$1"  ahead="$2}'
