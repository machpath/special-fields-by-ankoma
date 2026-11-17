#!/usr/bin/env bash
# Run the test suites on every supported Anki version and print a table.
#
#   tools/run_matrix.sh [--slow] [--only ENV[,ENV...]] [--no-create]
#
#   tests/engine + tests/acceptance  in every headless environment
#   tests/ui, tests/flow             in the two Qt environments (offscreen)
#
# Missing environments are created with uv (26.05 and 26.08 were missing at
# the start of the build); pytest is installed where it is missing.
# --slow       also run the full-size acceptance test (check 13, -m slow)
# --only       restrict to some environments (names as in the table)
# --no-create  don't create missing environments; mark them "missing"
#
# Environment variables:
#   SFA_SRC       directory put on PYTHONPATH (default: <project>/src);
#                 point it at a shim to test something other than engine.py
#   SFA_VENV_DIR  where the environments live (default /home/claude)
#   SFA_LOG_DIR   where logs go (default /tmp/sfa-d/matrix/<timestamp>)
#
# Exit status: 0 if nothing failed, 1 otherwise. Suites that do not exist
# (or contain no tests) are reported, not counted as failures.

set -u

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${SFA_VENV_DIR:-/home/claude}"
SRC="${SFA_SRC:-$PROJECT/src}"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="${SFA_LOG_DIR:-/tmp/sfa-d/matrix/$STAMP}"
SLOW=0
CREATE=1
ONLY=""

while [ $# -gt 0 ]; do
  case "$1" in
    --slow) SLOW=1 ;;
    --no-create) CREATE=0 ;;
    --only) shift; ONLY="${1:-}" ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

# name | python | packages to install | kind (headless/qt)
ENVS=(
  "venv-py39-25.2.7|3.9|anki==25.2.7|headless"
  "venv-25.2.7|3.13|anki==25.2.7|headless"
  "venv-25.7.5|3.13|anki==25.7.5|headless"
  "venv-25.9.5|3.13|anki==25.9.5|headless"
  "venv-26.5|3.13|anki==26.5|headless"
  "venv-26.8.1|3.13|anki==26.8.1|headless"
  "venv-26.9.4|3.13|anki==26.9.4|headless"
  "venv-26.11b1|3.13|anki==26.11b1|headless"
  "venv-aqt25|3.13|aqt==25.2.7 anki==25.2.7 PyQt6==6.6.1 PyQt6-Qt6==6.6.2 PyQt6-WebEngine==6.6.0|qt"
  "venv-aqt26|3.13|aqt[qt]==26.9.4 anki==26.9.4|qt"
)

mkdir -p "$LOG_DIR"
command -v uv >/dev/null 2>&1 || { echo "uv not found on PATH" >&2; exit 2; }

want() {  # is env $1 selected by --only?
  [ -z "$ONLY" ] && return 0
  case ",$ONLY," in *",$1,"*) return 0 ;; esac
  return 1
}

ensure_env() {  # name python packages -> 0 if usable
  local name="$1" py="$2" pkgs="$3" dir="$VENV_DIR/$1"
  if [ ! -x "$dir/bin/python" ]; then
    [ "$CREATE" = 1 ] || return 1
    echo ">> creating $dir (python $py; $pkgs)"
    uv venv -q --python "$py" "$dir" >>"$LOG_DIR/setup.log" 2>&1 || return 1
    # shellcheck disable=SC2086
    uv pip install -q --python "$dir/bin/python" $pkgs >>"$LOG_DIR/setup.log" 2>&1 || return 1
  fi
  if ! "$dir/bin/python" -c "import pytest" >/dev/null 2>&1; then
    echo ">> installing pytest into $dir"
    uv pip install -q --python "$dir/bin/python" pytest >>"$LOG_DIR/setup.log" 2>&1 || return 1
  fi
  return 0
}

has_tests() {  # directory contains test_*.py or *_test.py
  [ -d "$1" ] && [ -n "$(find "$1" -maxdepth 3 \( -name 'test_*.py' -o -name '*_test.py' \) -print -quit)" ]
}

# run one suite; prints a table cell
run_suite() {  # env-name python suite-dir extra-args...
  local name="$1" py="$2" suite="$3"; shift 3
  local log="$LOG_DIR/$name--$(basename "$suite").log"
  if ! has_tests "$PROJECT/$suite"; then
    echo "absent"
    return 0
  fi
  ( cd "$PROJECT" && env PYTHONPATH="$SRC" PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
      "$py" -m pytest "$suite" -q -p no:cacheprovider -rfE "$@" ) >"$log" 2>&1
  local rc=$?
  local summary
  summary="$(grep -E '^(=+ )?[0-9]+ (passed|failed|error|skipped|deselected)|no tests ran|^=+ .*(passed|failed|error).* =+$' "$log" | tail -1 | sed -E 's/=+//g; s/^ +| +$//g; s/ in [0-9.]+s.*$//')"
  local p f e
  p="$(echo "$summary" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')"; p="${p:-0}"
  f="$(echo "$summary" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+')"; f="${f:-0}"
  e="$(echo "$summary" | grep -oE '[0-9]+ errors?' | grep -oE '[0-9]+')"; e="${e:-0}"
  case "$rc" in
    0) echo "PASS $p" ;;
    1) echo "FAIL $((f + e))/$((p + f + e))"; FAILED=1 ;;
    5) echo "no tests" ;;
    *) echo "ERROR rc=$rc"; FAILED=1 ;;
  esac
}

FAILED=0
ROWS=()
for spec in "${ENVS[@]}"; do
  IFS='|' read -r name pyver pkgs kind <<<"$spec"
  want "$name" || continue
  if ! ensure_env "$name" "$pyver" "$pkgs"; then
    ROWS+=("$name|?|?|missing|missing|missing|missing")
    FAILED=1
    continue
  fi
  py="$VENV_DIR/$name/bin/python"
  info="$("$py" -c 'import sys; from anki.buildinfo import version; print(version, sys.version.split()[0])' 2>/dev/null)"
  anki_v="${info%% *}"; py_v="${info##* }"
  echo ">> $name (Anki $anki_v, Python $py_v)"
  if [ "$kind" = headless ]; then
    eng="$(run_suite "$name" "$py" tests/engine)"
    acc="$(run_suite "$name" "$py" tests/acceptance)"
    if [ "$SLOW" = 1 ]; then
      slow="$(run_suite "$name-slow" "$py" tests/acceptance -m slow -s)"
      acc="$acc; slow: $slow"
    fi
    ui="n/a"; flow="n/a"
  else
    eng="n/a"; acc="n/a"
    ui="$(run_suite "$name" "$py" tests/ui)"
    flow="$(run_suite "$name" "$py" tests/flow)"
  fi
  case "$eng$acc$ui$flow" in *FAIL*|*ERROR*) FAILED=1 ;; esac
  ROWS+=("$name|$anki_v|$py_v|$eng|$acc|$ui|$flow")
done

echo
echo "PYTHONPATH=$SRC"
echo "logs: $LOG_DIR"
printf '%-18s %-9s %-8s %-14s %-30s %-12s %-12s\n' "environment" "Anki" "Python" "tests/engine" "tests/acceptance" "tests/ui" "tests/flow"
printf '%-18s %-9s %-8s %-14s %-30s %-12s %-12s\n' "------------------" "---------" "--------" "--------------" "------------------------------" "------------" "------------"
for r in "${ROWS[@]}"; do
  IFS='|' read -r a b c d e f g <<<"$r"
  printf '%-18s %-9s %-8s %-14s %-30s %-12s %-12s\n' "$a" "$b" "$c" "$d" "$e" "$f" "$g"
done
echo
echo "PASS n = all n tests passed; FAIL f/n = f of n failed or errored; absent = suite has no test files;"
echo "no tests = pytest collected nothing; n/a = suite not run in this kind of environment."
exit "$FAILED"
